# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""The sugar limit must charge the quantity WHO and the FDA actually legislate.

Operator, 2026-10-21: *"follow the WHO and FDA guidelines on sugar and every
other nutrient. Thats wha a clinician or dietician will do."*

The reported harm, reproduced below as `test_two_bananas_no_longer_exhaust_a_
diabetics_whole_budget`: WHO's FREE-sugars percentage was charged against
TOTAL sugars, so ~30 g of banana — sugar WHO's definition expressly excludes —
spent a 21.1 g daily allowance.
"""

import pytest

from app.services import free_sugars as fs


# ── the case that decides the order of evidence ───────────────────────────

def test_fruit_juice_is_ALL_free_sugar():
    """WHO names fruit juice in its own definition, and this is the one answer
    the function must not get wrong.

    A real row on this record is `1 cup of orange juice — 20.65 g`. Juice
    resolves to the `fruit_fresh` band and a 100%-juice label truthfully
    declares ZERO added sugars, so BOTH the class rule and the label rule say
    "no free sugar" on their own. Only checking the guideline's own vocabulary
    first gets it right.
    """
    got = fs.free_sugars_for(band="fruit_fresh", total_sugars_g=20.65,
                             added_sugars_g=0.0, food_name="1 cup of orange juice")
    assert got.grams == pytest.approx(20.65)
    assert got.basis == "who_named_source"
    assert got.assessed


def test_whole_fruit_is_NO_free_sugar():
    """WHO: *"does not include the sugars in fresh fruits and vegetables"*."""
    got = fs.free_sugars_for(band="fruit_fresh", total_sugars_g=15.8,
                             food_name="banana")
    assert got.grams == 0.0
    assert got.basis == "who_intrinsic"


def test_milk_sugars_are_intrinsic():
    got = fs.free_sugars_for(band="dairy", total_sugars_g=5.0, food_name="milk")
    assert got.grams == 0.0


def test_honey_is_free_sugar_by_name_and_by_class():
    by_name = fs.free_sugars_for(band="unknown", total_sugars_g=82.1,
                                 food_name="1 tbsp honey")
    assert by_name.grams == pytest.approx(82.1)
    by_class = fs.free_sugars_for(band="sugar_sweet", total_sugars_g=82.1,
                                  food_name="table sugar")
    assert by_class.grams == pytest.approx(82.1)
    assert by_class.basis == "who_class"


# ── unknown is not zero ───────────────────────────────────────────────────

def test_a_composite_dish_is_UNASSESSED_not_zero():
    """§3aa, on the nutrient the operator reported. A pizza holds intrinsic and
    added sugar together and no guideline apportions it per dish. Answering
    zero would report compliance nobody measured."""
    got = fs.free_sugars_for(band="prepared_dish", total_sugars_g=8.96,
                             food_name="Pizza with pepperoni")
    assert got.grams is None, "a composite must never be scored as zero free sugar"
    assert got.assessed is False
    assert got.unassessed_g == pytest.approx(8.96)


def test_an_unclassified_food_is_unassessed():
    got = fs.free_sugars_for(band=None, total_sugars_g=3.8,
                             food_name="eba, okro and stew")
    assert got.grams is None
    assert got.unassessed_g == pytest.approx(3.8)


def test_an_unassessed_food_contributes_NOTHING_to_a_total():
    """The upper bound is reported beside the total, never added into it —
    otherwise "up to" silently becomes "is"."""
    got = fs.free_sugars_for(band="soup_stew", total_sugars_g=12.0)
    assert got.grams is None
    assert got.unassessed_g == 12.0


# ── a label is a declared fact ────────────────────────────────────────────

def test_a_label_figure_outranks_the_class():
    got = fs.free_sugars_for(band="nutrition_drink", total_sugars_g=5.14,
                             added_sugars_g=4.16,
                             food_name="8 Fl oz Boost Glucose Control")
    assert got.grams == pytest.approx(4.16)
    assert got.basis == "label"


def test_added_sugars_above_total_is_capped_and_SAID():
    """Measured on this record: the Boost rows store added 4.1616 against total
    4.1371. Added sugar cannot exceed the sugar the food contains, so the
    larger figure is a basis error — capped, and the reason says so rather than
    letting a derived free-sugar figure exceed the food's own sugar."""
    got = fs.free_sugars_for(band="nutrition_drink", total_sugars_g=4.1371,
                             added_sugars_g=4.1616, food_name="Boost")
    assert got.grams == pytest.approx(4.1371)
    assert got.basis == "label_capped"
    assert "more than" in got.reason


def test_a_zero_label_is_a_measurement_not_an_absence():
    """Peanuts declare 0.0 g added sugars on this record. That is a stated
    zero and must read as assessed, unlike a composite with no figure."""
    got = fs.free_sugars_for(band="nut_seed", total_sugars_g=3.26,
                             added_sugars_g=0.0, food_name="peanuts")
    assert got.grams == 0.0
    assert got.assessed is True
    assert got.basis == "label"


# ── the limit itself ──────────────────────────────────────────────────────

def test_the_limit_is_WHOs_percentage_of_the_patients_own_energy():
    """5% conditional for diabetes, 10% strong otherwise, at 4 kcal/g. 21.1 g
    on the reference record's 1,688 kcal is the figure §3az already records."""
    assert fs.who_free_sugar_limit_g(1688, diabetes=True) == pytest.approx(21.1, abs=0.05)
    assert fs.who_free_sugar_limit_g(1688, diabetes=False) == pytest.approx(42.2, abs=0.05)


def test_the_fda_dv_agrees_with_WHO_at_2000_kcal():
    """The FDA's 50 g added-sugars DV IS WHO's 10% of 2,000 kcal. That the two
    authorities give the same number is why one rule can cite both."""
    assert fs.who_free_sugar_limit_g(2000, diabetes=False) == pytest.approx(
        fs.FDA_ADDED_SUGARS_DV_G)


def test_two_bananas_no_longer_exhaust_a_diabetics_whole_budget():
    """THE REPORTED BUG. ~30 g of banana sugar against a 21.1 g limit used to
    read 142% of a day's allowance. WHO excludes it entirely."""
    limit = fs.who_free_sugar_limit_g(1688, diabetes=True)
    two_bananas = fs.free_sugars_for(band="fruit_fresh", total_sugars_g=31.6,
                                     food_name="2 bananas")
    assert two_bananas.grams == 0.0
    assert (two_bananas.grams or 0) / limit == 0.0


# ── the anti-food-list guard ──────────────────────────────────────────────

def test_every_food_word_in_this_module_is_QUOTED_from_an_authority():
    """§3c forbids aliases and §3an fails the build on a condition→food
    literal. This module names four foods, and each one must appear in a
    definition it cites — otherwise it is the per-food table those rules exist
    to prevent, wearing a citation.
    """
    cited = (fs.WHO_FREE_SUGARS_DEFINITION + " "
             + fs.WHO_INTRINSIC_EXCLUSION + " "
             + fs.FDA_ADDED_SUGARS_DEFINITION).lower()
    for stem in fs._WHO_NAMED_FREE_SOURCES:
        assert stem in cited, (
            f"{stem!r} is not named by WHO or the FDA — a food word that is not "
            f"quoted from an authority does not belong in this module")


def test_the_band_classes_are_structural_not_foods():
    """The class sets must hold BAND names, never foods. A band is a structural
    category resolved by `food_category_service`; the moment a food name
    appears in one of these sets this module has become a lookup table."""
    every = fs._INTRINSIC_ONLY | fs._ALL_FREE | fs._UNASSESSABLE
    known_bands = {
        "fruit_fresh", "vegetable", "dairy", "cheese", "legume_cooked",
        "nut_seed", "grain_cooked", "egg", "lean_meat", "fatty_meat",
        "oil_fat", "water", "tea_coffee", "condiment", "sugar_sweet",
        "bread_baked", "cereal_dry", "snack_processed", "prepared_dish",
        "soup_stew", "beverage", "alcohol", "nutrition_drink", "unknown",
    }
    assert every <= known_bands, f"not band categories: {sorted(every - known_bands)}"


def test_no_class_is_claimed_twice():
    """A band in two sets would make the answer depend on check order."""
    assert not (fs._INTRINSIC_ONLY & fs._ALL_FREE)
    assert not (fs._INTRINSIC_ONLY & fs._UNASSESSABLE)
    assert not (fs._ALL_FREE & fs._UNASSESSABLE)
