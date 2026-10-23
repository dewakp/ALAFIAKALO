# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""A meal keeps the components it was estimated from.

Operator, 2026-10-22: *"save meals component."* A breakfast stored at 3,090
kcal could not say that 2,706 kcal of it was ONE item — "sardines", resolved to
USDA "Fish oil, sardine" — because the writer stored only the sum, and finding
the meals built on that row meant re-running the estimator over 836 of them.
"""

import datetime
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.nutrition import NutritionLog, NutritionLogComponent
from app.services import nutrient_enrichment as ne

pytestmark = pytest.mark.asyncio


def _session_factory(session):
    """`_enrich` opens its own session; hand it the test's (see
    test_one_bad_component.py for why backend-test cannot reach any other)."""
    class _Ctx:
        def __call__(self):
            return self

        async def __aenter__(self):
            return session

        async def __aexit__(self, *exc):
            return False

    return _Ctx()


BREAKFAST = [
    {"food_name": "sardines", "matched_name": "Fish oil, sardine", "counted": True,
     "qty_g": 300.0, "qty_text": "3 pieces", "source": "usda", "fdc_id": 173578,
     "confidence": 1.0, "nutrients_scaled": {"calories": 2706.0, "fat_g": 300.0}},
    {"food_name": "brioche bread slices", "matched_name": "brioche", "counted": True,
     "qty_g": 56.0, "qty_text": "2 slices", "source": "mcp_open_food_facts", "fdc_id": None,
     "confidence": 0.92, "nutrients_scaled": {"calories": 162.6}},
    {"food_name": "raw", "matched_name": None, "counted": False, "qty_g": 30.0,
     "qty_text": "default", "source": None, "fdc_id": None, "confidence": 0.0,
     "nutrients_scaled": {}, "warnings": ["no data"]},
]


async def _log(db, food_name="3 Pieces of Sardines, 2 Brioche Bread Slices"):
    from app.models.user import User
    user = User(email=f"comp{uuid.uuid4().hex[:8]}@example.com", hashed_password="x", full_name="T")
    db.add(user)
    await db.flush()
    log = NutritionLog(user_id=user.id, log_date=datetime.date(2026, 10, 22),
                       meal_type="breakfast", food_name=food_name, nutrient_status="pending")
    db.add(log)
    await db.commit()
    await db.refresh(log)
    return log


def _meal(components, kcal):
    async def fake(db_, description, notes=None, **kw):
        return {"description": description, "components": components,
                "aggregate_nutrients": {"calories": kcal}, "total_weight_g": 356.0,
                "warnings": [], "excluded_components": [c["food_name"] for c in components
                                                        if not c["counted"]],
                "believable": True}
    return fake


async def _components(db, log_id):
    return (await db.execute(select(NutritionLogComponent).where(
        NutritionLogComponent.nutrition_log_id == log_id
    ).order_by(NutritionLogComponent.position))).scalars().all()


async def test_each_component_is_stored_with_what_it_resolved_to(monkeypatch, db):
    """THE POINT: the wrong match is visible per item, not hidden in the sum."""
    log = await _log(db)
    monkeypatch.setattr("app.services.nutrient_estimator.estimate_meal_nutrients",
                        _meal(BREAKFAST, 2868.6))
    monkeypatch.setattr(ne, "async_session", _session_factory(db))

    await ne._enrich(log.id)

    rows = await _components(db, log.id)
    assert [(r.food_name, r.matched_name, r.qty_g) for r in rows] == [
        ("sardines", "Fish oil, sardine", 300.0),
        ("brioche bread slices", "brioche", 56.0),
        ("raw", None, 30.0),
    ]
    assert rows[0].nutrients == {"calories": 2706.0, "fat_g": 300.0}
    assert rows[0].fdc_id == 173578 and rows[0].source == "usda"
    # An excluded component is RECORDED, marked as not counted — the omission
    # is itself the finding.
    assert [r.counted for r in rows] == [True, True, False]


async def test_a_re_estimate_replaces_the_components_never_adds_beside_them(monkeypatch, db):
    log = await _log(db)
    monkeypatch.setattr(ne, "async_session", _session_factory(db))
    monkeypatch.setattr("app.services.nutrient_estimator.estimate_meal_nutrients",
                        _meal(BREAKFAST, 2868.6))
    await ne._enrich(log.id)

    fixed = [dict(BREAKFAST[0], matched_name="Fish, sardine, Atlantic, canned in oil",
                  qty_g=100.0, nutrients_scaled={"calories": 208.0})]
    monkeypatch.setattr("app.services.nutrient_estimator.estimate_meal_nutrients",
                        _meal(fixed, 208.0))
    log.calories = None
    await db.commit()
    await ne._enrich(log.id)

    rows = await _components(db, log.id)
    assert [(r.food_name, r.matched_name, r.qty_g) for r in rows] == [
        ("sardines", "Fish, sardine, Atlantic, canned in oil", 100.0)]


async def test_the_single_food_fallback_says_it_had_no_portion(monkeypatch, db):
    """When nothing parsed as a portion the meal stores a per-100 g profile.
    Its component says so (qty NULL), rather than claiming a weight."""
    log = await _log(db, food_name="garri")

    async def nothing(db_, description, notes=None, **kw):
        return {"description": description, "components": [], "aggregate_nutrients": {},
                "total_weight_g": 0.0, "warnings": [], "excluded_components": [],
                "believable": True}

    async def per100(db_, name, serving=None):
        return {"source": "ai", "fdc_id": None, "food_name": "garri", "confidence": 0.7,
                "nutrients": {"calories": 360.0}}

    monkeypatch.setattr("app.services.nutrient_estimator.estimate_meal_nutrients", nothing)
    monkeypatch.setattr("app.services.nutrient_estimator.estimate_nutrients", per100)
    monkeypatch.setattr(ne, "async_session", _session_factory(db))
    await ne._enrich(log.id)

    rows = await _components(db, log.id)
    assert len(rows) == 1 and rows[0].qty_g is None
    assert rows[0].qty_text.startswith("per 100 g") and rows[0].source == "ai"


async def _token(client: AsyncClient, email: str) -> str:
    await client.post("/api/v1/auth/register", json={
        "email": email, "password": "SecureP@ss123", "full_name": "Comp User",
        "date_of_birth": "1990-01-01"})
    r = await client.post("/api/v1/auth/login", data={"username": email, "password": "SecureP@ss123"})
    return r.json()["access_token"]


async def test_the_api_returns_them_to_the_owner_and_404s_anyone_else(client: AsyncClient, db):
    owner = await _token(client, f"own{uuid.uuid4().hex[:6]}@example.com")
    other = await _token(client, f"oth{uuid.uuid4().hex[:6]}@example.com")
    r = await client.post("/api/v1/nutrition/", headers={"Authorization": f"Bearer {owner}"},
                          json={"log_date": "2026-10-22", "meal_type": "breakfast",
                                "food_name": "oatmeal", "calories": 150.0})
    log_id = r.json()["id"]

    r = await client.get(f"/api/v1/nutrition/{log_id}/components",
                         headers={"Authorization": f"Bearer {owner}"})
    assert r.status_code == 200
    body = r.json()
    # Typed calories: nothing was estimated — and the payload SAYS so, rather
    # than handing back an empty list that reads as a meal with nothing in it.
    assert body["components"] == [] and body["estimated"] is False

    db.add(NutritionLogComponent(nutrition_log_id=log_id, position=0, food_name="oats",
                                 matched_name="Oats, raw", qty_g=40.0, nutrients={"calories": 150.0}))
    await db.commit()
    body = (await client.get(f"/api/v1/nutrition/{log_id}/components",
                             headers={"Authorization": f"Bearer {owner}"})).json()
    assert body["estimated"] is True
    assert body["components"][0]["matched_name"] == "Oats, raw"

    r = await client.get(f"/api/v1/nutrition/{log_id}/components",
                         headers={"Authorization": f"Bearer {other}"})
    assert r.status_code == 404


async def test_figures_the_patient_types_retire_the_components(client: AsyncClient, db):
    """Components describe an ESTIMATE. Once the patient types the figures,
    the items no longer add up to the meal and must not be shown as its
    breakdown — `/components` then says, truthfully, "not estimated"."""
    owner = await _token(client, f"typ{uuid.uuid4().hex[:6]}@example.com")
    h = {"Authorization": f"Bearer {owner}"}
    log_id = (await client.post("/api/v1/nutrition/", headers=h, json={
        "log_date": "2026-10-22", "meal_type": "lunch", "food_name": "rice",
        "calories": 200.0})).json()["id"]
    db.add(NutritionLogComponent(nutrition_log_id=log_id, position=0, food_name="rice",
                                 matched_name="Rice, white, cooked", qty_g=150.0,
                                 nutrients={"calories": 195.0}))
    await db.commit()

    r = await client.patch(f"/api/v1/nutrition/{log_id}", headers=h, json={"calories": 320.0})
    assert r.status_code == 200

    body = (await client.get(f"/api/v1/nutrition/{log_id}/components", headers=h)).json()
    assert body["estimated"] is False and body["components"] == []


async def test_reestimate_recomputes_this_meal_and_never_adds_one(client: AsyncClient, db, monkeypatch):
    """The diary's Re-analyze used to POST /estimate-meal with the meal's date
    and type, which SAVES A NEW LOG. Re-analysing must correct the meal it was
    pressed on: same id, figures cleared for the writer, no second row."""
    import app.api.nutrition as api_mod
    queued = []
    monkeypatch.setattr(api_mod, "enrich_log", lambda log_id: queued.append(log_id))

    owner = await _token(client, f"rea{uuid.uuid4().hex[:6]}@example.com")
    other = await _token(client, f"reb{uuid.uuid4().hex[:6]}@example.com")
    h = {"Authorization": f"Bearer {owner}"}
    log_id = (await client.post("/api/v1/nutrition/", headers=h, json={
        "log_date": "2026-10-22", "meal_type": "breakfast", "food_name": "sardines",
        "calories": 3090.0, "fat_g": 315.0})).json()["id"]

    r = await client.post(f"/api/v1/nutrition/{log_id}/reestimate", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == log_id and body["nutrient_status"] == "pending"
    assert body["calories"] is None and body["fat_g"] is None
    assert queued == [log_id]

    rows = (await client.get("/api/v1/nutrition/", headers=h)).json()
    assert [x["id"] for x in rows] == [log_id], "re-analysing must not create a meal"

    r = await client.post(f"/api/v1/nutrition/{log_id}/reestimate",
                          headers={"Authorization": f"Bearer {other}"})
    assert r.status_code == 404


async def test_reanalyze_keeps_the_photo_and_clears_the_whole_estimate(client: AsyncClient, db, monkeypatch):
    """2026-10-23: "Photo disappeared when reanalyzed." The clear-list was
    "every column not on a keep-list", and the keep-list omitted
    `food_thumbnail`. Re-analyse clears NUTRIENTS — named by the catalog — and
    the extended panel, which the fill-blanks writer would otherwise keep."""
    import app.api.nutrition as api_mod
    monkeypatch.setattr(api_mod, "enrich_log", lambda log_id: None)
    owner = await _token(client, f"pho{uuid.uuid4().hex[:6]}@example.com")
    h = {"Authorization": f"Bearer {owner}"}
    log_id = (await client.post("/api/v1/nutrition/", headers=h, json={
        "log_date": "2026-10-22", "meal_type": "dinner", "food_name": "sardines",
        "calories": 3090.0, "food_image_uris": "media/42",
        "food_thumbnail": "data:image/jpeg;base64,AAAA"})).json()["id"]
    row = (await db.execute(select(NutritionLog).where(NutritionLog.id == log_id))).scalar_one()
    row.extended_nutrients = {"phytate_mg": 9.0}
    await db.commit()

    body = (await client.post(f"/api/v1/nutrition/{log_id}/reestimate", headers=h)).json()

    assert body["food_image_uris"] == "media/42"
    assert body["food_thumbnail"] == "data:image/jpeg;base64,AAAA"
    assert body["calories"] is None
    await db.refresh(row)
    assert row.extended_nutrients is None
