"""Regression guard for nutrition believability.

Captures every historical failure (water→2122 kcal, rice→dry match, suya→peanut,
Boost→522/serving, "100 chicken thigh", impossible macros) as deterministic cases
over the pure believability/parser/reference layers — so these never regress.
These need no DB, USDA, or AI, so they're fast and stable in CI.
"""
import pytest

from app.services import plausibility as P
from app.services import nutrition_reference as R
from app.services.meal_parser import extract_nutrition_facts


# ── Category classification ─────────────────────────────────────────────
@pytest.mark.parametrize("food,category", [
    ("cooked rice", "grain_cooked"),
    ("mixed rice and beans", "legume_cooked"),  # 'beans' wins (legume) — fine
    ("suya", "fatty_meat"),
    ("Boost Glucose Control", "nutrition_drink"),
    ("olive oil", "oil_fat"),
    ("spinach", "vegetable"),
    ("apple", "fruit_fresh"),
    ("cheddar cheese", "cheese"),
    ("water", "water"),
    ("grilled chicken breast", "lean_meat"),
])
def test_classify(food, category):
    assert R.classify(food) == category


# ── Output believability: historical bad matches are caught by category band ──
@pytest.mark.parametrize("food,nutrients,believable", [
    # rice resolved to a dry/fortified record (360) vs cooked band 80–200
    ("cooked rice", {"calories": 360, "protein_g": 7, "carbs_g": 79}, False),
    ("cooked rice", {"calories": 130, "protein_g": 2.7, "carbs_g": 28}, True),
    # Boost mismatched to 522 kcal/100g vs nutrition_drink band 50–160
    ("Boost Glucose Control", {"calories": 522, "protein_g": 25, "carbs_g": 96, "fat_g": 8}, False),
    # suya matched to a peanut/seed product (589) vs fatty_meat 200–420
    ("suya", {"calories": 589, "protein_g": 24, "carbs_g": 21, "fat_g": 50}, False),
    ("suya", {"calories": 270, "protein_g": 28, "carbs_g": 4, "fat_g": 16}, True),
])
def test_band_catches_bad_matches(food, nutrients, believable):
    _, _, ok = P.review(food, nutrients)
    assert ok is believable


def test_impossible_calories_clamped():
    n, warnings, ok = P.review("cold water", {"calories": 2122, "protein_g": 0, "carbs_g": 0, "fat_g": 0})
    assert ok is False
    assert n["calories"] <= P.MAX_KCAL_100G
    assert warnings


def test_macro_sum_over_100_flagged():
    _, _, ok = P.review("frankenfood", {"calories": 800, "protein_g": 60, "carbs_g": 60, "fat_g": 40})
    assert ok is False


def test_sodium_clamped_to_salt():
    n, _, ok = P.review("mystery", {"calories": 100, "sodium_mg": 99999})
    assert n["sodium_mg"] <= P.SALT_NA_100G and ok is False


def test_clean_food_passes():
    n, warnings, ok = P.review("cooked rice", {"calories": 130, "protein_g": 2.7, "carbs_g": 28, "fat_g": 0.3})
    assert ok is True and warnings == []


# ── Input believability: implausible portions capped ─────────────────────
def test_validate_parse_caps_huge_portion():
    q, warnings = P.validate_parse("chicken thigh", 14000)  # "100 of chicken thigh"
    assert q <= 2000 and warnings


def test_validate_parse_keeps_normal_portion():
    q, warnings = P.validate_parse("chicken thigh", 150)
    assert q == 150 and warnings == []


# ── Authoritative input: explicit labels are extracted (and trusted upstream) ──
def test_extract_boost_label():
    facts = extract_nutrition_facts(
        "8 Fl oz Boost Glucose Control 190 Calories, 7g of Proteins, 16 g of "
        "Carbohydrates, 7g of Total Fat (1 g of Saturated fat), 210 mg of Sodium")
    assert facts is not None
    assert facts["nutrients"]["calories"] == 190
    assert facts["nutrients"]["protein_g"] == 7
    assert facts["nutrients"]["fat_g"] == 7  # not the saturated 1
    assert "boost" in facts["name"].lower()
    assert round(facts["serving_g"]) == 237  # 8 fl oz


def test_extract_returns_none_for_normal_meal():
    assert extract_nutrition_facts("2 eggs and a slice of toast") is None
    assert extract_nutrition_facts("0.75 cups of rice and beans, suya") is None


@pytest.mark.parametrize("text", ["unknown", "Unknown", "  unknown  ", "?", "n/a", "unspecified"])
def test_shell_entries_never_yield_fabricated_calories(text):
    """"unknown" is what the importer writes for a meal with no description —
    16 rows on this database. It reached USDA and the AI tier as if it were a
    dish, and a shell entry that acquires calories puts them inside a day's
    totals where nothing distinguishes them from food the patient ate."""
    from app.services.nutrient_estimator import _is_placeholder

    assert _is_placeholder(text)


@pytest.mark.parametrize("text", ["unknown pepper soup", "chin chin", "eba"])
def test_a_real_dish_is_not_mistaken_for_a_shell(text):
    from app.services.nutrient_estimator import _is_placeholder

    assert not _is_placeholder(text)


def test_a_tin_of_fish_is_not_a_drinks_can():
    """"1 can of Titus Sardines" parsed as 355 g — a soda can — instead of a
    ~120 g tin. That was one half of a meal that stored 3,892 kcal."""
    from app.services.meal_parser import parse_meal_text

    for text, ceiling in (("1 can of Titus Sardines", 200),
                          ("1 can of mackerel", 200),
                          ("1 can of coke", 400)):
        grams = sum(c.qty_g or 0 for c in parse_meal_text(text))
        if "coke" in text:
            assert grams > 300, "a drinks can is still a drinks can"
        else:
            assert grams <= ceiling, f"{text!r} parsed as {grams} g"


def test_the_writer_consults_the_estimators_own_verdict():
    """The estimator judges its own output — energy density at the meal level,
    category bands per component — and the background writer IGNORED the
    verdict, so a flagged estimate was stored as fact: 3,892 kcal with 394 g of
    fat, more fat than the meal weighed.

    A static check, because the write happens in its own session and a
    behavioural test of it proves less than reading the gate is there at all.
    """
    import inspect

    from app.services import nutrient_enrichment

    src = inspect.getsource(nutrient_enrichment)
    assert 'meal.get("believable") is False' in src, (
        "nutrient_enrichment must refuse an estimate the estimator flagged")
    gate = src.index('meal.get("believable") is False')
    after = src[gate:gate + 400]
    assert 'nutrient_status = "failed"' in after
    assert "return" in after, "a flagged estimate must not fall through to storage"


@pytest.mark.asyncio
async def test_an_impossible_meal_is_flagged_by_the_estimator(db):
    """The other half of the gate: the verdict has to be produced at all.
    Sardines resolving to ~900 kcal/100 g is denser than pure fat."""
    from app.services import plausibility

    # review_meal is what the writer's gate ultimately rests on.
    assert plausibility.review_meal(270.0, {"calories": 3892.0}), (
        "a meal denser than pure fat must be flagged")
    assert not plausibility.review_meal(270.0, {"calories": 400.0})
