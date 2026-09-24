"""Provider callbacks that tell us what actually happened.

Today that is Resend's delivery events. The application could not answer "did
it arrive?" for any message it has ever sent: `send_email` returns True the
moment Resend answers 200, and Resend answers 200 with a message id for a send
it will never transmit — an address on its suppression list, added
automatically after an earlier hard bounce.

On 2026-09-23 that produced three "Email sent via Resend to …" log lines for
one bounce and two sends that never left the building, and those lines were
then reported to the user as proof of delivery. The send RESPONSE cannot tell
us; only the delivery EVENT can, and this is where it arrives.

§3ah's rule governs the failure modes, because a payment webhook already taught
them once:

- **A refused webhook must never be silent.** 21 of 31 Stripe deliveries were
  rejected at the signature check with no log line and no row — two thirds of
  the traffic vanished with no trace anywhere. Every refusal here logs why,
  with the ids and the age that separate a wrong secret from a second endpoint
  from an expired replay.
- **A mail outage must never fail the webhook.** The admin alert runs after the
  row exists and is wrapped: a non-2xx over an email problem sends the provider
  into a multi-day retry cascade for an event we already recorded.
"""

import base64
import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.email_event import FAILURE_EVENTS, EmailEvent
from app.services.email import send_email

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

# Svix tolerates a 5-minute clock skew and so do we. Wider re-opens a replay
# window; narrower rejects honest deliveries from a provider whose clock drifts.
_TOLERANCE_SECONDS = 5 * 60


def _verify_svix(body: bytes, headers) -> tuple[bool, str]:
    """Resend signs with the Svix scheme. Returns (ok, reason_if_not).

    The signed content is `{id}.{timestamp}.{body}` over the RAW bytes — not a
    re-serialised dict. Round-tripping through json would change key order and
    whitespace and fail every signature.
    """
    secret = (settings.RESEND_WEBHOOK_SECRET or "").strip()
    if not secret:
        # Refuse rather than trust unsigned input. An endpoint that accepts
        # anything is a public writer into our tables, and "temporarily
        # permissive" is how that becomes permanent.
        return False, "no signing secret configured"

    svix_id = headers.get("svix-id") or headers.get("webhook-id") or ""
    svix_ts = headers.get("svix-timestamp") or headers.get("webhook-timestamp") or ""
    svix_sig = headers.get("svix-signature") or headers.get("webhook-signature") or ""
    if not (svix_id and svix_ts and svix_sig):
        return False, "missing svix-id/timestamp/signature header"

    try:
        age = abs(time.time() - int(svix_ts))
    except ValueError:
        return False, "timestamp is not an integer"
    if age > _TOLERANCE_SECONDS:
        return False, f"timestamp outside tolerance ({int(age)}s)"

    # "whsec_" is a human-readable prefix, not part of the key material.
    raw = secret.split("_", 1)[1] if secret.startswith("whsec_") else secret
    try:
        key = base64.b64decode(raw)
    except Exception:
        return False, "signing secret is not valid base64"

    signed = b"%s.%s.%s" % (svix_id.encode(), svix_ts.encode(), body)
    expected = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()

    # The header carries a space-separated list, each "v1,<signature>", so a
    # secret can be rotated without dropping deliveries signed by the old one.
    for part in svix_sig.split():
        _, _, candidate = part.partition(",")
        if candidate and hmac.compare_digest(candidate, expected):
            return True, ""
    return False, "no signature matched"


def _parse_occurred(value) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        # An unreadable timestamp is discarded, never repaired — inventing one
        # would make a stale retry look current, which is the thing this column
        # exists to reveal.
        return None


def _first_recipient(data: dict) -> str | None:
    to = data.get("to")
    if isinstance(to, list):
        return str(to[0])[:320] if to else None
    return str(to)[:320] if to else None


@router.post("/resend", include_in_schema=False)
async def resend_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    body = await request.body()

    ok, reason = _verify_svix(body, request.headers)
    if not ok:
        # Named, with the ids — this is exactly what was missing when two
        # thirds of Stripe's traffic disappeared (§3ah).
        logger.warning(
            "Resend webhook REFUSED (%s): svix-id=%s bytes=%d secret_configured=%s",
            reason, request.headers.get("svix-id", "-"), len(body),
            bool(settings.RESEND_WEBHOOK_SECRET),
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Invalid signature")

    try:
        event = json.loads(body)
    except ValueError:
        logger.warning("Resend webhook REFUSED (body is not JSON): %d bytes", len(body))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Body is not JSON")

    data = event.get("data") or {}
    event_type = str(event.get("type") or "")[:64]
    bounce = data.get("bounce") or {}

    row = EmailEvent(
        provider="resend",
        message_id=str(data.get("email_id") or "")[:128] or None,
        event_type=event_type,
        recipient=_first_recipient(data),
        subject=str(data.get("subject") or "")[:500] or None,
        bounce_type=str(bounce.get("type") or "")[:32] or None,
        reason=(bounce.get("message") or data.get("reason") or None),
        occurred_at=_parse_occurred(event.get("created_at")),
        received_at=datetime.now(timezone.utc),
        # Verbatim. The columns above are a guess about which fields matter,
        # made before the first real incident.
        payload=body.decode("utf-8", errors="replace")[:60000],
    )
    db.add(row)
    await db.commit()

    logger.info("Resend event recorded: %s to=%s id=%s", event_type,
                row.recipient or "-", row.message_id or "-")

    if event_type in FAILURE_EVENTS:
        # The point of the whole feature: somebody finds out without opening a
        # dashboard. Best-effort — the row is already committed.
        try:
            await _alert_admin(row)
        except Exception:
            logger.exception("Resend webhook: admin alert failed for %s", row.recipient)

    return {"ok": True}


async def _alert_admin(row: EmailEvent) -> None:
    """Tell the operator a message did not arrive.

    CONTACT_DELIVERY_EMAIL first: alafia.app publishes DKIM and SPF and has NO
    MX records (§3d), so the nominal desk addresses cannot receive. That
    setting is the one real mailbox.
    """
    to = (settings.CONTACT_DELIVERY_EMAIL
          or (settings.ADMIN_EMAILS[0] if settings.ADMIN_EMAILS else ""))
    if not to:
        logger.warning("Resend failure for %s not alerted: no admin address set",
                       row.recipient)
        return

    await send_email(
        to=to,
        subject=f"[ALAFIA] Email {row.event_type} — {row.recipient or 'unknown'}",
        html_body=(
            f"<h2>A message did not reach its recipient</h2>"
            f"<p><strong>Event:</strong> {row.event_type}<br>"
            f"<strong>To:</strong> {row.recipient or '—'}<br>"
            f"<strong>Subject:</strong> {row.subject or '—'}<br>"
            f"<strong>Bounce type:</strong> {row.bounce_type or '—'}<br>"
            f"<strong>Reason:</strong> {row.reason or '—'}</p>"
            f"<p>After a hard bounce Resend SUPPRESSES the address: later sends "
            f"return 200 with an id and are never transmitted. A corrected "
            f"address has to be removed from the suppression list, or it will "
            f"look like it is sending and silently go nowhere.</p>"
        ),
    )
