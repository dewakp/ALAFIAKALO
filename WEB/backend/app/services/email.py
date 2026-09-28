"""Email service — sends transactional email via SMTP.

Usage:
    from app.services.email import send_email, send_password_reset_email

All methods are async-safe (run SMTP in executor to avoid blocking the event loop).
"""

import asyncio
import base64
import smtplib
from collections.abc import Sequence
from dataclasses import dataclass
from urllib.parse import quote

import httpx
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class Attachment:
    """A file travelling with a letter, INLINE when it carries a content_id.

    `content` is raw bytes. Both transports need it encoded differently —
    Resend wants a base64 string in JSON, SMTP wants a base64-encoded MIME
    part — so the encoding happens in each transport and never at the call
    site, which would otherwise have to know which provider is configured.

    An inline attachment (`content_id` set) is referenced from the HTML as
    `<img src="cid:THAT_ID">`. Without a content_id the file is a plain
    attachment.

    `caption` is NOT transport data — it is ignored when sending, and read only
    by letters that render the image and want a line of text beneath it.
    """

    filename: str
    content: bytes
    content_type: str = "application/octet-stream"
    content_id: str | None = None
    caption: str | None = None


def _mime_part(att: Attachment) -> MIMEBase:
    """One base64 MIME part, whatever the type.

    MIMEBase rather than MIMEImage on purpose: MIMEImage sniffs the subtype,
    which meant `imghdr` — removed in Python 3.13. We already know the type
    from the caller, so guessing it is both unnecessary and a version
    dependency.
    """
    main, _, sub = (att.content_type or "application/octet-stream").partition("/")
    part = MIMEBase(main or "application", sub or "octet-stream")
    part.set_payload(att.content)
    encoders.encode_base64(part)
    return part


def _smtp_configured() -> bool:
    return bool(settings.SMTP_HOST and settings.SMTP_USER)


def _resend_configured() -> bool:
    return bool(settings.RESEND_API_KEY)


async def _send_via_resend(
    to: str,
    subject: str,
    html_body: str,
    attachments: Sequence[Attachment] | None = None,
) -> bool:
    """Send through Resend's HTTPS API.

    Preferred over SMTP: no outbound mail ports, no STARTTLS negotiation, and a
    real error body when something is wrong (bad key, unverified sending domain)
    instead of an opaque socket failure.

    Attachments go in Resend's own `attachments` array — `content` base64, and
    `content_id` for anything the HTML embeds as `cid:`. Documented ceiling is
    40 MB per email AFTER base64, which inflates by 4/3, so the caller's raw
    bytes are the figure to watch.
    """
    payload = {
        "from": f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>",
        "to": [to],
        "subject": subject,
        "html": html_body,
    }
    if attachments:
        payload["attachments"] = [
            {
                "filename": att.filename,
                "content": base64.b64encode(att.content).decode("ascii"),
                "content_type": att.content_type,
                **({"content_id": att.content_id} if att.content_id else {}),
            }
            for att in attachments
        ]
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{settings.RESEND_API_BASE}/emails",
                headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
                json=payload,
            )
        if resp.status_code in (200, 201):
            # "ACCEPTED", not "sent". Resend answers 200 with a message id for a
            # send it will never transmit — an address on its suppression list,
            # added automatically after an earlier hard bounce. This line said
            # "Email sent via Resend to …" three times for one bounce and two
            # sends that never left the building, and that sentence was then
            # reported as proof of delivery.
            #
            # What arrives is knowable only from a delivery EVENT, never from
            # this response (§3d: a success path reporting success without
            # evidence, as the 17 unsubscribe links did).
            logger.info("Resend ACCEPTED mail for %s: %s (id=%s) — acceptance is "
                        "not delivery; a suppressed or bouncing address also "
                        "returns 200", to, subject, (resp.json() or {}).get("id"))
            return True
        # Body, not just the status: Resend explains WHY (e.g. the sending domain
        # is not verified), and that is the difference between a five-minute fix
        # and an afternoon.
        logger.error("Resend rejected mail to %s: %s %s", to, resp.status_code, resp.text[:300])
        return False
    except Exception:
        logger.exception("Resend request failed for %s", to)
        return False


def _build_message(
    to: str,
    subject: str,
    html_body: str,
    attachments: Sequence[Attachment] | None = None,
) -> MIMEMultipart:
    """Assemble the MIME tree, whose SHAPE depends on what is being carried.

    `multipart/alternative` cannot hold an inline image — a `cid:` reference
    only resolves against a sibling inside `multipart/related`, so an image
    attached to an `alternative` renders as a broken picture in the letter
    while the send itself reports success. The three shapes:

        html only                 alternative
        html + inline images      related
        ... plus plain files      mixed[ related|alternative, files... ]
    """
    attachments = list(attachments or [])
    inline = [a for a in attachments if a.content_id]
    plain = [a for a in attachments if not a.content_id]

    body = MIMEMultipart("related") if inline else MIMEMultipart("alternative")
    body.attach(MIMEText(html_body, "html"))
    for att in inline:
        part = _mime_part(att)
        # Angle brackets are required: a cid: URL resolves against the
        # Content-ID *addr-spec*, and a bare id matches nothing in some clients.
        part.add_header("Content-ID", f"<{att.content_id}>")
        part.add_header("Content-Disposition", "inline", filename=att.filename)
        body.attach(part)

    if plain:
        msg = MIMEMultipart("mixed")
        msg.attach(body)
        for att in plain:
            part = _mime_part(att)
            part.add_header("Content-Disposition", "attachment",
                            filename=att.filename)
            msg.attach(part)
    else:
        msg = body

    msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
    msg["To"] = to
    msg["Subject"] = subject
    return msg


def _send_sync(
    to: str,
    subject: str,
    html_body: str,
    attachments: Sequence[Attachment] | None = None,
) -> None:
    """Blocking SMTP send — called inside an executor."""
    msg = _build_message(to, subject, html_body, attachments)
    connect = smtplib.SMTP_SSL if settings.SMTP_PORT == 465 else smtplib.SMTP
    with connect(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as server:
        if settings.SMTP_TLS and settings.SMTP_PORT != 465:
            server.starttls()
        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.sendmail(settings.SMTP_FROM_EMAIL, to, msg.as_string())
    logger.info("Email sent to %s: %s", to, subject)


async def send_email(
    to: str,
    subject: str,
    html_body: str,
    attachments: Sequence[Attachment] | None = None,
) -> bool:
    """Send an email. Resend if configured, else SMTP. False if neither works."""
    if _resend_configured():
        return await _send_via_resend(to, subject, html_body, attachments)

    if not _smtp_configured():
        logger.warning("No email provider configured — email to %s skipped", to)
        return False
    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None, _send_sync, to, subject, html_body, attachments)
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

async def send_record_shared_email(
    to: str,
    *,
    owner_name: str,
    data_type: str,
    recipient_name: str | None = None,
    read_access: bool = True,
    write_access: bool = False,
    expires_at: str | None = None,
) -> bool:
    """Tell someone a patient has shared a record with them.

    Sharing used to be silent on the recipient's side: the grant was created and
    returned to the owner, and the person given access learned nothing. Someone
    could hold access to a patient's labs and never know.

    NO CLINICAL CONTENT travels in this mail. It names who shared, what KIND of
    record, and where to go — never a value, a result or a diagnosis. Email is
    not a channel we control once it leaves, and the record itself is behind
    the login where it belongs.

    Transactional, so it must never consult `marketing_opt_out_at` (§3d):
    opting out of announcements cannot opt someone out of being told that they
    now hold a patient's data.
    """
    greeting = f"Hi {_escape(recipient_name.split()[0])}," if recipient_name else "Hi,"
    owner = _escape(owner_name or "An ALAFIA member")
    kind = _escape((data_type or "health").replace("_", " "))
    url = f"{settings.PUBLIC_WEB_URL.rstrip('/')}/share-records"

    if write_access and read_access:
        access = "view and update"
    elif write_access:
        access = "update"
    else:
        access = "view"

    expiry = (f"<p style=\"margin:0 0 16px\">This access expires on {_escape(expires_at)}.</p>"
              if expires_at else "")

    subject = f"{settings.APP_NAME} — {owner_name or 'a member'} shared their {kind} records with you"
    html = f"""
      <div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:520px;margin:0 auto;color:#0f172a">
        <h2 style="color:#f97316;margin:0 0 16px">A record has been shared with you</h2>
        <p style="margin:0 0 16px">{greeting}</p>
        <p style="margin:0 0 16px">
          <strong>{owner}</strong> has shared their <strong>{kind}</strong> records
          with you on {_escape(settings.APP_NAME)}. You can {access} them.
        </p>
        {expiry}
        <p style="margin:0 0 24px">
          <a href="{url}" style="background:#f97316;color:#fff;padding:12px 20px;
             border-radius:8px;text-decoration:none;display:inline-block">Open shared records</a>
        </p>
        <p style="margin:0;font-size:13px;color:#64748b">
          The records themselves are not in this email — sign in to see them.
          If you were not expecting this, you can ignore it; nothing is shared
          from your own account.
        </p>
      </div>
    """
    return await send_email(to, subject, html)


async def send_share_invitation_email(
    to: str,
    *,
    owner_name: str,
    data_types: str,
    recipient_name: str | None = None,
    message: str | None = None,
) -> bool:
    """Invite someone to receive a patient's records.

    `send_invitation` wrote an invitation row and returned it — despite the
    name, nothing was sent. The invitee never heard about it, so the invitation
    could only be discovered by someone already logged in and looking for it,
    which is precisely the person who does not need an invitation.

    An invitation ASKS; `send_record_shared_email` reports a share that has
    already happened. Different letters, because the reader has to do something
    about one of them.
    """
    greeting = f"Hi {_escape(recipient_name.split()[0])}," if recipient_name else "Hi,"
    owner = _escape(owner_name or "An ALAFIA member")
    kinds = _escape((data_types or "health").replace("_", " "))
    url = f"{settings.PUBLIC_WEB_URL.rstrip('/')}/share-records"
    note = (f'<p style="margin:0 0 16px;padding:12px;background:#f8fafc;'
            f'border-radius:8px;font-style:italic">{_escape(message)}</p>'
            if message else "")

    subject = f"{settings.APP_NAME} — {owner_name or 'a member'} wants to share their records with you"
    html = f"""
      <div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:520px;margin:0 auto;color:#0f172a">
        <h2 style="color:#f97316;margin:0 0 16px">You've been invited to view a record</h2>
        <p style="margin:0 0 16px">{greeting}</p>
        <p style="margin:0 0 16px">
          <strong>{owner}</strong> would like to share their <strong>{kinds}</strong>
          records with you on {_escape(settings.APP_NAME)}.
        </p>
        {note}
        <p style="margin:0 0 24px">
          <a href="{url}" style="background:#f97316;color:#fff;padding:12px 20px;
             border-radius:8px;text-decoration:none;display:inline-block">Review the invitation</a>
        </p>
        <p style="margin:0;font-size:13px;color:#64748b">
          No records are in this email, and nothing is shared until you accept.
          If you were not expecting this, you can ignore it.
        </p>
      </div>
    """
    return await send_email(to, subject, html)


async def send_signup_receipt_email(
    to: str,
    *,
    full_name: str | None = None,
    plan_label: str,
    amount_label: str | None = None,
    verification_pending: bool = False,
    verify_url: str | None = None,
) -> bool:
    """Receipt and welcome, sent the moment payment succeeds.

    Sent BEFORE the account exists when verification is still outstanding —
    deliberately. Money has changed hands, and the person is entitled to a
    record of that whether or not they have clicked the link yet. Waiting until
    the account is created would leave a paid customer with nothing in writing.

    When verification is still pending this letter carries the link, so the one
    email a payer is guaranteed to open is also the one that finishes signup.
    """
    greeting = f"Hi {_escape(full_name.split()[0])}," if full_name else "Hi,"
    plan = _escape(plan_label)
    amount = f"<p style=\"margin:0 0 8px\"><strong>Amount:</strong> {_escape(amount_label)}</p>" if amount_label else ""

    if verification_pending and verify_url:
        subject = f"{settings.APP_NAME} — payment received, one step left"
        headline = "Payment received — one step left"
        action = f"""
          <p style="margin:0 0 16px">
            To finish setting up your account, confirm your email address using
            the link we sent when you started. Lost it? Open the page below and
            we will send a fresh one.
          </p>
          <p style="margin:0 0 24px">
            <a href="{verify_url}" style="background:#f97316;color:#fff;padding:12px 20px;
               border-radius:8px;text-decoration:none;display:inline-block">Finish setting up</a>
          </p>
          <p style="margin:0 0 16px;font-size:13px;color:#64748b">
            Your membership is paid and waiting. Nothing further is charged.
          </p>
        """
    else:
        subject = f"Welcome to {settings.APP_NAME}"
        headline = f"Welcome to {settings.APP_NAME}"
        action = f"""
          <p style="margin:0 0 24px">
            <a href="{settings.PUBLIC_WEB_URL.rstrip('/')}/login"
               style="background:#f97316;color:#fff;padding:12px 20px;border-radius:8px;
               text-decoration:none;display:inline-block">Open ALAFIA</a>
          </p>
        """

    html = f"""
      <div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:520px;margin:0 auto;color:#0f172a">
        <h2 style="color:#f97316;margin:0 0 16px">{headline}</h2>
        <p style="margin:0 0 16px">{greeting}</p>
        <p style="margin:0 0 16px">Thank you — your payment went through.</p>
        <div style="margin:0 0 20px;padding:14px;background:#f8fafc;border-radius:8px">
          <p style="margin:0 0 8px"><strong>Membership:</strong> {plan}</p>
          {amount}
          <p style="margin:0;font-size:13px;color:#64748b">
            A full receipt is also available from your card provider.
          </p>
        </div>
        {action}
        <p style="margin:0;font-size:13px;color:#64748b">
          ALAFIA helps you track meals, medication, labs and therapies, share
          records with the people caring for you, and ask questions of your own
          health record. If anything looks wrong, reply and tell us.
        </p>
      </div>
    """
    return await send_email(to, subject, html)

async def send_signup_incomplete_email(to: str, *, full_name: str | None = None) -> bool:
    """Tell someone their signup never finished, and how to finish it.

    Sent to people whose account was created by the old one-step form: it made
    a loginable account, took no payment, sent no email, and showed no result,
    so they were left holding something that could not do anything and had no
    way to know why. Two of them sat like that for over a fortnight.

    TRANSACTIONAL, not marketing — it must NOT consult `marketing_opt_out_at`.
    This is about an action the person themselves started on their own account,
    exactly like a verification or a password reset. Gating it on a marketing
    preference would withhold the one message that unblocks them.

    It carries no clinical content of any kind and makes no claim about what
    they were charged beyond the truth: nothing.
    """
    greeting = f"Hi {_escape(full_name.split()[0])}," if full_name else "Hi,"
    login_url = f"{settings.PUBLIC_WEB_URL.rstrip('/')}/login"

    html = f"""
      <div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:520px;margin:0 auto;color:#0f172a">
        <h2 style="color:#f97316;margin:0 0 16px">Your {_escape(settings.APP_NAME)} signup didn't finish</h2>
        <p style="margin:0 0 16px">{greeting}</p>
        <p style="margin:0 0 16px">
          You started creating an {_escape(settings.APP_NAME)} account and it never
          completed. That was a fault on our side, not anything you did.
        </p>
        <p style="margin:0 0 16px">
          <strong>You were not charged.</strong> Your account exists and your
          password works — it just has no membership attached yet, which is why
          it would not let you in.
        </p>
        <p style="margin:0 0 16px">
          Sign in and choose a plan and you are set up:
        </p>
        <p style="margin:0 0 24px">
          <a href="{login_url}" style="background:#f97316;color:#fff;padding:12px 20px;
             border-radius:8px;text-decoration:none;display:inline-block">Sign in and finish</a>
        </p>
        <p style="margin:0 0 16px;font-size:13px;color:#64748b">
          Forgotten your password? Use "Forgot password" on that page.
        </p>
        <p style="margin:0;font-size:13px;color:#64748b">
          Sorry for the wasted trip. If you would rather not continue, ignore
          this and nothing further will happen — you will not be billed and we
          will not chase you.
        </p>
      </div>
    """
    return await send_email(to, f"Your {settings.APP_NAME} signup didn't finish", html)


def is_clinical_role(role: str | None) -> bool:
    """True when `role` is one of the clinical roles, by the enum's own grouping.

    Derived from `ROLE_CATEGORIES` rather than a hand-typed list: the categories
    already say which roles are clinical, and a second copy here would go stale
    the first time a role is added — §3ad's "never type a code from memory",
    applied to a role vocabulary instead of an ICD code.

    `patient` is deliberately NOT clinical. Every account is a patient account;
    a clinical role is what is added ON TOP, which is exactly the distinction
    this function exists to draw.
    """
    if not role:
        return False
    from app.models.user_roles import ROLE_CATEGORIES
    return any(role in members for members in ROLE_CATEGORIES.values())


async def send_complimentary_invitation_email(
    to: str,
    *,
    display_name: str | None = None,
    months: int = 12,
    signup_deadline: str | None = None,
    clinical_role: str | None = None,
    practice: str | None = None,
    screenshots: Sequence[Attachment] | None = None,
    postal_address: str | None = None,
) -> bool:
    """Invite someone to claim a complimentary membership that is waiting for them.

    ONE template, two faces. `clinical_role` switches both the wording and what
    the letter promises, because the two must never drift apart: describing a
    clinician board to someone who will not be granted a clinical role is a
    promise the account cannot keep. Pass the role only when it will actually be
    granted — an honorific is NOT a role. "Dr." in front of a name can mean a
    PhD, and `display_name` carries that without implying clinical access.

    MARKETING, not transactional — and the distinction is the opposite of
    `send_signup_incomplete_email` above. That one is sent about an action the
    person themselves began, so it must ignore `marketing_opt_out_at`. This one
    is UNSOLICITED: nobody asked for it, so it discloses why it arrived and
    offers a reply path. Getting that backwards would mail an offer to someone
    who opted out.

    The flow it describes is the one the system actually implements: sign up,
    confirm the address, then STOP at the payment step. There is no code path
    that lets a web signup skip payment on its own, so an operator finishes it
    with `scripts/activate_comp_signup.py`. Saying "close the tab" is therefore
    an instruction, not a courtesy — a card entered there would charge them for
    something they were told was free.
    """
    name = _escape(display_name) if display_name else None
    greeting = f"Welcome, {name}" if name else "Welcome"
    app = _escape(settings.APP_NAME)
    signup_url = f"{settings.PUBLIC_WEB_URL.rstrip('/')}/signup"
    clinical = is_clinical_role(clinical_role)

    # "1 months" went out in TWO sentences of a one-month invitation before this
    # existed — the headline offer and the deadline line both interpolated the
    # bare number. Every letter until 2026-09-28 was for 12 months, which is why
    # it had never shown. A grant length is the single most material figure in
    # this letter, so it must not arrive looking like a template someone forgot
    # to finish.
    months_label = f"{months} month" if months == 1 else f"{months} months"

    # Only rendered when a clinical role is actually being granted.
    clinician_block = ""
    if clinical:
        where = f" (we have you as {_escape(practice)})" if practice else ""
        clinician_block = f"""
        <h3 style="margin:28px 0 8px;font-size:16px;">Your account is both clinician and patient</h3>
        <p style="margin:0 0 16px;">
          Every {app} account is a patient account. Yours is elevated with
          {_escape((clinical_role or '').replace('_', ' '))} access on top of it, so you can move
          between your own health record and the clinical view of patients who
          choose to share theirs with you.
        </p>
        <p style="margin:0 0 16px;">
          Your clinician profile{where} — specialty, credentials and NPI — is what a
          patient sees when deciding whether to share their record with you. Your
          patient profile is separate, private, and yours.
        </p>"""

    deadline_line = ""
    if signup_deadline:
        deadline_line = (
            f'<p style="margin:0 0 16px;"><strong>Please sign up by '
            f'{_escape(signup_deadline)}.</strong> Your {months_label} begin{"s" if months == 1 else ""} '
            f'once your account is active.</p>'
        )

    # Screenshots travel INLINE (cid:), never as a link to an image host: a
    # remote <img> in a letter is a tracking pixel by construction, and it rots
    # the moment the URL moves.
    #
    # The clinician letter and the patient letter must not show the same
    # pictures. The 2026-09-15 invitation showed the CLINICIAN BOARD — a
    # patient's conditions, medications, labs and dialysis on one screen — which
    # is the right illustration for someone being granted clinical access and a
    # promise the account cannot keep for anyone else. What each reader is shown
    # has to match what they will actually be able to open.
    shots_block = ""
    if screenshots:
        figures = []
        for shot in screenshots:
            if not shot.content_id:
                # Rendering it anyway produces a broken image in a letter that
                # cannot be recalled, while the send still reports success.
                raise ValueError(
                    f"screenshot {shot.filename!r} has no content_id, so "
                    f"cid: cannot resolve and the letter would show a broken "
                    f"image")
            caption = (
                f'<div style="font-size:12px;color:#6b7280;margin:6px 0 0;">'
                f'{_escape(shot.caption)}</div>'
            ) if shot.caption else ""
            figures.append(
                f'<div style="margin:0 0 18px;">'
                f'<img src="cid:{shot.content_id}" '
                f'alt="{_escape(shot.caption or shot.filename)}" width="560" '
                f'style="width:100%;max-width:560px;height:auto;border:1px solid '
                f'#e5e7eb;border-radius:8px;display:block;">{caption}</div>'
            )
        shots_block = (
            '<h3 style="margin:28px 0 8px;font-size:16px;">What it looks '
            'like</h3>' + "".join(figures) +
            '<p style="margin:0 0 16px;font-size:12px;color:#6b7280;">'
            'Shown on a new, empty account — nothing has been logged in it, and '
            'no patient’s data appears in these images.</p>'
        )

    # CAN-SPAM requires a physical postal address in commercial email, and this
    # letter is unsolicited. `send_comp_invitation.py` has always REFUSED to run
    # without POSTAL_ADDRESS and printed it back as confirmation — while nothing
    # here ever rendered it, so the gate collected the value and discarded it and
    # the letter went out without the address it was demanding. Found on
    # 2026-09-27 by reading the rendered bytes; the printed confirmation line
    # looked like proof and was not. §3ar — a control nothing observes does
    # nothing — and §3d's "verify the side effect, not the status".
    postal_line = (
        f'<p style="color:#9ca3af;font-size:12px;margin:10px 0 0;">'
        f'{_escape(postal_address)}</p>'
    ) if postal_address else ""

    html = f"""
    <html><body style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;
                       max-width:560px;margin:0 auto;color:#0f172a;line-height:1.55;">
      <h2 style="color:#ea580c;margin:0 0 4px;">{app}</h2>
      <h3 style="margin:0 0 16px;font-size:18px;">{greeting}</h3>

      <p style="margin:0 0 16px;">
        We have set aside a complimentary {app} membership for
        <strong>{months_label}</strong> for you — no card, no charge, nothing to
        cancel.
      </p>
      {clinician_block}

      <h3 style="margin:28px 0 8px;font-size:16px;">Setting it up takes two minutes</h3>
      <ol style="margin:0 0 16px;padding-left:20px;">
        <li style="margin-bottom:8px;">
          Go to <a href="{signup_url}" style="color:#ea580c;">{signup_url}</a> and sign
          up with <strong>{_escape(to)}</strong> — use that address exactly, as it is
          the one your complimentary membership is attached to.
        </li>
        <li style="margin-bottom:8px;">
          Choose your own password and confirm the link we email you. (We never see
          your password, and the confirmation link is good for 24 hours.)
        </li>
        <li style="margin-bottom:8px;">
          You will then be offered a payment step.
          <strong>Close the tab there — do not enter any card details.</strong>
          We will activate your membership and email you the moment it is live.
        </li>
      </ol>
      {deadline_line}
      {shots_block}

      <p style="margin:0 0 16px;">
        If anything does not work as it should, just reply to this message and a
        person will read it.
      </p>
      <p style="margin:24px 0 0;">— The {app} team</p>

      <hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0;">
      <p style="color:#6b7280;font-size:12px;margin:0;">
        You are receiving this because a complimentary {app} membership was
        created for this address. If that was not meant for you, reply and we
        will remove it — nothing has been charged and no account exists yet.
      </p>
      {postal_line}
    </body></html>
    """
    return await send_email(
        to, f"Your complimentary {settings.APP_NAME} membership", html,
        attachments=list(screenshots or []))
