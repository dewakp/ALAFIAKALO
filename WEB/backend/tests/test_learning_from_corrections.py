"""Correcting a meal must teach NUTRIENTS, not just the food's name.

From production, verified on live data: a "Confirm / correct — teach ALAFIA"
click at 20:55 wrote a row into `food_training_samples` (the vision corpus) and
nothing into `learned_food_nutrients` — whose newest row was from 2026-07-06.
The UI said "ALAFIA learned the right foods", which was literally true and
nutritionally useless: `get_learned` reads only that second table, so the next
estimate re-derived everything and answered with a different product's numbers.

Learning is deliberately refused when the serving weight is unknown: stated
values are per serving, and storing them as per-100 g without a weight bakes in
a silent scaling error — worse than not learning at all.
"""

import pytest
from sqlalchemy import select

from app.models.learned_nutrient import LearnedFoodNutrient
from app.models.user import User
from app.services.learned_nutrient_service import get_learned


async def _user(db, email: str) -> User:
    u = User(email=email, hashed_password="x", full_name="Learner")
    db.add(u)
    await db.flush()
    return u


@pytest.mark.asyncio
async def test_stated_values_are_remembered_for_next_time(db):
    from app.services.nutrient_estimator import _learn_stated

    user = await _user(db, "learn1@example.com")
    # 150 g serving carrying the label figures.
    await _learn_stated(db, "Nounos Yogurt",
                        {"fat_g": 6.0, "carbs_g": 14.0, "calcium_mg": 170.0},
                        serving_weight_g=150.0, user_id=user.id)

    learned = await get_learned(db, "Nounos Yogurt")
    assert learned is not None, "the next lookup must start from the user's numbers"
    # Stored per 100 g: 6 g per 150 g serving -> 4 g per 100 g.
    assert learned["nutrients"]["fat_g"] == pytest.approx(4.0, abs=0.01)
    assert learned["nutrients"]["carbs_g"] == pytest.approx(9.333, abs=0.01)


@pytest.mark.asyncio
async def test_nothing_is_learned_without_a_serving_weight(db):
    """Per-serving values stored as per-100 g would be silently wrong."""
    from app.services.nutrient_estimator import _learn_stated

    await _learn_stated(db, "Mystery Yogurt", {"fat_g": 6.0}, serving_weight_g=None)
    assert await get_learned(db, "Mystery Yogurt") is None

    await _learn_stated(db, "Mystery Yogurt", {"fat_g": 6.0}, serving_weight_g=1.0)
    assert await get_learned(db, "Mystery Yogurt") is None


@pytest.mark.asyncio
async def test_learning_never_breaks_the_estimate(db):
    """Best-effort: a failure here must not take the meal down with it."""
    from app.services.nutrient_estimator import _learn_stated

    # A nonsense payload must be swallowed, not raised.
    await _learn_stated(db, "Odd Food", {"fat_g": "not a number"}, serving_weight_g=100.0)


@pytest.mark.asyncio
async def test_a_whole_meal_teaches_what_the_user_stated(db, monkeypatch):
    """End to end through the estimator the save path actually calls."""
    from app.services import nutrient_estimator as est_mod

    async def _fake(_db, food_name, *a, **k):
        return {"nutrients": {"calories": 60.0, "fat_g": 99.0}, "fdc_id": None,
                "source": "usda", "confidence": 0.5, "believable": True}

    monkeypatch.setattr(est_mod, "estimate_nutrients", _fake)

    await est_mod.estimate_meal_nutrients(
        db, "100 g Nounos Yogurt with 6 g fat, 14 g carbohydrate")

    learned = await get_learned(db, "nounos yogurt")
    assert learned is not None, "a saved meal with stated values must teach"
    assert learned["nutrients"]["fat_g"] == pytest.approx(6.0, abs=0.1)


@pytest.mark.asyncio
async def test_the_learned_row_wins_on_the_next_lookup(db):
    """The point of learning: the next estimate starts from it."""
    from app.services.nutrient_estimator import _learn_stated, estimate_nutrients

    await _learn_stated(db, "Nounos Yogurt", {"fat_g": 6.0, "calories": 90.0},
                        serving_weight_g=100.0)

    result = await estimate_nutrients(db, "Nounos Yogurt")
    assert result["source"] == "learned", result.get("source")
    assert result["nutrients"]["fat_g"] == pytest.approx(6.0, abs=0.1)


@pytest.mark.asyncio
async def test_rows_actually_land_in_the_learned_table(db):
    """The table `get_learned` reads — the one a correction never used to touch."""
    from app.services.nutrient_estimator import _learn_stated

    await _learn_stated(db, "Nounos Yogurt", {"fat_g": 6.0}, serving_weight_g=100.0)
    rows = (await db.execute(select(LearnedFoodNutrient))).scalars().all()
    assert any("nounos" in r.food_name_normalized for r in rows), [r.food_name_normalized for r in rows]
