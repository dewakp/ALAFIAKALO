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


def _is_relevant_usda_match(query: str, description: str | None) -> bool:
    """Return True when USDA description is a reasonably close lexical match."""
    if not description:
        return False

    query_tokens = _tokenize_food_text(query)
    desc_tokens = _tokenize_food_text(description)
    if not query_tokens or not desc_tokens:
        return False

    overlap = query_tokens.intersection(desc_tokens)
    overlap_ratio = len(overlap) / len(query_tokens)

    # Require at least half of the query tokens to be present in the USDA result.
    return overlap_ratio >= 0.5


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

    # Pick the first Foundation or SR Legacy match, else first result.
    best = results[0]
    for r in results:
        if r.get("data_type") in ("Foundation", "SR Legacy"):
            best = r
            break

    # Reject weak lexical matches so unknown foods can fall back to AI.
    if not _is_relevant_usda_match(food_name, best.get("description")):
        logger.info(
            "USDA result rejected as weak match for '%s' -> '%s'",
            food_name,
            best.get("description"),
        )
        return None

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

    item_results: list[dict] = []
    for item in items:
        match = await _try_usda_single(item)
        if match:
            item_results.append(match)

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


async def _try_ai(food_name: str, serving_size: str | None = None) -> dict | None:
    """Estimate nutrients via AI. Tries Ollama first, then OpenAI."""
    user_msg = f"Food: {food_name}"
    if serving_size:
        user_msg += f"\nServing: {serving_size}"

    # Try Ollama (local)
    result = await _call_ollama(user_msg)
    if result:
        result["ai_model"] = settings.OLLAMA_MODEL
        return result

    # Try OpenAI (cloud)
    result = await _call_openai(user_msg)
    if result:
        return result

    return None


# TODO(alafia-model): replace with ALAFIAModel.NLM nutrient lookup — Phase 4
async def _call_ollama(user_msg: str) -> dict | None:
    """Call local Ollama for nutrient estimation."""
    url = f"{settings.OLLAMA_BASE_URL}/api/chat"
    payload = {
        "model": settings.OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.3},
    }
    try:
        async with httpx.AsyncClient(timeout=float(settings.OLLAMA_TIMEOUT)) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        logger.debug("Ollama unavailable, will try OpenAI", exc_info=True)
        return None

    return _parse_ai_response(data.get("message", {}).get("content", ""), settings.OLLAMA_MODEL)


# TODO(alafia-model): remove once ALAFIAModel Phase 4 (NLM + USDA/WAFCT RAG) is live
async def _call_openai(user_msg: str) -> dict | None:
    """Call OpenAI API for nutrient estimation."""
    api_key = settings.OPENAI_API_KEY if hasattr(settings, "OPENAI_API_KEY") else None
    if not api_key:
        return None

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-4o-mini",
                    "messages": [
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user", "content": user_msg},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 1500,
                    "response_format": {"type": "json_object"},
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        logger.warning("OpenAI call failed", exc_info=True)
        return None

    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    model = data.get("model", "gpt-4o-mini")
    return _parse_ai_response(content, model)


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


# ── Public API ────────────────────────────────────────────────────────────────


async def estimate_nutrients(
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
    # 1. Check cache
    cached = await _get_cached(db, food_name)
    if cached:
        logger.info("Cache HIT for '%s' (source=%s)", food_name, cached["source"])
        return cached

    # 2. Try USDA Foundation / SR Legacy / FNDDS
    usda_result = await _try_usda(food_name)
    if usda_result:
        logger.info("USDA match for '%s': fdc_id=%s", food_name, usda_result["fdc_id"])
        await _save_to_cache(
            db,
            food_name,
            source="usda",
            nutrients=usda_result["nutrients"],
            fdc_id=usda_result["fdc_id"],
            serving_size=usda_result["serving_size"],
            serving_weight_g=usda_result["serving_weight_g"],
            confidence=1.0,
        )
        return usda_result

    # 3. Try MCP Branded Foods (USDA Branded → Open Food Facts)
    #    Handles OTC supplements, packaged beverages, branded products
    #    (e.g. "Boost Glucose Control", "Ensure", "Gatorade")
    mcp_result = await _try_mcp_branded(food_name)
    if mcp_result:
        await _save_to_cache(
            db,
            food_name,
            source=mcp_result["source"],
            nutrients=mcp_result["nutrients"],
            fdc_id=mcp_result.get("fdc_id"),
            serving_size=mcp_result.get("serving_size"),
            serving_weight_g=mcp_result.get("serving_weight_g"),
            confidence=mcp_result["confidence"],
        )
        return mcp_result

    # 5. Fall back to AI (TODO(alafia-model): replace with ALAFIAModel Phase 4)
    ai_result = await _try_ai(food_name, serving_size)
    if ai_result:
        if not ai_result.get("food_name"):
            ai_result["food_name"] = food_name
        logger.info("AI estimated nutrients for '%s' (model=%s, confidence=%.2f)",
                     food_name, ai_result["ai_model"], ai_result["confidence"])
        # Cache AI result for reuse across the app
        await _save_to_cache(
            db,
            food_name,
            source="ai",
            nutrients=ai_result["nutrients"],
            ai_model=ai_result["ai_model"],
            serving_size=ai_result.get("serving_size"),
            serving_weight_g=ai_result.get("serving_weight_g"),
            confidence=ai_result["confidence"],
        )
        return ai_result

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
    from app.services.meal_parser import parse_meal_text

    components = parse_meal_text(description)
    if not components:
        return {
            "description": description,
            "components": [],
            "aggregate_nutrients": {},
            "total_weight_g": 0.0,
        }

    component_results: list[dict] = []
    aggregate: dict[str, float] = {}

    for comp in components:
        est = await estimate_nutrients(db, comp.food_name)
        per_100g = est.get("nutrients") or {}

        # Scale each nutrient by the actual quantity proportion
        scale = comp.qty_g / 100.0
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
            "qty_g": comp.qty_g,
            "qty_text": comp.qty_text,
            "source": est.get("source"),
            "fdc_id": est.get("fdc_id"),
            "confidence": est.get("confidence", 0.0),
            "nutrients_scaled": scaled,
        })

    total_weight_g = round(sum(c.qty_g for c in components), 1)

    return {
        "description": description,
        "components": component_results,
        "aggregate_nutrients": aggregate,
        "total_weight_g": total_weight_g,
    }
