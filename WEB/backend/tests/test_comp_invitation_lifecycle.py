# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""The complimentary membership runs itself: invite, observe, respond.

Operator, 2026-10-20: *"move sending to backend. All this must be automated not
sender triggered."* and *"system knows what actions invitees/subscribers perform
and responds accordingly."*

The letter that went to `bass797@aol.com` that day says:

    "You will then be offered a payment step. Close the tab there — do not
     enter any card details. We will activate your membership and email you
     the moment it is live."

On 2026-09-15 that sentence had NO tooling behind it. On 2026-10-20 it had
tooling nobody was obliged to run. These tests are what make it true: the
account, the membership and the welcome all follow from verification itself.
"""

import datetime
import uuid

import pytest

from app.models.comp_invitation import CompInvitation
from app.models.pending_registration import PendingRegistration
from app.models.user import User
from app.services import comp_invitation_service as svc

pytestmark = pytest.mark.asyncio


#: `materialise` re-asserts the account-holder age rule at the moment of
#: creation — "the check belongs on the same side of the door as the creation".
#: A fixture without a date of birth is refused, correctly, so every pending row
#: here carries one.
#: Stored as TEXT on this table, not a date — asyncpg refuses a date object.
ADULT_DOB = "1960-01-01"


def _future(days: int = 7) -> datetime.date:
    return datetime.date.today() + datetime.timedelta(days=days)


async def _invite(db, email, **kw) -> CompInvitation:
    inv = CompInvitation(
        email=email, display_name=kw.get("display_name", "Dr. Bass"),
        months=kw.get("months", 12), deadline=kw.get("deadline", _future()),
        clinical_role=kw.get("clinical_role"), practice=kw.get("practice"),
        sent_at=kw.get("sent_at", datetime.datetime.now(datetime.timezone.utc)),
    )
    db.add(inv)
    await db.flush()
    return inv


def _addr() -> str:
    return f"inv{uuid.uuid4().hex[:8]}@example.com"


# ── the offer is a record ─────────────────────────────────────────────────

async def test_an_invitation_survives_a_failed_send(db, monkeypatch):
    """A send failure must not discard the offer.

    The row carrying `send_error` is the only thing that can tell an operator a
    letter never left; an absent row says nothing at all (§3aa).
    """
    async def boom(*a, **k):
        raise RuntimeError("provider down")

    monkeypatch.setattr(
        "app.services.email.send_complimentary_invitation_email", boom)

    email = _addr()
    inv = await svc.create_and_send(
        db, email=email, display_name="Dr. Bass", months=12,
        deadline=_future(), clinical_role=None, practice=None)
    assert inv.id is not None
    assert inv.sent_at is None
    assert "provider down" in (inv.send_error or "")


async def test_a_live_invitation_is_found_case_insensitively(db):
    """The letter says to use the address exactly; the reader will not."""
    email = _addr()
    await _invite(db, email)
    assert await svc.find_live(db, email.upper()) is not None
    assert await svc.find_live(db, f"  {email}  ") is not None


# ── stages are READ, never stored ─────────────────────────────────────────

async def test_stage_is_invited_before_anything_happens(db):
    inv = await _invite(db, _addr())
    prog = await svc.stage_of(db, inv)
    assert prog.stage == "invited"
    assert prog.waiting_on_us is False


async def test_stage_follows_the_pending_registration(db):
    email = _addr()
    inv = await _invite(db, email)
    db.add(PendingRegistration(
        email=email, password_hash="x", full_name="Dr. Bass",
        verification_token_hash="t",
        date_of_birth="1960-01-01", country="US",
        expires_at=datetime.datetime.now(datetime.timezone.utc)
        + datetime.timedelta(days=1)))
    await db.flush()
    assert (await svc.stage_of(db, inv)).stage == "started_signup"


async def test_verified_but_not_active_is_WAITING_ON_US(db):
    """The row an operator must see. They did everything the letter asked and
    are holding nothing until we act — so this is never a member nudge."""
    email = _addr()
    inv = await _invite(db, email)
    db.add(PendingRegistration(
        email=email, password_hash="x", full_name="Dr. Bass",
        verification_token_hash="t",
        date_of_birth="1960-01-01", country="US",
        email_verified_at=datetime.datetime.now(datetime.timezone.utc),
        expires_at=datetime.datetime.now(datetime.timezone.utc)
        + datetime.timedelta(days=1)))
    await db.flush()

    prog = await svc.stage_of(db, inv)
    assert prog.stage == "verified"
    assert prog.waiting_on_us is True


async def test_an_expired_offer_reads_as_expired_not_invited(db):
    inv = await _invite(db, _addr(), deadline=datetime.date.today()
                        - datetime.timedelta(days=1))
    assert (await svc.stage_of(db, inv)).stage == "expired"


# ── the reaction pass ─────────────────────────────────────────────────────

async def test_someone_who_already_acted_is_NOT_reminded(db, monkeypatch):
    """§3aa, aimed at a person: a nudge saying "you have not signed up" sent to
    someone who signed up yesterday. The stage is read at SEND time."""
    sent: list[str] = []

    async def record(to, **k):
        sent.append(to)
        return True

    monkeypatch.setattr(
        "app.services.email.send_complimentary_invitation_email", record)

    email = _addr()
    await _invite(db, email)
    db.add(PendingRegistration(
        email=email, password_hash="x", full_name="X",
        verification_token_hash="t",
        date_of_birth="1960-01-01", country="US",
        email_verified_at=datetime.datetime.now(datetime.timezone.utc),
        expires_at=datetime.datetime.now(datetime.timezone.utc)
        + datetime.timedelta(days=1)))
    await db.flush()

    summary = await svc.run_reaction_pass(db)
    assert sent == [], "a verified invitee must never be nudged"
    assert summary["waiting_on_us"] >= 1


async def test_a_letter_that_never_left_is_not_REMINDED(db, monkeypatch):
    """A reminder about an invitation nobody received is a lie told twice."""
    sent: list[str] = []

    async def record(to, **k):
        sent.append(to)
        return True

    monkeypatch.setattr(
        "app.services.email.send_complimentary_invitation_email", record)

    await _invite(db, _addr(), sent_at=None)
    await svc.run_reaction_pass(db)
    assert sent == []


async def test_reminders_are_capped(db, monkeypatch):
    async def record(to, **k):
        return True

    monkeypatch.setattr(
        "app.services.email.send_complimentary_invitation_email", record)

    inv = await _invite(db, _addr())
    inv.reminders_sent = svc.MAX_REMINDERS
    await db.flush()
    summary = await svc.run_reaction_pass(db)
    assert summary["reminded"] == 0


# ── the promise in the letter ─────────────────────────────────────────────

async def test_verification_activates_grants_and_welcomes(db, monkeypatch):
    """THE WHOLE POINT. Verified -> account + membership + welcome, with no
    human in the loop."""
    welcomed: list[dict] = []

    async def welcome(to, **k):
        welcomed.append({"to": to, **k})
        return True

    monkeypatch.setattr("app.services.email.send_membership_active_email", welcome)

    email = _addr()
    inv = await _invite(db, email, months=12, clinical_role="nephrologist")
    pending = PendingRegistration(
        email=email, password_hash="x", full_name="Dr. Bass",
        first_name="Raymond", last_name="Bass",
        verification_token_hash="t",
        date_of_birth="1960-01-01", country="US",
        email_verified_at=datetime.datetime.now(datetime.timezone.utc),
        expires_at=datetime.datetime.now(datetime.timezone.utc)
        + datetime.timedelta(days=1))
    db.add(pending)
    await db.flush()

    user = await svc.activate_if_invited(db, pending)
    assert user is not None, "a verified invitee must be activated"
    await db.refresh(inv)
    assert inv.activated_at is not None
    assert inv.user_id == user.id

    # The membership itself, read back from the row rather than assumed.
    from sqlalchemy import text as _text

    row = (await db.execute(_text(
        "select status, provider, price_usd, cancel_at_period_end "
        "from subscriptions where user_id = :u"), {"u": user.id})).first()
    assert row is not None, "activation must grant a membership"
    assert row[0] == "active" and row[1] == "none"
    assert float(row[2]) == 0.0 and row[3] is True

    # And they were told.
    assert welcomed and welcomed[0]["to"] == email
    assert welcomed[0]["complimentary"] is True


async def test_an_unverified_invitee_is_NEVER_activated(db):
    """A complimentary offer is a reason not to charge someone. It is never a
    reason to skip proving they own the address (§3au)."""
    email = _addr()
    await _invite(db, email)
    pending = PendingRegistration(
        email=email, password_hash="x", full_name="X",
        verification_token_hash="t",
        date_of_birth="1960-01-01", country="US",
        expires_at=datetime.datetime.now(datetime.timezone.utc)
        + datetime.timedelta(days=1))
    db.add(pending)
    await db.flush()

    assert await svc.activate_if_invited(db, pending) is None


async def test_an_uninvited_signup_is_untouched(db):
    """The ordinary case, and it must never read as an error."""
    pending = PendingRegistration(
        email=_addr(), password_hash="x", full_name="X",
        verification_token_hash="t",
        date_of_birth="1960-01-01", country="US",
        email_verified_at=datetime.datetime.now(datetime.timezone.utc),
        expires_at=datetime.datetime.now(datetime.timezone.utc)
        + datetime.timedelta(days=1))
    db.add(pending)
    await db.flush()
    assert await svc.activate_if_invited(db, pending) is None


async def test_a_failed_welcome_does_not_undo_the_membership(db, monkeypatch):
    """§3ah: a mail outage must never cost the thing it was announcing."""
    async def boom(*a, **k):
        raise RuntimeError("mail down")

    monkeypatch.setattr("app.services.email.send_membership_active_email", boom)

    email = _addr()
    inv = await _invite(db, email)
    pending = PendingRegistration(
        email=email, password_hash="x", full_name="X",
        verification_token_hash="t",
        date_of_birth="1960-01-01", country="US",
        email_verified_at=datetime.datetime.now(datetime.timezone.utc),
        expires_at=datetime.datetime.now(datetime.timezone.utc)
        + datetime.timedelta(days=1))
    db.add(pending)
    await db.flush()

    user = await svc.activate_if_invited(db, pending)
    assert user is not None
    await db.refresh(inv)
    assert inv.activated_at is not None, "the grant must stand without the letter"


async def test_signup_start_marks_the_invitation_claimed(db):
    email = _addr()
    inv = await _invite(db, email)
    await svc.note_signup_started(db, email)
    await db.refresh(inv)
    assert inv.claimed_at is not None


# ── a reminder is a NUDGE, not the letter again ──────────────────────────

async def test_a_reminder_is_not_the_invitation_resent(db, monkeypatch):
    """Dr. Bass's row went live on 2026-10-20 with the reaction pass already
    running in production. Left alone it would have mailed him a verbatim copy
    of the same letter two days later, which reads as a system that has lost
    track of itself rather than as a nudge."""
    invites: list[str] = []
    nudges: list[dict] = []

    async def invite(to, **k):
        invites.append(to)
        return True

    async def nudge(to, **k):
        nudges.append({"to": to, **k})
        return True

    monkeypatch.setattr(
        "app.services.email.send_complimentary_invitation_email", invite)
    monkeypatch.setattr(
        "app.services.email.send_comp_invitation_reminder_email", nudge)

    email = _addr()
    await _invite(db, email, deadline=_future(3))
    summary = await svc.run_reaction_pass(db)

    assert summary["reminded"] == 1
    assert invites == [], "the full invitation must not be sent twice"
    assert nudges and nudges[0]["to"] == email
    # The one new fact a reminder carries.
    assert nudges[0]["days_left"] == 3


async def test_a_reminder_never_invents_a_countdown(db, monkeypatch):
    """`days_left` comes from the row's own deadline. A wrong number of days on
    a deadline letter is worse than none: it is the only fact it carries."""
    seen: list[int] = []

    async def nudge(to, **k):
        seen.append(k.get("days_left"))
        return True

    monkeypatch.setattr(
        "app.services.email.send_comp_invitation_reminder_email", nudge)

    await _invite(db, _addr(), deadline=_future(1))
    await svc.run_reaction_pass(db)
    assert seen == [1]
