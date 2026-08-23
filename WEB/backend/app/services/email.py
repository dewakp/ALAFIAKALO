"""Email service — sends transactional email via SMTP.

Usage:
    from app.services.email import send_email, send_password_reset_email

All methods are async-safe (run SMTP in executor to avoid blocking the event loop).
"""

import asyncio
import smtplib
from urllib.parse import quote

import httpx
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def _smtp_configured() -> bool:
    return bool(settings.SMTP_HOST and settings.SMTP_USER)


def _resend_configured() -> bool:
    return bool(settings.RESEND_API_KEY)


async def _send_via_resend(to: str, subject: str, html_body: str) -> bool:
    """Send through Resend's HTTPS API.

    Preferred over SMTP: no outbound mail ports, no STARTTLS negotiation, and a
    real error body when something is wrong (bad key, unverified sending domain)
    instead of an opaque socket failure.
    """
    payload = {
        "from": f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>",
        "to": [to],
        "subject": subject,
        "html": html_body,
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{settings.RESEND_API_BASE}/emails",
                headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
                json=payload,
            )
        if resp.status_code in (200, 201):
            logger.info("Email sent via Resend to %s: %s (id=%s)", to, subject,
                        (resp.json() or {}).get("id"))
            return True
        # Body, not just the status: Resend explains WHY (e.g. the sending domain
        # is not verified), and that is the difference between a five-minute fix
        # and an afternoon.
        logger.error("Resend rejected mail to %s: %s %s", to, resp.status_code, resp.text[:300])
        return False
    except Exception:
        logger.exception("Resend request failed for %s", to)
        return False


def _build_message(to: str, subject: str, html_body: str) -> MIMEMultipart:
    msg = MIMEMultipart("alternative")
    msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(html_body, "html"))
    return msg


def _send_sync(to: str, subject: str, html_body: str) -> None:
    """Blocking SMTP send — called inside an executor."""
    msg = _build_message(to, subject, html_body)
    connect = smtplib.SMTP_SSL if settings.SMTP_PORT == 465 else smtplib.SMTP
    with connect(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as server:
        if settings.SMTP_TLS and settings.SMTP_PORT != 465:
            server.starttls()
        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.sendmail(settings.SMTP_FROM_EMAIL, to, msg.as_string())
    logger.info("Email sent to %s: %s", to, subject)


async def send_email(to: str, subject: str, html_body: str) -> bool:
    """Send an email. Resend if configured, else SMTP. False if neither works."""
    if _resend_configured():
        return await _send_via_resend(to, subject, html_body)

    if not _smtp_configured():
        logger.warning("No email provider configured — email to %s skipped", to)
        return False
    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _send_sync, to, subject, html_body)
        return True
    except Exception:
        logger.exception("Failed to send email to %s", to)
        return False


def password_reset_url(reset_token: str) -> str:
    """The one place the reset link is built, so email and debug logging agree.

    quote() is belt-and-braces: a JWT is [A-Za-z0-9_-] plus dots, all of which are
    query-safe, but the token format is not this function's to assume.
    """
    return (
        f"{settings.PUBLIC_WEB_URL.rstrip('/')}/reset-password"
        f"?token={quote(reset_token, safe='')}"
    )


async def send_password_reset_email(to: str, reset_token: str) -> bool:
    """Send a password reset email containing a one-click link.

    The token travels in the link rather than being shown as a "code" to copy:
    a reset JWT is ~200 characters, so asking a person to transcribe it between
    two windows was the reason the flow needed a visible token field at all.
    """
    reset_url = password_reset_url(reset_token)
    subject = f"{settings.APP_NAME} — Password Reset"
    html_body = f"""
    <html><body style="font-family:sans-serif;max-width:480px;margin:auto;">
      <h2>{settings.APP_NAME}</h2>
      <p>You requested a password reset. Click below to choose a new password:</p>
      <p style="text-align:center;margin:28px 0;">
        <a href="{reset_url}"
           style="background:#ea580c;color:#fff;text-decoration:none;padding:12px 24px;
                  border-radius:8px;display:inline-block;font-weight:600;">
          Reset my password
        </a>
      </p>
      <p style="color:#6b7280;font-size:13px;">
        If the button doesn't work, paste this link into your browser:<br>
        <span style="word-break:break-all;">{reset_url}</span>
      </p>
      <p>This link expires in {settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES} minutes.</p>
      <p>If you didn't request this, please ignore this email — your password is unchanged.</p>
      <hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0;">
      <p style="color:#6b7280;font-size:12px;">{settings.APP_NAME} — Holistic Health Platform</p>
    </body></html>
    """
    return await send_email(to, subject, html_body)


def smtp_configured() -> bool:
    """True when ANY email provider is usable (Resend or SMTP).

    Kept under this name because callers ask one question — "can we send mail?" —
    and signup uses it to refuse rather than silently issue an account nobody can
    verify.
    """
    return _resend_configured() or _smtp_configured()


def email_provider() -> str:
    """Which provider will actually be used — surfaced in admin health."""
    if _resend_configured():
        return "resend"
    if _smtp_configured():
        return f"smtp:{settings.SMTP_HOST}"
    return "none"


async def send_verification_email(to: str, token: str) -> bool:
    """Send the signup email-verification link.

    The link carries the token to the SPA, which posts it to
    /auth/signup/verify-email. The raw token is also shown as a fallback for
    mail clients that mangle links.
    """
    verify_url = f"{settings.PUBLIC_WEB_URL.rstrip('/')}/verify-email?token={token}"
    subject = f"{settings.APP_NAME} — Verify your email"
    html_body = f"""
    <html><body style="font-family:sans-serif;max-width:480px;margin:auto;">
      <h2>{settings.APP_NAME}</h2>
      <p>Welcome. Confirm this address to continue setting up your account.</p>
      <p style="text-align:center;margin:28px 0;">
        <a href="{verify_url}"
           style="background:#ea580c;color:#fff;text-decoration:none;padding:12px 24px;
                  border-radius:8px;display:inline-block;font-weight:600;">
          Verify my email
        </a>
      </p>
      <p style="color:#6b7280;font-size:13px;">
        If the button doesn't work, paste this link into your browser:<br>
        <span style="word-break:break-all;">{verify_url}</span>
      </p>
      <p>This link expires in 24 hours and can be used once.</p>
      <p>If you didn't start this signup, ignore this email — no account has been created.</p>
      <hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0;">
      <p style="color:#6b7280;font-size:12px;">{settings.APP_NAME} — Holistic Health Platform</p>
    </body></html>
    """
    return await send_email(to, subject, html_body)


def _escape(value: str) -> str:
    """Minimal HTML escaping for values that reach the template.

    The decline reason comes from Stripe, not from us, and lands inside an HTML
    body — so it is escaped rather than trusted, like any other external string.
    """
    return (str(value).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


async def send_payment_failed_email(
    to: str,
    *,
    full_name: str | None = None,
    reason: str | None = None,
    first_payment: bool = True,
    amount_label: str | None = None,
    next_attempt: str | None = None,
) -> bool:
    """Tell a user their card was declined, and say WHY.

    Without this the whole event is invisible to the person it happened to: the
    paywall looks exactly as it did before they tried to pay, so a declined card
    reads as "nothing happened" and they have no reason to think anything needs
    fixing. `reason` is the bank's own decline reason, mapped to plain language —
    "the card didn't have enough available funds" is actionable in a way that
    "payment failed" never is.

    ``first_payment`` distinguishes "your membership never started" from "we
    couldn't renew your membership", which are different problems for the reader.
    """
    manage_url = f"{settings.PUBLIC_WEB_URL.rstrip('/')}/subscription"
    greeting = f"Hi {_escape(full_name.split()[0])}," if full_name else "Hi,"

    if first_payment:
        subject = f"{settings.APP_NAME} — your payment didn’t go through"
        headline = "Your payment didn’t go through"
        lede = ("Your card was declined, so your ALAFIA Membership never started "
                "and you haven’t been charged.")
    else:
        subject = f"{settings.APP_NAME} — we couldn’t renew your membership"
        headline = "We couldn’t renew your membership"
        lede = ("The card on file was declined, so this renewal didn’t go "
                "through. Your access continues for a short grace period.")

    reason_block = (
        f"""<p style="background:#fff4f4;border:1px solid #f3c2c2;border-radius:8px;
                     padding:12px 14px;margin:18px 0;">
              <strong>Why it failed:</strong> {_escape(reason)}.
            </p>"""
        if reason else ""
    )
    amount_block = (
        f"""<p style="color:#6b7280;font-size:13px;">Amount attempted: {_escape(amount_label)}</p>"""
        if amount_label else ""
    )
    retry_block = (
        f"""<p style="color:#6b7280;font-size:13px;">
              We’ll automatically try again on {_escape(next_attempt)}. Updating your
              card before then will settle it sooner.
            </p>"""
        if next_attempt else ""
    )

    html_body = f"""
    <html><body style="font-family:sans-serif;max-width:480px;margin:auto;">
      <h2>{settings.APP_NAME}</h2>
      <p>{greeting}</p>
      <h3 style="margin-bottom:6px;">{headline}</h3>
      <p>{lede}</p>
      {reason_block}
      {amount_block}
      <p style="text-align:center;margin:28px 0;">
        <a href="{manage_url}"
           style="background:#ea580c;color:#fff;text-decoration:none;padding:12px 24px;
                  border-radius:8px;display:inline-block;font-weight:600;">
          Try a different card
        </a>
      </p>
      {retry_block}
      <p style="color:#6b7280;font-size:13px;">
        If the button doesn't work, paste this link into your browser:<br>
        <span style="word-break:break-all;">{manage_url}</span>
      </p>
      <p>If you think this is a mistake, your bank can usually say more than we can see.</p>
      <hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0;">
      <p style="color:#6b7280;font-size:12px;">{settings.APP_NAME} — Holistic Health Platform</p>
    </body></html>
    """
    return await send_email(to, subject, html_body)
