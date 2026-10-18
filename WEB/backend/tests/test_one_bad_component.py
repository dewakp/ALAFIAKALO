# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""One implausible component must not void the whole meal.

Operator, 2026-10-18: *"things that used to work stop working reliably."*
Measured on their own production rows:

    "1 boiled egg, 1 cup of tea, 1 slice of kiwi"   stored 92 kcal, and now
        reports `tea: 1 kcal/100g is outside the expected 22-110 for
        'tea_coffee'` -> the WHOLE meal rejected -> the screen says
        "unavailable"
    "Banana, numb earl grey tea"  -> "numb earl grey tea" categorised DAIRY,
        band 30-160, so 1 kcal/100 g is judged impossible
    "Organic Milk (Pasteurized, Nonfat), ..." -> components `pasteurized` 16 g,
        `nonfat` 14 g, `carton` 100 g

Plain tea really is ~1 kcal/100 g: the BAND is wrong, not the value. The band
comes from `food_category_cache`, filled the first time a name is seen — so the
same text is judged differently on different days, which is precisely why a
meal that worked stops working with nothing about the meal having changed.

§3am's rule is kept: an impossible number is still never stored. What ends is
the collateral damage of discarding every sound component beside it.
"""

import pytest

pytestmark = pytest.mark.asyncio


class _Comp:
    def __init__(self, name, qty_g, qty_text="default"):
        self.food_name = name
        self.qty_g = qty_g
        self.qty_text = qty_text


def _fake_estimates(mapping):
    """`estimate_nutrients` stand-in: name -> (per100, believable)."""
    async def _est(db, food_name, serving=None, **kw):
        per100, ok = mapping[food_name]
        return {"nutrients": dict(per100), "believable": ok,
                "source": "usda", "fdc_id": None, "confidence": 1.0,
                "plausibility_warnings": [] if ok else [f"{food_name}: out of band"]}
    return _est


async def _run(monkeypatch, db, description, components, estimates):
    from app.services import nutrient_estimator as ne

    # `parse_meal_text` is imported INSIDE estimate_meal_nutrients, so it is
    # not an attribute of this module — patch it where it is defined.
    monkeypatch.setattr("app.services.meal_parser.parse_meal_text",
                        lambda *a, **k: components)
    monkeypatch.setattr(ne, "estimate_nutrients", _fake_estimates(estimates))
    return await ne.estimate_meal_nutrients(db, description, notes=None)


async def test_a_sound_component_survives_a_flagged_one(monkeypatch, db):
    """THE REPORTED BUG. Egg + kiwi must still be counted when tea is flagged."""
    meal = await _run(
        monkeypatch, db, "1 boiled egg, 1 cup of tea, 1 slice of kiwi",
        [_Comp("egg", 50.0), _Comp("tea", 250.0), _Comp("kiwi", 30.0)],
        {"egg": ({"calories": 155.0}, True),
         "tea": ({"calories": 1.0}, False),
         "kiwi": ({"calories": 61.0}, True)},
    )
    assert meal["believable"] is True, meal["warnings"]
    # 155*0.5 + 61*0.3 = 77.5 + 18.3
    assert round(meal["aggregate_nutrients"]["calories"], 1) == 95.8
    assert meal["excluded_components"] == ["tea"]


async def test_the_omission_is_stated_first(monkeypatch, db):
    """A total that silently omits an item reads as the whole meal (§3aa)."""
    meal = await _run(
        monkeypatch, db, "banana, numb earl grey tea",
        [_Comp("banana", 100.0), _Comp("numb earl grey tea", 100.0)],
        {"banana": ({"calories": 89.0}, True),
         "numb earl grey tea": ({"calories": 1.0}, False)},
    )
    assert meal["warnings"], "an exclusion must never be silent"
    assert meal["warnings"][0].startswith("NOT COUNTED in this total:")
    assert "numb earl grey tea" in meal["warnings"][0]


async def test_the_weight_counts_only_what_was_counted(monkeypatch, db):
    """Keeping the excluded grams would hand review_meal a density built from
    one set of nutrients and a different set of food."""
    meal = await _run(
        monkeypatch, db, "banana, carton",
        [_Comp("banana", 100.0), _Comp("carton", 100.0)],
        {"banana": ({"calories": 89.0}, True),
         "carton": ({"calories": 35.0}, False)},
    )
    assert meal["total_weight_g"] == 100.0


async def test_a_meal_with_nothing_countable_is_still_refused(monkeypatch, db):
    """The other half: if every component is flagged there is nothing sound to
    store, and storing an impossible number remains worse than storing none."""
    meal = await _run(
        monkeypatch, db, "carton, wrapper",
        [_Comp("carton", 100.0), _Comp("wrapper", 100.0)],
        {"carton": ({"calories": 35.0}, False),
         "wrapper": ({"calories": 900.0}, False)},
    )
    assert meal["believable"] is False
    assert not meal["aggregate_nutrients"]


async def test_a_meal_level_impossibility_is_still_refused(monkeypatch, db):
    """§3am's sardine meal: every component passes its own band, and the TOTAL
    is impossible — more fat than the meal weighed. That verdict comes from
    review_meal on the kept aggregate and must survive this change."""
    meal = await _run(
        monkeypatch, db, "1 can of titus sardines",
        [_Comp("sardines", 505.0)],
        {"sardines": ({"calories": 997.0, "fat_g": 78.0}, True)},
    )
    assert meal["believable"] is False, meal["warnings"]
