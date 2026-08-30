"""A portion multiplier must scale every nutrient, and never leave stale ones.

A patient logged a meal, then edited the description to record that they ate a
quarter of it:

    1 ripe plantain boiled, 2 eggs fried …          413 kcal
    0.25 x (1 ripe plantain boiled, 2 eggs fried …) 413 kcal   ← unchanged

Two independent faults produced that identical number.

1. **`0.25 x (…)` did not parse at all** — not "went unscaled". The wrapping
   parenthesis made the segment splitter yield ZERO components, so the estimate
   returned every nutrient as None.

2. **The PATCH endpoint applied fields and stopped**, so the previous meal's
   nutrients stayed attached to the new description. The empty estimate wrote
   nothing over them and the old numbers were displayed as if recalculated:
   697 mg of potassium and 372 mg of cholesterol recorded for 174 and 93. On a
   dialysis patient that is a fourfold overstatement of potassium.

Stale values that look computed are worse than no values at all.
"""

from datetime import date

import pytest

from app.services.meal_parser import parse_meal_text, _extract_meal_multiplier

MEAL = ("1 ripe plantain boiled, 2 eggs fried with onions 6 cherry tomatoes, "
        "4 pitted olives, 2 teaspoons of canola oil")


# ── Parsing ───────────────────────────────────────────────────────────────

def test_a_parenthesised_multiplier_still_yields_every_component():
    """The regression: this returned zero components, hence zero nutrients."""
    plain = parse_meal_text(MEAL)
    scaled = parse_meal_text(f"0.25 x ({MEAL})")

    assert len(plain) == 4
    assert len(scaled) == len(plain), "the multiplier must not lose foods"


def test_grams_scale_by_the_multiplier():
    plain = sum(c.qty_g for c in parse_meal_text(MEAL))
    scaled = sum(c.qty_g for c in parse_meal_text(f"0.25 x ({MEAL})"))
    assert scaled == pytest.approx(plain * 0.25, rel=0.01)


@pytest.mark.parametrize("text,factor", [
    ("0.25 x ({m})", 0.25),
    ("0.25 × ({m})", 0.25),      # the multiplication sign, not the letter
    ("2x ({m})", 2.0),           # no space
    ("1/2 x ({m})", 0.5),        # a fraction
    ("0.5 x {m}", 0.5),          # no parentheses at all
])
def test_multiplier_forms(text, factor):
    plain = sum(c.qty_g for c in parse_meal_text(MEAL))
    scaled = sum(c.qty_g for c in parse_meal_text(text.format(m=MEAL)))
    assert scaled == pytest.approx(plain * factor, rel=0.01)


@pytest.mark.parametrize("text", [
    "6 cherry tomatoes",
    "2 teaspoons of canola oil",
    "1 ripe plantain boiled",
    "100 g chicken breast",
])
def test_ordinary_quantities_are_not_mistaken_for_a_meal_multiplier(text):
    """An x/× token is required, so a leading count is left alone."""
    factor, rest = _extract_meal_multiplier(text)
    assert factor == 1.0
    assert rest == text


@pytest.mark.parametrize("bad", ["0 x (rice)", "-1 x (rice)", "500 x (rice)"])
def test_absurd_factors_are_ignored_rather_than_applied(bad):
    """A zero would silently erase the meal; 500x is a typo, not a portion."""
    factor, _ = _extract_meal_multiplier(bad)
    assert factor == 1.0


def test_the_quantity_text_says_it_was_scaled():
    """Or the row reads "2 eggs" while carrying the grams of half an egg."""
    scaled = parse_meal_text(f"0.25 x ({MEAL})")
    assert any("0.25" in c.qty_text for c in scaled)


# ── The endpoint must not keep stale nutrients ────────────────────────────

@pytest.mark.asyncio
async def test_editing_the_description_clears_and_re_estimates(client, db):
    """Changing the food must never leave the previous meal's numbers behind."""
    from app.core.security import get_current_user
    from app.main import app
    from app.models.nutrition import NutritionLog
    from app.models.user import User

    user = User(email="mult@example.com", hashed_password="x", full_name="T")
    db.add(user)
    await db.flush()

    log = NutritionLog(
        user_id=user.id, log_date=date(2026, 8, 30), meal_type="dinner",
        food_name=MEAL, calories=412.6, potassium_mg=696.7,
        cholesterol_mg=372.0, nutrient_status="done",
    )
    db.add(log)
    await db.commit()

    app.dependency_overrides[get_current_user] = lambda: user
    try:
        resp = await client.patch(
            f"/api/v1/nutrition/{log.id}",
            json={"food_name": f"0.25 x ({MEAL})"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()

        # The old numbers must be GONE, not left to be read as fact.
        assert body["calories"] is None
        assert body["potassium_mg"] is None
        assert body["cholesterol_mg"] is None
        # …and the client is told values are coming, not that they are zero.
        assert body["nutrient_status"] == "pending"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_editing_a_note_does_not_discard_good_nutrients(client, db):
    """Only a change to the FOOD invalidates them."""
    from app.core.security import get_current_user
    from app.main import app
    from app.models.nutrition import NutritionLog
    from app.models.user import User

    user = User(email="mult2@example.com", hashed_password="x", full_name="T")
    db.add(user)
    await db.flush()
    log = NutritionLog(
        user_id=user.id, log_date=date(2026, 8, 30), meal_type="dinner",
        food_name=MEAL, calories=412.6, nutrient_status="done",
    )
    db.add(log)
    await db.commit()

    app.dependency_overrides[get_current_user] = lambda: user
    try:
        resp = await client.patch(
            f"/api/v1/nutrition/{log.id}", json={"notes": "ate on the balcony"})
        assert resp.status_code == 200
        assert resp.json()["calories"] == pytest.approx(412.6)
        assert resp.json()["nutrient_status"] == "done"
    finally:
        app.dependency_overrides.clear()
