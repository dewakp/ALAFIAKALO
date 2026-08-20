"""Dialysis balance as it reaches the clients, over HTTP.

The one thing these must not let regress: a treatment changes the day's
*balance*, never the dietary limit. KDOQI's potassium figure already assumes the
patient is on dialysis, so a limit that moved on treatment days would count the
same clearance twice.
"""

from datetime import date, datetime, timedelta

import pytest
from httpx import AsyncClient


async def _token(client: AsyncClient, email: str) -> str:
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "SecureP@ss123",
              "full_name": "Dialysis Tester", "date_of_birth": "1974-03-15"},
    )
    r = await client.post(
        "/api/v1/auth/login",
        data={"username": email, "password": "SecureP@ss123"},
    )
    return r.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _make_renal_patient(client: AsyncClient, token: str):
    """A dialysis patient, so the goals engine emits renal limits."""
    await client.put("/api/v1/users/me", headers=_auth(token), json={
        "height_cm": 177.8, "current_weight_kg": 75.0,
        "gender_at_birth": "male", "activity_level": "sedentary",
    })
    await client.post("/api/v1/chronic/conditions", headers=_auth(token), json={
        "condition_name": "End-Stage Renal Disease on hemodialysis",
        "category": "renal", "severity": "severe", "is_active": True,
    })


async def _add_session(client: AsyncClient, token: str, when: date, status="completed"):
    r = await client.post("/api/v1/chronic/therapy-sessions", headers=_auth(token), json={
        "therapy_type": "hemodialysis",
        "scheduled_date": datetime.combine(when, datetime.min.time()).isoformat(),
        "status": status,
        "duration_minutes": 184,
        "blood_flow_rate": 350,
        "dialysate_volume_liters": 30,
        "dialysate_potassium_meq": 1.0,
        "fluid_removed_ml": 608,
    })
    assert r.status_code in (200, 201), f"session setup failed: {r.status_code} {r.text[:200]}"
    return r


async def _add_lab(client: AsyncClient, token: str, name: str, value: float, when: date):
    r = await client.post("/api/v1/labs/", headers=_auth(token), json={
        "test_date": when.isoformat(), "test_name": name, "value": value, "unit": "mmol/L",
    })
    assert r.status_code in (200, 201), f"lab setup failed: {r.status_code} {r.text[:200]}"
    return r


@pytest.mark.asyncio
class TestDialysisBalanceOverHttp:
    async def test_a_rest_day_reports_no_dialysis(self, client: AsyncClient):
        token = await _token(client, "dia1@example.com")
        await _make_renal_patient(client, token)

        r = await client.get(f"/api/v1/nutrition/goal-progress?date={date.today()}",
                             headers=_auth(token))
        assert r.status_code == 200
        body = r.json()
        assert body.get("dialysis") in (None, {}) or body["dialysis"]["had_dialysis"] is False
        assert all(g.get("dialysis_balance") is None for g in body["goals"])

    async def test_the_potassium_limit_is_unchanged_on_a_treatment_day(self, client: AsyncClient):
        """The headline invariant."""
        token = await _token(client, "dia2@example.com")
        await _make_renal_patient(client, token)
        today = date.today()

        rest = await client.get(f"/api/v1/nutrition/goal-progress?date={today}",
                                headers=_auth(token))
        before = {g["key"]: g["goal"] for g in rest.json()["goals"]}

        await _add_session(client, token, today)
        await _add_lab(client, token, "Potassium", 4.5, today)

        after_r = await client.get(f"/api/v1/nutrition/goal-progress?date={today}",
                                   headers=_auth(token))
        after = {g["key"]: g["goal"] for g in after_r.json()["goals"]}

        assert after == before, "a treatment must not move any dietary limit"

    async def test_the_response_carries_the_days_balance(self, client: AsyncClient):
        token = await _token(client, "dia3@example.com")
        await _make_renal_patient(client, token)
        today = date.today()
        await _add_session(client, token, today)
        await _add_lab(client, token, "Potassium", 4.5, today)

        body = (await client.get(f"/api/v1/nutrition/goal-progress?date={today}",
                                 headers=_auth(token))).json()

        assert body["dialysis"] is not None
        assert body["dialysis"]["had_dialysis"] is True
        assert body["dialysis"]["session_count"] == 1

        potassium = next(g for g in body["goals"] if g["key"] == "potassium_mg")
        balance = potassium["dialysis_balance"]
        assert balance is not None
        for field in ("intake", "delta", "net", "direction", "calibrated"):
            assert field in balance, f"clients decode {field}"

    async def test_a_scheduled_session_is_not_counted(self, client: AsyncClient):
        token = await _token(client, "dia4@example.com")
        await _make_renal_patient(client, token)
        today = date.today()
        await _add_session(client, token, today, status="scheduled")
        await _add_lab(client, token, "Potassium", 4.5, today)

        body = (await client.get(f"/api/v1/nutrition/goal-progress?date={today}",
                                 headers=_auth(token))).json()
        summary = body.get("dialysis")
        assert summary is None or summary["session_count"] == 0

    async def test_a_high_potassium_withholds_the_removal_credit(self, client: AsyncClient):
        token = await _token(client, "dia5@example.com")
        await _make_renal_patient(client, token)
        today = date.today()
        await _add_session(client, token, today)
        await _add_lab(client, token, "Potassium", 6.2, today)   # hyperkalaemic

        body = (await client.get(f"/api/v1/nutrition/goal-progress?date={today}",
                                 headers=_auth(token))).json()
        potassium = next(g for g in body["goals"] if g["key"] == "potassium_mg")
        balance = potassium.get("dialysis_balance")
        if balance:   # only present when the session modelled
            assert balance["delta"] == 0
            assert balance["withheld"]

    async def test_the_page_still_renders_when_no_serum_exists(self, client: AsyncClient):
        """No bloods at all must degrade, not 500."""
        token = await _token(client, "dia6@example.com")
        await _make_renal_patient(client, token)
        today = date.today()
        await _add_session(client, token, today)

        r = await client.get(f"/api/v1/nutrition/goal-progress?date={today}",
                             headers=_auth(token))
        assert r.status_code == 200
        assert r.json()["goals"]
