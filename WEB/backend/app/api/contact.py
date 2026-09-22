"""Contact form — public, unauthenticated, never paywalled.

Mounted on the app directly rather than under `api_router`, for the same reason
`/unsubscribe` is (§3d): that router carries
`Depends(require_active_subscription)`, and the people most likely to need the
contact form are the ones who cannot get in — an account that will not
authenticate, a lapsed subscription, a privacy request from someone who has
already deleted their account.

**Submissions do not leave our infrastructure.** The obvious way to build a
marketing contact form is a third-party relay like FormSubmit, which is what
the CRAM marketing site uses. That is fine for a security consultancy. It is
not fine here: two of these desks are Privacy and the Data Protection Officer,
so a message can carry a patient's health details, and posting that to a
third-party form service would disclose it to a processor nobody has an
agreement with.

**And email is not where the message lives.** `alafia.app` publishes DKIM and
SPF but has NO MX records — it can send and cannot receive, so the per-desk
contact@/privacy@/dpo@ addresses would bounce silently. Every submission is
written to `contact_submissions` FIRST and the request succeeds on that write;
the desk notification is attempted afterwards and its outcome recorded on the
row (`notified_at`, `notify_error`).

Delivery therefore goes to `settings.CONTACT_DELIVERY_EMAIL` — one real mailbox,
with the desk named in the subject for filtering. Confirmed working to an
external inbox on 2026-09-03; receiving needs no DNS change, only SENDING
requires the verified domain. Clear that setting once MX records exist and the
per-desk mailboxes are real.

If a notification ever fails, the row is still the record. Read the table; do
not assume an empty inbox means nothing came in.

Spam handling is deliberately quiet. A honeypot field that only a bot fills is
accepted with the same 200 as a real message — telling a bot it was detected
just teaches it to try again without the field.
"""

# NO `from __future__ import annotations` here, deliberately. It turns
# annotations into strings, and the @limiter.limit wrapper then leaves FastAPI
# unable to resolve `ContactRequest` — it demotes the body to a QUERY parameter
# and every submit 422s with {"loc":["query","payload"]}. auth.py's identical
# limiter+body routes work precisely because they lack this import.
import html
import logging
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.rate_limit import limiter
from app.models.contact import ContactSubmission
from app.services.email import send_email

logger = logging.getLogger(__name__)

router = APIRouter(tags=["contact"])

# Which desk each topic reaches. The VALUE is chosen by the server from a fixed
# map — the client sends a key, never an address, so the form can never be
# turned into an open relay by posting a `to` field of someone's choosing.
TOPIC_DESKS: dict[str, tuple[str, str]] = {
    "support": ("contact@alafia.app", "General & Support"),
    "privacy": ("privacy@alafia.app", "Privacy"),
    "dpo": ("dpo@alafia.app", "Data Protection Officer"),
    "security": ("security@alafia.app", "Security Disclosure"),
    "billing": ("contact@alafia.app", "Billing & Membership"),
    "clinical": ("contact@alafia.app", "Clinical & Care Teams"),
    # Requests to join the iOS TestFlight build, from the landing page. The
    # address is nominal like every other desk — CONTACT_DELIVERY_EMAIL routes
    # all of them to one real mailbox — and the point of the entry is that the
    # CLIENT sends this key and never an address.
    "beta_ios": ("contact@alafia.app", "iOS Beta Request"),
}

# Topics that also send a confirmation to the PERSON WHO WROTE.
#
# Scoped rather than global on purpose. Someone filing a security disclosure or
# a deletion request has not asked for an automated reply in their inbox, and
# turning one on for every desk would change what four existing desks do to
# people who never opted into it. A beta request is different: the sender is
# volunteering and is waiting to hear back, so silence reads as a dead form.
CONFIRM_TO_SENDER: frozenset[str] = frozenset({"beta_ios"})


class ContactRequest(BaseModel):
    # A key from TOPIC_DESKS, not an address.
    topic: str = Field(..., max_length=32)
    name: str = Field(..., min_length=1, max_length=120)
    email: EmailStr
    message: str = Field(..., min_length=10, max_length=5000)
    organization: str | None = Field(None, max_length=160)
    phone: str | None = Field(None, max_length=40)
    # Honeypot. Real users never see it; bots fill every field they find.
    website: str | None = Field(None, max_length=200)


class ContactResponse(BaseModel):
    ok: bool
    desk: str
    # Quotable handle for the sender. The row exists under this reference even
    # if the notification email never arrives.
    reference: str


def _render(payload: ContactRequest, desk_label: str, reference: str = "") -> str:
    """The email body. Every value is escaped — a contact form is untrusted
    input arriving from the open internet, and it renders in our own inbox."""
    def esc(v: str | None) -> str:
        return html.escape(v or "—")

    return f"""\
<h2>New {esc(desk_label)} enquiry — {esc(reference)}</h2>
<table cellpadding="6" style="border-collapse:collapse">
  <tr><td><strong>Name</strong></td><td>{esc(payload.name)}</td></tr>
  <tr><td><strong>Email</strong></td><td>{esc(payload.email)}</td></tr>
  <tr><td><strong>Organisation</strong></td><td>{esc(payload.organization)}</td></tr>
  <tr><td><strong>Phone</strong></td><td>{esc(payload.phone)}</td></tr>
  <tr><td><strong>Topic</strong></td><td>{esc(desk_label)}</td></tr>
</table>
<h3>Message</h3>
<p style="white-space:pre-wrap">{esc(payload.message)}</p>
<hr>
<p style="color:#666;font-size:12px">Sent from the alafia.app contact form.
Reply directly to reach the sender.</p>
"""


def _render_confirmation(payload: ContactRequest, desk_label: str, reference: str) -> str:
    """What the SENDER receives — an acknowledgement, never a copy of the desk mail.

    Deliberately thin. It confirms that the request arrived and gives the
    reference; it does not quote the message back, because a contact form can
    carry health details and mail is not a channel we control once it leaves
    (§3d, on why a share notification names no clinical content).

    It also promises nothing about timing or outcome. Being added to a beta is
    a decision a person makes afterwards.
    """
    def esc(v: str | None) -> str:
        return html.escape(v or "")

    return f"""\
<p>Hello {esc(payload.name)},</p>
<p>We have your {esc(desk_label).lower()} — it reached us and is on the list.</p>
<p>Your reference is <strong>{esc(reference)}</strong>. Quote it if you follow up.</p>
<p>If you are already a member on the web, mention the email address you signed
up with and we will match it when the invitations go out.</p>
<p style="color:#666;font-size:12px">You are receiving this because this address
was entered on the ALAFIA beta request form at alafia.app. If that was not you,
no account has been changed and you can ignore this.</p>
"""


@router.post("/contact", response_model=ContactResponse)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def submit_contact(
    request: Request,
    payload: ContactRequest,
    db: AsyncSession = Depends(get_db),
) -> ContactResponse:
    """Record a contact message, then notify the desk that owns it.

    The ROW is the receipt. `alafia.app` has no MX records — it can send and
    cannot receive — so a version of this that only emailed would have Resend
    accept the send, report success, and bounce where nobody looks. The request
    therefore succeeds on the write, and a failed notification is recorded on
    the row rather than returned as a rejection: the message is already safe.
    """
    desk = TOPIC_DESKS.get(payload.topic)
    if desk is None:
        # An unknown topic is a client bug or a probe, not a routing decision to
        # improvise. Refusing beats quietly sending it to the default desk.
        raise HTTPException(status_code=422, detail="Unknown contact topic.")
    to_address, desk_label = desk
    # A single real mailbox overrides the per-desk addresses. The desk is still
    # resolved server-side and still named in the subject, so filtering and
    # routing survive; only the delivery point changes.
    if settings.CONTACT_DELIVERY_EMAIL:
        to_address = settings.CONTACT_DELIVERY_EMAIL

    # Honeypot: accept and discard, with the same shape as a real reply. A bot
    # told it failed simply retries without the field.
    if payload.website:
        logger.info("contact: honeypot triggered, discarding (topic=%s)", payload.topic)
        return ContactResponse(ok=True, desk=desk_label, reference="ALF-000000")

    reference = f"ALF-{secrets.token_hex(3).upper()}"
    row = ContactSubmission(
        reference=reference,
        topic=payload.topic,
        name=payload.name,
        email=str(payload.email),
        organization=payload.organization,
        phone=payload.phone,
        message=payload.message,
        status="new",
    )
    db.add(row)
    try:
        await db.commit()
    except Exception:  # noqa: BLE001
        await db.rollback()
        logger.exception("contact: could not record submission (topic=%s)", payload.topic)
        raise HTTPException(
            status_code=503,
            detail="We could not record your message just now. Please try again shortly.",
        )

    # Notification. Best-effort by design — see the docstring.
    try:
        sent = await send_email(
            to=to_address,
            subject=f"[{desk_label}] {reference} — {payload.name}",
            html_body=_render(payload, desk_label, reference),
        )
        row.notified_at = datetime.now(timezone.utc) if sent else None
        row.notify_error = None if sent else "send_email returned False"
        if not sent:
            logger.error(
                "contact: %s recorded but NOT notified (desk=%s). alafia.app has "
                "no MX records; check that this desk can receive mail.",
                reference, to_address)
    except Exception as exc:  # noqa: BLE001
        row.notify_error = f"{type(exc).__name__}: {exc}"[:300]
        logger.exception("contact: %s recorded, notification raised", reference)
    finally:
        try:
            await db.commit()
        except Exception:  # noqa: BLE001
            await db.rollback()

    # Acknowledge to the sender, where the topic asks for it. Best-effort in the
    # strongest sense: the request has already succeeded on the write, the desk
    # has already been told, and a bounced confirmation must never cost us the
    # submission. It is logged, not raised, and not recorded as `notify_error` —
    # that column is about whether the DESK was told, and conflating the two
    # would make a delivered request look unrecorded.
    if payload.topic in CONFIRM_TO_SENDER:
        try:
            confirmed = await send_email(
                to=str(payload.email),
                subject=f"We have your request — {reference}",
                html_body=_render_confirmation(payload, desk_label, reference),
            )
            if not confirmed:
                logger.warning("contact: %s confirmation to sender not sent", reference)
        except Exception:  # noqa: BLE001
            logger.exception("contact: %s confirmation to sender raised", reference)

    logger.info("contact: %s recorded for %s (topic=%s, notified=%s)",
                reference, to_address, payload.topic, bool(row.notified_at))
    return ContactResponse(ok=True, desk=desk_label, reference=reference)


@router.get("/contact/topics")
async def contact_topics() -> dict:
    """The desks the form may target.

    Served rather than hardcoded in the client so the three clients cannot
    drift from the routing table, and so a desk can be added or retired without
    shipping an app release — the same reason provider strategy lives in the
    backend (§3).
    """
    return {
        "topics": [
            {"key": key, "label": label}
            for key, (_addr, label) in TOPIC_DESKS.items()
        ]
    }
