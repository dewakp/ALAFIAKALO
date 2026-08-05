"""Portion phrase → grams.

Every phrasing below came out of a real vision-model reply or a USDA serving
string. Quantity estimation is only useful if it is right on these.
"""

import pytest

from app.services.portion_estimator import estimate_grams


@pytest.mark.parametrize("text,food,expected,tol", [
    # Stated weight always wins, whatever else is in the string.
    ("150 g", "rice", 150, 0.5),
    ("1 cup / 150 g", "jollof rice", 150, 0.5),
    ("0.4 kg", "yam", 400, 1),
    ("6 oz", "chicken breast", 170, 1),
    # Volume × density — rice is not water.
    ("1 cup", "jollof rice", 158, 2),
    ("2 cups", "beans", 346, 3),
    ("1 cup", "spinach", 72, 2),        # leaves are mostly air
    ("1 tbsp", "palm oil", 14, 1),
    # Per-food unit weights, with size adjustment.
    ("1 medium carrot", "carrot", 61, 1),
    ("2 eggs", "egg", 100, 1),
    ("1 large egg", "egg", 70, 1),
])
def test_known_portions(text, food, expected, tol):
    got = estimate_grams(text, food).grams
    assert got is not None and abs(got - expected) <= tol, f"{text!r} → {got}"


@pytest.mark.parametrize("text,expected", [
    ("½ cup", 79), ("1/2 cup", 79), ("¾ cup", 119), ("1 1/2 cups", 238), ("1 cup", 158),
])
def test_fractions(text, expected):
    """NFKC rewrites '½' to '1⁄2' with U+2044, which the ASCII regexes miss —
    normalising before substituting silently turned half a cup into a full one."""
    got = estimate_grams(text, "rice").grams
    assert got is not None and abs(got - expected) <= 2, f"{text!r} → {got}"


def test_longest_food_key_wins():
    """'sweet potato' must not be matched by the 'potato' rule."""
    assert estimate_grams("1 medium", "sweet potato").grams == pytest.approx(130, abs=1)
    assert estimate_grams("1 medium", "potato").grams == pytest.approx(173, abs=1)


def test_learned_correction_overrides_heuristics():
    plain = estimate_grams("1 cup", "jollof rice")
    learned = estimate_grams("1 cup", "jollof rice", learned_g=210)
    assert learned.grams == pytest.approx(210, abs=0.5)
    assert learned.confidence > plain.confidence
    assert "correction" in learned.basis


def test_learned_correction_scales_with_count():
    assert estimate_grams("2 cups", "rice", learned_g=100).grams == pytest.approx(200, abs=0.5)


@pytest.mark.parametrize("text", ["", None, "some food", "a bit"])
def test_uninterpretable_returns_none_not_a_guess(text):
    """Better to say nothing than to invent a number that becomes a calorie count."""
    est = estimate_grams(text, "stew")
    assert est.grams is None and est.confidence == 0.0


def test_confidence_ordering_reflects_trustworthiness():
    stated = estimate_grams("150 g", "rice").confidence
    volume = estimate_grams("1 cup", "rice").confidence
    vague = estimate_grams("a plate", "rice").confidence
    assert stated > volume > vague > 0


def test_results_are_clamped_to_sane_range():
    assert estimate_grams("500 kg", "rice").grams == 5000.0     # MAX_G
    assert estimate_grams("0.0001 g", "salt").grams == 1.0      # MIN_G


def test_as_dict_shape_is_api_ready():
    d = estimate_grams("1 cup / 150 g", "rice").as_dict()
    assert d["estimated_grams"] == 150.0
    assert 0 <= d["grams_confidence"] <= 1
    assert isinstance(d["grams_basis"], str) and d["grams_basis"]
