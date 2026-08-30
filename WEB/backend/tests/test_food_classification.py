"""Food category matching was substring-based, so it fired on coincidences.

`classify()` decides a food's plausibility band AND its default portion, and it
matched raw substrings:

    "ripe plantain boiled"       b-OIL-ed     -> oil_fat  (700-902 kcal/100 g)
    "hard boiled eggs"           b-OIL-ed     -> oil_fat, not egg
    "broiled chicken"            br-OIL-ed    -> oil_fat, not meat
    "2 teaspoons of canola oil"  TEA-spoons   -> tea_coffee

The plantain reached a patient: 116 kcal/100 g was judged against an oil's band
and reported as "likely a wrong match".

A keyword must now END a word, with any prefix and an optional plural — the line
between morphology and coincidence:

    peanuts   pea+NUT+s    matches      boiled     b+oil+ed     does not
    tomatoes  TOMATO+es    matches      teaspoons  TEA+spoons   does not

Declaration order still decides priority, because it encodes intent
(`nutrition_drink` above `sugar_sweet` so BOOST is not a confection). Only a
strictly more specific phrase may displace an earlier rule, which is what makes
"peanut butter" a nut rather than the butter it contains.
"""

import pytest

from app.services.nutrition_reference import classify


@pytest.mark.parametrize("name,expected", [
    # The reported case, and its family.
    ("ripe plantain boiled", "unknown"),      # plantain is uncatalogued — but NOT an oil
    ("hard boiled eggs", "egg"),
    ("hard-boiled medium sized brown eggs", "egg"),
    ("broiled chicken", "lean_meat"),
    ("broiled yellow oranges", "fruit_fresh"),
    # A unit is not a food.
    ("2 teaspoons of canola oil", "oil_fat"),
    (".3 teaspoon of peanut oil", "oil_fat"),
])
def test_a_substring_coincidence_no_longer_decides_the_category(name, expected):
    assert classify(name) == expected


@pytest.mark.parametrize("name,expected", [
    ("peanuts", "nut_seed"),          # pea+NUT+s
    ("groundnuts", "nut_seed"),
    ("tomatoes", "vegetable"),        # TOMATO+es
    ("watermelon", "fruit_fresh"),    # water+MELON, previously "water"
    ("dates", "fruit_dried"),
])
def test_plurals_and_compounds_still_match(name, expected):
    """Requiring a whole word lost these; allowing any substring caused the
    bugs above. Ending a word keeps both correct."""
    assert classify(name) == expected


@pytest.mark.parametrize("name,expected", [
    # Declaration order encodes intent and must survive.
    ("boost fiber chocolate", "nutrition_drink"),   # not sugar_sweet
    ("diet coke", "diet_beverage"),                 # not beverage
    ("pineapple juice", "beverage"),                # not fruit_fresh
])
def test_rule_priority_is_preserved(name, expected):
    assert classify(name) == expected


def test_a_more_specific_phrase_displaces_a_vaguer_earlier_one():
    """`butter` sits in oil_fat, declared before nut_seed's `peanut butter`."""
    assert classify("peanut butter") == "nut_seed"
    assert classify("butter") == "oil_fat"


def test_a_cooking_medium_still_does_not_decide_the_food():
    """The head-phrase rule must keep working alongside the new matching."""
    assert classify("beans cooked in palm oil") == "legume_cooked"


def test_the_oil_band_is_only_used_for_actual_oils():
    """The band drives plausibility: a 116 kcal/100 g food judged against
    700-902 is reported to a clinician as a wrong match."""
    from app.services.nutrition_reference import expected_kcal_band

    low, high = expected_kcal_band("olive oil")
    assert (low, high) == (700, 902)
    assert expected_kcal_band("hard boiled eggs") != (700, 902)
