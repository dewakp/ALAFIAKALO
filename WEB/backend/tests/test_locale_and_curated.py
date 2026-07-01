"""Regression tests for the data-driven curated catalog + locale unit factors.

These lock in the two "curated dishes become data" / "per-locale units" workstream
items so they can't silently regress (parity with the old hardcoded behaviour +
correct locale scaling).
"""
import pytest

from app.services import curated_foods, locale_units


# ── Curated dish catalog (loaded from app/data/regional_dishes.json) ──────────

@pytest.mark.parametrize("name,expected_label_contains,kcal", [
    ("suya", "Suya", 270.0),
    ("beef suya", "Suya", 270.0),
    ("jollof rice", "Jollof", 160.0),
    ("rice and beans", "Rice and beans", 155.0),
    ("rice and bean", "Rice and beans", 155.0),   # singular alt in the OR-group
    ("tomato stew", "Tomato stew", 120.0),
    ("coffee", "Coffee", 1.0),
    ("black coffee", "Coffee", 1.0),
    ("green tea", "Tea", 1.0),
    ("egg", "Egg, whole, raw", 143.0),
    ("boiled egg", "hard-boiled", 155.0),
])
def test_curated_lookup_matches(name, expected_label_contains, kcal):
    result = curated_foods.lookup(name)
    assert result is not None, f"expected a curated match for {name!r}"
    label, nutrients = result
    assert expected_label_contains.lower() in label.lower()
    assert nutrients["calories"] == kcal


@pytest.mark.parametrize("name", ["", "chicken thigh", "scrambled eggs", "grilled salmon"])
def test_curated_lookup_passthrough(name):
    # Non-curated foods fall through (None) so USDA/AI handles them.
    assert curated_foods.lookup(name) is None


def test_curated_boiled_egg_distinct_from_raw():
    raw = curated_foods.lookup("egg")[1]
    boiled = curated_foods.lookup("hard boiled egg")[1]
    assert boiled["calories"] == 155.0 and raw["calories"] == 143.0


# ── Locale cooking-measure volumes ────────────────────────────────────────────

def test_us_baseline_is_identity():
    f = locale_units.volume_factors(country="United States")
    assert f == {"cup": 1.0, "tbsp": 1.0, "tsp": 1.0}


def test_preferred_units_overrides_country():
    # Explicit metric preference wins even for a US country.
    f = locale_units.volume_factors(country="United States", preferred_units="metric")
    assert f["cup"] > 1.0  # 250 ml / 240 ml baseline


def test_metric_cup_larger_than_us():
    f = locale_units.volume_factors(country="France")
    assert f["cup"] == round(250.0 / 240.0, 4)


def test_australian_tablespoon_is_20ml():
    f = locale_units.volume_factors(country="Australia")
    assert f["tbsp"] == round(20.0 / 15.0, 4)  # AU tbsp = 20 ml


def test_locale_suffix_fallback():
    assert locale_units.units_for_locale(locale="en-US")["system"] == "us"
    assert locale_units.units_for_locale(locale="fr-FR")["system"] == "metric"


def test_unknown_defaults_to_metric():
    assert locale_units.units_for_locale()["system"] == "metric"
