"""Nutrient values a user types are FACTS ABOUT THE FOOD, not ingredients.

From production. The user logged:

    "Nounos Yogurt with 170 mg calcium, 210 potassium, 25 mg cholesterol,
     6g fat, 40 mg Na, 14 g carbohydrate"

and got back **1142 kcal, 88.9 g protein, 86.2 g fat** for a pot of yogurt.

The description was split on its commas like any multi-item meal, so every fact
became a food to look up and sum:

    'nounos yogurt with mg calcium'  100 g
    'potassium'                      100 g
    'mg cholesterol'                 100 g
    'fat'                              6 g   <- pure fat, ~900 kcal/100 g
    'mg na'                          100 g
    'carbohydrate'                    14 g

`extract_nutrition_facts` did not rescue it either: that path REQUIRES a calorie
figure, and this label had none — so six stated nutrients were discarded whole.
"""

import pytest

from app.services.meal_parser import extract_nutrient_facts

YOGURT = ("Nounos Yogurt with 170 mg calcium, 210 potassium, 25 mg cholesterol, "
          "6g fat, 40 mg Na, 14 g carbohydrate")


def test_the_food_survives_and_the_facts_are_lifted_out():
    food, facts = extract_nutrient_facts(YOGURT)
    assert food.lower().strip() == "nounos yogurt", food
    assert facts == {
        "calcium_mg": 170.0, "potassium_mg": 210.0, "cholesterol_mg": 25.0,
        "fat_g": 6.0, "sodium_mg": 40.0, "carbs_g": 14.0,
    }


def test_a_bare_number_uses_the_nutrients_own_unit():
    """"210 potassium" is 210 MG. Reading it as grams is off by a thousand."""
    _, facts = extract_nutrient_facts("yogurt with 210 potassium")
    assert facts["potassium_mg"] == 210.0


def test_units_are_converted_when_stated():
    _, facts = extract_nutrient_facts("supplement with 500 mcg folate is not a macro, 2 g protein")
    assert facts["protein_g"] == 2.0


def test_sodium_aliases():
    for text in ("40 mg Na", "40 mg sodium", "40 mg salt"):
        _, facts = extract_nutrient_facts(f"soup with {text}")
        assert facts["sodium_mg"] == 40.0, text


def test_saturated_fat_is_not_read_as_total_fat():
    """Longest name wins, or "saturated fat" silently becomes "fat"."""
    _, facts = extract_nutrient_facts("cheese with 5 g saturated fat")
    assert facts.get("saturated_fat_g") == 5.0
    assert "fat_g" not in facts


def test_the_reverse_order_is_read_too():
    _, facts = extract_nutrient_facts("yogurt, calcium 170 mg, protein 12 g")
    assert facts["calcium_mg"] == 170.0
    assert facts["protein_g"] == 12.0


def test_a_real_meal_is_left_alone():
    """A description with no stated nutrients must pass through untouched."""
    text = "0.5 cup of basmati rice, 1 cup of goat meat vindaloo"
    food, facts = extract_nutrient_facts(text)
    assert facts == {}
    assert food == text


def test_a_food_named_after_a_nutrient_is_not_eaten():
    """"fat" only counts as a fact when it carries a number."""
    food, facts = extract_nutrient_facts("chicken thigh with the fat trimmed")
    assert facts == {}
    assert "chicken" in food.lower()


@pytest.mark.asyncio
async def test_stated_values_win_over_the_estimate(db, monkeypatch):
    """The user read these off the pot; an estimate does not outrank that."""
    from app.services import nutrient_estimator as est_mod

    async def _fake(_db, food_name, *a, **k):
        # A deliberately wrong profile, to prove the stated numbers survive it.
        return {"nutrients": {"calories": 900.0, "fat_g": 99.0, "calcium_mg": 1.0},
                "fdc_id": None, "source": "usda", "confidence": 0.5, "believable": True}

    monkeypatch.setattr(est_mod, "estimate_nutrients", _fake)

    meal = await est_mod.estimate_meal_nutrients(db, YOGURT)
    agg = meal["aggregate_nutrients"]

    assert agg["fat_g"] == 6.0, agg          # not 99
    assert agg["calcium_mg"] == 170.0, agg   # not 1
    assert agg["potassium_mg"] == 210.0, agg
    assert len(meal["components"]) == 1, meal["components"]
