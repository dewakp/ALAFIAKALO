# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""An item with no usable weight is never 100 g.

Measured on the 2026-10-23 production repair, with components stored:
"2 sachets of brown sugar" parsed as 100 g -> 380 kcal (two sachets are ~8 g);
".5 cup of roasted corn flour" was not parsed at all.

Operator, 2026-10-24: "Instead of assuming portion let user determine. If no
portion size exists — surface the error." A COUNT the patient stated becomes
grams through the food's own USDA portion; no amount at all is not counted and
is named on the meal. The assumed serving (choice C) is gone: it sent a bare
"Smoothie" to USDA's 864 g "1 medium" and 769 kcal.
"""

import pytest

from app.services import food_match_verifier
from app.services import nutrient_estimator as ne
from app.services.meal_parser import parse_meal_text

pytestmark = pytest.mark.asyncio

# Captured at import — before conftest's autouse fixture replaces it.
_REAL_PORTION_FROM_RECORD = ne._portion_from_record


def _estimate(per100, fdc_id=None, name=None):
    async def fake(db, food_name, serving_size=None):
        return {"source": "usda" if fdc_id else "ai", "fdc_id": fdc_id, "food_name": name or food_name,
                "confidence": 1.0, "nutrients": dict(per100), "believable": True}
    return fake


def test_a_leading_dot_decimal_is_a_quantity():
    [c] = parse_meal_text(".5 cup of rice")
    assert c.qty_g == 92.5 and c.qty_text == ".5 cup"


async def test_the_records_own_portion_is_used(monkeypatch, db):
    import importlib
    real = importlib.import_module("app.services.nutrient_estimator")
    # undo conftest's offline stub for the portion lookup, keep the network out
    monkeypatch.setattr(real, "_portion_from_record", _REAL_PORTION_FROM_RECORD)
    monkeypatch.setattr(ne, "_portion_cache", {})

    async def detail(fdc_id):
        return {"portions": [{"description": "1 packet", "gram_weight": 4.0, "amount": 1}]}

    async def pick(text, food, portions):
        assert "2 sachets" in text
        return 0, 2.0

    monkeypatch.setattr(ne, "get_usda_food_detail", detail)
    monkeypatch.setattr(food_match_verifier, "choose_portion", pick)
    monkeypatch.setattr(ne, "estimate_nutrients", _estimate({"calories": 380.0}, fdc_id=168833,
                                                              name="Sugars, brown"))

    out = await ne.estimate_meal_nutrients(db, "2 sachets of brown sugar")

    [c] = out["components"]
    assert c["qty_g"] == 8.0 and "USDA portion" in c["qty_text"]
    assert out["aggregate_nutrients"]["calories"] == pytest.approx(30.4)


async def test_no_amount_is_not_counted_and_nothing_is_assumed(monkeypatch, db):
    """The Smoothie: no amount stated. Nothing may pick a serving for it."""
    monkeypatch.setattr(ne, "_portion_from_record", _REAL_PORTION_FROM_RECORD)
    monkeypatch.setattr(ne, "_portion_cache", {})

    async def detail(fdc_id):
        return {"portions": [{"description": "1 medium", "gram_weight": 864.0, "amount": 1}]}

    async def pick(*a, **k):
        raise AssertionError("no amount was stated, so no portion may be chosen")

    monkeypatch.setattr(ne, "get_usda_food_detail", detail)
    monkeypatch.setattr(food_match_verifier, "choose_portion", pick)
    monkeypatch.setattr(ne, "estimate_nutrients", _estimate({"calories": 89.0}, fdc_id=2709000,
                                                              name="Smoothie, fruit"))

    out = await ne.estimate_meal_nutrients(db, "Smoothie")

    [c] = out["components"]
    assert c["qty_g"] is None and c["counted"] is False
    assert c["qty_text"] == "no amount given"
    assert out["excluded_components"] == ["smoothie (no amount given)"]
    assert not out["aggregate_nutrients"].get("calories")


async def test_an_unstated_item_beside_a_weighed_one_is_named(monkeypatch, db):
    monkeypatch.setattr(ne, "estimate_nutrients", _estimate({"calories": 250.0}))

    out = await ne.estimate_meal_nutrients(db, "beef, 200 g rice")

    beef = next(c for c in out["components"] if c["food_name"] == "beef")
    assert beef["qty_g"] is None and beef["counted"] is False
    assert "beef (no amount given)" in out["excluded_components"]
    assert out["aggregate_nutrients"]["calories"] == 500.0   # the rice only


async def test_a_typical_portion_is_not_a_unit_a_count_can_multiply(monkeypatch, db):
    """FNDDS "Quantity not specified" is what OTHER people typically eat."""
    monkeypatch.setattr(ne, "_portion_from_record", _REAL_PORTION_FROM_RECORD)
    monkeypatch.setattr(ne, "_portion_cache", {})

    async def detail(fdc_id):
        return {"portions": [{"description": "Quantity not specified", "gram_weight": 240.0, "amount": 1}]}

    async def pick(text, food, portions):
        return 0, 2.0

    monkeypatch.setattr(ne, "get_usda_food_detail", detail)
    monkeypatch.setattr(food_match_verifier, "choose_portion", pick)
    monkeypatch.setattr(ne, "estimate_nutrients", _estimate({"calories": 100.0}, fdc_id=1, name="Stew"))

    out = await ne.estimate_meal_nutrients(db, "2 stew")

    [c] = out["components"]
    assert c["counted"] is False and c["qty_text"] == "no amount given"


async def test_a_portion_recorded_for_several_units_is_divided(monkeypatch, db):
    """USDA: 'slices (1/4" thick)' = 53 g for AMOUNT 10. Eight slices of fried
    plantain were stored as 424 g (53 g each) instead of 42 g."""
    monkeypatch.setattr(ne, "_portion_from_record", _REAL_PORTION_FROM_RECORD)
    monkeypatch.setattr(ne, "_portion_cache", {})

    async def detail(fdc_id):
        return {"portions": [{"description": 'slices (1/4" thick)', "gram_weight": 53.0, "amount": 10.0}]}

    async def pick(text, food, portions):
        return 0, 8.0

    monkeypatch.setattr(ne, "get_usda_food_detail", detail)
    monkeypatch.setattr(food_match_verifier, "choose_portion", pick)
    monkeypatch.setattr(ne, "estimate_nutrients", _estimate({"calories": 309.0}, fdc_id=168199,
                                                              name="Plantains, green, fried"))

    out = await ne.estimate_meal_nutrients(db, "8 fried plantains")   # a count, no weight

    [c] = out["components"]
    assert c["qty_g"] == 42.4


def test_a_bracketed_ingredient_with_no_amount_gets_none():
    """It used to become a guessed teaspoon, tablespoon or 30 g share, counted
    as if the patient had said it."""
    comps = parse_meal_text("jollof rice (rice, tomato, palm oil, pepper)")
    inner = [c for c in comps if c.food_name != "jollof rice"]
    assert inner and all(c.qty_text == "default" for c in inner), [(c.food_name, c.qty_text) for c in comps]


async def test_the_meal_preview_names_an_unweighed_item_instead_of_failing(client, monkeypatch):
    """`qty_g` was a required float, so a "no amount given" item made
    /estimate-meal answer 500 — the web pre-save suggestion's endpoint."""
    async def unweighed(db_, description, **kw):
        return {"description": description, "aggregate_nutrients": {}, "total_weight_g": None,
                "warnings": [], "believable": True,
                "excluded_components": ["smoothie (no amount given)"],
                "components": [{"food_name": "smoothie", "qty_g": None, "qty_text": "no amount given",
                                "counted": False, "source": "usda", "fdc_id": 1, "confidence": 1.0,
                                "nutrients_scaled": {}}]}
    monkeypatch.setattr("app.api.nutrition.estimate_meal_nutrients", unweighed)
    import uuid
    email = f"prev{uuid.uuid4().hex[:6]}@example.com"
    await client.post("/api/v1/auth/register", json={"email": email, "password": "SecureP@ss123",
                                                     "full_name": "Prev User", "date_of_birth": "1990-01-01"})
    tok = (await client.post("/api/v1/auth/login", data={"username": email, "password": "SecureP@ss123"})).json()["access_token"]

    r = await client.post("/api/v1/nutrition/estimate-meal", json={"description": "Smoothie"},
                          headers={"Authorization": f"Bearer {tok}"})

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["excluded_components"] == ["smoothie (no amount given)"]
    assert body["components"][0]["qty_g"] is None and body["components"][0]["counted"] is False
