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


# ── Intake normalisation ─────────────────────────────────────────────────
#
# The patient is not a calculator. Their locale picks a default system, they
# may change it in Profile and toggle freely, and a reading may arrive in
# whatever unit the facility's device happened to print — so a value MUST be
# able to travel with its unit, and the backend converts.
#
# Before this existed, `inches_to_cm` and `pounds_to_kg` had no callers at all:
# the API took a bare `height_cm` and stored whatever number arrived. A US
# patient entering their height as 70 was stored as 70 cm.

# Unit spellings accepted at intake, per measurement, mapped to a converter
# that returns the canonical metric value.
_INTAKE_ALIASES: dict[str, dict[str, str]] = {
    "length": {
        "cm": "cm", "centimeter": "cm", "centimetre": "cm", "centimeters": "cm",
        "in": "in", "inch": "in", "inches": "in", '"': "in",
    },
    "mass": {
        "kg": "kg", "kilogram": "kg", "kilograms": "kg", "kilo": "kg",
        "lb": "lb", "lbs": "lb", "pound": "lb", "pounds": "lb",
    },
    "temperature": {
        "c": "c", "°c": "c", "celsius": "c", "centigrade": "c",
        "f": "f", "°f": "f", "fahrenheit": "f",
    },
    "volume": {
        "ml": "ml", "milliliter": "ml", "millilitre": "ml", "milliliters": "ml",
        "floz": "floz", "fl oz": "floz", "fluid ounce": "floz", "oz": "floz",
    },
}

_INTAKE_CONVERT = {
    ("length", "in"): inches_to_cm,
    ("mass", "lb"): pounds_to_kg,
    ("temperature", "f"): fahrenheit_to_celsius,
    ("volume", "floz"): fluid_ounces_to_ml,
}


class UnknownUnitError(ValueError):
    """The caller named a unit we do not recognise for this measurement.

    Raised rather than silently assuming metric: guessing is how a number ends
    up stored in the wrong unit, which is the failure this module prevents.
    """


def normalize_unit(measurement: str, unit: Optional[str]) -> Optional[str]:
    """Canonical short form for a unit spelling, or None when unit is absent."""
    if unit is None:
        return None
    key = str(unit).strip().lower()
    if not key:
        return None
    aliases = _INTAKE_ALIASES.get(measurement, {})
    if key not in aliases:
        raise UnknownUnitError(
            f"unrecognised {measurement} unit {unit!r}; "
            f"expected one of: {', '.join(sorted(set(aliases.values())))}"
        )
    return aliases[key]


def to_canonical(
    value: Optional[float],
    measurement: str,
    unit: Optional[str] = None,
) -> Optional[float]:
    """Convert an incoming value to the metric unit the database stores.

    `unit=None` means the value is already canonical — the field names carry
    the unit (`height_cm`, `weight_kg`), so a client that sends no unit is
    taken at its word rather than reinterpreted against a profile preference.
    Reinterpreting would turn a correct 170 cm into 431 cm the moment a user
    toggled their display units.
    """
    if value is None:
        return None
    normalized = normalize_unit(measurement, unit)
    if normalized is None:
        return value
    converter = _INTAKE_CONVERT.get((measurement, normalized))
    return converter(value) if converter else value


# ── Plausibility, against the patient rather than a constant ─────────────
#
# A fixed 30-280 cm range accepts 70 cm for a 52-year-old, because 70 cm is a
# real height — for a one-year-old. The patient's AGE is on the record and it
# settles it: no adult is 70 cm, and 70 *inches* is 178 cm, which is an
# unremarkable adult height.
#
# `to_celsius` above already works this way — it reads a value over 45 as
# Fahrenheit, because no one has a body temperature of 98.6 °C. This is the
# same reasoning applied to length.

# (low_cm, high_cm) by age in years. Wide on purpose: these reject the
# impossible, not the unusual.
_HEIGHT_BANDS_CM: tuple[tuple[float, float, float], ...] = (
    #  max_age, low,   high
    (2.0,       40.0,  100.0),
    (12.0,      65.0,  180.0),
    (17.0,      110.0, 215.0),
    (float("inf"), 120.0, 280.0),   # adult: shortest adults on record ~63 cm.
                                    # Those are documented exceptions, and the
                                    # caller records them with
                                    # acknowledge_unusual — naming a unit is
                                    # NOT itself an override, because "70 cm"
                                    # stated confidently is still wrong far
                                    # more often than it is right.
)


def plausible_height_range_cm(age_years: Optional[float]) -> tuple[float, float]:
    """The cm range a person of this age can plausibly be."""
    if age_years is None:
        return 30.0, 280.0
    for max_age, low, high in _HEIGHT_BANDS_CM:
        if age_years <= max_age:
            return low, high
    return 30.0, 280.0


def infer_length_unit(
    value: Optional[float],
    age_years: Optional[float],
) -> Optional[str]:
    """Guess the unit of a BARE height, or None when it reads fine as cm.

    Returns "in" when the number is impossible as centimetres for someone this
    age but ordinary as inches. Only ever consulted when the caller did not say
    which unit they meant — an explicit unit is always obeyed.
    """
    if value is None or value <= 0:
        return None
    low, high = plausible_height_range_cm(age_years)
    if low <= value <= high:
        return None
    as_cm = inches_to_cm(value)
    if low <= as_cm <= high:
        return "in"
    return None


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
