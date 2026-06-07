"""Canonical unit registry and conversions for ALAFIA / LAFIAKALO.

Policy
------
LAFIAKALO stores **metric** as the canonical system in the database (column
names bake in the unit, e.g. ``body_temperature_c``, ``weight_kg``,
``height_cm``, ``blood_glucose_mg_dl``). Any imperial value arriving from
ALAFIA / Firebase is converted to metric on import. Values are presented in
either Metric or Imperial at the edge (API / UI) based on the user's preferred
system, so LAFIAKALO stays truly global while the stored data never drifts.

A quantity is only ever shown with its unit attached (``format_quantity``);
a bare number is only acceptable when no quantity exists.
"""

from __future__ import annotations

import re
from typing import Optional

UnitSystem = str  # "metric" | "imperial"

METRIC: UnitSystem = "metric"
IMPERIAL: UnitSystem = "imperial"

# Regions (ISO 3166-1 alpha-2) that conventionally use the imperial system.
# The United States, Liberia and Myanmar are the only non-metric countries.
_IMPERIAL_REGIONS = {"US", "LR", "MM"}

# Country-name spellings (lower-cased) that map to the imperial system.
_IMPERIAL_COUNTRY_NAMES = {
    "united states", "united states of america", "usa", "u.s.", "u.s.a.",
    "america", "liberia", "myanmar", "burma",
}

# Canonical metric unit per measurement type (what the DB stores).
CANONICAL_UNIT: dict[str, str] = {
    "temperature": "°C",
    "mass": "kg",
    "length": "cm",
    "volume": "mL",
    "glucose": "mg/dL",
}

# The unit each measurement type is displayed in for a given system.
DISPLAY_UNIT: dict[str, dict[UnitSystem, str]] = {
    "temperature": {METRIC: "°C", IMPERIAL: "°F"},
    "mass":        {METRIC: "kg", IMPERIAL: "lb"},
    "length":      {METRIC: "cm", IMPERIAL: "in"},
    "volume":      {METRIC: "mL", IMPERIAL: "fl oz"},
    "glucose":     {METRIC: "mg/dL", IMPERIAL: "mmol/L"},
}


# ── Temperature ──────────────────────────────────────────────────────────
def fahrenheit_to_celsius(value: float) -> float:
    return round((value - 32.0) * 5.0 / 9.0, 2)


def celsius_to_fahrenheit(value: float) -> float:
    return round(value * 9.0 / 5.0 + 32.0, 2)


def to_celsius(value: Optional[float], unit: Optional[str] = None) -> Optional[float]:
    """Normalize a temperature to Celsius (the canonical unit).

    Converts when the unit string contains 'f', or — when no unit is given —
    auto-detects Fahrenheit for physiologically impossible Celsius values
    (> 45 °C).
    """
    if value is None:
        return None
    if unit and "f" in unit.lower():
        return fahrenheit_to_celsius(value)
    if unit is None and value > 45:
        return fahrenheit_to_celsius(value)
    return value


# ── Mass ─────────────────────────────────────────────────────────────────
def pounds_to_kg(value: float) -> float:
    return round(value * 0.45359237, 3)


def kg_to_pounds(value: float) -> float:
    return round(value / 0.45359237, 2)


# ── Length ───────────────────────────────────────────────────────────────
def inches_to_cm(value: float) -> float:
    return round(value * 2.54, 2)


def cm_to_inches(value: float) -> float:
    return round(value / 2.54, 2)


# ── Volume ───────────────────────────────────────────────────────────────
def fluid_ounces_to_ml(value: float) -> float:
    return round(value * 29.5735295625, 2)


def ml_to_fluid_ounces(value: float) -> float:
    return round(value / 29.5735295625, 2)


# ── Glucose ──────────────────────────────────────────────────────────────
# Conversion factor for glucose: 1 mmol/L = 18.0182 mg/dL.
_GLUCOSE_MGDL_PER_MMOL = 18.0182


def mmol_to_mg_dl(value: float) -> float:
    return round(value * _GLUCOSE_MGDL_PER_MMOL, 1)


def mg_dl_to_mmol(value: float) -> float:
    return round(value / _GLUCOSE_MGDL_PER_MMOL, 2)


# ── Display helpers ──────────────────────────────────────────────────────
_TO_IMPERIAL = {
    "temperature": celsius_to_fahrenheit,
    "mass": kg_to_pounds,
    "length": cm_to_inches,
    "volume": ml_to_fluid_ounces,
    "glucose": mg_dl_to_mmol,
}


def convert_for_display(
    value: Optional[float],
    measurement: str,
    system: UnitSystem = METRIC,
) -> Optional[float]:
    """Convert a canonical (metric) value into the requested display system."""
    if value is None:
        return None
    if system == IMPERIAL and measurement in _TO_IMPERIAL:
        return _TO_IMPERIAL[measurement](value)
    return value


def display_unit(measurement: str, system: UnitSystem = METRIC) -> str:
    """Return the unit label for a measurement in the requested system."""
    return DISPLAY_UNIT.get(measurement, {}).get(system, CANONICAL_UNIT.get(measurement, ""))


def units_for_locale(
    locale: Optional[str] = None,
    country: Optional[str] = None,
) -> UnitSystem:
    """Derive the default measurement system from a locale and/or country.

    Returns ``IMPERIAL`` only for the three non-metric regions (US, Liberia,
    Myanmar); every other locale defaults to ``METRIC`` — LAFIAKALO's global
    default. Accepts locale strings like ``"en-US"`` / ``"en_US"`` and free-text
    country names.
    """
    if locale:
        parts = re.split(r"[-_]", locale.strip())
        region = parts[-1].upper() if len(parts) > 1 else parts[0].upper()
        if region in _IMPERIAL_REGIONS:
            return IMPERIAL
    if country and country.strip().lower() in _IMPERIAL_COUNTRY_NAMES:
        return IMPERIAL
    return METRIC


def format_quantity(
    value: Optional[float],
    measurement: str,
    system: UnitSystem = METRIC,
    *,
    precision: int = 1,
) -> str:
    """Render a value with its unit, e.g. ``"37.0 °C"`` / ``"98.6 °F"``.

    A unit is always attached when a quantity exists; an absent quantity
    renders as ``"—"`` rather than a misleading bare number.
    """
    if value is None:
        return "—"
    converted = convert_for_display(value, measurement, system)
    unit = display_unit(measurement, system)
    return f"{converted:.{precision}f} {unit}".strip()
