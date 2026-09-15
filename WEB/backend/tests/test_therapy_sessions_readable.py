"""A stored session is always readable, whatever it holds.

The weight plausibility check lived on the schema the RESPONSE inherits, so one
historical session with pre/post weights 8.1 kg apart turned
GET /chronic/therapy-sessions into a 500 for that patient's entire history — and
the iOS hemodialysis screen, which asks for 500 sessions, would not open. Six
sessions on one record in the dev copy of production failed it. The check still
guards what is ENTERED; it must never refuse to read the record.
"""

from datetime import datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.chronic_conditions import TherapySession, TherapyStatus, TherapyType
from app.models.user import User

EMAIL = "hd.history@example.com"


async def _token(client: AsyncClient) -> str:
    await client.post(
        "/api/v1/auth/register",
        json={"email": EMAIL, "password": "SecureP@ss123",
              "full_name": "History Tester", "date_of_birth": "1970-01-01"},
    )
    r = await client.post("/api/v1/auth/login", data={"username": EMAIL, "password": "SecureP@ss123"})
    return r.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_a_stored_session_that_fails_the_intake_check_is_still_listed(client: AsyncClient, db):
    token = await _token(client)
    user = (await db.execute(select(User).where(User.email == EMAIL))).scalar_one()
    now = datetime.utcnow()
    db.add(TherapySession(
        user_id=user.id, therapy_type=TherapyType.HEMODIALYSIS, status=TherapyStatus.COMPLETED,
        scheduled_date=datetime(2019, 3, 4, 7, 0),
        pre_dialysis_weight_kg=66.2, post_dialysis_weight_kg=58.1,   # 8.1 kg apart
        created_at=now, updated_at=now,
    ))
    await db.commit()

    # The exact request the iOS HD screen makes.
    r = await client.get("/api/v1/chronic/therapy-sessions",
                         params={"therapy_type": "HEMODIALYSIS", "limit": 500}, headers=_auth(token))

    assert r.status_code == 200, r.text[:300]
    (session,) = r.json()
    # Shown as recorded — questioning it is the reader's call, not a reason to hide it.
    assert (session["pre_dialysis_weight_kg"], session["post_dialysis_weight_kg"]) == (66.2, 58.1)


@pytest.mark.asyncio
async def test_the_same_weights_are_still_refused_when_entered(client: AsyncClient):
    token = await _token(client)
    r = await client.post("/api/v1/chronic/therapy-sessions", headers=_auth(token), json={
        "therapy_type": "hemodialysis", "scheduled_date": "2026-09-15T07:00:00",
        "status": "completed", "pre_dialysis_weight_kg": 66.2, "post_dialysis_weight_kg": 58.1,
    })
    assert r.status_code == 422, r.text[:300]
    assert "one of them is wrong" in r.text
