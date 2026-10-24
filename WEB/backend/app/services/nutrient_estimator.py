# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""Food → Nutrient estimation pipeline.

Strategy:
  1. Check local cache (food_nutrient_cache table)
  2. Search USDA FoodData Central
  3. Fall back to AI (Ollama local → OpenAI cloud)
  4. Cache AI results for app-wide reuse
"""

import json
import logging
import re
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.nutrition_data import (
    search_usda_foods,
    get_usda_food_detail,
    NUTRIENT_CATALOG,
    EXTENDED_NUTRIENTS,
)
from app.models.food_nutrient_cache import FoodNutrientCache
from app.services.mcp_nutrition_server import (
    search_branded_food as _mcp_search_branded,
    get_branded_food_detail as _mcp_get_branded_detail,
    search_open_food_facts as _mcp_search_off,
)

logger = logging.getLogger(__name__)


# All known nutrient keys for validation
_ALL_NUTRIENT_KEYS = {n["key"] for n in NUTRIENT_CATALOG + EXTENDED_NUTRIENTS}

# ── AI Prompt ─────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a clinical nutrition AI with expertise in global food composition databases.
Given a food name and optional serving size, estimate the nutrient content.

IMPORTANT: Return ALL nutrients PER 100 GRAMS of the food, regardless of any
serving size mentioned. Serving size info is context only.

Return ONLY a valid JSON object (no markdown, no commentary):
{
  "serving_size": "description of one standard serving",
  "serving_weight_g": <grams per standard serving>,
  "confidence": <0.0-1.0>,
  "nutrients": {
    "calories": <kcal per 100g>,
    "protein_g": <g>, "carbs_g": <g>, "fat_g": <g>,
    "fiber_g": <g>, "sugar_g": <g>,
    "saturated_fat_g": <g>, "trans_fat_g": <g>,
    "monounsaturated_fat_g": <g>, "polyunsaturated_fat_g": <g>,
    "omega3_g": <g>, "omega6_g": <g>,
    "cholesterol_mg": <mg>,
    "sodium_mg": <mg>, "potassium_mg": <mg>,
    "calcium_mg": <mg>, "iron_mg": <mg>, "magnesium_mg": <mg>,
    "zinc_mg": <mg>, "phosphorus_mg": <mg>, "copper_mg": <mg>,
    "manganese_mg": <mg>, "selenium_mcg": <mcg>, "iodine_mcg": <mcg>,
    "vitamin_a_iu": <IU>, "vitamin_c_mg": <mg>, "vitamin_d_iu": <IU>,
    "vitamin_e_mg": <mg>, "vitamin_k_mcg": <mcg>,
    "vitamin_b1_thiamine_mg": <mg>, "vitamin_b2_riboflavin_mg": <mg>,
    "vitamin_b3_niacin_mg": <mg>, "vitamin_b5_pantothenic_acid_mg": <mg>,
    "vitamin_b6_mg": <mg>, "vitamin_b7_biotin_mcg": <mcg>,
    "vitamin_b9_folate_mcg": <mcg>, "vitamin_b12_mcg": <mcg>,
    "choline_mg": <mg>,
    "water_ml": <ml>, "caffeine_mg": <mg>, "alcohol_g": <g>,
    "tryptophan_g": <g>, "threonine_g": <g>, "isoleucine_g": <g>,
    "leucine_g": <g>, "lysine_g": <g>, "methionine_g": <g>,
    "phenylalanine_g": <g>, "valine_g": <g>,
    "arginine_g": <g>, "histidine_g": <g>
  }
}

Guidelines:
- Use USDA SR Legacy / FNDDS as the primary reference.
- For West African / Nigerian foods (suya, garri, egusi, fufu, kpomo, dodo,
  jollof rice, moin moin, akara, kilishi, banga soup, etc.) use the
  West African Food Composition Table (WAFCT 2019).
- For South/East Asian foods use IFCT (India) or FAO regional tables.
- For complex dishes, estimate from typical ingredient proportions.
- Confidence: 0.90+ for well-documented staples with USDA entries;
  0.70-0.89 for ethnic/regional foods with published composition tables;
  0.50-0.69 for complex/mixed dishes estimated from recipes;
  <0.50 for highly variable or undocumented foods.
- Omit keys you cannot estimate. Do NOT guess wildly.
- Do NOT include any text outside the JSON object.
"""


def _normalize_food_name(name: str) -> str:
    """Lowercase, strip, collapse whitespace."""
    return re.sub(r"\s+", " ", name.strip().lower())


def _tokenize_food_text(text: str) -> set[str]:
    """Tokenize food text into lowercase alphanumeric tokens."""
    return {
        t
        for t in re.findall(r"[a-z0-9]+", text.lower())
        if len(t) >= 3
    }


def _stem(token: str) -> str:
    """Crude singular/plural stem so 'eggs'~'egg', 'crackers'~'cracker'."""
    return token[:-1] if len(token) > 3 and token.endswith("s") else token


# When a query is a bare food name, prefer the base/raw USDA entry and avoid
# processed variants (which are far more calorie-dense), e.g. "Banana, raw" (~89)
# over "Banana, baked" / "Bananas, dehydrated" (~160–346).
_RAW_TOKENS = {"raw", "fresh"}
_PROCESSED_TOKENS = {
    "baked", "candied", "dehydrated", "dried", "fried", "roasted", "toasted",
    "powder", "powdered", "juice", "canned", "sweetened", "syrup", "chip", "chips",
    "bread", "bean", "sauce", "cake", "pie", "jam", "jelly", "glazed", "battered",
    "breaded", "smoked", "cured", "fritter", "flour", "concentrate", "crisp",
}


def _rank_score(query: str, description: str | None, base_ratio: float) -> float:
    """Ranking score (higher = better): token overlap, + bonus for raw/base form,
    − penalty per processed descriptor not present in the query."""
    d = {_stem(t) for t in re.findall(r"[a-z0-9]+", (description or "").lower()) if len(t) >= 3}
    q = {_stem(t) for t in re.findall(r"[a-z0-9]+", query.lower()) if len(t) >= 3}
    bonus = 0.5 if d & _RAW_TOKENS else 0.0
    penalty = 0.15 * len((d & _PROCESSED_TOKENS) - q)
    return base_ratio + bonus - penalty


def _match_score(query: str, description: str | None) -> float | None:
    """Lexical relevance score for a USDA description, or None if it's not a match.

    A match REQUIRES the query's head noun (last meaningful token, ≈ the actual
    food) to be present, plus ≥50% token overlap. This stops e.g. 'cold water'
    from matching 'Oil, flaxseed, cold pressed' (they share only 'cold', not the
    head noun 'water'), which previously yielded 884 kcal/100 g for water.
    """
    if not description:
        return None
    q = [_stem(t) for t in re.findall(r"[a-z0-9]+", query.lower()) if len(t) >= 3]
    d = {_stem(t) for t in re.findall(r"[a-z0-9]+", description.lower()) if len(t) >= 3}
    if not q or not d:
        return None
    q_set = set(q)
    ratio = len(q_set & d) / len(q_set)
    head = q[-1]  # head noun ≈ the food itself (e.g. 'vinegar', 'water', 'thigh')
    if head not in d or ratio < 0.5:
        return None
    return ratio


def _is_relevant_usda_match(query: str, description: str | None) -> bool:
    """Return True when USDA description is a reasonably close lexical match."""
    return _match_score(query, description) is not None


# ── Cache layer ───────────────────────────────────────────────────────────────


async def _get_cached(db: AsyncSession, food_name: str) -> dict | None:
    """Look up a cached nutrient estimate by normalized food name."""
    normalized = _normalize_food_name(food_name)
    result = await db.execute(
        select(FoodNutrientCache).where(
            FoodNutrientCache.food_name_normalized == normalized
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        return None

    # Bump hit count (fire-and-forget)
    await db.execute(
        update(FoodNutrientCache)
        .where(FoodNutrientCache.id == row.id)
        .values(hit_count=FoodNutrientCache.hit_count + 1)
    )

    return {
        "source": row.source,
        "fdc_id": row.fdc_id,
        "ai_model": row.ai_model,
        # The record it resolved to when known; the typed name only for rows
        # written before that was recorded (ax001).
        "food_name": row.matched_name or row.food_name_original,
        "serving_size": row.serving_size,
        "serving_weight_g": row.serving_weight_g,
        "confidence": row.confidence,
        "nutrients": row.nutrients,
        "cached": True,
    }


async def _save_to_cache(
    db: AsyncSession,
    food_name: str,
    source: str,
    nutrients: dict,
    fdc_id: int | None = None,
    ai_model: str | None = None,
    serving_size: str | None = None,
    serving_weight_g: float | None = None,
    confidence: float = 1.0,
    matched_name: str | None = None,
) -> None:
    """Persist a nutrient estimate to the cache."""
    normalized = _normalize_food_name(food_name)
    entry = FoodNutrientCache(
        food_name_normalized=normalized,
        food_name_original=food_name.strip(),
        matched_name=(matched_name or None) and str(matched_name)[:512],
        source=source,
        fdc_id=fdc_id,
        ai_model=ai_model,
        serving_size=serving_size,
        serving_weight_g=serving_weight_g,
        nutrients=nutrients,
        confidence=confidence,
        hit_count=0,
    )
    db.add(entry)
    await db.flush()
    logger.info("Cached nutrient estimate for '%s' (source=%s)", food_name, source)


# ── USDA lookup ───────────────────────────────────────────────────────────────


def _merge_nutrients(results: list[dict]) -> dict[str, float]:
    """Combine nutrient maps from multiple matched items."""
    merged: dict[str, float] = {}
    for res in results:
        for key, value in (res.get("nutrients") or {}).items():
            if isinstance(value, (int, float)):
                merged[key] = round(merged.get(key, 0.0) + float(value), 4)
    return merged


class SourceUnavailable(Exception):
    """An authoritative source could not be ASKED — a 429, a timeout, a model
    outage behind the match verifier. Distinct from "asked, and it has no such
    food": reporting an outage as a miss let the AI tier's answer be cached as
    if USDA had nothing, and the cache never asked USDA again. A repair pass on
    2026-10-22 drew 4,157 USDA 429s in one run; every one of them used to
    become a permanent downgrade."""


# ── Reference authorities beyond USDA (WAFCT 2019, …) ──────────────────────
#
# `reference_foods` is small (WAFCT: 1,028 rows) and read on every new food, so
# it is held in memory and re-read every few minutes — a production load (the
# licence gate, see scripts/load_reference_foods.py) takes effect without a
# restart, and an empty table simply contributes no candidates.
_REFERENCE_TTL_S = 600.0
# Sources that hold ONE component, not a food's profile. Never offered as a
# match for what a food IS; consulted only to add what they measure.
_COMPONENT_SOURCES = {"phyfoodcomp_1_0"}
_reference_rows: list[dict] = []
_reference_loaded_at = float("-inf")


async def _reference_foods(db: AsyncSession | None) -> list[dict]:
    global _reference_rows, _reference_loaded_at
    import time
    if db is None or time.monotonic() - _reference_loaded_at < _REFERENCE_TTL_S:
        return _reference_rows
    from app.models.reference_food import ReferenceFood
    try:
        rows = (await db.execute(select(ReferenceFood))).scalars().all()
    except Exception:
        logger.warning("reference_foods unreadable — lookup continues without it", exc_info=True)
        return _reference_rows
    _reference_rows = [{
        "source": r.source, "code": r.code, "name_en": r.name_en,
        "scientific_name": r.scientific_name, "name_fr": r.name_fr,
        "food_group": r.food_group, "nutrients": r.nutrients or {},
        "biblio": r.biblio,
        "tokens": {_stem(t) for t in re.findall(r"[a-z0-9]+", " ".join(
            x for x in (r.name_en, r.scientific_name, r.name_fr) if x).lower()) if len(t) >= 3},
    } for r in rows]
    _reference_loaded_at = time.monotonic()
    return _reference_rows


def _reference_candidates(rows: list[dict], *queries: str, limit: int = 5,
                          component: bool = False) -> list[dict]:
    """Rows sharing words with any query, best overlap first. The model decides
    which (if any) IS the food; this only decides what it is shown.

    `component=False` offers whole-profile tables only (WAFCT); `True` offers
    only the single-component ones (PhyFoodComp)."""
    rows = [r for r in rows if (r["source"] in _COMPONENT_SOURCES) == component]
    q = {_stem(t) for qq in queries if qq
         for t in re.findall(r"[a-z0-9]+", qq.lower()) if len(t) >= 3}
    if not q:
        return []
    # Ties go to the PLAINEST entry: every WAFCT milk shares the word "milk",
    # and in row order the first is not cow's milk.
    scored = sorted(((len(q & r["tokens"]) / len(q), len(r["tokens"]), i, r)
                     for i, r in enumerate(rows) if q & r["tokens"]),
                    key=lambda x: (-x[0], x[1], x[2]))
    return [{
        "description": r["name_en"] + (f" ({r['scientific_name']})" if r["scientific_name"] else ""),
        "data_type": r["source"], "food_category": r["food_group"],
        "nutrients": r["nutrients"], "_reference": r,
    } for *_, r in scored[:limit]]


async def _add_phytate(db: AsyncSession | None, food_name: str, result: dict) -> None:
    """Best-effort, and that is ENFORCED here, not just stated: an error in an
    optional enrichment must never fail the food it decorates. A KeyError in
    the body below failed every estimate in production for four hours."""
    try:
        await _add_phytate_body(db, food_name, result)
    except Exception:
        logger.warning("Phytate enrichment failed for '%s' — profile kept without it",
                       food_name, exc_info=True)


async def _add_phytate_body(db: AsyncSession | None, food_name: str, result: dict) -> None:
    """Add phytate to a resolved profile from PhyFoodComp, when it has none.

    USDA carries no phytate. It binds iron and zinc, and phosphorus held as
    phytate is poorly absorbed — both matter on this record. Best-effort: a
    missing or unverifiable figure leaves the profile as it was."""
    nutrients = result.get("nutrients") or {}
    if "phytate_mg" in nutrients:
        return
    from app.services import food_match_verifier
    rows = await _reference_foods(db)
    cands = _reference_candidates(rows, food_name, result.get("food_name") or "",
                                  limit=8, component=True)
    if not cands:
        return
    try:
        pick = await food_match_verifier.choose(food_name, [
            {"description": c["description"] + (f" [{c['_reference'].get('biblio')}]" if c["_reference"].get("biblio") else ""),
             "data_type": c["data_type"], "nutrients": {}} for c in cands])
    except food_match_verifier.Unavailable:
        return
    if pick is None:
        return
    ref = cands[pick]["_reference"]
    for k in ("phytate_mg", "phytate_phosphorus_mg"):
        if k in ref["nutrients"]:
            nutrients[k] = ref["nutrients"][k]
    # Provenance on the RESULT, never in `nutrients`: meal aggregation scales
    # every value there by weight, and a string would break the arithmetic.
    result["phytate_source"] = f"{ref['source']}:{ref['code']}"
    result["nutrients"] = nutrients
    logger.info("Phytate for '%s' from %s (%s)", food_name, result["phytate_source"], ref["name_en"][:80])


async def _try_usda_single(food_name: str, db: AsyncSession | None = None) -> dict | None:
    """Look a food up in the composition AUTHORITIES — USDA and any loaded
    reference table — and return the record the model verifies IS the food.

    Returns None when no authority holds it; raises `SourceUnavailable` when one
    could not be asked AND nothing else answered."""
    reference = await _reference_foods(db)
    usda_down: Exception | None = None
    try:
        results = await search_usda_foods(food_name, page_size=5)
    except Exception as exc:
        logger.warning("USDA API call failed for '%s'", food_name, exc_info=True)
        results, usda_down = [], exc
    found = await _choose_usda(food_name, results, rewrite=True, reference=reference)
    if found is None and usda_down is not None:
        # USDA could not be asked and no reference table answered: an outage,
        # not an absence (§3bj).
        raise SourceUnavailable(f"usda: {type(usda_down).__name__}") from usda_down
    return found


async def _choose_usda(food_name: str, results: list[dict], rewrite: bool,
                       reference: list[dict] | None = None) -> dict | None:
    """Rank the retrieved candidates and let the model choose which IS the food.
    When none is, retrieve again under the database's own name for it — the
    first search only finds what the patient's spelling happens to share."""
    from app.services import food_match_verifier
    if not results and not rewrite:
        return None

    # Rank ALL candidates by lexical relevance (head-noun match + token overlap),
    # then prefer Foundation/SR Legacy, then USDA's own order. Picking the *best*
    # match — not merely the first SR Legacy row — prevents an incidental token
    # collision (e.g. 'cold') from selecting a wrong, calorie-dense food.
    scored = []
    for idx, r in enumerate(results):
        desc = r.get("description")
        ratio = _match_score(food_name, desc)
        if ratio is None:
            continue
        rank = _rank_score(food_name, desc, ratio)  # raw-bonus / processed-penalty

        # ── AN EMPTY RECORD MUST NEVER OUTRANK A COMPLETE ONE ──────────────
        #
        # This is what broke grapefruit, measured 2026-10-21. USDA returns TWO
        # rows called "Grapefruit, raw" and they tie on relevance:
        #
        #     Grapefruit, raw   Survey (FNDDS)    42 kcal   dt_pref 1
        #     Grapefruit, raw   Foundation       NO DATA    dt_pref 0   <- won
        #
        # The dataset preference sorted BEFORE "does this row carry numbers",
        # so the empty Foundation row won the tie, `_try_usda_single` returned
        # None, and the whole USDA rung failed. Grapefruit then fell through to
        # `_try_mcp_branded`, which answered with a sweetened 222 ml drink:
        # 45 kcal, 0 g protein, NO potassium, and 9.9 g of ADDED sugar in a
        # fruit that has none. On a dialysis record the silently missing
        # potassium is the worst part of that.
        #
        # Banana escaped only by luck — its FNDDS row had no empty twin.
        has_data = 0 if _has_any_substance(r.get("nutrients") or {}) else 1

        # Operator, 2026-10-21: *"FNDDS is more current, use it first."* A
        # clinician reaches for the current survey of what people actually eat
        # before the legacy reference tables, and FNDDS is also the dataset
        # that carries Added Sugars (usda 1235) — the quantity WHO and the FDA
        # actually legislate.
        dt_pref = {"Survey (FNDDS)": 0, "Foundation": 1, "SR Legacy": 2}.get(
            r.get("data_type"), 3)
        scored.append((has_data, -rank, dt_pref, idx, r))

    if not scored and not rewrite:
        logger.info("No relevant USDA match for '%s' (candidates: %s)",
                    food_name, [r.get("description") for r in results[:5]])
        return None

    scored.sort(key=lambda x: (x[0], x[1], x[2], x[3]))

    # ── THE MODEL CHOOSES WHICH RECORD IS THE FOOD ─────────────────────────
    #
    # Lexical relevance only asks whether the typed words occur somewhere in
    # the description, so "sardines" scored a perfect 1.0 against "Fish oil,
    # sardine" and was cached as 902 kcal / 100 g fat / 0 protein for four
    # months; "milk" did the same against "Crackers, milk". The 2026-10-22
    # audit found 46% of linked rows were a different food. The ranking above
    # still decides which candidates are SHOWN; `food_match_verifier` decides
    # which one, if any, is the food. Empty records are never offered.
    offered = [x[-1] for x in scored if x[0] == 0][:5]
    # Candidates from the reference tables sit BESIDE USDA's in one choice, so
    # "bitter leaf" is judged with Vernonia and bitter gourd side by side —
    # asked separately, USDA's bitter gourd was accepted before Vernonia was
    # ever seen.
    offered += _reference_candidates(reference or [], food_name)
    try:
        pick = await food_match_verifier.choose(food_name, [
            {"description": r.get("description"), "data_type": r.get("data_type"),
             "category": r.get("food_category"), "nutrients": r.get("nutrients") or {}}
            for r in offered]) if offered else None
        if pick is None and rewrite:
            names = await food_match_verifier.standard_name(food_name)
            if names:
                standard = names[0]
                try:
                    more = await search_usda_foods(standard, page_size=5)
                except Exception as exc:
                    raise SourceUnavailable(f"usda: {type(exc).__name__}") from exc
                seen = {r.get("fdc_id") for r in offered if r.get("fdc_id")}
                seen_ref = {id(r.get("_reference")) for r in offered if r.get("_reference")}
                # The NEW candidates go first: the first round's were already
                # judged not to be the food, and with two authorities they fill
                # the cap on their own — appended last, "Watermelon, raw" was
                # retrieved and then truncated away.
                pool = [r for r in more if r.get("fdc_id") not in seen] + [
                    r for r in _reference_candidates(reference or [], *names)
                    if id(r["_reference"]) not in seen_ref] + offered
                # Relevance is judged against the DATABASE name now, so the
                # second list is not discarded for sharing no words with the
                # patient's spelling ("paw paw" vs "Papaya, raw").
                return await _choose_usda_pool(food_name, standard, pool)
    except food_match_verifier.Unavailable as exc:
        raise SourceUnavailable(f"verifier: {exc}") from exc
    if pick is None:
        logger.info("No USDA candidate verified as '%s' (offered: %s)",
                    food_name, [r.get("description") for r in offered])
        return None
    return await _usda_result(offered[pick], food_name)


async def _choose_usda_pool(food_name: str, standard: str, pool: list[dict]) -> dict | None:
    from app.services import food_match_verifier
    pool = [r for r in pool if _has_any_substance(r.get("nutrients") or {})][:10]
    if not pool:
        return None
    pick = await food_match_verifier.choose(food_name, [
        {"description": r.get("description"), "data_type": r.get("data_type"),
         "category": r.get("food_category"), "nutrients": r.get("nutrients") or {}}
        for r in pool])
    if pick is None:
        logger.info("No USDA candidate verified as '%s' (searched also as %r)", food_name, standard)
        return None
    return await _usda_result(pool[pick], food_name)


async def _usda_result(best: dict, food_name: str) -> dict | None:
    ref = best.get("_reference")
    if ref is not None:
        return {
            "source": ref["source"], "fdc_id": None, "ai_model": None,
            "food_name": ref["name_en"], "reference_code": ref["code"],
            "serving_size": "100 g", "serving_weight_g": 100.0, "confidence": 1.0,
            "nutrients": dict(ref["nutrients"]), "cached": False,
        }

    # If the best result has very few nutrients, try getting full detail.
    nutrients = best.get("nutrients", {})
    fdc_id = best.get("fdc_id")
    if fdc_id and len(nutrients) < 10:
        try:
            detail = await get_usda_food_detail(fdc_id)
            if detail:
                nutrients = detail["nutrients"]
        except Exception:
            pass

    if not nutrients or "calories" not in nutrients:
        return None

    return {
        "source": "usda",
        "fdc_id": fdc_id,
        "ai_model": None,
        "food_name": best.get("description", food_name),
        "serving_size": f'{best.get("serving_size", 100)} {best.get("serving_size_unit", "g")}',
        "serving_weight_g": best.get("serving_size") or 100.0,
        "confidence": 1.0,
        "nutrients": nutrients,
        "cached": False,
    }


def _is_relevant_branded_match(query: str, description: str | None) -> bool:
    """Looser relevance check for branded/OTC products.

    Requires 30% token overlap (vs 50% for generic USDA) because branded
    descriptions often include UPC codes, sizes, and flavour suffixes that
    are not in the user's query (e.g. query "boost glucose control" matches
    "BOOST GLUCOSE CONTROL, VERY VANILLA, UPC: 041679301163").
    """
    if not description:
        return False
    query_tokens = _tokenize_food_text(query)
    desc_tokens = _tokenize_food_text(description)
    if not query_tokens or not desc_tokens:
        return False
    overlap = query_tokens.intersection(desc_tokens)
    if len(overlap) / len(query_tokens) < 0.30:
        return False

    # …and the product must not be mostly words the user did not ask for.
    #
    # Measuring only overlap/query lets a ONE-WORD dish name score 100% against
    # any packaged product containing it: "vindaloo" matched a simmer sauce and
    # answered 80 kcal / 1.6 g protein for a goat curry, with confidence 1.0 — so
    # the AI tier that actually knows what a vindaloo is was never reached.
    # Jaccard counts the words the product adds as well as the ones it shares,
    # which costs nothing on a real product match ("boost glucose control" against
    # "BOOST Glucose Control, Very Vanilla" still clears it) and rejects a generic
    # dish name landing on a branded jar.
    union = query_tokens | desc_tokens
    return len(overlap) / len(union) >= 0.50


async def _try_mcp_branded(food_name: str) -> dict | None:
    """Try MCP-tier branded food lookup.

    Pipeline:
      1. USDA FDC Branded Foods search
      2. If no USDA Branded match → Open Food Facts search
    """
    # ── Step 1: USDA Branded Foods ────────────────────────────────────────
    unavailable: list[str] = []
    try:
        branded_results = await _mcp_search_branded(food_name, max_results=8)
    except Exception as exc:
        logger.warning("MCP branded search error for '%s'", food_name, exc_info=True)
        branded_results = []
        unavailable.append(f"branded: {type(exc).__name__}")

    # Candidates are gathered first and the model chooses among them
    # (`food_match_verifier`): "paw paw" passed the lexical rule against "PAW
    # FAN WITH CANDY" and "to taste" against butter biscuits. 106 of 256 cached
    # branded rows were judged not credible for their name.
    offered: list[tuple[dict, dict]] = []
    for item in branded_results:
        desc = item.get("description", "")
        if not _is_relevant_branded_match(food_name, desc):
            continue
        nutrients = item.get("nutrients") or {}
        fdc_id = item.get("fdc_id")

        # If nutrients are sparse, fetch full detail
        if fdc_id and len(nutrients) < 8:
            try:
                detail = await _mcp_get_branded_detail(fdc_id)
                if detail:
                    nutrients = detail["nutrients"]
            except Exception:
                pass

        if not nutrients or "calories" not in nutrients:
            continue

        # An all-zero record is an EMPTY record, not a food with no calories.
        # "goat meat vindaloo" matched a branded row whose every nutrient was
        # 0.0, so the dish contributed nothing and a rice-and-curry dinner logged
        # as 108 kcal — the meal looked light instead of looking unresolved.
        # §3aa's rule applied to a nutrient profile: silence is not a value.
        if not _has_any_substance(nutrients):
            logger.info("Ignoring all-zero branded match for '%s' (fdc_id=%s)",
                        food_name, fdc_id)
            continue
        offered.append((item, nutrients))
        if len(offered) == 5:
            break

    from app.services import food_match_verifier
    try:
        pick = await food_match_verifier.choose(food_name, [
            {"description": it.get("description"), "data_type": "Branded",
             "brand": it.get("brand_owner") or it.get("brand_name"), "nutrients": nu}
            for it, nu in offered]) if offered else None
    except food_match_verifier.Unavailable as exc:
        pick = None
        unavailable.append(f"verifier: {exc}")
    if pick is not None:
        item, nutrients = offered[pick]
        desc = item.get("description", "")
        fdc_id = item.get("fdc_id")
        serving_size = item.get("serving_size")
        serving_unit = item.get("serving_size_unit") or ""
        serving_str = (
            f"{serving_size} {serving_unit}".strip() if serving_size else None
        )
        logger.info(
            "MCP Branded USDA match for '%s': '%s' (fdc_id=%s)",
            food_name, desc, fdc_id,
        )
        return {
            "source": "mcp_branded_usda",
            "fdc_id": fdc_id,
            "ai_model": None,
            "food_name": desc,
            "serving_size": serving_str,
            "serving_weight_g": serving_size,
            "confidence": 1.0,
            "nutrients": nutrients,
            "cached": False,
        }

    # ── Step 2: Open Food Facts fallback ──────────────────────────────────
    try:
        off_results = await _mcp_search_off(food_name, max_results=5)
    except Exception as exc:
        logger.warning("MCP Open Food Facts error for '%s'", food_name, exc_info=True)
        off_results = []
        unavailable.append(f"open_food_facts: {type(exc).__name__}")

    off_offered = []
    for item in off_results:
        name = item.get("product_name", "") or item.get("brands", "")
        combined = f"{item.get('brands', '')} {name}"
        if not _is_relevant_branded_match(food_name, combined):
            continue
        nutrients = item.get("nutrients") or {}
        if not nutrients or "calories" not in nutrients or not _has_any_substance(nutrients):
            continue
        off_offered.append((item, name, nutrients))

    try:
        pick = await food_match_verifier.choose(food_name, [
            {"description": nm, "data_type": "Open Food Facts", "brand": it.get("brands"),
             "nutrients": nu} for it, nm, nu in off_offered]) if off_offered else None
    except food_match_verifier.Unavailable as exc:
        pick = None
        unavailable.append(f"verifier: {exc}")
    if pick is not None:
        item, name, nutrients = off_offered[pick]
        logger.info(
            "MCP Open Food Facts match for '%s': '%s'",
            food_name, name,
        )
        return {
            "source": "mcp_open_food_facts",
            "fdc_id": None,
            "ai_model": None,
            "food_name": name,
            "serving_size": item.get("serving_size"),
            "serving_weight_g": None,
            "confidence": 0.92,
            "nutrients": nutrients,
            "cached": False,
        }

    if unavailable:
        raise SourceUnavailable("; ".join(unavailable))
    return None


async def _try_usda(food_name: str, db: AsyncSession | None = None) -> dict | None:
    """Search USDA for the phrase as ONE food.

    This used to fall back to splitting a mixed description into items and
    SUMMING their per-100 g profiles into one "per-100 g" — arithmetic that can
    never describe 100 g of anything (§3c). It cached "bitter leaves/uziza/
    egusi/peanut/palm…" at 1,180 kcal and 113.7 g fat per 100 g, above pure fat,
    and "basmati rice + sardines + …" at 2,472 kcal. A meal is resolved by
    `estimate_meal_nutrients`, which scales each item by its own weight; a
    composite NAME that reaches this single-food path falls through to the
    tiers that can describe a dish.
    """
    return await _try_usda_single(food_name, db)


# ── AI estimation ─────────────────────────────────────────────────────────────


# TODO(alafia-model): replace with ALAFIAModel.NLM nutrient lookup — Phase 4
async def _try_ai(food_name: str, serving_size: str | None = None) -> dict | None:
    """Estimate nutrients via the ALAFIAModel router (Ollama local → OpenAI fallback)."""
    user_msg = f"Food: {food_name}"
    if serving_size:
        user_msg += f"\nServing: {serving_size}"

    from app.services.alafia_model_service import alafia_chat, ALAFIAModelError

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ]
    try:
        raw = await alafia_chat(messages, temperature=0.3, max_tokens=1500, json_mode=True)
    except ALAFIAModelError:
        logger.debug("ALAFIAModel LLM unavailable for nutrient estimation", exc_info=True)
        return None

    return _parse_ai_response(raw, "alafia-model")


def _parse_ai_response(raw: str, model: str) -> dict | None:
    """Parse and validate the AI JSON response."""
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        # Try to extract JSON from markdown code blocks
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(1))
            except json.JSONDecodeError:
                logger.warning("AI returned unparseable response: %s", raw[:200])
                return None
        else:
            logger.warning("AI returned unparseable response: %s", raw[:200])
            return None

    nutrients = parsed.get("nutrients", {})
    if not nutrients or not isinstance(nutrients, dict):
        return None

    # Filter to only known nutrient keys and valid numeric values
    clean_nutrients: dict[str, float] = {}
    for k, v in nutrients.items():
        if k in _ALL_NUTRIENT_KEYS and isinstance(v, (int, float)) and v >= 0:
            clean_nutrients[k] = round(float(v), 4)

    if "calories" not in clean_nutrients:
        return None

    confidence = parsed.get("confidence", 0.6)
    if not isinstance(confidence, (int, float)):
        confidence = 0.6
    confidence = max(0.0, min(1.0, float(confidence)))

    return {
        "source": "ai",
        "fdc_id": None,
        "ai_model": model,
        "food_name": parsed.get("food_name") or "",
        "serving_size": parsed.get("serving_size"),
        "serving_weight_g": parsed.get("serving_weight_g"),
        "confidence": confidence,
        "nutrients": clean_nutrients,
        "cached": False,
    }


# ── Curated overrides ───────────────────────────────────────────────────────
# Common, easily-mismatched items (esp. zero-calorie drinks) that the USDA/branded
# APIs and small LLMs get badly wrong — e.g. plain water matching "Cold Water
# Lobster" or flaxseed oil. These are authoritative and checked FIRST.

# Words that may decorate "water" without changing that it's 0-kcal water.
_WATER_MODIFIERS = {
    "a", "some", "glass", "glasses", "cup", "cups", "of", "cold", "warm", "hot",
    "iced", "ice", "tap", "room", "temperature", "sparkling", "mineral", "filtered",
    "distilled", "plain", "fresh", "chilled", "bottle", "bottled", "bottles", "with",
}


_PLACEHOLDER_RE = re.compile(
    r"^\s*(meal\s*\d*|snack|breakfast|lunch|dinner|food|n/?a|none|nil|test|"
    r"same as (the )?previous.*|see (above|previous).*|leftover|unspecified|"
    # "unknown" is what the mobile importer writes when a meal arrives with no
    # description — 16 rows on this database. It reached USDA and the AI tier as
    # if it were a dish, which is exactly how a shell entry acquires fabricated
    # calories that then sit inside a day's totals.
    r"unknown|tbd|\?|--?)\s*$",
    re.IGNORECASE,
)


def _is_placeholder(text: str) -> bool:
    """True for non-food / shell entries that must not yield fabricated calories."""
    return not text or not text.strip() or bool(_PLACEHOLDER_RE.match(text.strip()))


def _curated_lookup(food_name: str) -> tuple[str, dict] | None:
    """Return (canonical_label, per-100g nutrients) for a curated food, else None."""
    toks = re.findall(r"[a-z]+", food_name.lower())
    if not toks:
        return None
    # Any mix of modifiers + "water" (cold/tap/sparkling/glass of water, …) → 0 kcal.
    # Guarded so "coconut water", "tonic water", "water spinach", "watermelon" are
    # NOT treated as plain water (they carry calories / are different foods).
    if "water" in toks and all(t == "water" or t in _WATER_MODIFIERS for t in toks):
        return ("Water", {"calories": 0.0, "protein_g": 0.0, "carbs_g": 0.0,
                          "fat_g": 0.0, "sugar_g": 0.0, "fiber_g": 0.0, "water_ml": 100.0})

    # Composite / regional dishes + generic beverages/eggs USDA matches poorly are
    # curated as DATA in app/data/regional_dishes.json (add new dishes there, not here).
    # Prepared forms ("scrambled eggs") that aren't listed fall through to USDA.
    from app.services import curated_foods
    return curated_foods.lookup(food_name)


# ── Public API ────────────────────────────────────────────────────────────────


def _has_any_substance(nutrients: dict) -> bool:
    """True when a profile carries a non-zero macro.

    A record of all zeros contributes nothing to a meal while looking like a
    successful lookup — the worst kind of miss, because it is indistinguishable
    from a genuinely calorie-free food until the totals come out wrong.
    """
    for key in ("calories", "protein_g", "carbs_g", "fat_g"):
        value = nutrients.get(key)
        if isinstance(value, (int, float)) and value > 0:
            return True
    return False


async def estimate_nutrients(
    db: AsyncSession,
    food_name: str,
    serving_size: str | None = None,
) -> dict[str, Any]:
    """Estimate nutrients for a food, then run the believability guardrail.

    Wraps the lookup pipeline (learned → curated → cache → USDA → branded → AI)
    with a plausibility review so impossible values never reach the user.
    """
    from app.services import plausibility
    from app.services.food_aliases import canonicalize
    from app.services.meal_parser import extract_nutrient_facts

    # Facts the user stated about the food are NOT part of its name. The pre-save
    # suggestion posts the whole description as one food_name, so
    # "Nounos Yogurt with 170 mg calcium, 210 potassium, 6g fat, 14 g carbohydrate"
    # was looked up verbatim — nothing matches that, and the fallback answered
    # with a different product's numbers (494 kcal) while the user's own figures
    # sat unread in the string.
    clean_name, stated = extract_nutrient_facts(food_name)
    display_name = clean_name or food_name

    # Locale normalization: map non-English / regional names to an English head-noun
    # for lookup (e.g. "arroz"→rice, "jollof"→jollof rice). Display keeps the original.
    lookup_name = canonicalize(display_name)
    result = await _estimate_nutrients_impl(db, lookup_name, serving_size)

    if stated and isinstance(result, dict):
        # Report them verbatim, per SERVING as the user stated them. They are not
        # merged into `nutrients` (which is per-100 g) — mixing the two bases is
        # how a 150 g yogurt turns into a four-figure calorie count.
        result["stated_nutrients"] = dict(stated)
        result["stated_food_name"] = display_name
    if isinstance(result, dict) and isinstance(result.get("nutrients"), dict):
        # Resolve what this food IS before judging its calories: know it? ->
        # check USDA -> store -> learn (services/food_category_service.py).
        from app.services.food_category_service import (
            resolve_band_category, reference_energy_range,
        )
        try:
            resolved_category, _src = await resolve_band_category(db, lookup_name)
            reference_range = await reference_energy_range(db, lookup_name)
        except Exception:  # noqa: BLE001 - never fail a lookup over a category
            resolved_category, reference_range = None, None
        corrected, warnings, believable = plausibility.review(
            lookup_name, result["nutrients"],
            category=resolved_category, reference_range=reference_range)
        result["nutrients"] = corrected

        # ── FREE sugars: the quantity WHO and the FDA actually legislate ────
        #
        # Derived here because this is the one place that already knows what
        # the food IS (`resolved_category`) as well as what it contains. The
        # alternative — reading `added_sugars_g` — was measured and cannot
        # work: USDA serves nutrient 1235 for Branded foods only, so it is
        # absent from every FNDDS and SR Legacy food. See
        # services/free_sugars.py for both definitions and the measurement.
        #
        # Both keys are per 100 g like everything else in `nutrients`, so the
        # meal path scales and sums them with no special case.
        try:
            from app.services.free_sugars import free_sugars_for

            # The name the USER typed decides a WHO-named source, not the
            # canonicalised lookup name: "1 cup of orange juice" canonicalises
            # toward "orange", and WHO counts juice sugars as free while whole
            # fruit's are excluded. Losing the word loses the distinction.
            share = free_sugars_for(
                band=resolved_category,
                total_sugars_g=corrected.get("sugar_g"),
                added_sugars_g=corrected.get("added_sugars_g"),
                food_name=f"{display_name} {lookup_name}",
            )
            if share.grams is not None:
                corrected["free_sugars_g"] = round(share.grams, 4)
            else:
                # Never written as 0: a composite dish's sugars are not known
                # to be intrinsic, and a zero here would read as a measured
                # absence on the one screen a diabetic uses (§3aa).
                corrected["free_sugars_unassessed_g"] = round(share.unassessed_g, 4)
            result["free_sugars_basis"] = share.basis
            result["free_sugars_reason"] = share.reason
        except Exception:  # noqa: BLE001 - never fail a lookup over a derivation
            logger.exception("Free-sugar share could not be derived for '%s'",
                             food_name)

        if warnings:
            result["plausibility_warnings"] = warnings
            result["believable"] = believable
            if not believable:
                result["confidence"] = min(float(result.get("confidence", 1.0)), 0.4)
            logger.warning("Plausibility review for '%s': believable=%s issues=%s",
                           food_name, believable, warnings)
    return result


async def _estimate_nutrients_impl(
    db: AsyncSession,
    food_name: str,
    serving_size: str | None = None,
) -> dict[str, Any]:
    """
    Estimate nutrients for a food.

    Pipeline: Cache → USDA → AI → Cache AI result.

    Returns dict with keys:
        source, fdc_id, ai_model, food_name, serving_size,
        serving_weight_g, confidence, nutrients, cached
    """
    # -1. Learned values (user-verified corrections) — highest authority.
    from app.services.learned_nutrient_service import get_learned
    learned = await get_learned(db, food_name)
    if learned:
        logger.info("Learned nutrient match for '%s'", food_name)
        return learned

    # 0. Curated overrides (authoritative for common, often-mismatched items).
    curated = _curated_lookup(food_name)
    if curated:
        label, nutrients = curated
        logger.info("Curated nutrient match for '%s' -> '%s'", food_name, label)
        return {
            "source": "curated", "fdc_id": None, "ai_model": None,
            "food_name": label, "serving_size": "100 g", "serving_weight_g": 100.0,
            "confidence": 1.0, "nutrients": nutrients, "cached": False,
        }

    # 1. Check cache
    cached = await _get_cached(db, food_name)
    if cached:
        logger.info("Cache HIT for '%s' (source=%s)", food_name, cached["source"])
        return cached

    # Self-correcting source selection: prefer the first candidate whose calorie
    # density fits the food's category band; keep out-of-band ones only as a last
    # resort. This generalizes the per-food fixes — a wrong USDA/branded match
    # (rice→dry, Boost→522/serving, suya→peanut) is rejected for a better source.
    from app.services import nutrition_reference

    def _in_band(res: dict) -> bool:
        try:
            cal = float((res.get("nutrients") or {}).get("calories"))
        except (TypeError, ValueError):
            return True  # no calories to judge → don't block
        return nutrition_reference.kcal_in_band(food_name, cal)

    fallbacks: list[dict] = []

    # A profile that is physically impossible is not an estimate, whichever
    # tier produced it, and is never returned or cached. `plausibility.review`
    # always held these checks — above pure fat, macros over 100 g, energy that
    # contradicts its own macros — and nothing applied them before a tier's
    # answer was written to the shared cache. The 2026-10-22 audit found 66
    # cached profiles that fail on arithmetic alone.
    from app.services import plausibility

    def _possible(res: dict | None, tier: str) -> dict | None:
        if not res:
            return None
        _, warnings, ok = plausibility.review(food_name, res.get("nutrients") or {})
        if not ok:
            logger.warning("Rejected impossible %s profile for '%s': %s",
                           tier, food_name, "; ".join(warnings))
            return None
        return res

    # An authority that could not be ASKED is not one that said no. Its
    # absence may still be answered by a lower tier, but that answer is NOT
    # cached: caching it would make a rate limit a permanent verdict.
    unavailable: list[str] = []

    async def _ask(tier):
        try:
            return await tier(food_name)
        except SourceUnavailable as exc:
            unavailable.append(str(exc))
            return None

    # 2. USDA Foundation / SR Legacy / FNDDS
    # A match the model VERIFIED against an authority's own record is not
    # second-guessed by the keyword category band. That band classifies by
    # WORDS: "water melon" fell in a 0-5 kcal "water" band and the verified
    # "Watermelon, raw" (30 kcal) was refused; "sardines in olive oil" fell in
    # an oil band and real sardines (208 kcal) were refused. Measured
    # 2026-10-23 in the production repair: 11 foods stalled this way. The
    # physical checks in `_possible` still apply to every tier; the band
    # remains only on the AI estimate, which is a guess, not a record.
    usda_result = _possible(await _ask(lambda n: _try_usda(n, db)), "usda")
    if usda_result:
        await _add_phytate(db, food_name, usda_result)
        await _save_to_cache(db, food_name, source=usda_result["source"], nutrients=usda_result["nutrients"],
                             fdc_id=usda_result["fdc_id"], serving_size=usda_result["serving_size"],
                             serving_weight_g=usda_result["serving_weight_g"], confidence=1.0,
                             matched_name=usda_result.get("food_name"))
        return usda_result

    # 3. Branded (Boost/Ensure/Gatorade/OTC) via MCP (USDA Branded → Open Food Facts)
    mcp_result = _possible(await _ask(_try_mcp_branded), "branded")
    if mcp_result:
        await _add_phytate(db, food_name, mcp_result)
        await _save_to_cache(db, food_name, source=mcp_result["source"], nutrients=mcp_result["nutrients"],
                             fdc_id=mcp_result.get("fdc_id"), serving_size=mcp_result.get("serving_size"),
                             serving_weight_g=mcp_result.get("serving_weight_g"), confidence=mcp_result["confidence"],
                             matched_name=mcp_result.get("food_name"))
        return mcp_result

    # 4. AI fallback (escalated when USDA/branded were missing or out-of-band).
    ai_result = _possible(await _try_ai(food_name, serving_size), "ai")
    if ai_result:
        if not ai_result.get("food_name"):
            ai_result["food_name"] = food_name
        if unavailable and (_in_band(ai_result) or not fallbacks):
            logger.warning("Not caching AI estimate for '%s' — an authority was unavailable (%s)",
                           food_name, "; ".join(unavailable))
            ai_result["authority_unavailable"] = list(unavailable)
            return ai_result
        if _in_band(ai_result) or not fallbacks:
            await _add_phytate(db, food_name, ai_result)
            await _save_to_cache(db, food_name, source="ai", nutrients=ai_result["nutrients"],
                                 ai_model=ai_result["ai_model"], serving_size=ai_result.get("serving_size"),
                                 serving_weight_g=ai_result.get("serving_weight_g"), confidence=ai_result["confidence"])
            return ai_result
        fallbacks.append(ai_result)

    # 5. No source fit the band → return the best candidate, flagged low-confidence
    #    (NOT cached as authoritative, so learning/corrections can override it).
    if fallbacks:
        best = max(fallbacks, key=lambda r: float(r.get("confidence", 0) or 0))
        best["confidence"] = min(float(best.get("confidence", 1.0) or 1.0), 0.4)
        best["out_of_band"] = True
        if unavailable:
            best["authority_unavailable"] = list(unavailable)
        logger.warning("All sources out of band for '%s' — returning best flagged candidate", food_name)
        # Log the miss for review/learning (never let flagging break estimation).
        try:
            from app.services.flagged_estimate_service import record_flagged
            await record_flagged(db, food_name, best, reason="out_of_band")
        except Exception:  # pragma: no cover — defensive
            logger.debug("flagged-estimate logging skipped for '%s'", food_name, exc_info=True)
        return best

    # 6. Nothing worked
    logger.warning("No nutrient data found for '%s'", food_name)
    return {
        "authority_unavailable": list(unavailable) or None,
        "source": None,
        "fdc_id": None,
        "ai_model": None,
        "food_name": food_name,
        "serving_size": serving_size,
        "serving_weight_g": None,
        "confidence": 0.0,
        "nutrients": {},
        "cached": False,
    }


async def _learn_stated(db: AsyncSession, food_name: str, stated: dict,
                        serving_weight_g: float | None, user_id: int | None = None) -> None:
    """Remember what the user told us, so the NEXT lookup starts from their numbers.

    Correcting a meal used to teach identification only: `/ai/vision/feedback`
    writes the vision corpus (`food_training_samples`) and never touches
    `learned_food_nutrients`, which is the one table `get_learned` consults. So
    "ALAFIA learned the right foods" was literally true and nutritionally
    useless — the next estimate re-derived everything from scratch and answered
    with a different product's numbers.

    Only learned when the serving weight is KNOWN and credible. Stated values are
    per serving; storing them as per-100 g without a weight would bake in a
    silent scaling error, which is worse than not learning at all.
    """
    if not stated or not serving_weight_g or serving_weight_g < 5:
        return
    factor = 100.0 / float(serving_weight_g)
    per100 = {k: round(v * factor, 4) for k, v in stated.items()
              if isinstance(v, (int, float))}
    try:
        from app.services import plausibility
        from app.services.learned_nutrient_service import record_correction
        reviewed, _warnings, believable = plausibility.review(food_name, per100)
        if not believable:
            logger.info("Not learning %r — stated values failed the plausibility review", food_name)
            return
        await record_correction(db, food_name, reviewed,
                                serving_weight_g=round(float(serving_weight_g), 1),
                                user_id=user_id, source="user_correction")
        logger.info("Learned %r from stated values (%.0f g serving)", food_name, serving_weight_g)
    except Exception:
        # Learning is best-effort and must never break the estimate itself.
        logger.exception("Could not record stated nutrients for %r", food_name)


_PLACEHOLDER_QTY_RE = re.compile(r"(?:default|\d+(?:\.\d+)?|\.\d+|\d+/\d+|half|quarter)", re.I)
_portion_cache: dict[int, list[dict]] = {}


def _weight_is_placeholder(qty_text: str | None) -> bool:
    """The parser stated no weight: "default" (no amount at all) or a bare
    count with a unit it does not know ("2" for "2 sachets")."""
    return bool(qty_text) and bool(_PLACEHOLDER_QTY_RE.fullmatch(qty_text.strip()))


async def _portion_from_record(comp, est: dict) -> tuple[float, str] | None:
    """(grams, description) for a COUNT the patient stated ("2 eggs", "3
    sachets"), from the resolved food's own USDA portion list — the patient
    determined how many, the record says what one weighs. None when there is no
    such list or none of its portions is a unit the words name."""
    fdc_id = est.get("fdc_id")
    if not fdc_id:
        return None
    from app.services import food_match_verifier
    portions = _portion_cache.get(fdc_id)
    if portions is None:
        try:
            detail = await get_usda_food_detail(fdc_id)
        except Exception:
            logger.warning("USDA portions unavailable for fdc %s", fdc_id, exc_info=True)
            return None
        portions = (detail or {}).get("portions") or []
        _portion_cache[fdc_id] = portions
    text = (getattr(comp, "source_text", "") or "").strip() or f"{comp.qty_text} {comp.food_name}"
    try:
        chosen = await food_match_verifier.choose_portion(text, est.get("food_name") or comp.food_name, portions)
    except food_match_verifier.Unavailable:
        return None
    if chosen is None:
        return None
    idx, count = chosen
    p = portions[idx]
    grams = round(food_match_verifier.per_unit_grams(p) * count, 1)
    desc = str(p.get("description") or "")
    # FNDDS names its default portion "Quantity not specified" — the survey's
    # typical amount eaten by OTHER people. That is an assumption about this
    # patient's plate, not a unit their count can multiply (operator,
    # 2026-10-24: "Instead of assuming portion let user determine").
    if "not specified" in desc.lower():
        return None
    return grams, f"{count:g} x {desc} ({grams:.0f} g, USDA portion)"


async def estimate_meal_nutrients(
    db: AsyncSession,
    description: str,
    *,
    notes: str | None = None,
    country: str | None = None,
    preferred_units: str | None = None,
    locale: str | None = None,
) -> dict[str, Any]:
    """Estimate a meal. Every food lookup inside runs with the patient's
    country as context (`food_match_verifier.region`). Reset on every exit, so
    a batch run never carries one patient's context into the next meal."""
    from app.services import food_match_verifier
    token = food_match_verifier.region.set(country)
    try:
        return await _estimate_meal_nutrients_body(
            db, description, notes=notes, country=country,
            preferred_units=preferred_units, locale=locale)
    finally:
        food_match_verifier.region.reset(token)


async def _estimate_meal_nutrients_body(
    db: AsyncSession,
    description: str,
    *,
    notes: str | None = None,
    country: str | None = None,
    preferred_units: str | None = None,
    locale: str | None = None,
) -> dict[str, Any]:
    """Estimate aggregate nutrients for a complete free-text meal description.

    Pipeline:
      1. Parse the description into (food_name, qty_g) pairs via the NLM meal
         parser (handles fractions, parenthetical ingredients, ethnic food names).
      2. For each food component: Cache → USDA → AI fallback to get per-100 g
         nutrient profile.
      3. Scale each nutrient by ``qty_g / 100``.
      4. Sum scaled nutrients across all components to produce meal-level totals.

    Returns a dict with keys:
        description        — original input string
        components         — list of per-food results with scaled nutrients
        aggregate_nutrients — summed nutrients for the whole meal
        total_weight_g     — sum of all component gram weights
    """
    from app.services.meal_parser import parse_meal_text, extract_nutrition_facts
    from app.services import plausibility

    empty = {"description": description, "components": [],
             "aggregate_nutrients": {}, "total_weight_g": 0.0}

    # Non-food / placeholder entries (Firebase shells, "same as previous", bare
    # "snack", "meal3", "n/a") must not be turned into fabricated calories.
    if _is_placeholder(description):
        return empty

    # ── Authoritative input: if the text carries an explicit label, TRUST it
    #    (no re-estimation) and learn it permanently. Fixes "I gave the right
    #    numbers and it still computed something else" (the Boost case).
    #    The NOTES field counts as label text too. A user who writes the panel
    #    values there — the obvious place to put "240 cal, 10 g protein" for a
    #    dish no database has, like goat meat vindaloo — was previously ignored
    #    entirely: only `food_name` ever reached this function, so the numbers
    #    they had already supplied were thrown away and the log came back empty.
    facts = extract_nutrition_facts(description)
    if not facts and notes:
        facts = extract_nutrition_facts(notes)
        # ⚠️ The panel came from a DIFFERENT FIELD than the food name, so the
        # name must come from the description — always, not only when
        # `extract_nutrition_facts` left it blank. It never leaves it blank: it
        # fills `name` with the panel's own leading text, so the old guard could
        # not fire and the food was named after its numbers. Measured:
        #
        #   learned_food_nutrients ->
        #     "190 calories, 16 g of protein, 16 g of carbs, 3g of fiber, 4"
        #
        # That is §3am's poisoned row created afresh — the same shape as the
        # `boost glucose control contains` entry still in that table. The store
        # is SHARED and preferred over USDA and AI, so one bad row is served to
        # every patient forever.
        if facts and description and description.strip():
            facts["name"] = description.strip()[:120]
    if facts:
        # ── What the panel does NOT say, the store may already know ──────────
        #
        # A printed panel states values PER SERVING and usually does not say
        # what the serving WEIGHS, and it lists the macros a label is required
        # to carry — not phosphorus, not potassium. So a correctly-read label
        # produced calories and protein and then `None` for the two numbers a
        # dialysis patient is actually managed on, while the figures sat in
        # `learned_food_nutrients` the whole time (this carton: 127.6552 mg
        # phosphorus and 102.1242 mg potassium per 100 g, 244.8 g per serving
        # → 312.5 and 250).
        #
        # This is a LOOKUP IN WHAT WE HAVE LEARNED, never a table of products:
        # the name comes from the parser, the values come from the store, and
        # both improve on their own as labels are read. Nothing here knows what
        # Boost is.
        from app.services.learned_nutrient_service import get_learned
        from app.services.meal_parser import parse_meal_text as _parse

        known = None
        try:
            # The parser's name, not the raw description — it is what the store
            # is keyed by, and it is what strips a trailing "(nutritional
            # drink)" so the product can be found at all.
            parsed_first = (_parse(description) or [None])[0]
            if parsed_first is not None:
                known = await get_learned(db, parsed_first.food_name)
        except Exception:  # noqa: BLE001 — enrichment is a bonus, never a gate
            logger.exception("Could not consult learned values for %r", description[:60])

        # The serving's weight is what the label or the learned record says —
        # never assumed. Without one, the printed figures are still exactly
        # this serving (the 100 below cancels), but no weight is reported and
        # nothing is scaled onto them.
        stated_g = facts["serving_g"] or (known or {}).get("serving_weight_g")
        serving_g = stated_g or 100.0
        per100 = {k: round(v * 100.0 / serving_g, 4) for k, v in facts["nutrients"].items()}
        per100, warnings, believable = plausibility.review(facts["name"], per100)
        # ⚠️ LEARN ONLY WHEN THE SERVING MASS IS KNOWN.
        #
        # A panel states values PER SERVING. Without the serving's weight there
        # is no density to store, and `serving_g or 100.0` silently asserts one:
        # "190 Calories … 16 g of Protein" off an 8 fl oz carton would be filed
        # as 190 kcal per 100 g, when the carton is 244.8 g and the true figure
        # is 77.6. That row is then preferred over USDA for every later meal —
        # a 2.45x overstatement learned from a correct label. §3c: store per-100
        # GRAMS, and a derived number that looks measured is how a wrong figure
        # becomes authoritative.
        #
        # The ESTIMATE below is unaffected: the panel is this serving, and
        # scaling by `serving_g/100` returns exactly what was printed.
        if facts.get("serving_g"):
            try:
                from app.services.learned_nutrient_service import record_correction
                await record_correction(db, facts["name"], per100,
                                        serving_weight_g=facts["serving_g"], source="label")
            except Exception:  # learning is best-effort; never block the estimate
                logger.exception("Failed to persist label values for '%s'", facts["name"])
        else:
            logger.info(
                "Label for %r states no serving weight — using it for THIS meal "
                "but not learning a per-100 g density from it",
                facts["name"][:60])
        scaled = {k: round(v * serving_g / 100.0, 4) for k, v in per100.items()}
        # The panel is authoritative for everything it states. What it is
        # SILENT about is filled from what has been learned, scaled to the same
        # serving — so a label that prints no phosphorus no longer erases a
        # phosphorus we already know. A stated value is never overwritten.
        if known and stated_g:
            for key, value in (known.get("nutrients") or {}).items():
                if key in scaled or not isinstance(value, (int, float)):
                    continue
                scaled[key] = round(float(value) * serving_g / 100.0, 4)
        return {
            "description": description,
            "components": [{
                "food_name": facts["name"], "qty_g": stated_g,
                "qty_text": "from label", "source": "user_provided",
                "fdc_id": None, "confidence": 1.0, "nutrients_scaled": scaled,
                "warnings": warnings, "believable": believable,
            }],
            "aggregate_nutrients": scaled,
            "total_weight_g": round(stated_g, 1) if stated_g else None,
            "warnings": warnings,
            "believable": believable,
        }

    # ── What the user STATED about the food, lifted out before anything is
    #    looked up. "Nounos Yogurt with 170 mg calcium, 210 potassium, 6g fat,
    #    14 g carbohydrate" is ONE food plus facts — split on commas it became
    #    six "foods" (100 g of potassium, 6 g of pure fat …) priced and summed
    #    into 1142 kcal for a pot of yogurt.
    from app.services.meal_parser import extract_nutrient_facts
    food_text, stated = extract_nutrient_facts(description)

    # Localize cup/tbsp/tsp sizes to the user's locale (US label baseline by default).
    from app.services import locale_units
    vol_factors = locale_units.volume_factors(country, preferred_units, locale)
    components = parse_meal_text(food_text or description, vol_factors=vol_factors)

    # ── "NAME (what it is)" is one thing, not two ───────────────────────────
    #
    # The parser expands a parenthetical as recipe sub-ingredients, which is
    # right for "Jollof rice (rice, tomatoes, pepper, oil)" — those were eaten.
    # It is wrong for an APPOSITION: "Boost Glucose Control (nutritional
    # drink)" became 100 g of Boost plus 30 g of an unrelated USDA "nutritional
    # drink", and the vision caption path produces exactly that shape.
    #
    # The anchor is the LEARNING STORE, not a list of products: if the head
    # resolves to something we have learned from a label, it is a packaged item
    # sold as one serving, and a trailing parenthetical describes it. Nothing
    # here knows what Boost is, and it improves as more labels are read.
    #
    # Two shape conditions keep it from eating real food:
    #   * the description is exactly HEAD (TAIL) — nothing after the bracket;
    #   * TAIL carries no digit and no "with"/"plus", so "(with 2 eggs)" and
    #     "(and rice)" are still treated as food.
    if len(components) > 1:
        shape = re.match(r"^\s*([^()]+?)\s*\(([^()]*)\)\s*$", (food_text or description))
        if shape:
            tail = shape.group(2).lower()
            looks_like_a_descriptor = (
                not any(ch.isdigit() for ch in tail)
                and not re.search(r"\b(with|plus|and)\b", tail)
            )
            if looks_like_a_descriptor:
                from app.services.learned_nutrient_service import get_learned
                head_known = await get_learned(db, components[0].food_name)
                if head_known and head_known.get("serving_weight_g"):
                    logger.info(
                        "Treating %r as a descriptor of the labelled product %r, "
                        "not as a separate food", shape.group(2)[:40],
                        components[0].food_name[:40])
                    components = components[:1]

    if not components:
        # Nothing but facts ("170 mg calcium, 6 g fat") is still worth keeping.
        if stated:
            return {
                "description": description,
                "components": [{
                    "food_name": (food_text or description).strip()[:120] or description[:120],
                    "qty_g": 0.0, "qty_text": "as stated", "source": "user_provided",
                    "fdc_id": None, "confidence": 1.0, "nutrients_scaled": dict(stated),
                    "warnings": [], "believable": True,
                }],
                "aggregate_nutrients": dict(stated),
                "total_weight_g": 0.0,
            }
        return empty

    component_results: list[dict] = []
    aggregate: dict[str, float] = {}
    excluded: list[str] = []      # components the guard refused, named for the caller
    kept_weight_g: float = 0.0    # grams actually counted into `aggregate`

    from app.services import plausibility

    for comp in components:
        est = await estimate_nutrients(db, comp.food_name)
        per_100g = dict(est.get("nutrients") or {})

        # ── A LEARNED product is measured by its own serving, not by 100 g ──
        #
        # `qty_text == "default"` is the parser saying the patient stated no
        # portion, so 100 g is a placeholder rather than a measurement. For a
        # food we have learned from a label that is simply the wrong number:
        # "Boost Glucose Control" scored 77.6 kcal where the carton — the only
        # way it is sold — is 244.8 g and 190 kcal, and the patient had to
        # write "8 fl oz" to get the right answer. Understating by 2.45x also
        # understates its phosphorus and potassium by 2.45x.
        #
        # Deliberately NARROW: only the learned store, only when no portion was
        # stated. USDA rows carry serving sizes too, and adopting those would
        # silently re-portion every food in the product. The learned store is
        # the one that grows from labels we have actually read.
        portion_g, portion_text = comp.qty_g, comp.qty_text
        if comp.qty_text == "default" and est.get("source") == "learned":
            learned_serving = est.get("serving_weight_g")
            if isinstance(learned_serving, (int, float)) and learned_serving > 0:
                portion_g = float(learned_serving)
                # Say where the portion came from. "default" reads as a guess
                # and this no longer is one (§3aa).
                portion_text = f"1 serving ({portion_g:.0f} g, from the label)"

        # ── THE PATIENT DETERMINES THE AMOUNT ─────────────────────────────
        #
        # "2 sachets of brown sugar" parsed as 100 g (380 kcal; two sachets are
        # ~8 g), a bare "beef" as 100 g "default" — the parser's placeholder
        # stored as a measurement. Never 100 g, and never an assumed serving:
        # operator, 2026-10-24, *"Instead of assuming portion let user
        # determine. If no portion size exists — surface the error."* An
        # assumed portion (choice C) sent "Smoothie" to an 864 g USDA cup.
        #
        # * a COUNT the patient stated ("2", "half") becomes grams through the
        #   food's own USDA portion — they said how many, the record says what
        #   one weighs;
        # * NO amount at all, or a count no unit of the record fits, is
        #   "no amount given": not counted, and named on the meal so the
        #   patient can add it.
        weight_unknown = False
        if portion_text == comp.qty_text and _weight_is_placeholder(comp.qty_text):
            from_record = None
            if comp.qty_text.strip().lower() != "default":
                from_record = await _portion_from_record(comp, est)
            if from_record is not None:
                portion_g, portion_text = from_record
            else:
                weight_unknown = True
                portion_text = "no amount given"

        # Input-side believability: cap an implausibly large parsed portion
        # (usually a count misread as grams, e.g. "100 of chicken thigh").
        qty_g, parse_warnings = plausibility.validate_parse(comp.food_name, portion_g)

        # Per-100 g hard ceiling backstop (the review step already clamps to 902).
        cal = per_100g.get("calories")
        if isinstance(cal, (int, float)) and cal > 902:
            per_100g["calories"] = 902.0

        # Scale each nutrient by the actual quantity proportion
        scale = qty_g / 100.0
        scaled: dict[str, float] = {
            key: round(float(val) * scale, 4)
            for key, val in per_100g.items()
            if isinstance(val, (int, float))
        }

        # ── ONE BAD COMPONENT MUST NOT VOID THE WHOLE MEAL ─────────────────
        #
        # Operator, 2026-10-18: *"things that used to work stop working
        # reliably."* Measured on their own rows:
        #
        #   "1 boiled egg, 1 cup of tea, 1 slice of kiwi"   stored 92 kcal,
        #       and now reports  tea: 1 kcal/100g is outside the expected
        #       22-110 for 'tea_coffee'  -> whole meal rejected
        #   "Banana, numb earl grey tea"  -> "numb earl grey tea" categorised
        #       DAIRY, band 30-160, so 1 kcal/100g is "impossible"
        #   "Organic Milk (Pasteurized, Nonfat), ..." -> components `pasteurized`
        #       16 g, `nonfat` 14 g, `carton` 100 g
        #
        # Plain tea IS about 1 kcal/100 g. The BAND is wrong, not the value —
        # and the band comes from `food_category_cache`, which is filled the
        # first time a name is seen. So the same text can be judged differently
        # on different days, which is exactly "it used to work": nothing in the
        # meal changed, the cached category did.
        #
        # Excluding the flagged component keeps §3am's rule — an impossible
        # number is still never stored — while ending the collateral damage of
        # discarding everything beside it. Most of what it removes is parser
        # debris (`carton`, `pasteurized`) or a wrong match, which is precisely
        # what should be removed.
        component_believable = (
            est.get("believable", True) and est.get("out_of_band") is not True
            and not weight_unknown
        )
        if weight_unknown:
            from app.services.amount_history import NO_AMOUNT_SUFFIX
            excluded.append(f"{comp.food_name}{NO_AMOUNT_SUFFIX}")
            qty_g, scaled = None, {}
        elif component_believable:
            kept_weight_g += qty_g
            for key, val in scaled.items():
                aggregate[key] = round(aggregate.get(key, 0.0) + val, 4)
        else:
            excluded.append(comp.food_name)

        component_results.append({
            "food_name": comp.food_name,
            # What the lookup resolved it to — "sardines" -> "Fish oil, sardine".
            # Stored with the meal (nutrition_log_components) so a wrong match
            # is visible per item instead of hidden in the total.
            "matched_name": est.get("food_name"),
            "counted": bool(component_believable),
            "qty_g": qty_g,
            "qty_text": portion_text,
            "source": est.get("source"),
            "fdc_id": est.get("fdc_id"),
            "confidence": est.get("confidence", 0.0),
            "nutrients_scaled": scaled,
            "warnings": (est.get("plausibility_warnings") or []) + parse_warnings,
            "believable": component_believable,
        })

    # The weight of what was actually COUNTED. Keeping the excluded component's
    # grams here would hand `review_meal` a total whose nutrients and mass come
    # from different sets of food, and the density it checks would be wrong by
    # construction.
    total_weight_g = round(kept_weight_g, 1)

    # Anything the user stated OUTRANKS the estimate — they read it off the pot.
    if stated:
        aggregate.update(stated)
        # …and is remembered, so the next lookup for this food starts from the
        # user's own numbers instead of re-deriving them.
        if len(component_results) == 1:
            await _learn_stated(db, component_results[0]["food_name"], stated,
                                component_results[0].get("qty_g"))

    # Believability guardrail at the meal level + roll up component warnings.
    from app.services import plausibility
    warnings = plausibility.review_meal(total_weight_g, aggregate)
    for c in component_results:
        for w in c["warnings"]:
            warnings.append(f"{c['food_name']}: {w}")
    if excluded:
        # Say it plainly and FIRST. A total that silently omits an item reads
        # as the whole meal, and a quiet undercount is the failure this change
        # could introduce if the exclusion were not stated (§3aa).
        warnings.insert(0, (
            "NOT COUNTED in this total: " + ", ".join(excluded)
            + " — the estimate for each was outside the plausible range for "
              "its food category, so it was left out rather than discarding "
              "the whole meal."))

    return {
        "description": description,
        "components": component_results,
        "aggregate_nutrients": aggregate,
        "total_weight_g": total_weight_g,
        "warnings": warnings,
        "excluded_components": excluded,
        # The meal stands on what SURVIVED. It is unbelievable only when
        # nothing was countable at all, or when the kept total is itself
        # impossible — the 3,892 kcal / 394 g fat case is still refused,
        # because that verdict comes from `review_meal` on the kept aggregate.
        "believable": bool(aggregate) and not plausibility.review_meal(
            total_weight_g, aggregate),
    }
