"""What a food IS — looked up from an authority, then remembered.

The band a food is judged against (and its default portion) used to come from a
hand-written keyword list matched against the food's NAME. That is guessing from
spelling, and it guessed wrong in ways that reached patients:

    "hard boiled eggs"      b-OIL-ed    -> oil_fat, expected 700-902 kcal/100 g
    "ripe plantain boiled"  b-OIL-ed    -> oil_fat
    "black teabag"          no keyword  -> unknown

USDA FoodData Central already publishes a `foodCategory` for every food it
holds. So the question "what kind of food is this?" has an authority, and the
answer only has to be found once:

    know it?  -> `food_nutrient_cache.band_category`, written by a previous run
    check     -> USDA search for the food name, take its `foodCategory`
    store     -> write it back to the cache row
    learn     -> every later meal with that food resolves without a lookup

The keyword list survives only as the last resort, for foods no authority knows,
and anything resolved that way is recorded as `category_source="keyword"` so a
guess is never mistaken for a lookup.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.food_nutrient_cache import FoodNutrientCache
from app.services import nutrition_reference

logger = logging.getLogger(__name__)


#: A bridge between two published taxonomies — USDA's food categories and the
#: band categories `nutrition_reference` prices. This is NOT a per-food list:
#: it is ~25 entries covering USDA's whole vocabulary, and a food never appears
#: in it. Matching is on a normalised substring so USDA's Foundation, SR Legacy
#: and FNDDS wordings ("Fruits and Fruit Juices" vs "Other starchy vegetables")
#: all land somewhere sensible.
_USDA_TO_BAND: tuple[tuple[str, str], ...] = (
    ("fats and oils", "oil_fat"),
    ("dairy and egg", "egg"),                 # refined below by the egg check
    ("egg", "egg"),
    ("cheese", "cheese"),
    ("milk", "dairy"),
    ("yogurt", "dairy"),
    ("legumes", "legume_cooked"),
    ("beans", "legume_cooked"),
    ("nut and seed", "nut_seed"),
    ("nuts", "nut_seed"),
    ("beef", "lean_meat"),
    ("pork", "fatty_meat"),
    ("poultry", "lean_meat"),
    ("finfish", "lean_meat"),
    ("shellfish", "lean_meat"),
    ("lamb, veal", "lean_meat"),
    ("sausages and luncheon", "fatty_meat"),
    ("cereal grains", "grain_cooked"),
    ("baked products", "bread_baked"),
    ("breakfast cereals", "cereal_dry"),
    ("starchy vegetables", "grain_cooked"),
    ("vegetables", "vegetable"),
    ("fruits", "fruit_fresh"),
    ("tea", "tea_coffee"),
    ("coffee", "tea_coffee"),
    ("water", "water"),
    ("beverages", "beverage"),
    ("alcoholic", "alcohol"),
    ("sweets", "sugar_sweet"),
    ("snacks", "snack_processed"),
    ("soups, sauces", "soup_stew"),
    ("spices and herbs", "condiment"),
    ("fast foods", "prepared_dish"),
    ("restaurant foods", "prepared_dish"),
    ("meals, entrees", "prepared_dish"),
    ("baby foods", "prepared_dish"),
)


def band_for_usda_category(usda_category: str | None) -> str | None:
    """Map USDA's own food category onto a band category, or None."""
    if not usda_category:
        return None
    text = usda_category.strip().lower()
    # Longest bridge entry wins, so "starchy vegetables" is not swallowed by
    # "vegetables" and "nut and seed" is not swallowed by a shorter entry.
    best: tuple[int, str] | None = None
    for needle, band in _USDA_TO_BAND:
        if needle in text and (best is None or len(needle) > best[0]):
            best = (len(needle), band)
    return best[1] if best else None


#: How a food was PREPARED or presented says nothing about what it is: boiling
#: a plantain does not stop it being a fruit. These words are dropped before a
#: category lookup so they cannot dilute the match — "ripe plantain boiled"
#: against "Plantains, green, raw" shares one token in five otherwise, and the
#: right answer is rejected as a coincidence.
#:
#: A closed, structural vocabulary of cooking methods and states. No food
#: appears in it.
_PREPARATION_WORDS = frozenset({
    "raw", "fresh", "frozen", "ripe", "unripe", "overripe", "green",
    "boiled", "boild", "fried", "grilled", "roasted", "baked", "steamed",
    "broiled", "sauteed", "sautéed", "stewed", "braised", "poached", "cooked",
    "hot", "cold", "iced", "warm", "chilled",
    "sliced", "chopped", "diced", "mashed", "shredded", "ground", "crushed",
    "whole", "half", "large", "medium", "small", "extra", "hard", "soft",
    "plain", "unsalted", "salted", "cup", "serving", "piece", "pieces",
})

#: Colours describe a variety, never the food itself, and on a short query one
#: can carry the whole match: "black teabag" scored 50% coverage against
#: "Olives, black" on the word "black" alone and was filed as a vegetable.
#: Dropped from the QUERY side only — "Beans, black" still matches a query for
#: beans, because the food word is what has to line up.
_MODIFIER_WORDS = frozenset({
    "black", "white", "red", "green", "yellow", "brown", "purple", "golden",
    "dark", "light", "pale",
})


def _content_tokens(text: str, *, drop_modifiers: bool = False) -> set[str]:
    """Stemmed food words, with preparation (and optionally colour) words removed.

    `drop_modifiers` applies to the QUERY side only: what the user named has to
    line up on the food itself, while the candidate keeps its colour so
    "Beans, black" still answers a query for black beans.
    """
    from app.services.nutrient_estimator import _tokenize_food_text, _stem
    ignore = _PREPARATION_WORDS | (_MODIFIER_WORDS if drop_modifiers else frozenset())
    return {
        _stem(t) for t in _tokenize_food_text(text)
        if t not in ignore and _stem(t) not in ignore
    }


async def reference_kcal_per_100g(db: AsyncSession, food_name: str) -> float | None:
    """What the AUTHORITY says this food's energy is, per 100 g.

    A category band is a coarse stand-in for this. It has to be coarse: one band
    covers every vegetable, so olives — which USDA files under "Olives, pickles,
    pickled vegetables" at ~289 kcal — fail a band of 8-130 built for lettuce
    and carrots, and a correct estimate gets reported as a wrong match.

    When USDA holds the food itself, its own energy is the better expectation,
    and it needs no taxonomy bridge. Returns None when nothing matches well
    enough, and the band is used instead.
    """
    name = _normalise(food_name)
    if not name:
        return None
    try:
        from app.core.nutrition_data import search_usda_foods

        query_tokens = _content_tokens(name, drop_modifiers=True)
        if not query_tokens:
            return None
        best: tuple[float, float] | None = None      # (jaccard, kcal)
        for hit in (await search_usda_foods(name)) or []:
            kcal = (hit.get("nutrients") or {}).get("calories")
            if kcal is None or kcal <= 0:
                continue
            desc_tokens = _content_tokens(hit.get("description") or "")
            if not desc_tokens:
                continue
            overlap = query_tokens & desc_tokens
            if len(overlap) / len(query_tokens) < 0.5:
                continue
            jaccard = len(overlap) / len(query_tokens | desc_tokens)
            if best is None or jaccard > best[0]:
                best = (jaccard, float(kcal))
        if best and best[0] >= 0.3:
            return best[1]
    except Exception:  # noqa: BLE001 - fall back to the band
        logger.warning("USDA reference energy lookup failed for %r", name, exc_info=True)
    return None


def _normalise(food_name: str) -> str:
    return " ".join((food_name or "").lower().split())


async def resolve_band_category(db: AsyncSession, food_name: str) -> tuple[str, str]:
    """The band category for a food, and how we came to know it.

    Returns ``(band_category, source)`` where source is "cache", "usda" or
    "keyword". Never raises: an unreachable USDA must not stop a meal being
    logged, so the keyword fallback stands in and is recorded as such.
    """
    name = _normalise(food_name)
    if not name:
        return "unknown", "keyword"

    # ── know it? ──────────────────────────────────────────────────────────
    from app.models.food_category_cache import FoodCategoryCache

    learned = (await db.execute(
        select(FoodCategoryCache).where(
            FoodCategoryCache.food_name_normalized == name)
    )).scalar_one_or_none()
    if learned is not None:
        learned.hit_count = (learned.hit_count or 0) + 1
        return learned.band_category, "cache"

    row = (await db.execute(
        select(FoodNutrientCache).where(
            FoodNutrientCache.food_name_normalized == name)
    )).scalar_one_or_none()
    if row is not None and row.band_category:
        return row.band_category, "cache"

    # ── check ─────────────────────────────────────────────────────────────
    usda_category: str | None = None
    band: str | None = None
    try:
        from app.core.nutrition_data import search_usda_foods

        hits = await search_usda_foods(name)

        # The BEST match decides, not the first one with a mappable category.
        # USDA ranks loosely: "black teabag" returns "Black Russian" (liquor)
        # above any tea, and "cherry tomatoes" returns "Cherries, raw" above
        # "Tomatoes, raw". Taking the first mappable hit adopted both.
        #
        # Scored the way canon 3c settled it — Jaccard, which counts the words
        # the CANDIDATE adds as well as those it shares, so a one-word query
        # cannot score full marks against an unrelated longer name.
        query_tokens = _content_tokens(name, drop_modifiers=True)
        best_score = 0.0
        for hit in hits or []:
            candidate = hit.get("food_category")
            mapped = band_for_usda_category(candidate)
            if not mapped:
                continue
            desc_tokens = _content_tokens(hit.get("description") or "")
            if not query_tokens or not desc_tokens:
                continue
            overlap = query_tokens & desc_tokens
            # Both directions must hold: the candidate has to cover the food the
            # user named, AND not be mostly words they never asked for. Overlap
            # alone let "cherry tomatoes" land on "Cherries, raw".
            covers = len(overlap) / len(query_tokens)
            jaccard = len(overlap) / len(query_tokens | desc_tokens)
            if covers < 0.5:
                continue
            if jaccard > best_score:
                best_score, usda_category, band = jaccard, candidate, mapped

        # Below this the "match" is a coincidence of one shared word.
        if best_score < 0.3:
            usda_category, band = None, None

        # ── check again, in the branded catalogue ─────────────────────────
        # The generic tables (Foundation / SR Legacy / FNDDS) hold whole foods,
        # so a packaged item is simply absent from them: "black teabag" has no
        # generic entry and fell through to the keyword list as unknown. USDA's
        # Branded dataType answers it directly — foodCategory "Tea Bags".
        if not band:
            from app.services.mcp_nutrition_server import search_branded_food
            branded = await search_branded_food(name)
            items = branded.get("results") if isinstance(branded, dict) else branded
            for hit in items or []:
                candidate = hit.get("food_category")
                mapped = band_for_usda_category(candidate)
                if not mapped:
                    continue
                desc_tokens = _content_tokens(hit.get("description") or "")
                if not query_tokens or not desc_tokens:
                    continue
                # A branded description carries brand, flavour and size the user
                # never typed, so Jaccard is the wrong bar here (canon 3c makes
                # the same allowance for branded lookups). Coverage of the food
                # the user named is what must hold.
                if len(query_tokens & desc_tokens) / len(query_tokens) >= 0.5:
                    usda_category, band = candidate, mapped
                    break
    except Exception:  # noqa: BLE001 - a lookup failure is not a logging failure
        logger.warning("USDA category lookup failed for %r", name, exc_info=True)

    source = "usda" if band else "keyword"
    if not band:
        band = nutrition_reference.classify(name)

    # ── store, so the next meal does not repeat the lookup ────────────────
    #
    # This used to write ONLY onto an existing `food_nutrient_cache` row, so a
    # food never seen before had its USDA answer thrown away and every later
    # meal repeated the lookup — the half of the loop that was described but
    # not implemented. `food_category_cache` gives the answer somewhere to live
    # regardless, without an empty nutrient row shadowing a real lookup.
    try:
        db.add(FoodCategoryCache(
            food_name_normalized=name,
            usda_food_category=usda_category,
            band_category=band,
            source=source,
        ))
        if row is not None:
            row.band_category = band
            row.usda_food_category = usda_category
            row.category_source = source
        await db.flush()
    except Exception:  # noqa: BLE001 - learning must never fail the request
        logger.warning("Could not store category for %r", name, exc_info=True)

    return band, source
