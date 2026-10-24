# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""A bracket DESCRIBES its item unless the patient measured what is in it.

Measured on 1,107 meals (2026-10-24): 223 of 288 bracketed items carried a
description or an unmeasured ingredient list — "(cooked)", "(ripe with brown
spots)", "Okro soup(crowfeet, cow skin, goat meat, dried crayfish)" — and the
parser stored each word as a separate food. In production, meal 1116 counted
"ripe with brown spots" at 27 kcal, and meal 1118 held "cooked",
"cooked/stewed" and "cooking medium" as items. Under "the patient determines the
amount" each would have been asked for an amount.
"""

import pytest

from app.services import nutrient_estimator as ne
from app.services.meal_parser import parse_meal_text


def test_a_description_is_part_of_the_item_not_a_food():
    comps = parse_meal_text("50 g Salmon fillet (cooked), Banana (ripe with brown spots)")
    assert [(c.food_name, c.qty_text, c.qualifier) for c in comps] == [
        ("salmon fillet", "50 g", "cooked"),
        ("banana", "default", "ripe with brown spots"),
    ]


def test_an_unmeasured_ingredient_list_describes_one_dish():
    [c] = parse_meal_text("Okro soup(crowfeet, cow skin, goat meat - ira, dried crayfish)")
    assert c.food_name == "okro soup"
    assert c.qualifier == "crowfeet, cow skin, goat meat - ira, dried crayfish"


def test_a_measured_recipe_is_still_its_items():
    names = [(c.food_name, c.qty_text) for c in
             parse_meal_text("custard mix(2 tablespoons of custard powder, 1 cup of milk)")]
    assert ("custard powder", "2 tablespoons") in names and ("milk", "1 cup") in names


def test_a_bracketed_amount_is_still_an_amount():
    [c] = parse_meal_text("Organic Leek(0.1 bunch)")
    assert c.qualifier == "" and c.qty_text != "default"


def test_an_amount_need_not_lead_its_phrase():
    """"(with 2 eggs)" is two eggs — it used to parse as a food named
    "with eggs" with no amount."""
    names = [(c.food_name, c.qty_text) for c in parse_meal_text("Boost Glucose Control (with 2 eggs)")]
    assert ("eggs", "2") in names


@pytest.mark.asyncio
async def test_the_lookup_uses_the_item_s_own_name(monkeypatch, db):
    """Learned and cached foods are keyed by the bare name; a description in
    the lookup missed the printed Boost label."""
    asked = []

    async def fake(db_, name, serving_size=None):
        asked.append(name)
        return {"source": "usda", "fdc_id": None, "food_name": name, "confidence": 1.0,
                "nutrients": {"calories": 200.0}, "believable": True}

    monkeypatch.setattr(ne, "estimate_nutrients", fake)
    out = await ne.estimate_meal_nutrients(db, "50 g Salmon fillet (cooked)")
    assert asked == ["salmon fillet"]
    assert [c["food_name"] for c in out["components"]] == ["salmon fillet"]
