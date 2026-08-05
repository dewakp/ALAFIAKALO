"""Email service — sends transactional email via SMTP.

Usage:
    from app.services.email import send_email, send_password_reset_email

All methods are async-safe (run SMTP in executor to avoid blocking the event loop).
"""

import asyncio
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def _smtp_configured() -> bool:
    return bool(settings.SMTP_HOST and settings.SMTP_USER)


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
    """Send an email asynchronously. Returns True on success, False on failure."""
    if not _smtp_configured():
        logger.warning("SMTP not configured — email to %s skipped", to)
        return False
    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _send_sync, to, subject, html_body)
        return True
    except Exception:
        logger.exception("Failed to send email to %s", to)
        return False


async def send_password_reset_email(to: str, reset_token: str) -> bool:
    """Send a password reset email with a secure token link."""
    subject = f"{settings.APP_NAME} — Password Reset"
    html_body = f"""
    <html><body style="font-family:sans-serif;max-width:480px;margin:auto;">
      <h2>{settings.APP_NAME}</h2>
      <p>You requested a password reset. Use the code below to reset your password:</p>
      <p style="font-size:18px;background:#f3f4f6;padding:12px;border-radius:8px;text-align:center;letter-spacing:2px;">
        <strong>{reset_token}</strong>
      </p>
      <p>This code expires in {settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES} minutes.</p>
      <p>If you didn't request this, please ignore this email.</p>
      <hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0;">
      <p style="color:#6b7280;font-size:12px;">{settings.APP_NAME} — Holistic Health Platform</p>
    </body></html>
    """
    return await send_email(to, subject, html_body)


def smtp_configured() -> bool:
    """Public probe — callers decide how to behave when mail cannot be sent.

    Signup uses this to refuse rather than to silently issue an account that no
    one can verify.
    """
    return _smtp_configured()


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
