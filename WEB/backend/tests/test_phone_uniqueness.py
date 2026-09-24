"""A phone number identifies ONE account — the way an email address does.

`users.phone_number` has carried a UNIQUE index all along, but the index
compares the literal string, so `9712606446` and `+19712606446` are two
different values and the same person could hold two accounts without it ever
firing. Production stores all three of its numbers as bare digits.

Email has had the full treatment since it shipped: normalised on write
(`email.strip().lower()`), a `email_taken()` pre-check, and a race-safe
`IntegrityError` fallback. Phone had none of the three — so a duplicate number
either slipped past the constraint in a different format, or hit it and 500'd
on the live signup path.

These pin all four halves: one canonical form, the pre-check, the race, and a
refusal that names the right field.
"""

from datetime import datetime, timezone

import pytest

from app.core.phone import to_e164
from app.core.security import hash_password
from app.models.user import User
from app.services import auth_alerts
from app.services import signup_service as svc

START = "/api/v1/auth/signup/start"


@pytest.fixture(autouse=True)
def quiet_alerts(monkeypatch):
    async def _noop(**_kw):
        return True

    monkeypatch.setattr(auth_alerts, "send_email", _noop)
    auth_alerts._recent.clear()


def _details(email="new.person@example.com", phone=None, country="US"):
    body = {
        "email": email,
        "password": "a-long-enough-password",
        "first_name": "Ada",
        "last_name": "Demo",
        "date_of_birth": "1980-01-01",
        "country": country,
    }
    if phone is not None:
        body["phone"] = phone
    return body


async def _seed(db, *, email, phone) -> User:
    user = User(email=email, phone_number=phone,
                hashed_password=hash_password("x" * 20), full_name="Seeded")
    db.add(user)
    await db.flush()
    await db.commit()
    return user


# ── One canonical form ──────────────────────────────────────────────────

@pytest.mark.parametrize("typed,region,expected", [
    ("9712606446",      "US", "+19712606446"),   # bare national
    ("(971) 260-6446",  "US", "+19712606446"),   # punctuation
    ("+1 971 260 6446", None, "+19712606446"),   # already E.164, region ignored
    ("+2348012345678",  "US", "+2348012345678"), # a + wins over the region
])
def test_one_number_has_one_stored_form(typed, region, expected):
    """Every way a person types their number must land on the same string, or
    the UNIQUE index is comparing formats rather than people."""
    assert to_e164(typed, region) == expected


@pytest.mark.parametrize("bad", ["", "   ", "12345", "not a phone"])
def test_what_is_not_a_number_is_refused_not_guessed(bad):
    assert to_e164(bad, "US") is None


def test_a_nine_digit_us_number_is_refused_rather_than_prefixed():
    """Production holds a 9-digit value on a US account. Prefixing +1 would
    fabricate a DIFFERENT person's number in a clinical record (§3am: refuse
    rather than assume)."""
    assert to_e164("678901234", "US") is None


def test_a_bare_number_with_no_region_is_refused():
    """Without a country there is no honest way to pick a calling code."""
    assert to_e164("9712606446", None) is None


# ── The pre-check ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_phone_taken_matches_the_canonical_form(client, db):
    await _seed(db, email="holder@example.com", phone="+19712606446")

    assert await svc.phone_taken(db, "+19712606446") is True
    assert await svc.phone_taken(db, "+19999999999") is False


@pytest.mark.asyncio
async def test_signup_refuses_a_number_already_registered(client, db):
    await _seed(db, email="holder@example.com", phone="+19712606446")

    res = await client.post(START, json=_details(phone="(971) 260-6446"))

    assert res.status_code == 409, res.text
    detail = res.json()["detail"].lower()
    assert "phone" in detail and "already registered" in detail


@pytest.mark.asyncio
async def test_the_refusal_names_the_phone_not_the_email(client, db):
    """The failure this replaces: every IntegrityError answered "Email or
    username already registered", naming a field the person got right."""
    await _seed(db, email="holder@example.com", phone="+19712606446")

    detail = (await client.post(START, json=_details(phone="9712606446"))).json()["detail"]

    assert "email" not in detail.lower()


@pytest.mark.asyncio
async def test_an_unparseable_number_is_refused_with_the_fix(client, db):
    res = await client.post(START, json=_details(phone="12345"))

    assert res.status_code == 422, res.text
    # A guard that cannot explain itself gets blamed for what it did not do.
    assert "country code" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_a_valid_number_is_stored_canonically(client, db):
    """Typed one way, stored the one way — otherwise the next signup's
    pre-check compares different strings and reports the number free."""
    res = await client.post(START, json=_details(phone="(971) 260-6446"))
    assert res.status_code in (200, 202), res.text

    pending = await svc.get(db, "new.person@example.com")
    assert pending is not None
    assert pending.phone == "+19712606446"


@pytest.mark.asyncio
async def test_signup_without_a_phone_is_unaffected(client, db):
    """Phone is optional; the new gate must not close the ordinary path."""
    res = await client.post(START, json=_details())

    assert res.status_code in (200, 202), res.text


# ── The race the pre-check cannot cover ─────────────────────────────────

@pytest.mark.asyncio
async def test_a_number_claimed_after_signup_started_is_refused_not_500(client, db):
    """The pre-check is not a lock. Until now `materialise()` had no handler on
    its flush at all, so the loser of this race met a 500 on the LIVE path."""
    res = await client.post(START, json=_details(phone="9712606446"))
    assert res.status_code in (200, 202), res.text

    # Somebody else takes the number while the signup sits unfinished.
    await _seed(db, email="faster@example.com", phone="+19712606446")

    pending = await svc.get(db, "new.person@example.com")
    # `email_verified` is a read-only property over this column, not a field.
    pending.email_verified_at = datetime.now(timezone.utc)
    await db.commit()

    with pytest.raises(svc.PhoneAlreadyRegistered):
        await svc.materialise(db, pending, require_paid=False)

    # materialise() rolled back its own failed flush, but this session is the
    # TEST's, and its teardown commits — which would retry the insert that just
    # lost the race. In the app that is `get_db`'s job: it rolls back on any
    # exception, so the endpoint never re-flushes.
    await db.rollback()


@pytest.mark.asyncio
async def test_a_gate_refusal_is_still_None_not_an_exception(client, db):
    """PhoneAlreadyRegistered must stay distinct from "a gate is unmet", or the
    endpoints answer "that number is taken" to an unverified signup."""
    res = await client.post(START, json=_details(email="ungated@example.com"))
    assert res.status_code in (200, 202), res.text

    pending = await svc.get(db, "ungated@example.com")
    # Email never verified — a gate, not a conflict.
    assert await svc.materialise(db, pending, require_paid=False) is None
