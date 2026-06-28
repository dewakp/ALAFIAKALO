"""ALAFIA Nutrition MCP Server

A Model Context Protocol (MCP) server exposing branded/packaged-food
nutrition lookup tools for the ALAFIA nutrient-estimation pipeline.

Tools
-----
search_branded_food        Search USDA FDC Branded Foods (OTC supplements, packaged drinks, etc.)
get_branded_food_detail    Full 150-nutrient profile for a branded food by FDC ID
search_open_food_facts     Open Food Facts API search (global packaged foods, supplements)
lookup_upc                 Open Food Facts product lookup by UPC / EAN barcode

Integration
-----------
The tools are plain ``async`` functions importable directly by the backend:

    from app.services.mcp_nutrition_server import (
        search_branded_food,
        get_branded_food_detail,
        search_open_food_facts,
        lookup_upc,
    )

They are *also* registered with a FastMCP instance so the server can be run
as a standalone MCP endpoint (stdio, SSE, or streamable-HTTP transport):

    # stdio — for Claude Desktop / MCP client direct connection
    python -m app.services.mcp_nutrition_server

    # SSE / HTTP — network endpoint (default port 8003)
    MCP_TRANSPORT=sse  python -m app.services.mcp_nutrition_server
    MCP_TRANSPORT=http python -m app.services.mcp_nutrition_server

Deployment
----------
fastmcp pulls a newer Starlette than FastAPI 0.115.6 permits, so this server is
NOT mounted on the FastAPI app. Instead it runs as its own container — see the
``mcp`` service in ``WEB/docker-compose.yml`` (built from ``Dockerfile.mcp`` with
``requirements-mcp.txt``), exposing the MCP endpoint on port 8003:

    docker compose up mcp        # → http://localhost:8003

TODO(alafia-model): replace external API calls with ALAFIAModel.infer("nlm", ...) Phase 4
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# ── Lazy import FastMCP so the module loads even if fastmcp is not installed ──
try:
    from fastmcp import FastMCP as _FastMCP
    _mcp = _FastMCP("ALAFIA Nutrition MCP Server")
    _HAS_MCP = True
except ImportError:  # pragma: no cover
    _mcp = None  # type: ignore[assignment]
    _HAS_MCP = False
    logger.warning(
        "fastmcp not installed — MCP protocol exposure unavailable. "
        "Tool functions are still callable in-process."
    )


def _mcp_tool():
    """Decorator shim — registers with FastMCP when available, else no-op."""
    def _decorator(fn):
        if _HAS_MCP and _mcp is not None:
            _mcp.tool()(fn)
        return fn
    return _decorator


# ── Constants ─────────────────────────────────────────────────────────────────

USDA_BASE = "https://api.nal.usda.gov/fdc/v1"
OFF_SEARCH = "https://world.openfoodfacts.org/cgi/search.pl"
OFF_PRODUCT = "https://world.openfoodfacts.org/api/v0/product"

# Lazy-loaded to avoid circular import at module load time
_USDA_ID_TO_KEY: dict[int, str] | None = None


def _get_usda_id_map() -> dict[int, str]:
    global _USDA_ID_TO_KEY
    if _USDA_ID_TO_KEY is None:
        from app.core.nutrition_data import _USDA_ID_TO_KEY as _m
        _USDA_ID_TO_KEY = _m
    return _USDA_ID_TO_KEY


def _get_usda_key() -> str:
    try:
        from app.core.config import settings
        return settings.USDA_API_KEY or "DEMO_KEY"
    except Exception:
        return os.environ.get("USDA_API_KEY", "DEMO_KEY")


# Open Food Facts → our nutrient key.
# OFF stores macros in g per 100g; minerals/vitamins mostly in g or mg per 100g.
# Values marked *g→mg* need ×1000 to convert g→mg.
_OFF_MAP: dict[str, tuple[str, float]] = {
    # key in OFF nutriments               (our_key,             multiplier)
    "energy-kcal_100g":                   ("calories",                  1.0),
    "proteins_100g":                      ("protein_g",                 1.0),
    "carbohydrates_100g":                 ("carbs_g",                   1.0),
    "fat_100g":                           ("fat_g",                     1.0),
    "fiber_100g":                         ("fiber_g",                   1.0),
    "sugars_100g":                        ("sugar_g",                   1.0),
    "saturated-fat_100g":                 ("saturated_fat_g",           1.0),
    "trans-fat_100g":                     ("trans_fat_g",               1.0),
    "cholesterol_100g":                   ("cholesterol_mg",         1000.0),  # g→mg
    "sodium_100g":                        ("sodium_mg",              1000.0),  # g→mg
    "potassium_100g":                     ("potassium_mg",           1000.0),  # g→mg
    "calcium_100g":                       ("calcium_mg",             1000.0),  # g→mg
    "iron_100g":                          ("iron_mg",                1000.0),  # g→mg
    "magnesium_100g":                     ("magnesium_mg",           1000.0),  # g→mg
    "zinc_100g":                          ("zinc_mg",                1000.0),  # g→mg
    "phosphorus_100g":                    ("phosphorus_mg",          1000.0),  # g→mg
    "selenium_100g":                      ("selenium_mcg",        1_000_000.0),  # g→µg
    "iodine_100g":                        ("iodine_mcg",          1_000_000.0),  # g→µg
    "vitamin-c_100g":                     ("vitamin_c_mg",           1000.0),  # g→mg
    "vitamin-e_100g":                     ("vitamin_e_mg",           1000.0),  # g→mg
    "vitamin-k_100g":                     ("vitamin_k_mcg",       1_000_000.0),  # g→µg
    "vitamin-a-iu_100g":                  ("vitamin_a_iu",              1.0),
    "vitamin-d_100g":                     ("vitamin_d_mcg",          1000.0),  # g→µg (mcg)
    "vitamin-b1_100g":                    ("vitamin_b1_thiamine_mg",  1000.0),  # g→mg
    "vitamin-b2_100g":                    ("vitamin_b2_riboflavin_mg", 1000.0),
    "vitamin-b3_100g":                    ("vitamin_b3_niacin_mg",    1000.0),
    "vitamin-b5_100g":                    ("vitamin_b5_pantothenic_acid_mg", 1000.0),
    "vitamin-b6_100g":                    ("vitamin_b6_mg",           1000.0),
    "vitamin-b9-folic-acid_100g":         ("vitamin_b9_folate_mcg",  1_000_000.0),
    "vitamin-b12_100g":                   ("vitamin_b12_mcg",        1_000_000.0),
    "omega-3-fat_100g":                   ("omega3_g",                  1.0),
    "omega-6-fat_100g":                   ("omega6_g",                  1.0),
    "water_100g":                         ("water_ml",                  1.0),
}


def _map_off_nutrients(nutriments: dict) -> dict[str, float]:
    """Convert Open Food Facts nutriments dict → our standard nutrient key→value (per 100g)."""
    out: dict[str, float] = {}
    for off_key, (our_key, mult) in _OFF_MAP.items():
        val = nutriments.get(off_key)
        if val is not None and isinstance(val, (int, float)) and val >= 0:
            out[our_key] = round(float(val) * mult, 4)
    return out


def _map_usda_nutrients(food_nutrients: list[dict]) -> dict[str, float]:
    """Convert USDA FDC foodNutrients list → our standard nutrient key→value."""
    id_map = _get_usda_id_map()
    out: dict[str, float] = {}
    for fn in food_nutrients:
        nid = fn.get("nutrientId") or (fn.get("nutrient") or {}).get("id")
        value = fn.get("value") if "value" in fn else fn.get("amount")
        if nid and nid in id_map and value is not None:
            out[id_map[nid]] = round(float(value), 4)
    return out


# ── Tool implementations ───────────────────────────────────────────────────────


@_mcp_tool()
async def search_branded_food(
    query: str,
    max_results: int = 8,
) -> list[dict[str, Any]]:
    """Search the USDA FoodData Central **Branded Foods** database.

    Returns OTC nutritional supplements, packaged beverages, and branded
    products (e.g. "Boost Glucose Control", "Ensure", "Gatorade").
    Each result includes a ``nutrients`` dict with values **per 100 g**.

    Args:
        query: Product name or brand + flavour (e.g. "Boost Glucose Control Very Vanilla")
        max_results: Maximum number of results to return (default 8, max 25)

    Returns:
        List of product dicts with keys:
        fdc_id, description, brand_owner, brand_name, serving_size,
        serving_size_unit, gtin_upc, nutrients (per-100g dict)
    """
    api_key = _get_usda_key()
    params = {
        "api_key": api_key,
        "query": query,
        "pageSize": min(max_results, 25),
        "dataType": "Branded",
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{USDA_BASE}/foods/search", params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        logger.warning("USDA Branded search failed for '%s'", query, exc_info=True)
        return []

    results = []
    for f in data.get("foods", []):
        nutrients = _map_usda_nutrients(f.get("foodNutrients", []))
        if not nutrients:
            continue
        results.append({
            "fdc_id": f.get("fdcId"),
            "description": f.get("description", ""),
            "brand_owner": f.get("brandOwner"),
            "brand_name": f.get("brandName"),
            "data_type": "Branded",
            "serving_size": f.get("servingSize"),
            "serving_size_unit": f.get("servingSizeUnit"),
            "gtin_upc": f.get("gtinUpc"),
            "nutrients": nutrients,
        })
    logger.info(
        "USDA Branded search '%s' → %d results", query, len(results)
    )
    return results


@_mcp_tool()
async def get_branded_food_detail(fdc_id: int) -> dict[str, Any] | None:
    """Get the full 150-nutrient profile for a branded food from USDA FDC.

    Args:
        fdc_id: USDA FoodData Central food ID (from search_branded_food results)

    Returns:
        Dict with keys: fdc_id, description, brand_owner, data_type,
        nutrients (per-100g), portions, serving_info  — or None if not found.
    """
    api_key = _get_usda_key()
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{USDA_BASE}/food/{fdc_id}",
                params={"api_key": api_key},
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        logger.warning("USDA detail fetch failed for fdc_id=%s", fdc_id, exc_info=True)
        return None

    nutrients = _map_usda_nutrients(data.get("foodNutrients", []))
    portions = [
        {
            "description": p.get("portionDescription") or p.get("modifier") or "Portion",
            "gram_weight": p.get("gramWeight"),
            "amount": p.get("amount"),
        }
        for p in data.get("foodPortions", [])
    ]
    label_nutrients = data.get("labelNutrients") or {}

    return {
        "fdc_id": data.get("fdcId"),
        "description": data.get("description", ""),
        "brand_owner": data.get("brandOwner"),
        "brand_name": data.get("brandName"),
        "data_type": data.get("dataType", "Branded"),
        "serving_size": data.get("servingSize"),
        "serving_size_unit": data.get("servingSizeUnit"),
        "gtin_upc": data.get("gtinUpc"),
        "nutrients": nutrients,
        "portions": portions,
        # labelNutrients has per-serving values — useful for cross-checking
        "label_nutrients": {
            k: round(v.get("value", 0), 4)
            for k, v in label_nutrients.items()
            if isinstance(v, dict) and "value" in v
        },
    }


@_mcp_tool()
async def search_open_food_facts(
    query: str,
    max_results: int = 5,
) -> list[dict[str, Any]]:
    """Search the Open Food Facts (OFF) database for packaged/branded products.

    OFF is a free community database covering >3 million international products.
    Use as a fallback when USDA Branded search returns no results.
    Each result includes a ``nutrients`` dict with values **per 100 g**.

    Args:
        query: Product name or brand (e.g. "Boost Protein Very Vanilla")
        max_results: Maximum number of results to return (default 5)

    Returns:
        List of product dicts with keys:
        product_name, brands, serving_size, barcode, nutrients (per-100g dict)
    """
    params = {
        "search_terms": query,
        "json": "1",
        "page_size": min(max_results, 10),
        "fields": (
            "product_name,brands,serving_size,quantity,"
            "nutriments,code,image_url"
        ),
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(OFF_SEARCH, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        logger.warning("Open Food Facts search failed for '%s'", query, exc_info=True)
        return []

    results = []
    for p in data.get("products", []):
        nutriments = p.get("nutriments") or {}
        nutrients = _map_off_nutrients(nutriments)
        if not nutrients or "calories" not in nutrients:
            continue
        results.append({
            "product_name": p.get("product_name", ""),
            "brands": p.get("brands", ""),
            "serving_size": p.get("serving_size"),
            "quantity": p.get("quantity"),
            "barcode": p.get("code"),
            "image_url": p.get("image_url"),
            "source": "open_food_facts",
            "nutrients": nutrients,
        })
    logger.info(
        "Open Food Facts search '%s' → %d results", query, len(results)
    )
    return results


@_mcp_tool()
async def lookup_upc(upc: str) -> dict[str, Any] | None:
    """Look up a food product by UPC/EAN barcode via Open Food Facts.

    Args:
        upc: UPC (12-digit) or EAN-13 barcode string

    Returns:
        Product dict with product_name, brands, nutrients (per-100g), or None.
    """
    # Sanitise barcode — digits only
    barcode = re.sub(r"[^0-9]", "", upc.strip())
    if len(barcode) < 8:
        return None
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{OFF_PRODUCT}/{barcode}.json",
                params={"fields": "product_name,brands,serving_size,quantity,nutriments"},
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        logger.warning("UPC lookup failed for '%s'", upc, exc_info=True)
        return None

    if data.get("status") != 1:
        return None

    p = data.get("product") or {}
    nutriments = p.get("nutriments") or {}
    nutrients = _map_off_nutrients(nutriments)
    if not nutrients:
        return None

    return {
        "product_name": p.get("product_name", ""),
        "brands": p.get("brands", ""),
        "serving_size": p.get("serving_size"),
        "quantity": p.get("quantity"),
        "barcode": barcode,
        "source": "open_food_facts",
        "nutrients": nutrients,
    }


@_mcp_tool()
async def get_med_nutrients(
    medication_name: str,
    dose_amount: float,
    dose_unit: str,
) -> dict[str, Any]:
    """Resolve a medication dose to its nutrient contribution.

    Looks up the global med→nutrient profile DB for the named medication and
    returns the absolute nutrient amounts delivered by the specified dose.

    Examples:
      - get_med_nutrients("Calcitriol", 0.5, "mcg") →
          {"vitamin_d_iu": 20.0}
      - get_med_nutrients("Tums Regular Strength", 2, "tablet") →
          {"calcium_mg": 400.0}
      - get_med_nutrients("Fish Oil", 1000, "mg") →
          {"omega3_g": 0.3}

    Args:
        medication_name: Brand or generic name of the medication
        dose_amount: Numeric quantity of the dose taken
        dose_unit: Unit of the dose (mg, mcg, IU, tablet, capsule, mEq, g, mL)

    Returns:
        {
          "profile_id": int | None,
          "med_name_resolved": str,
          "dose_amount": float,
          "dose_unit": str,
          "dose_unit_canonical": str | None,
          "nutrients": {nutrient_key: absolute_amount},
          "source": "seeded" | "ai_discovered" | "unknown",
        }

    TODO(alafia-model): replace lookup with ALAFIAModel.resolve_medication_nutrients()
    """
    from app.core.database import async_session
    from app.services.med_nutrient_service import lookup_med_nutrients

    async with async_session() as db:
        return await lookup_med_nutrients(db, medication_name, dose_amount, dose_unit)


# ── Standalone entry point ────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if not _HAS_MCP:
        print(
            "ERROR: fastmcp is not installed. "
            "Run: pip install fastmcp",
            file=sys.stderr,
        )
        sys.exit(1)

    if transport in ("sse", "http", "streamable-http"):
        port = int(os.environ.get("MCP_PORT", "8003"))
        logger.info("Starting ALAFIA Nutrition MCP Server (%s) on 0.0.0.0:%s", transport, port)
        _mcp.run(transport=transport, host="0.0.0.0", port=port)
    else:
        _mcp.run()  # stdio — for Claude Desktop / MCP client direct connection
