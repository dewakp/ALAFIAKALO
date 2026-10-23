# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""Tests for NLM-style food extraction and composite USDA matching."""

import pytest

from app.services.nlm_food_extractor import extract_food_items_nlm
from app.services import nutrient_estimator as estimator_module


def test_extract_food_items_nlm_composite_phrase():
    """Extractor should split composite phrases and expand known abbreviations."""
    items = extract_food_items_nlm("Grilled chicken, potatoes porridge, RCF")
    assert items == ["chicken", "potatoes porridge", "roasted corn flour"]


@pytest.mark.asyncio
async def test_a_composite_name_is_never_summed_into_one_per_100g(monkeypatch):
    """This test used to PIN the bug. It asserted that the three items of
    "Grilled chicken, potatoes porridge, RCF" merged into one "per-100 g" of
    645 kcal and 103 g carbs — three foods' densities added together, which
    describes 100 g of nothing (§3c). In production that path cached
    "bitter leaves/uziza/egusi/peanut/palm…" at 1,180 kcal and 113.7 g fat per
    100 g, above pure fat. A composite name that reaches the single-food path
    is now a miss, so it falls through to a tier that can describe a dish."""
    seen = []

    async def fake_search_usda_foods(query: str, page_size: int = 5):
        seen.append(query)
        return [] if "," in query else [
            {"fdc_id": 101, "description": query, "data_type": "Foundation",
             "nutrients": {"calories": 165.0, "protein_g": 31.0, "carbs_g": 0.0, "fat_g": 3.6}}]

    monkeypatch.setattr(estimator_module, "search_usda_foods", fake_search_usda_foods)

    assert await estimator_module._try_usda("Grilled chicken, potatoes porridge, RCF") is None
    assert seen == ["Grilled chicken, potatoes porridge, RCF"], "no per-item summing pass"
