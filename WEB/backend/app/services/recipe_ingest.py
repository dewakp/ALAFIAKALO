"""Recipe-URL ingestion — the third meal-content input (URL / description / photo).

Recipe pages embed schema.org/Recipe JSON-LD (name, recipeIngredient, yield,
often per-serving nutrition). We parse that — no HTML scraping heuristics —
then price the ingredient list through the believability-guarded estimator.

Learning pipeline: when the page publishes its own nutrition, that authoritative
per-serving profile is converted to per-100 g and recorded in
`learned_food_nutrients` (source="recipe") under the dish name — so future
*descriptions* naming the dish, and photo labels tied to it, price correctly.
"""

import ipaddress
import json
import logging
import re
import socket
from typing import Any
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

_LDJSON_RE = re.compile(
    r"<script[^>]*type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
    re.IGNORECASE | re.DOTALL,
)

# schema.org NutritionInformation → our nutrient keys ("240 calories", "4 g")
_NUTRITION_FIELDS = {
    "calories": "calories",
    "proteinContent": "protein_g",
    "carbohydrateContent": "carbs_g",
    "fatContent": "fat_g",
    "fiberContent": "fiber_g",
    "sugarContent": "sugar_g",
    "sodiumContent": "sodium_mg",
    "cholesterolContent": "cholesterol_mg",
}


class RecipeError(Exception):
    """User-facing recipe ingestion failure."""


def _assert_public_http(url: str) -> None:
    """SSRF guard: only public http(s) hosts."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise RecipeError("Provide a full http(s) recipe link.")
    host = parsed.hostname
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        raise RecipeError("That site could not be found — check the link.")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise RecipeError("That link points to a private address and can't be fetched.")


def _first_str(v: Any) -> str:
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, list) and v:
        return _first_str(v[0])
    if isinstance(v, dict):
        return _first_str(v.get("name") or v.get("@value") or "")
    return ""


def _parse_servings(recipe_yield: Any) -> int:
    text = _first_str(recipe_yield) or str(recipe_yield or "")
    m = re.search(r"\d+", text)
    n = int(m.group()) if m else 1
    return max(1, min(n, 64))


def _parse_amount(v: Any) -> float | None:
    m = re.search(r"[\d.]+", str(v or ""))
    return float(m.group()) if m else None


def _walk_for_recipe(node: Any) -> dict | None:
    """Find the first @type Recipe object in a JSON-LD document (incl. @graph)."""
    if isinstance(node, list):
        for item in node:
            found = _walk_for_recipe(item)
            if found:
                return found
        return None
    if not isinstance(node, dict):
        return None
    t = node.get("@type")
    types = t if isinstance(t, list) else [t]
    if any(str(x).lower() == "recipe" for x in types if x):
        return node
    for key in ("@graph", "mainEntity", "itemListElement"):
        if key in node:
            found = _walk_for_recipe(node[key])
            if found:
                return found
    return None


def parse_recipe_html(html: str) -> dict | None:
    """Extract a normalized recipe from a page's JSON-LD blocks.

    Returns {name, ingredients: [str], servings: int, nutrition: {…}|None}.
    """
    for m in _LDJSON_RE.finditer(html):
        raw = m.group(1).strip()
        try:
            doc = json.loads(raw)
        except json.JSONDecodeError:
            continue
        recipe = _walk_for_recipe(doc)
        if not recipe:
            continue
        ingredients = [
            _first_str(i) for i in (recipe.get("recipeIngredient") or [])
            if _first_str(i)
        ]
        if not ingredients:
            continue
        nutrition = None
        raw_nut = recipe.get("nutrition")
        if isinstance(raw_nut, dict):
            parsed = {
                ours: _parse_amount(raw_nut.get(theirs))
                for theirs, ours in _NUTRITION_FIELDS.items()
                if _parse_amount(raw_nut.get(theirs)) is not None
            }
            if parsed.get("calories"):
                nutrition = parsed
        return {
            "name": _first_str(recipe.get("name")) or "Recipe",
            "ingredients": ingredients[:40],
            "servings": _parse_servings(recipe.get("recipeYield")),
            "nutrition": nutrition,   # per serving, as published
        }
    return None


async def fetch_recipe(url: str) -> dict:
    """Fetch a recipe URL and parse its structured recipe data."""
    _assert_public_http(url)
    try:
        async with httpx.AsyncClient(
            timeout=20.0, follow_redirects=True,
            headers={
                # Recipe sites widely block "bot-ish" agents; a standard browser
                # UA is required to read the public page a user just visited.
                "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                               "AppleWebKit/537.36 (KHTML, like Gecko) "
                               "Chrome/126.0.0.0 Safari/537.36"),
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
            },
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            html = resp.text
    except httpx.HTTPError as e:
        raise RecipeError(f"Could not fetch that page ({e.__class__.__name__}).")

    recipe = parse_recipe_html(html)
    if not recipe:
        raise RecipeError(
            "No structured recipe found on that page — try the recipe's own page "
            "(not a listing), or enter the ingredients as a description."
        )
    return recipe
