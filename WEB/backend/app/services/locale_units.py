"""Locale-aware cooking-measure volumes.

A "cup"/"tablespoon"/"teaspoon" is not the same size everywhere: the US uses
customary/label measures, most of the world uses metric, and Australia's
tablespoon is 20 ml. When a user writes "1 cup of rice" we should honour *their*
locale's measure. This maps a country / unit preference to the volume (ml) of
each measure, and to a scale factor against the estimator's baseline so the
food-density tables in `meal_parser` stay valid (they're calibrated to a 240 ml
cup / 15 ml tbsp / 5 ml tsp).
"""
from __future__ import annotations

# Baseline the meal_parser density tables are calibrated to.
_BASE = {"cup": 240.0, "tbsp": 15.0, "tsp": 5.0}

# Volume (ml) of each measure per unit system.
_SYSTEMS: dict[str, dict[str, float]] = {
    "us":     {"cup": 240.0, "tbsp": 15.0, "tsp": 5.0},    # US FDA label (= baseline)
    "metric": {"cup": 250.0, "tbsp": 15.0, "tsp": 5.0},    # most of the world
    "uk":     {"cup": 250.0, "tbsp": 15.0, "tsp": 5.0},
    "au":     {"cup": 250.0, "tbsp": 20.0, "tsp": 5.0},    # AU tablespoon = 20 ml
}
_DEFAULT_SYSTEM = "metric"

# Countries that use US customary measures (imperial-ish for cooking).
_US_COUNTRIES = {"united states", "us", "usa", "u.s.", "u.s.a.", "america"}
_AU_COUNTRIES = {"australia", "au", "aus"}
_UK_COUNTRIES = {"united kingdom", "uk", "gb", "great britain", "england",
                 "scotland", "wales", "northern ireland", "ireland"}


def _system_for(country: str | None, preferred_units: str | None,
                locale: str | None = None) -> str:
    """Resolve a unit system. Explicit `preferred_units` wins over country/locale."""
    pu = (preferred_units or "").strip().lower()
    if pu in ("imperial", "us", "customary"):
        return "us"
    if pu == "metric":
        return "metric"

    c = (country or "").strip().lower()
    if c:
        if c in _US_COUNTRIES:
            return "us"
        if c in _AU_COUNTRIES:
            return "au"
        if c in _UK_COUNTRIES:
            return "uk"
        return "metric"

    # Fall back to the locale region suffix (e.g. "en-US" → US).
    loc = (locale or "").strip().lower()
    if loc.endswith("-us") or loc == "en-us":
        return "us"
    if loc.endswith("-au"):
        return "au"
    if loc.endswith(("-gb", "-uk", "-ie")):
        return "uk"
    return _DEFAULT_SYSTEM


def units_for_locale(country: str | None = None, preferred_units: str | None = None,
                     locale: str | None = None) -> dict:
    """Return {cup, tbsp, tsp} volumes (ml) + resolved `system` name."""
    system = _system_for(country, preferred_units, locale)
    measures = _SYSTEMS.get(system, _SYSTEMS[_DEFAULT_SYSTEM])
    return {**measures, "system": system}


def volume_factors(country: str | None = None, preferred_units: str | None = None,
                   locale: str | None = None) -> dict:
    """Scale factors (cup/tbsp/tsp) vs the parser's 240/15/5 ml baseline.

    Multiply a baseline volume→grams conversion by these to localize it.
    Returns all-1.0 for the US/label baseline so existing behaviour is unchanged.
    """
    u = units_for_locale(country, preferred_units, locale)
    return {k: round(u[k] / _BASE[k], 4) for k in _BASE}
