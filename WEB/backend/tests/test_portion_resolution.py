# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""An item with no usable weight is never 100 g.

Measured on the 2026-10-23 production repair, with components stored:
"2 sachets of brown sugar" parsed as 100 g -> 380 kcal (two sachets are ~8 g);
"1 serving of ranch dressing" as 100 g -> 430 kcal, 45 g fat (~30 g);
".5 cup of roasted corn flour" was not parsed at all. 72% of logged items state
no weight. Operator choice C: the record's own portion first, then an ASSUMED
serving labelled as one, and "weight unknown" only when both fail.
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


async def test_otherwise_an_assumed_serving_labelled_as_one(monkeypatch, db):
    async def assume(text, food, meal=""):
        return 150.0, 120.0, 200.0
    monkeypatch.setattr(food_match_verifier, "assumed_portion", assume)
    monkeypatch.setattr(ne, "estimate_nutrients", _estimate({"calories": 250.0}))

    out = await ne.estimate_meal_nutrients(db, "beef")

    [c] = out["components"]
    assert c["qty_g"] == 150.0 and c["qty_text"].startswith("assumed portion")
    assert "120-200" in c["qty_text"]
    assert out["aggregate_nutrients"]["calories"] == 375.0


async def test_weight_unknown_is_not_counted_and_says_so(monkeypatch, db):
    async def no(text, food, meal=""):
        return None
    monkeypatch.setattr(food_match_verifier, "assumed_portion", no)
    monkeypatch.setattr(ne, "estimate_nutrients", _estimate({"calories": 250.0}))

    out = await ne.estimate_meal_nutrients(db, "beef, 200 g rice")

    beef = next(c for c in out["components"] if c["food_name"] == "beef")
    assert beef["qty_g"] is None and beef["counted"] is False
    assert any("weight unknown" in x for x in out["excluded_components"])
    assert out["aggregate_nutrients"]["calories"] == 500.0   # the rice only


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

    out = await ne.estimate_meal_nutrients(db, "fried plantains")   # no weight stated

    [c] = out["components"]
    assert c["qty_g"] == 42.4
