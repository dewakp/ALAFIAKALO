"""Food → Nutrient estimation pipeline.

Strategy:
  1. Check local cache (food_nutrient_cache table)
  2. Search USDA FoodData Central
  3. Fall back to AI (Ollama local → OpenAI cloud)
  4. Cache AI results for app-wide reuse
"""

import asyncio
import json
import logging
import re
from typing import Any

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.nutrition_data import (
    search_usda_foods,
    get_usda_food_detail,
    DB_COLUMN_KEYS,
    NUTRIENT_CATALOG,
    EXTENDED_NUTRIENTS,
)
from app.models.food_nutrient_cache import FoodNutrientCache
from app.services.nlm_food_extractor import extract_food_items_nlm
from app.services.mcp_nutrition_server import (
    search_branded_food as _mcp_search_branded,
    get_branded_food_detail as _mcp_get_branded_detail,
    search_open_food_facts as _mcp_search_off,
)

logger = logging.getLogger(__name__)

# How many USDA item lookups may run at once for one multi-item meal. Enough to
# collapse a 10-item list into ~one round trip, low enough not to get this client
# rate-limited by USDA.
_USDA_ITEM_CONCURRENCY = 8

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
        "food_name": row.food_name_original,
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
) -> None:
    """Persist a nutrient estimate to the cache."""
    normalized = _normalize_food_name(food_name)
    entry = FoodNutrientCache(
        food_name_normalized=normalized,
        food_name_original=food_name.strip(),
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


async def _try_usda_single(food_name: str) -> dict | None:
    """Search USDA for one food phrase and return best match."""
    try:
        results = await search_usda_foods(food_name, page_size=5)
    except Exception:
        logger.warning("USDA API call failed for '%s'", food_name, exc_info=True)
        return None

    if not results:
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
        dt_pref = 0 if r.get("data_type") in ("Foundation", "SR Legacy") else 1
        scored.append((-rank, dt_pref, idx, r))

    if not scored:
        logger.info("No relevant USDA match for '%s' (candidates: %s)",
                    food_name, [r.get("description") for r in results[:5]])
        return None

    scored.sort(key=lambda x: (x[0], x[1], x[2]))
    best = scored[0][-1]

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
    return len(overlap) / len(query_tokens) >= 0.30


async def _try_mcp_branded(food_name: str) -> dict | None:
    """Try MCP-tier branded food lookup.

    Pipeline:
      1. USDA FDC Branded Foods search
      2. If no USDA Branded match → Open Food Facts search
    """
    # ── Step 1: USDA Branded Foods ────────────────────────────────────────
    try:
        branded_results = await _mcp_search_branded(food_name, max_results=8)
    except Exception:
        logger.warning("MCP branded search error for '%s'", food_name, exc_info=True)
        branded_results = []

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
    except Exception:
        logger.warning("MCP Open Food Facts error for '%s'", food_name, exc_info=True)
        off_results = []

    for item in off_results:
        name = item.get("product_name", "") or item.get("brands", "")
        combined = f"{item.get('brands', '')} {name}"
        if not _is_relevant_branded_match(food_name, combined):
            continue
        nutrients = item.get("nutrients") or {}
        if not nutrients or "calories" not in nutrients:
            continue
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

    return None


async def _try_usda(food_name: str) -> dict | None:
    """Search USDA, including NLM-style extracted sub-items for mixed descriptions."""
    # First, try the original phrase directly.
    direct = await _try_usda_single(food_name)
    if direct:
        return direct

    # If no direct match, extract items (NLM-style normalization) and try each item.
    items = extract_food_items_nlm(food_name)
    if len(items) <= 1:
        return None

    # Look the items up CONCURRENTLY.
    #
    # This loop used to be sequential: a 10-item meal ("3 sardines, 4 pitted
    # olives, 4 cherry tomatoes, …") meant 10 round trips to USDA one after the
    # other. Locally that alone took 7.6s; over production latency it pushed the
    # whole save past the client's 30s timeout, and because estimation happens
    # inside the save, the user LOST the meal they had typed.
    #
    # Bounded so a long list cannot open an unlimited number of sockets or get
    # this client rate-limited by USDA.
    semaphore = asyncio.Semaphore(_USDA_ITEM_CONCURRENCY)

    async def _lookup(item: str) -> dict | None:
        async with semaphore:
            try:
                return await _try_usda_single(item)
            except Exception:
                logger.debug("USDA item lookup failed for %r", item, exc_info=True)
                return None

    settled = await asyncio.gather(*(_lookup(i) for i in items))
    # gather preserves order, so the merged result stays deterministic.
    item_results: list[dict] = [r for r in settled if r]

    if not item_results:
        return None

    merged = _merge_nutrients(item_results)
    if "calories" not in merged:
        return None

    match_ratio = len(item_results) / len(items)
    confidence = round(0.55 + (0.35 * match_ratio), 3)

    return {
        "source": "usda",
        "fdc_id": item_results[0].get("fdc_id") if len(item_results) == 1 else None,
        "ai_model": None,
        "food_name": ", ".join(items),
        "serving_size": f"Composite meal ({len(item_results)}/{len(items)} items matched)",
        "serving_weight_g": None,
        "confidence": confidence,
        "nutrients": merged,
        "cached": False,
    }


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
    r"same as (the )?previous.*|see (above|previous).*|leftover|unspecified|tbd|--?)\s*$",
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
    # Locale normalization: map non-English / regional names to an English head-noun
    # for lookup (e.g. "arroz"→rice, "jollof"→jollof rice). Display keeps the original.
    lookup_name = canonicalize(food_name)
    result = await _estimate_nutrients_impl(db, lookup_name, serving_size)
    if isinstance(result, dict) and isinstance(result.get("nutrients"), dict):
        corrected, warnings, believable = plausibility.review(lookup_name, result["nutrients"])
        result["nutrients"] = corrected
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

    # 2. USDA Foundation / SR Legacy / FNDDS
    usda_result = await _try_usda(food_name)
    if usda_result:
        if _in_band(usda_result):
            await _save_to_cache(db, food_name, source="usda", nutrients=usda_result["nutrients"],
                                 fdc_id=usda_result["fdc_id"], serving_size=usda_result["serving_size"],
                                 serving_weight_g=usda_result["serving_weight_g"], confidence=1.0)
            return usda_result
        logger.info("USDA match for '%s' out of category band → trying other sources", food_name)
        fallbacks.append(usda_result)

    # 3. Branded (Boost/Ensure/Gatorade/OTC) via MCP (USDA Branded → Open Food Facts)
    mcp_result = await _try_mcp_branded(food_name)
    if mcp_result:
        if _in_band(mcp_result):
            await _save_to_cache(db, food_name, source=mcp_result["source"], nutrients=mcp_result["nutrients"],
                                 fdc_id=mcp_result.get("fdc_id"), serving_size=mcp_result.get("serving_size"),
                                 serving_weight_g=mcp_result.get("serving_weight_g"), confidence=mcp_result["confidence"])
            return mcp_result
        fallbacks.append(mcp_result)

    # 4. AI fallback (escalated when USDA/branded were missing or out-of-band).
    ai_result = await _try_ai(food_name, serving_size)
    if ai_result:
        if not ai_result.get("food_name"):
            ai_result["food_name"] = food_name
        if _in_band(ai_result) or not fallbacks:
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


async def estimate_meal_nutrients(
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
        if facts and not facts.get("name"):
            facts["name"] = description.strip()[:120]
    if facts:
        serving_g = facts["serving_g"] or 100.0
        per100 = {k: round(v * 100.0 / serving_g, 4) for k, v in facts["nutrients"].items()}
        per100, warnings, believable = plausibility.review(facts["name"], per100)
        try:
            from app.services.learned_nutrient_service import record_correction
            await record_correction(db, facts["name"], per100, serving_weight_g=serving_g, source="label")
        except Exception:  # learning is best-effort; never block the estimate
            logger.exception("Failed to persist label values for '%s'", facts["name"])
        scaled = {k: round(v * serving_g / 100.0, 4) for k, v in per100.items()}
        return {
            "description": description,
            "components": [{
                "food_name": facts["name"], "qty_g": serving_g,
                "qty_text": "from label", "source": "user_provided",
                "fdc_id": None, "confidence": 1.0, "nutrients_scaled": scaled,
                "warnings": warnings, "believable": believable,
            }],
            "aggregate_nutrients": scaled,
            "total_weight_g": round(serving_g, 1),
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

    from app.services import plausibility

    for comp in components:
        est = await estimate_nutrients(db, comp.food_name)
        per_100g = dict(est.get("nutrients") or {})

        # Input-side believability: cap an implausibly large parsed portion
        # (usually a count misread as grams, e.g. "100 of chicken thigh").
        qty_g, parse_warnings = plausibility.validate_parse(comp.food_name, comp.qty_g)

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

        # Accumulate into meal totals
        for key, val in scaled.items():
            aggregate[key] = round(aggregate.get(key, 0.0) + val, 4)

        component_results.append({
            "food_name": comp.food_name,
            "qty_g": qty_g,
            "qty_text": comp.qty_text,
            "source": est.get("source"),
            "fdc_id": est.get("fdc_id"),
            "confidence": est.get("confidence", 0.0),
            "nutrients_scaled": scaled,
            "warnings": (est.get("plausibility_warnings") or []) + parse_warnings,
            "believable": est.get("believable", True) and est.get("out_of_band") is not True,
        })

    total_weight_g = round(sum(c.qty_g for c in components), 1)

    # Anything the user stated OUTRANKS the estimate — they read it off the pot.
    if stated:
        aggregate.update(stated)

    # Believability guardrail at the meal level + roll up component warnings.
    from app.services import plausibility
    warnings = plausibility.review_meal(total_weight_g, aggregate)
    for c in component_results:
        for w in c["warnings"]:
            warnings.append(f"{c['food_name']}: {w}")

    return {
        "description": description,
        "components": component_results,
        "aggregate_nutrients": aggregate,
        "total_weight_g": total_weight_g,
        "warnings": warnings,
        "believable": all(c.get("believable", True) for c in component_results) and not
                      plausibility.review_meal(total_weight_g, aggregate),
    }
