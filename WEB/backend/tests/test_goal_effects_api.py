"""Per-goal effects must reach the client, not be computed and then dropped.

`apply_effects_to_totals` has always attached each effect to the goal it was
computed for. `NutrientGoalProgress` had no field to carry it, so
`nutrition.py` never passed it and every one was discarded at serialisation —
the day layer did the work, the wire threw it away, and nothing failed. That is
the same shape as the magnesium goal that was computed and dropped, and it is
invisible to any unit test of the day layer, which sees the attachment happen
and never sees the response.

So these go over real HTTP.
"""

from datetime import date, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.nutrient_effect import (
    AGENT_TREATMENT, PER_SESSION, REMOVES, NutrientEffect,
)
from app.models.user import User

EMAIL = "goaleffects@example.com"


async def _patient(client: AsyncClient, db) -> tuple[str, int]:
    await client.post("/api/v1/auth/register", json={
        "email": EMAIL, "password": "SecureP@ss123",
        "full_name": "Effects Tester", "date_of_birth": "1974-03-15",
    })
    r = await client.post("/api/v1/auth/login",
                          data={"username": EMAIL, "password": "SecureP@ss123"})
    token = r.json()["access_token"]
    # Biology, so the goals engine emits real figures rather than generic ones.
    await client.put("/api/v1/users/me", headers=_auth(token), json={
        "height_cm": 177.8, "current_weight_kg": 75.0,
        "gender_at_birth": "male", "activity_level": "sedentary",
    })
    user = (await db.execute(select(User).where(User.email == EMAIL))).scalar_one()
    return token, user.id


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _completed_session(client: AsyncClient, token: str, when: date):
    r = await client.post("/api/v1/chronic/therapy-sessions", headers=_auth(token), json={
        "therapy_type": "hemodialysis",
        "scheduled_date": datetime.combine(when, datetime.min.time()).isoformat(),
        "status": "completed",
        "duration_minutes": 184,
        "blood_flow_rate": 350,
        "dialysate_volume_liters": 30,
        "dialysate_potassium_meq": 1.0,
    })
    assert r.status_code in (200, 201), f"session setup failed: {r.text[:200]}"


def _protein_effect() -> NutrientEffect:
    """The seeded literature prior.

    `provenance` is load-bearing: a magnitude a model supplied is reported and
    NOT counted, so a row seeded as "llm" would be withheld and this test would
    pass while asserting nothing about the wire.
    """
    return NutrientEffect(
        agent_kind=AGENT_TREATMENT, agent_key="hemodialysis",
        agent_label="Hemodialysis", nutrient_key="protein_g", direction=REMOVES,
        magnitude=9.0, magnitude_unit="g", basis=PER_SESSION,
        mechanism="Free amino acids leave in the effluent.",
        evidence_level="high", provenance="literature_prior", confidence=0.8,
        times_confirmed=1, is_active=True,
    )


@pytest.mark.asyncio
async def test_a_per_goal_effect_reaches_the_client(client: AsyncClient, db):
    """The regression this file exists for."""
    token, _ = await _patient(client, db)
    today = date.today()
    await _completed_session(client, token, today)
    db.add(_protein_effect())
    await db.commit()

    r = await client.get(
        f"/api/v1/nutrition/goal-progress?date={today.isoformat()}",
        headers=_auth(token))

    assert r.status_code == 200, r.text[:300]
    goals = r.json()["goals"]
    protein = next((g for g in goals if g["key"] == "protein_g"), None)
    assert protein is not None, "no protein goal for an effect to attach to"
    assert protein["nutrient_effects"], (
        "the effect was computed by the day layer and dropped at serialisation"
    )

    effect = protein["nutrient_effects"][0]
    assert effect["agent"] == "Hemodialysis"
    assert effect["direction"] == REMOVES
    assert effect["mechanism"], "the mechanism is what makes an effect readable"


@pytest.mark.asyncio
async def test_the_day_summary_reaches_the_client_too(client: AsyncClient, db):
    """`effects` beside `dialysis`: what the patient met today, and what it did."""
    token, _ = await _patient(client, db)
    today = date.today()
    await _completed_session(client, token, today)
    db.add(_protein_effect())
    await db.commit()

    r = await client.get(
        f"/api/v1/nutrition/goal-progress?date={today.isoformat()}",
        headers=_auth(token))

    assert r.status_code == 200, r.text[:300]
    effects = r.json().get("effects")
    assert effects, "the day-level summary is absent"
    assert "Hemodialysis" in effects["agents"]
    assert any(a["nutrient_key"] == "protein_g" for a in effects["applied"])


@pytest.mark.asyncio
async def test_a_day_without_the_agent_carries_no_effects(client: AsyncClient, db):
    """A stored fact is not an exposure. Knowing what dialysis does to protein
    is not the same as the patient having dialysed."""
    token, _ = await _patient(client, db)
    db.add(_protein_effect())
    await db.commit()

    r = await client.get(
        f"/api/v1/nutrition/goal-progress?date={date.today().isoformat()}",
        headers=_auth(token))

    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert not body.get("effects") or not body["effects"]["applied"]
    for goal in body["goals"]:
        assert not goal.get("nutrient_effects"), goal["key"]
