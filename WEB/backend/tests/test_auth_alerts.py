"""Auth failures the operator has to hear about — and the alert that outlives them.

Three behaviours meet here, and the second is the subtle one.

**The refusal.** `/auth/signup/start` used to answer a taken address with the
success message verbatim, so the endpoint could not enumerate accounts (§3e).
The cost landed on real people: someone who had already signed up was told "a
verification link has been sent" for mail that by definition was never sent,
and had no way to learn that the thing to do was sign in. The operator asked
for that reversed. The address is now confirmed as registered, and what limits
the damage is RATE_LIMIT_AUTH (5/minute) — the same reasoning §3e applies to
recipient search, where a complete identifier resolves and a bulk sweep cannot.

**The alert.** The operator is told, and the notification must survive the
HTTPException that follows it. `get_db` rolls back on ANY exception,
HTTPException included, so the first version of this — writing through the
request's session — added the row, flushed it, and threw it away every single
time: a silent no-op reporting on silent failures. The alert takes its own
session for exactly that reason, and `test_the_alert_survives_the_refusal`
fails if anyone moves it back.
"""

import pytest
from sqlalchemy import select

from conftest import TestSession

from app.core.security import hash_password
from app.models.notifications import Notification
from app.models.user import User
from app.services import auth_alerts

ADMIN_EMAIL = "dew@6igma.com"
TAKEN = "already.a.member@example.com"

# `api_router` mounts under /api/v1, so the signup router's own "/auth/signup"
# prefix sits beneath it. Posting to the bare path answers a clean 404 — which
# a test asserting "not 409" passes without ever reaching the endpoint.
URL = "/api/v1/auth/signup/start"


def _details(email: str) -> dict:
    return {
        "email": email,
        "password": "a-long-enough-password",
        "first_name": "Ada",
        "last_name": "Demo",
        "date_of_birth": "1980-01-01",
        "country": "US",
    }


@pytest.fixture
def quiet_mail(monkeypatch):
    """Capture the operator's email instead of sending it."""
    sent = []

    async def _fake_send(to, subject, html_body):
        sent.append({"to": to, "subject": subject, "html": html_body})
        return True

    monkeypatch.setattr(auth_alerts, "send_email", _fake_send)
    # The in-process dedupe window is 15 minutes and this module raises several
    # identical failures; without clearing it, every test after the first would
    # assert on an alert that was correctly suppressed.
    auth_alerts._recent.clear()
    return sent


@pytest.fixture(autouse=True)
def alert_session(monkeypatch):
    """Point the alert's OWN session factory at the test engine.

    `auth_alerts` opens its own session deliberately — that separation is the
    property under test. But inside the test container DATABASE_URL reads
    `postgresql+asyncpg://…@localhost:5435/alafia`, and `localhost` there is the
    container itself, not the compose `db` service: unreachable. The write would
    be swallowed by the module's own try/except and the assertion below would
    fail for an environment reason rather than a real one — §0, blaming code for
    an artifact of the environment.

    Swapping the factory keeps the session SEPARATE from the request's, which is
    exactly what makes the rollback assertion meaningful.
    """
    monkeypatch.setattr(auth_alerts, "async_session", TestSession)


async def _seed(db, email: str) -> User:
    user = User(email=email, hashed_password="x", full_name="Seeded")
    db.add(user)
    await db.flush()
    await db.commit()
    return user


@pytest.mark.asyncio
async def test_a_taken_address_is_refused_and_told_why(client, db, quiet_mail):
    await _seed(db, TAKEN)

    res = await client.post(URL, json=_details(TAKEN))

    assert res.status_code == 409
    detail = res.json()["detail"]
    # It must name the way forward. A refusal with no route forward is what
    # sent this person back to the same form (§3aj).
    assert "already exists" in detail.lower()
    assert "sign" in detail.lower()


@pytest.mark.asyncio
async def test_a_fresh_address_is_not_refused(client, db, quiet_mail):
    """The control. A 409 for everyone would also 'pass' the test above."""
    res = await client.post(URL, json=_details("brand.new@example.com"))
    assert res.status_code != 409


@pytest.mark.asyncio
async def test_the_operator_is_emailed(client, db, quiet_mail):
    await _seed(db, TAKEN)
    await client.post(URL, json=_details(TAKEN))

    assert len(quiet_mail) == 1
    assert TAKEN in quiet_mail[0]["html"]
    assert "email_already_registered" in quiet_mail[0]["subject"]


@pytest.mark.asyncio
async def test_repeat_attempts_do_not_flood_the_operator(client, db, quiet_mail):
    """A credential-stuffing run is thousands of failures a minute. An operator
    mailed thousands of times filters the sender, losing the one that mattered."""
    await _seed(db, TAKEN)
    for _ in range(3):
        await client.post(URL, json=_details(TAKEN))

    assert len(quiet_mail) == 1


@pytest.mark.asyncio
async def test_the_alert_survives_the_refusal(client, db, quiet_mail):
    """The regression guard for the rollback bug.

    The notification is written while the request is on its way to raising a
    409. Through the request's session that row is rolled back and the operator
    is told nothing; through its own session it stands.
    """
    admin = await _seed(db, ADMIN_EMAIL)
    await _seed(db, TAKEN)

    res = await client.post(URL, json=_details(TAKEN))
    assert res.status_code == 409

    rows = (await db.execute(
        select(Notification).where(Notification.user_id == admin.id)
    )).scalars().all()
    assert len(rows) == 1
    assert "email_already_registered" in rows[0].message


# ── Login failures ──────────────────────────────────────────────────────
#
# The operator asked to be told about login errors too. The CALLER's answer must
# not change: "Incorrect email or password" for both an unknown address and a
# wrong password. Otherwise the 401 becomes an account-existence oracle — which
# the signup change above deliberately accepts for ONE endpoint, and there is no
# reason to hand it over on a second. Only the operator learns which it was.

LOGIN_URL = "/api/v1/auth/login"
KNOWN = "member@example.com"
PASSWORD = "the-right-password"


async def _seed_with_password(db, email: str) -> User:
    # A real hash. Seeding hashed_password="x" makes verify_password raise on an
    # unrecognised hash, so the endpoint 500s and the test "passes" for a reason
    # that has nothing to do with the password being wrong.
    user = User(email=email, hashed_password=hash_password(PASSWORD), full_name="Seeded")
    db.add(user)
    await db.flush()
    await db.commit()
    return user


@pytest.mark.asyncio
async def test_a_wrong_password_alerts_the_operator(client, db, quiet_mail):
    await _seed_with_password(db, KNOWN)

    res = await client.post(LOGIN_URL, data={"username": KNOWN, "password": "wrong"})

    assert res.status_code == 401
    assert len(quiet_mail) == 1
    assert "bad_password" in quiet_mail[0]["subject"]


@pytest.mark.asyncio
async def test_an_unknown_address_alerts_the_operator(client, db, quiet_mail):
    res = await client.post(LOGIN_URL,
                            data={"username": "nobody@example.com", "password": "x"})

    assert res.status_code == 401
    assert len(quiet_mail) == 1
    assert "no_such_account" in quiet_mail[0]["subject"]


@pytest.mark.asyncio
async def test_the_caller_cannot_tell_the_two_failures_apart(client, db, quiet_mail):
    """The operator is told which; the person at the keyboard is not."""
    await _seed_with_password(db, KNOWN)

    wrong_pw = await client.post(LOGIN_URL, data={"username": KNOWN, "password": "wrong"})
    auth_alerts._recent.clear()
    unknown = await client.post(LOGIN_URL,
                                data={"username": "nobody@example.com", "password": "x"})

    assert wrong_pw.status_code == unknown.status_code == 401
    assert wrong_pw.json()["detail"] == unknown.json()["detail"]
    # …and the operator got both, under different reasons.
    assert len(quiet_mail) == 2
    assert {"bad_password" in m["subject"] for m in quiet_mail} == {True, False}


@pytest.mark.asyncio
async def test_a_mail_outage_does_not_change_the_answer(client, db, monkeypatch):
    """An alert that breaks the request it is reporting on is worse than the
    failure it describes."""
    async def _boom(**_kw):
        raise RuntimeError("mail provider down")

    monkeypatch.setattr(auth_alerts, "send_email", _boom)
    auth_alerts._recent.clear()
    await _seed(db, TAKEN)

    res = await client.post(URL, json=_details(TAKEN))
    assert res.status_code == 409
