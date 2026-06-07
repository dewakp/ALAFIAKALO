"""Tests for NLM-style food extraction and composite USDA matching."""

import pytest

from app.services.nlm_food_extractor import extract_food_items_nlm
from app.services import nutrient_estimator as estimator_module


def test_extract_food_items_nlm_composite_phrase():
    """Extractor should split composite phrases and expand known abbreviations."""
    items = extract_food_items_nlm("Grilled chicken, potatoes porridge, RCF")
    assert items == ["chicken", "potatoes porridge", "roasted corn flour"]


@pytest.mark.asyncio
async def test_try_usda_uses_extracted_items_for_mixed_description(monkeypatch):
    """When full phrase fails, estimator should match extracted items and merge nutrients."""

    nutrient_map = {
        101: {"calories": 165.0, "protein_g": 31.0, "carbs_g": 0.0, "fat_g": 3.6},
        202: {"calories": 120.0, "protein_g": 3.0, "carbs_g": 27.0, "fat_g": 0.2},
        303: {"calories": 360.0, "protein_g": 8.0, "carbs_g": 76.0, "fat_g": 4.0},
    }

    async def fake_search_usda_foods(query: str, page_size: int = 5):
        q = query.strip().lower()
        if q == "grilled chicken, potatoes porridge, rcf":
            return []
        if q == "chicken":
            return [{"fdc_id": 101, "description": "chicken", "data_type": "Foundation", "nutrients": {}}]
        if q == "potatoes porridge":
            return [{"fdc_id": 202, "description": "potatoes porridge", "data_type": "Foundation", "nutrients": {}}]
        if q == "roasted corn flour":
            return [{"fdc_id": 303, "description": "roasted corn flour", "data_type": "Foundation", "nutrients": {}}]
        return []

    async def fake_get_usda_food_detail(fdc_id: int):
        return {"nutrients": nutrient_map[fdc_id]}

    monkeypatch.setattr(estimator_module, "search_usda_foods", fake_search_usda_foods)
    monkeypatch.setattr(estimator_module, "get_usda_food_detail", fake_get_usda_food_detail)

    result = await estimator_module._try_usda("Grilled chicken, potatoes porridge, RCF")

    assert result is not None
    assert result["source"] == "usda"
    assert result["fdc_id"] is None
    assert result["food_name"] == "chicken, potatoes porridge, roasted corn flour"
    assert result["serving_size"] == "Composite meal (3/3 items matched)"
    assert result["confidence"] == 0.9
    assert result["nutrients"]["calories"] == 645.0
    assert result["nutrients"]["protein_g"] == 42.0
    assert result["nutrients"]["carbs_g"] == 103.0
    assert result["nutrients"]["fat_g"] == 7.8
