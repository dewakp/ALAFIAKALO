"""Signing in with a phone number.

The login form has had a Phone tab since it shipped, and the backend only ever
compared `users.email`. So a correct number with a correct password was answered
"Incorrect email or password" — a real account refused, with a message naming a
field the person never filled in. Reported from production 2026-09-24 for
9712606446.

Numbers are stored in one shape and typed in another, so the lookup compares
candidate stored FORMS (§3e). A `regexp_replace` in the WHERE clause would be
Postgres-only and unindexable.

The non-enumeration rule still holds: an unknown identifier and a wrong password
must be indistinguishable to the caller.
"""

import pytest
from sqlalchemy import text

from app.core.security import hash_password
from app.models.user import User
from app.services import auth_alerts

URL = "/api/v1/auth/login"
PASSWORD = "the-right-password"
STORED_E164 = "+19712606446"


@pytest.fixture(autouse=True)
def quiet_alerts(monkeypatch):
    """A failed login alerts the operator; that send must not leave the suite."""
    async def _noop(**_kw):
        return True

    monkeypatch.setattr(auth_alerts, "send_email", _noop)
    auth_alerts._recent.clear()


async def _seed(db, *, email: str, phone: str | None) -> User:
    user = User(
        email=email,
        phone_number=phone,
        hashed_password=hash_password(PASSWORD),
        full_name="Phone Tester",
    )
    db.add(user)
    await db.flush()
    await db.commit()
    return user


async def _login(client, identifier: str, password: str = PASSWORD):
    return await client.post(URL, data={"username": identifier, "password": password})


# ── The number resolves however it was typed ────────────────────────────

@pytest.mark.parametrize("typed", [
    "9712606446",        # what the production screenshot shows
    "+19712606446",      # exactly as stored
    "19712606446",
    "(971) 260-6446",
    " 971-260-6446 ",
])
@pytest.mark.asyncio
async def test_a_stored_number_is_found_however_it_is_typed(client, db, typed):
    await _seed(db, email="phone.user@example.com", phone=STORED_E164)

    res = await _login(client, typed)

    assert res.status_code == 200, res.text
    assert res.json()["access_token"]


@pytest.mark.asyncio
async def test_email_login_still_works(client, db):
    """The regression that matters most: phone support must not cost email."""
    await _seed(db, email="phone.user@example.com", phone=STORED_E164)

    res = await _login(client, "phone.user@example.com")

    assert res.status_code == 200, res.text


@pytest.mark.asyncio
async def test_an_account_with_no_phone_is_unaffected(client, db):
    await _seed(db, email="nophone@example.com", phone=None)

    assert (await _login(client, "nophone@example.com")).status_code == 200
    assert (await _login(client, "9712606446")).status_code == 401


# ── Refusals stay indistinguishable ─────────────────────────────────────

@pytest.mark.asyncio
async def test_a_wrong_password_on_a_real_number_is_refused(client, db):
    await _seed(db, email="phone.user@example.com", phone=STORED_E164)

    res = await _login(client, "9712606446", password="wrong")

    assert res.status_code == 401


@pytest.mark.asyncio
async def test_the_caller_cannot_tell_an_unknown_number_from_a_wrong_password(client, db):
    await _seed(db, email="phone.user@example.com", phone=STORED_E164)

    wrong_pw = await _login(client, "9712606446", password="wrong")
    auth_alerts._recent.clear()
    unknown = await _login(client, "5550001111", password="wrong")

    assert wrong_pw.status_code == unknown.status_code == 401
    assert wrong_pw.json()["detail"] == unknown.json()["detail"]


@pytest.mark.asyncio
async def test_the_refusal_does_not_name_a_field_that_was_not_filled_in(client, db):
    """It said "Incorrect email or password" on the Phone tab."""
    await _seed(db, email="phone.user@example.com", phone=STORED_E164)

    detail = (await _login(client, "9712606446", password="wrong")).json()["detail"]

    assert "email" not in detail.lower()


# ── Shapes that must not reach the phone branch at all ──────────────────

@pytest.mark.asyncio
async def test_a_short_string_is_not_treated_as_a_number(client, db):
    """Below 7 digits it is a typo or a name fragment, not a phone number."""
    await _seed(db, email="phone.user@example.com", phone=STORED_E164)

    assert (await _login(client, "12345")).status_code == 401


@pytest.mark.asyncio
async def test_an_empty_identifier_is_refused_not_matched(client, db):
    await _seed(db, email="phone.user@example.com", phone=None)

    assert (await _login(client, "   ")).status_code == 401


@pytest.mark.asyncio
async def test_a_number_identifies_at_most_one_account(db):
    """The lookup takes the first match, which is only sound because the
    database refuses two accounts with the same number.

    Written after assuming the opposite: the first version of this file seeded
    two accounts on one number and the database refused the insert
    (`duplicate key value violates unique constraint "ix_users_phone_number"`).
    The invariant the login path depends on is asserted here rather than
    assumed.
    """
    indexdef = (await db.execute(text(
        "SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_users_phone_number'"
    ))).scalar_one_or_none()

    assert indexdef is not None, "ix_users_phone_number is gone — the lookup is now ambiguous"
    assert "UNIQUE" in indexdef.upper(), indexdef
