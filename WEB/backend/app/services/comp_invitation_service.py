# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""The complimentary-membership lifecycle, driven by what the person DOES.

Operator, 2026-10-20: *"move sending to backend. All this must be automated not
sender triggered."* and *"system knows what actions invitees/subscribers perform
and responds accordingly."*

Before this, every step was a human running a script:

    send_comp_invitation.py     sent a letter and wrote NO row
    activate_comp_signup.py     created the account — if someone remembered
    grant_comp.sh               granted the membership — if someone remembered
    send_membership_ready.py    told them — if someone remembered

The letter promises *"You will then be offered a payment step. Close the tab
there… We will activate your membership and email you the moment it is live."*
That sentence was true only as long as an operator was watching. On 2026-09-15
it went out with no tooling behind it at all; on 2026-10-20 it went out with
tooling nobody was obliged to run.

**The stages are observed, not stored.** `pending_registrations` already knows
who started and who verified, `users` knows who exists and who has signed in,
`subscriptions` knows what they hold. This module reads those and acts; it
stores only the offer itself and the moments we responded (§3ai — two
computations of one fact must not be able to disagree).

What it will NOT do:

* **Never activate without a verified email.** `materialise(require_paid=False)`
  waives the PAYMENT gate and never the email one (§3au), and this relies on
  exactly that: a complimentary offer is a reason not to charge someone, never
  a reason to skip proving they own the address.
* **Never let a letter failure cost an activation.** §3ah's rule, learned when
  a non-2xx over an email problem sent Stripe into a multi-day retry cascade.
  The membership is granted first and the mail is attempted after.
* **Never remind someone who has already acted.** The stage is read at SEND
  time, not when the pass was scheduled, or a person who signs up on day 6 is
  told on day 7 that they have not signed up — §3aa's error-as-empty-state,
  aimed at a human being.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.comp_invitation import CompInvitation
from app.models.user import User

logger = logging.getLogger(__name__)

#: How long after the last nudge before another one is allowed. A letter that
#: arrives daily is a letter people filter, and the whole offer lasts days.
MIN_REMINDER_GAP = timedelta(days=2)

#: Nudges are capped. Three unanswered letters is an answer.
MAX_REMINDERS = 2


# ── stages ────────────────────────────────────────────────────────────────

#: The journey, in order. Each is a fact read from the table that owns it —
#: only `invited` and `active` have anything stored here.
STAGES = (
    "invited",            # we offered; nothing has happened
    "started_signup",     # a pending_registrations row exists
    "verified",           # they confirmed the address — OUR move next
    "active",             # account exists and holds the membership
    "signed_in",          # they have actually been in
    "expired",            # the deadline passed with no account
    "revoked",            # withdrawn by an operator
)


@dataclass
class Progress:
    """Where one invitee is, and how long they have been there."""

    invitation: CompInvitation
    stage: str
    since: datetime | None
    user_id: int | None
    #: True when the next move is OURS, not theirs. This is the row an operator
    #: must see: the person did everything the letter asked and is waiting.
    waiting_on_us: bool


async def _pending_for(db: AsyncSession, email: str):
    """The pending registration for this address, if any."""
    from app.models.pending_registration import PendingRegistration

    return (await db.execute(
        select(PendingRegistration).where(
            func.lower(PendingRegistration.email) == email.strip().lower())
    )).scalar_one_or_none()


async def _user_for(db: AsyncSession, email: str) -> User | None:
    return (await db.execute(
        select(User).where(func.lower(User.email) == email.strip().lower())
    )).scalar_one_or_none()


async def stage_of(db: AsyncSession, inv: CompInvitation) -> Progress:
    """Read where this invitee actually is, from the tables that own each fact.

    Deliberately not a stored column. A stage written down at the moment we
    last looked goes stale the instant the person acts, and then an operator
    screen and a reminder job disagree about the same human being.
    """
    if inv.revoked_at:
        return Progress(inv, "revoked", inv.revoked_at, inv.user_id, False)

    user = await _user_for(db, inv.email)
    if user is not None:
        if user.last_login:
            return Progress(inv, "signed_in", user.last_login, user.id, False)
        return Progress(inv, "active", inv.activated_at or user.created_at,
                        user.id, False)

    pending = await _pending_for(db, inv.email)
    if pending is not None:
        verified_at = getattr(pending, "email_verified_at", None)
        if verified_at:
            # They did everything the letter asked. Whatever happens next is
            # ours to do, and until it happens they are holding nothing.
            return Progress(inv, "verified", verified_at, None, True)
        return Progress(inv, "started_signup", pending.created_at, None, False)

    today = datetime.now(timezone.utc).date()
    if inv.deadline < today:
        return Progress(inv, "expired", inv.sent_at, None, False)
    return Progress(inv, "invited", inv.sent_at, None, False)


async def progress_report(db: AsyncSession) -> list[Progress]:
    """Every invitation with its current stage, newest first."""
    rows = (await db.execute(
        select(CompInvitation).order_by(CompInvitation.created_at.desc())
    )).scalars().all()
    return [await stage_of(db, inv) for inv in rows]


# ── creating and sending ──────────────────────────────────────────────────

async def find_live(db: AsyncSession, email: str) -> CompInvitation | None:
    """A live offer for this address, matched case-insensitively.

    The letter says to use the address EXACTLY; this is the half of that
    promise we have to keep, since the reader will type it however they type it.
    """
    if not email:
        return None
    return (await db.execute(
        select(CompInvitation).where(
            func.lower(CompInvitation.email) == email.strip().lower(),
            CompInvitation.revoked_at.is_(None),
            CompInvitation.activated_at.is_(None),
        )
    )).scalar_one_or_none()


async def create_and_send(
    db: AsyncSession,
    *,
    email: str,
    display_name: str | None,
    months: int,
    deadline: date,
    clinical_role: str | None = None,
    practice: str | None = None,
    created_by_user_id: int | None = None,
) -> CompInvitation:
    """Record the offer, then send it. In that order, deliberately.

    A letter sent before the row exists is the state this module was written to
    end: the 2026-10-20 invitation to `bass797@aol.com` lived only in Resend's
    logs, so nothing could remind him and no screen could show him.

    A send failure does NOT discard the row. The offer was made as soon as it
    was recorded, and a row carrying `send_error` is the only thing that can
    tell an operator a letter never left — an absent row says nothing at all.
    """
    email = email.strip()
    inv = CompInvitation(
        email=email,
        display_name=(display_name or None),
        months=months,
        deadline=deadline,
        clinical_role=(clinical_role or None),
        practice=(practice or None),
        created_by_user_id=created_by_user_id,
    )
    db.add(inv)
    await db.flush()

    sent = False
    try:
        from app.services.email import send_complimentary_invitation_email

        sent = await send_complimentary_invitation_email(
            email,
            display_name=inv.display_name,
            months=inv.months,
            signup_deadline=inv.deadline.strftime("%-d %B %Y"),
            clinical_role=inv.clinical_role,
            practice=inv.practice,
        )
        if not sent:
            inv.send_error = "the mail provider reported no send"
    except Exception as exc:  # noqa: BLE001 — a mail outage must not lose the offer
        logger.exception("Invitation to %s could not be sent", email)
        inv.send_error = f"{type(exc).__name__}: {exc}"[:500]

    if sent:
        inv.sent_at = datetime.now(timezone.utc)
        inv.send_error = None
    await db.flush()
    return inv


# ── responding to what they do ────────────────────────────────────────────

async def note_signup_started(db: AsyncSession, email: str) -> None:
    """They began. Stamp it so a reminder knows not to treat them as silent."""
    inv = await find_live(db, email)
    if inv is not None and inv.claimed_at is None:
        inv.claimed_at = datetime.now(timezone.utc)
        await db.flush()
        logger.info("Comp invitation %s claimed by signup start", inv.id)


async def activate_if_invited(db: AsyncSession, pending) -> User | None:
    """The whole promise, kept automatically: verified → account → membership.

    Called the moment an address is verified. Returns the created user, or None
    when there is no live invitation for it — which is the ordinary case and
    must never be treated as an error.
    """
    inv = await find_live(db, pending.email)
    if inv is None:
        return None
    if not getattr(pending, "email_verified", False):
        # Belt and braces: `materialise` refuses this too. A complimentary
        # offer is a reason not to charge, never a reason to skip proving the
        # address belongs to them.
        logger.warning("Refusing to activate %s — email not verified", pending.email)
        return None

    from app.services import signup_service

    user = await signup_service.materialise(db, pending, require_paid=False)
    if user is None:
        logger.warning("materialise declined for invited address %s", pending.email)
        return None

    await grant_membership(db, user, inv)
    inv.activated_at = datetime.now(timezone.utc)
    inv.user_id = user.id
    await db.flush()

    # The letter said we would write the moment it was live. AFTER the grant,
    # and never allowed to undo it (§3ah).
    try:
        from app.services.email import send_membership_active_email

        await send_membership_active_email(
            user.email,
            display_name=inv.display_name or user.full_name,
            months=inv.months,
            complimentary=True,
            clinical_role=inv.clinical_role,
        )
    except Exception:  # noqa: BLE001
        logger.exception("Membership for %s is ACTIVE but the welcome failed", user.email)

    logger.info("Comp invitation %s activated for user %s", inv.id, user.id)
    return user


async def grant_membership(db: AsyncSession, user: User, inv: CompInvitation) -> None:
    """Write the complimentary subscription, its audit row, and any role.

    Mirrors `scripts/db/grant_comp_and_role.sql` exactly — `provider='none'`,
    price 0, `cancel_at_period_end=true` so nothing renews it — because two
    implementations of one grant WILL drift, and the one that drifts is the one
    nobody reads. §5b records what a grant with no audit row costs: a comped
    account whose membership had nothing on the record saying where it came
    from.
    """
    months = max(1, int(inv.months or 12))
    await db.execute(text("""
        INSERT INTO subscriptions (
            user_id, status, provider, plan, price_usd,
            current_period_start, current_period_end,
            cancel_at_period_end, created_at, updated_at)
        VALUES (:uid, 'active', 'none', 'plus_annual', 0,
                now(), now() + make_interval(months => :months),
                true, now(), now())
        ON CONFLICT (user_id) DO UPDATE
        SET status = 'active', provider = 'none', plan = 'plus_annual',
            price_usd = 0,
            current_period_start = EXCLUDED.current_period_start,
            current_period_end   = EXCLUDED.current_period_end,
            cancel_at_period_end = true, canceled_at = NULL, updated_at = now()
    """), {"uid": user.id, "months": months})

    await db.execute(text("""
        INSERT INTO subscription_events (user_id, provider, event_id, event_type,
                                         payload, created_at)
        VALUES (:uid, 'none',
                -- `:uid_text` is a SEPARATE parameter on purpose. Binding the
                -- same one as both an integer column and a string concatenation
                -- makes asyncpg refuse the statement outright:
                -- "inconsistent types deduced for parameter $1: text versus
                -- integer". The event id shape still matches
                -- grant_comp_and_role.sql exactly.
                'comp:' || :uid_text || ':' ||
                    to_char(now(), 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
                'complimentary_grant', :payload, now())
        ON CONFLICT (provider, event_id) DO NOTHING
    """), {"uid": user.id, "uid_text": str(user.id),
           "payload": (
               '{"granted_by": "comp_invitation_service.grant_membership", '
               f'"months": {months}, "invitation_id": {inv.id}, '
               f'"role": {"null" if not inv.clinical_role else chr(34) + inv.clinical_role + chr(34)}}}'
           )})

    if inv.clinical_role:
        await db.execute(text("""
            INSERT INTO user_role_assignments (user_id, role, is_primary,
                                               is_active, granted_at)
            VALUES (:uid, :role, false, true, now())
            ON CONFLICT (user_id, role) DO UPDATE
            SET is_active = true, revoked_at = NULL
        """), {"uid": user.id, "role": inv.clinical_role})
    await db.flush()


# ── the scheduled reaction pass ───────────────────────────────────────────

async def run_reaction_pass(db: AsyncSession) -> dict:
    """React to where each invitee now is. Safe to run repeatedly.

    Returns a summary rather than logging only, so the caller can say what it
    did — a job whose effect is invisible is one nobody can tell has stopped.
    """
    summary = {"reminded": 0, "waiting_on_us": 0, "expired": 0, "checked": 0}
    now = datetime.now(timezone.utc)

    for prog in await progress_report(db):
        summary["checked"] += 1
        inv = prog.invitation

        if prog.waiting_on_us:
            # NOT a reminder. They have done everything asked; nudging them
            # would blame them for our delay.
            summary["waiting_on_us"] += 1
            logger.warning(
                "Comp invitation %s (%s) is VERIFIED and not active — "
                "activation is owed to them", inv.id, inv.email)
            continue

        if prog.stage == "expired":
            summary["expired"] += 1
            continue

        if prog.stage not in ("invited", "started_signup"):
            continue
        if inv.sent_at is None:          # never left; a reminder would be a lie
            continue
        if inv.reminders_sent >= MAX_REMINDERS:
            continue
        if inv.last_reminder_at and (now - inv.last_reminder_at) < MIN_REMINDER_GAP:
            continue
        if inv.deadline < now.date():
            continue

        try:
            from app.services.email import send_complimentary_invitation_email

            ok = await send_complimentary_invitation_email(
                inv.email,
                display_name=inv.display_name,
                months=inv.months,
                signup_deadline=inv.deadline.strftime("%-d %B %Y"),
                clinical_role=inv.clinical_role,
                practice=inv.practice,
            )
        except Exception:  # noqa: BLE001
            logger.exception("Reminder to %s failed", inv.email)
            ok = False

        if ok:
            inv.reminders_sent += 1
            inv.last_reminder_at = now
            summary["reminded"] += 1

    await db.flush()
    return summary
