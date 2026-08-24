"""Separators the meal parser must honour, and the notes it must not ignore.

Both pinned from real logged meals that came back with no nutrients at all.

The "+" case is the instructive one. Two different splitters decide what a meal
contains: `extract_food_items_nlm` routes single-food vs meal, and
`parse_meal_text` does the actual work. They disagreed — the router split on
"+", the parser did not — so a meal was sent to the meal estimator, which then
found ONE component whose food name was the entire rest of the string:

    'boost glucose control + 0.5 cup of roasted corn flour'

Nothing matches that, so the log was saved with nutrient_status="failed" and the
UI showed "unavailable". **When two parsers decide the same question, a
disagreement between them is a bug even when each looks correct alone.**
"""

import pytest

from app.services.meal_parser import parse_meal_text, extract_nutrition_facts
from app.services.nlm_food_extractor import extract_food_items_nlm


def _names(description: str) -> list[str]:
    return [c.food_name for c in parse_meal_text(description)]


@pytest.mark.parametrize("separator", [",", " + ", " and ", "; ", " & "])
def test_every_separator_yields_two_components(separator):
    description = f"8 Fl oz Boost Glucose Control{separator}0.5 cup of Roasted corn flour"
    names = _names(description)
    assert len(names) == 2, f"{separator!r} did not separate: {names}"
    assert any("boost" in n for n in names)
    assert any("corn flour" in n for n in names)


def test_the_router_and_the_parser_agree_on_item_count():
    """A disagreement here is what produced a nonsense food name."""
    for description in [
        "8 Fl oz Boost Glucose Control + 0.5 cup of Roasted corn flour",
        "8 Fl oz Boost Glucose Control, 0.5 cup of Roasted corn flour",
        "0.5 cup of bismatti rice, 1 cup of goat meat vindaloo",
    ]:
        assert len(extract_food_items_nlm(description)) == len(_names(description)), (
            f"router and parser disagree on {description!r}"
        )


def test_quantities_survive_a_plus():
    comps = parse_meal_text("8 Fl oz Boost Glucose Control + 0.5 cup of Roasted corn flour")
    by_name = {c.food_name: c.qty_g for c in comps}
    assert any(q > 200 for q in by_name.values()), f"8 fl oz should be ~245 g: {by_name}"
    assert any(30 < q < 120 for q in by_name.values()), f"half a cup of flour: {by_name}"


def test_an_attached_plus_is_part_of_the_product_name():
    """"Boost+" and "Glucerna+" must not be torn in half."""
    names = _names("8 fl oz Boost+ vanilla")
    assert len(names) == 1, names


def test_a_number_after_and_still_does_not_split():
    """The guard that "+" deliberately does not share."""
    assert len(_names("1 and a half cups of rice")) == 1


# ── Notes carry label values for dishes no database has ────────────────────

def test_label_values_are_read_out_of_notes():
    notes = "Per serving: 240 calories, 18 g protein, 12 g carbs, 13 g fat"
    facts = extract_nutrition_facts(notes)
    assert facts is not None, "the panel the user typed must be readable"
    assert facts["nutrients"]["calories"] == 240


@pytest.mark.asyncio
async def test_notes_are_used_when_the_description_has_no_label(db):
    """goat meat vindaloo is in no food database; the user supplied the numbers."""
    from app.services.nutrient_estimator import estimate_meal_nutrients

    result = await estimate_meal_nutrients(
        db, "1 cup of goat meat vindaloo",
        notes="Per serving: 240 calories, 18 g protein, 12 g carbs, 13 g fat",
    )
    agg = result["aggregate_nutrients"]
    assert agg, "notes carrying a full label must produce nutrients"
    assert agg["calories"] == pytest.approx(240, abs=1)
    assert result["components"][0]["source"] == "user_provided"


# ── The quantity in the description must reach the stored totals ───────────

@pytest.mark.asyncio
async def test_a_single_item_is_scaled_by_its_stated_quantity(db, monkeypatch):
    """"8 Fl oz Boost Glucose Control" is 190 kcal, not 80.

    `estimate_nutrients` answers per 100 g/mL. Storing that unscaled divided
    every value by 2.37 (237 mL / 100 mL) — and unlike a failed lookup, the
    result LOOKS right, which is worse. Phosphorus and potassium were understated
    by the same factor on a dialysis patient's log.
    """
    from app.services import nutrient_estimator as est_mod

    per_100ml = {"calories": 80.0, "protein_g": 6.75, "carbs_g": 6.8,
                 "fat_g": 3.0, "phosphorus_mg": 105.0, "potassium_mg": 105.0}

    async def _fake_estimate(_db, food_name, *a, **k):
        assert "boost" in food_name.lower()
        return {"nutrients": dict(per_100ml), "fdc_id": 2484406, "source": "usda",
                "confidence": 0.9, "believable": True}

    monkeypatch.setattr(est_mod, "estimate_nutrients", _fake_estimate)

    meal = await est_mod.estimate_meal_nutrients(db, "8 Fl oz Boost Glucose Control")
    agg = meal["aggregate_nutrients"]

    # 8 fl oz ≈ 244.8 mL, so ~2.4x the per-100 figures.
    assert agg["calories"] == pytest.approx(196, abs=6), agg
    assert agg["protein_g"] == pytest.approx(16.5, abs=1), agg
    # The clinically load-bearing ones scale too.
    assert agg["phosphorus_mg"] == pytest.approx(257, abs=10), agg
    assert agg["potassium_mg"] == pytest.approx(257, abs=10), agg
