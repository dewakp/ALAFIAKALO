# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""An empty record must never outrank one that carries numbers.

Operator, 2026-10-21, on a foundational error in nutritional analysis, with
grapefruit as one of the examples. Measured cause:

USDA returns TWO rows called "Grapefruit, raw" and they tie on relevance:

    Grapefruit, raw   Survey (FNDDS)    42 kcal   dt_pref 1
    Grapefruit, raw   Foundation       NO DATA    dt_pref 0   <- won the tie

The sort key was `(-rank, dt_pref, idx)`, so the dataset preference ran BEFORE
"does this row carry any numbers". The empty Foundation row won,
`_try_usda_single` returned None, the whole USDA rung failed, and grapefruit
fell through to the branded rung — which answered with a sweetened 222 ml
drink: 45 kcal, 0 g protein, NO potassium, and 9.9 g of ADDED sugar in a fruit
that contains none.

Banana escaped only because its FNDDS row had no empty twin. Branded's banana
is 312 kcal.

Operator: *"FNDDS is more current, use it first."* Both halves are pinned here:
data before preference, and FNDDS before Foundation before SR Legacy.
"""

import pytest

from app.services import nutrient_estimator as ne

pytestmark = pytest.mark.asyncio


def _row(desc, kcal, data_type, fdc_id=1):
    nutrients = {} if kcal is None else {"calories": kcal, "protein_g": 1.0}
    return {"fdc_id": fdc_id, "description": desc, "data_type": data_type,
            "nutrients": nutrients, "food_category": None,
            "serving_size": None, "serving_size_unit": None}


async def _pick(monkeypatch, query, rows):
    async def fake_search(q, page_size=5):
        return rows

    monkeypatch.setattr(
        "app.core.nutrition_data.search_usda_foods", fake_search)
    monkeypatch.setattr(ne, "search_usda_foods", fake_search, raising=False)
    return await ne._try_usda_single(query)


async def test_an_empty_record_never_wins(monkeypatch):
    """THE REPORTED BUG, in its minimal form."""
    best = await _pick(monkeypatch, "grapefruit", [
        _row("Grapefruit, raw", 42, "Survey (FNDDS)", 2709165),
        _row("Grapefruit, raw", None, "Foundation", 2758977),
    ])
    assert best is not None, "an empty twin must not sink the whole rung"
    assert best["nutrients"]["calories"] == 42


async def test_fndds_is_preferred_among_equals(monkeypatch):
    """Operator: "FNDDS is more current, use it first." It is also the dataset
    carrying Added Sugars (usda 1235) — the quantity WHO and the FDA
    legislate."""
    best = await _pick(monkeypatch, "grapefruit", [
        _row("Grapefruit, raw", 39, "SR Legacy", 1),
        _row("Grapefruit, raw", 41, "Foundation", 2),
        _row("Grapefruit, raw", 42, "Survey (FNDDS)", 3),
    ])
    assert best["fdc_id"] == 3


async def test_relevance_still_beats_dataset(monkeypatch):
    """Dataset order is a TIE-BREAK, not an override: a more relevant row in a
    less-preferred dataset must still win, or "banana" picks banana chips
    because they happen to be in FNDDS."""
    best = await _pick(monkeypatch, "banana", [
        _row("Banana chips", 519, "Survey (FNDDS)", 1),
        _row("Banana, raw", 97, "SR Legacy", 2),
    ])
    assert best["fdc_id"] == 2


async def test_data_beats_relevance_only_when_the_better_row_is_empty(monkeypatch):
    """The guard is narrow. An empty row loses; it does not promote an
    irrelevant one above a relevant one that has data."""
    best = await _pick(monkeypatch, "grapefruit", [
        _row("Grapefruit, raw", None, "Survey (FNDDS)", 1),
        _row("Grapefruit, canned", 36, "Survey (FNDDS)", 2),
    ])
    assert best["fdc_id"] == 2
