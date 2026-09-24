"""Tell the operator when someone could not get in, or could not sign up.

Four real addresses signed up and were left holding an account that could do
nothing, two of them 16 and 19 days before anyone noticed (§3as). A fifth
person's verification mail bounced on a mistyped address and the first anyone
knew of it was opening the Resend dashboard by hand, four days later.

Every one of those was visible in the logs at the time. Nobody reads logs
unprompted, so the failure to sign up was indistinguishable from nobody trying.

This module makes an auth failure REACH the single system administrator, by two
channels, because they answer different questions:

  * an in-app notification is what they see next time they open the console;
  * an email is what reaches them when they do not.

Three rules it must not break:

  * **It must never fail the request it is reporting on.** Everything here is
    wrapped. An alert that breaks a login is worse than the failure it
    describes — §3ah, where a mail outage inside a webhook would have sent
    Stripe into a multi-day retry cascade.
  * **It must not flood.** A credential-stuffing run is thousands of login
    failures in a minute. One email per distinct problem per window; the log
    line is still written every time.
  * **It reports, it never decides.** Nothing here changes what the caller
    answers the user.
"""

import logging
import time
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import async_session
from app.core.notification_engine import create_notification
from app.models.notifications import NotificationCategory, NotificationPriority
from app.models.user import User
from app.services.email import send_email

logger = logging.getLogger(__name__)

AuthEventKind = Literal["registration", "login"]


def client_ip(request) -> str | None:
    """The caller's address, or None. Lives here so both call sites agree.

    `request.client` is None for an ASGI scope with no client (test transports,
    some proxies), and reaching into `.host` unguarded turns an alert into an
    AttributeError inside the failure path it is reporting on.
    """
    try:
        return request.client.host if request and request.client else None
    except Exception:
        return None

#: One email per (kind, reason, address) inside this window. A brute-force run
#: is thousands of failures a minute, and an operator who is mailed thousands of
#: times learns to filter the sender — which loses the one that mattered.
_ALERT_WINDOW_SECONDS = 15 * 60

#: Deliberately per-process and unbounded-in-time-but-bounded-in-size. Cloud Run
#: holds several instances, so this damps the flood rather than guaranteeing
#: exactly-once — which is the right trade for an alert, and is why the log line
#: below is unconditional.
_recent: dict[tuple, float] = {}
_RECENT_MAX = 2000


def _should_send(key: tuple) -> bool:
    now = time.time()
    if len(_recent) > _RECENT_MAX:
        cutoff = now - _ALERT_WINDOW_SECONDS
        for k, seen in list(_recent.items()):
            if seen < cutoff:
                _recent.pop(k, None)
    last = _recent.get(key)
    if last is not None and (now - last) < _ALERT_WINDOW_SECONDS:
        return False
    _recent[key] = now
    return True


def _admin_addresses() -> list[str]:
    """The operator's real mailbox.

    CONTACT_DELIVERY_EMAIL first: alafia.app publishes DKIM and SPF and has NO
    MX records (§3d), so the nominal desk addresses cannot receive mail at all.
    """
    if settings.CONTACT_DELIVERY_EMAIL:
        return [settings.CONTACT_DELIVERY_EMAIL]
    return [e for e in (settings.ADMIN_EMAILS or []) if e]


async def _admin_user(db: AsyncSession) -> User | None:
    emails = [e.strip().lower() for e in (settings.ADMIN_EMAILS or []) if e and e.strip()]
    if not emails:
        return None
    return (await db.execute(
        select(User).where(User.email.in_(emails)).order_by(User.id)
    )).scalars().first()


async def notify_admin_auth_failure(
    *,
    kind: AuthEventKind,
    reason: str,
    email: str | None = None,
    client_ip: str | None = None,
    detail: str | None = None,
) -> None:
    """Report one registration or login failure. Never raises.

    `reason` is a short stable slug ("email_already_registered",
    "bad_password") — it is the dedupe key and the thing worth counting.
    `detail` is free text for the operator.

    **It takes no session, deliberately.** The first version wrote through the
    REQUEST's session, and every caller raises an HTTPException immediately
    afterwards — `get_db` rolls back on any exception, HTTPException included,
    so the notification was added, flushed, and then discarded every single
    time. It would have been a silent no-op reporting on silent failures.

    So the write gets its own session and commits independently, the same shape
    the telemetry sink uses (§3ay): the alert must outlive the request that is
    about to fail.
    """
    # Unconditional, and first: the alert channels are best-effort, the log is
    # the record. §3d's "the row is the receipt", applied to an incident.
    logger.warning(
        "auth_failure kind=%s reason=%s email=%s ip=%s detail=%s",
        kind, reason, email or "-", client_ip or "-", detail or "-",
    )

    if not _should_send((kind, reason, (email or "").lower())):
        return

    title = (
        "Signup failed" if kind == "registration" else "Sign-in failed"
    )
    message = (
        f"{title}: {reason}."
        f"\nAddress: {email or 'not supplied'}"
        f"\nFrom: {client_ip or 'unknown'}"
        + (f"\n{detail}" if detail else "")
    )

    try:
        async with async_session() as session:
            admin = await _admin_user(session)
            if admin is not None:
                await create_notification(
                    session,
                    user_id=admin.id,
                    category=NotificationCategory.SYSTEM,
                    priority=(NotificationPriority.HIGH if kind == "registration"
                              else NotificationPriority.MEDIUM),
                    title=title,
                    message=message,
                    action_url="/minister",
                    metadata_dict={"kind": kind, "reason": reason,
                                   "email": email, "ip": client_ip},
                )
                # create_notification only flushes. Without this the row dies
                # with the session and the operator is told nothing.
                await session.commit()
    except Exception:
        logger.exception("auth alert: in-app notification failed (%s/%s)", kind, reason)

    for address in _admin_addresses():
        try:
            await send_email(
                to=address,
                subject=f"[ALAFIA] {title} — {reason}",
                html_body=(
                    f"<h2>{title}</h2>"
                    f"<p><strong>Reason:</strong> {reason}<br>"
                    f"<strong>Address:</strong> {email or 'not supplied'}<br>"
                    f"<strong>From:</strong> {client_ip or 'unknown'}</p>"
                    + (f"<p>{detail}</p>" if detail else "")
                    + f"<p>Further identical reports are suppressed for "
                      f"{_ALERT_WINDOW_SECONDS // 60} minutes. Every occurrence "
                      f"is still in the application log.</p>"
                ),
            )
        except Exception:
            # An alert that breaks the request it is reporting on is worse than
            # the failure it describes.
            logger.exception("auth alert: email to %s failed (%s/%s)",
                             address, kind, reason)
