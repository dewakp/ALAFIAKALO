"""Tests for recipe-URL ingestion: JSON-LD parsing, SSRF guard, auth gates."""

import pytest
from httpx import AsyncClient

from app.services.recipe_ingest import RecipeError, _assert_public_http, parse_recipe_html

_RECIPE_HTML = """
<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@graph":[
  {"@type":"Organization","name":"Some Site"},
  {"@type":"Recipe","name":"Nigerian Jollof Rice",
   "recipeIngredient":["2 cups long-grain rice","1 can tomato paste","1 onion","2 tbsp vegetable oil"],
   "recipeYield":"6 servings",
   "nutrition":{"@type":"NutritionInformation","calories":"310 calories",
                "proteinContent":"7 g","carbohydrateContent":"58 g","fatContent":"6 g"}}
]}
</script>
</head><body>irrelevant</body></html>
"""

_NO_NUTRITION_HTML = """
<script type='application/ld+json'>
{"@type":["Recipe"],"name":"Plain Beans","recipeIngredient":["1 cup beans"],"recipeYield":4}
</script>
"""


def test_parse_recipe_with_graph_and_nutrition():
    r = parse_recipe_html(_RECIPE_HTML)
    assert r["name"] == "Nigerian Jollof Rice"
    assert len(r["ingredients"]) == 4
    assert r["servings"] == 6
    assert r["nutrition"]["calories"] == 310.0
    assert r["nutrition"]["protein_g"] == 7.0


def test_parse_recipe_without_nutrition():
    r = parse_recipe_html(_NO_NUTRITION_HTML)
    assert r["name"] == "Plain Beans"
    assert r["servings"] == 4
    assert r["nutrition"] is None


def test_parse_non_recipe_page():
    assert parse_recipe_html("<html><body>no recipes here</body></html>") is None


def test_ssrf_guard_blocks_private():
    for bad in ("http://localhost/x", "http://127.0.0.1/x", "ftp://example.com/x",
                "http://169.254.169.254/latest"):
        with pytest.raises(RecipeError):
            _assert_public_http(bad)


@pytest.mark.asyncio
async def test_recipe_analyze_requires_auth(client: AsyncClient):
    r = await client.post("/api/v1/nutrition/recipe-analyze", json={"url": "https://example.com/r"})
    assert r.status_code == 401
