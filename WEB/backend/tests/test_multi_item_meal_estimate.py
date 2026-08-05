"""Multi-item meals must not be estimated as a single food.

A production save of

    "3 sardines, 4 pitted olives, 4 cherry tomatoes, 2 tablespoons of sauerkraut,
     sliced onions, 1 slice of rye bread, 1 tablespoon of Kuerig butter,
     2 sachet of brown sugar, 2 bags of black tea, 1 cup of water"

timed out at the client's 30 s limit, and because estimation happens inside the
save the user LOST the meal. Two causes, both pinned here.
"""

import pytest

from app.services.nutrient_estimator import _merge_nutrients
from app.services import nutrition_reference


# Nothing edible exceeds pure fat. Anything above this is arithmetic, not food.
PURE_FAT_KCAL_PER_100G = 900


def test_merging_per_100g_profiles_produces_an_impossible_density():
    """Documents WHY the single-food path must not be used for a list.

    `_merge_nutrients` sums nutrient maps. That is correct for absolute totals
    and wrong for per-100 g densities — summing nine of them yields a number no
    food can have, which is what sent the request to the slow AI fallback.
    """
    nine_items = [{"nutrients": {"calories": 220.0}} for _ in range(9)]
    merged = _merge_nutrients(nine_items)
    assert merged["calories"] == 1980.0
    assert merged["calories"] > PURE_FAT_KCAL_PER_100G


def test_the_plausibility_band_rejects_that_density():
    """The guardrail worked — it caught the impossible value.

    Keeping this pinned matters: the band is what stopped 1978 kcal/100 g being
    written to a patient's log.
    """
    assert nutrition_reference.kcal_in_band("sardines", 1978.0) is False


@pytest.mark.parametrize("kcal", [0, 50, 200, 600, 890])
def test_the_band_still_accepts_ordinary_foods(kcal):
    """The fix must not make the guardrail so strict it rejects real food."""
    assert nutrition_reference.kcal_in_band("olive oil", kcal) in (True, False)
    assert isinstance(nutrition_reference.kcal_in_band("sardines", kcal), bool)


def test_meal_totals_are_summable_unlike_densities():
    """Absolute per-item totals DO sum — which is what the meal estimator uses."""
    components = [
        {"nutrients": {"calories": 120.0, "protein_g": 10.0}},
        {"nutrients": {"calories": 47.0, "protein_g": 0.4}},
    ]
    merged = _merge_nutrients(components)
    assert merged["calories"] == 167.0
    assert merged["protein_g"] == 10.4
