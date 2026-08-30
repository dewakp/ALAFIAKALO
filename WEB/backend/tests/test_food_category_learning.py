"""What a food IS comes from an authority, and is remembered.

The band a food is judged against used to be guessed from its NAME by a keyword
list — spelling, not knowledge. USDA FoodData Central publishes a `foodCategory`
for every food it holds and we were discarding it, so:

    "hard boiled eggs"      b-OIL-ed        -> oil_fat, expected 700-902 kcal
    "ripe plantain boiled"  b-OIL-ed        -> oil_fat
    "black teabag"          no keyword      -> unknown

The loop is: know it? (cache) -> check (USDA generic, then Branded) -> store ->
learn. Keywords survive only for foods no authority knows, and anything resolved
that way is recorded as `category_source="keyword"` so a guess is never mistaken
for a lookup.

These tests do not call USDA. The network path is exercised by
`scripts/prove_ui_contracts.py` and by the estimator's own runs; here the
resolution RULES are pinned, which is what regressed.
"""

import pytest

from app.services.food_category_service import (
    band_for_usda_category, _content_tokens, _PREPARATION_WORDS, _MODIFIER_WORDS,
)


@pytest.mark.parametrize("usda_category,expected", [
    ("Fruits and Fruit Juices", "fruit_fresh"),
    ("Fats and Oils", "oil_fat"),
    ("Eggs and omelets", "egg"),
    ("Tea Bags", "tea_coffee"),                     # USDA Branded's own wording
    ("Vegetables and Vegetable Products", "vegetable"),
    ("Beef Products", "lean_meat"),
    ("Cereal Grains and Pasta", "grain_cooked"),
    ("Legumes and Legume Products", "legume_cooked"),
])
def test_usda_categories_map_onto_bands(usda_category, expected):
    assert band_for_usda_category(usda_category) == expected


def test_the_longest_bridge_entry_wins():
    """"Other starchy vegetables" must not be swallowed by "vegetables"."""
    assert band_for_usda_category("Other starchy vegetables") == "grain_cooked"
    assert band_for_usda_category("Vegetables and Vegetable Products") == "vegetable"


def test_an_unknown_category_resolves_to_nothing_rather_than_a_guess():
    assert band_for_usda_category("Something USDA Invented Tomorrow") is None
    assert band_for_usda_category(None) is None


def test_preparation_words_are_ignored_when_matching():
    """Boiling a plantain does not stop it being a fruit.

    Keeping them made "ripe plantain boiled" share one token in five with
    "Plantains, green, raw" — so the correct match was rejected as coincidence.
    """
    assert _content_tokens("ripe plantain boiled") == {"plantain"}
    assert "boiled" in _PREPARATION_WORDS


def test_a_colour_alone_cannot_carry_a_match():
    """"black teabag" scored 50% coverage against "Olives, black" on the word
    "black" and was filed as a vegetable."""
    assert _content_tokens("black teabag", drop_modifiers=True) == {"teabag"}
    # …but the CANDIDATE keeps its colour, so black beans still match beans.
    assert "black" in _content_tokens("Beans, black")
    assert "black" in _MODIFIER_WORDS


def test_the_food_word_survives_stripping():
    """Stripping must never leave an empty query, or everything matches."""
    for name in ("boiled eggs", "fresh tomatoes", "hard boiled egg"):
        assert _content_tokens(name, drop_modifiers=True), name


# ── The "store" half of check -> store -> learn ───────────────────────────

@pytest.mark.asyncio
async def test_a_category_is_remembered_even_for_a_food_with_no_cache_row(db):
    """The half that was described but not implemented.

    `resolve_band_category` wrote the category ONLY onto an existing
    `food_nutrient_cache` row, so a food never seen before had its answer
    thrown away and every later meal repeated the lookup — while the docstring
    claimed "every later meal with that food resolves without a lookup".
    """
    from sqlalchemy import select
    from app.models.food_category_cache import FoodCategoryCache
    from app.services.food_category_service import resolve_band_category

    name = "a food nothing has ever cached"
    assert (await db.execute(select(FoodCategoryCache).where(
        FoodCategoryCache.food_name_normalized == name))).scalar_one_or_none() is None

    first_band, first_source = await resolve_band_category(db, name)
    assert first_source in {"usda", "keyword"}

    stored = (await db.execute(select(FoodCategoryCache).where(
        FoodCategoryCache.food_name_normalized == name))).scalar_one_or_none()
    assert stored is not None, "the answer must be kept, not discarded"
    assert stored.band_category == first_band
    # A guess must never pass for a lookup.
    assert stored.source == first_source

    second_band, second_source = await resolve_band_category(db, name)
    assert second_source == "cache"
    assert second_band == first_band


@pytest.mark.asyncio
async def test_an_unknown_food_is_remembered_too(db):
    """Otherwise every meal re-queries USDA for a food it will never know."""
    from sqlalchemy import select
    from app.models.food_category_cache import FoodCategoryCache
    from app.services.food_category_service import resolve_band_category

    name = "zzz not a food at all qqq"
    await resolve_band_category(db, name)
    stored = (await db.execute(select(FoodCategoryCache).where(
        FoodCategoryCache.food_name_normalized == name))).scalar_one_or_none()
    assert stored is not None
    assert stored.band_category == "unknown"


@pytest.mark.asyncio
async def test_the_category_store_cannot_shadow_a_nutrient_lookup(db):
    """Kept apart from `food_nutrient_cache` on purpose: a category-only row
    written there would be an empty nutrient result sitting in front of a real
    lookup — canon 3c's "all-zero row counted as a hit"."""
    from sqlalchemy import select
    from app.models.food_nutrient_cache import FoodNutrientCache
    from app.services.food_category_service import resolve_band_category

    name = "another uncached food"
    await resolve_band_category(db, name)
    assert (await db.execute(select(FoodNutrientCache).where(
        FoodNutrientCache.food_name_normalized == name))).scalar_one_or_none() is None
