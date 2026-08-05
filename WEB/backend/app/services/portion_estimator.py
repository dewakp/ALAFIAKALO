"""Turn a portion phrase into grams.

Vision models answer with prose — "1 cup / 150 g", "1 medium sized slice",
"half a plate of jollof". Nothing downstream can use prose: nutrients are per
100 g, so without grams there is no calorie number, and "quantity estimation"
does not exist.

Resolution order, most trustworthy first:

  1. an explicit weight in the text            ("150 g", "0.4 kg", "6 oz")
  2. a household measure × food density        ("1 cup" of rice → 158 g)
  3. a per-food unit weight                    ("1 medium carrot" → 61 g)
  4. a coarse size word                        ("a small plate" → 250 g)

Every result carries the rule that produced it and a confidence, so the caller
can show its work and so a low-confidence guess can be flagged for correction
rather than silently trusted.

Learned corrections (`nutrition_learning.record_correction(serving_weight_g=…)`)
take priority over everything here — see `estimate_grams(learned_g=…)`.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# ── Mass units → grams ───────────────────────────────────────────────────
_MASS_UNITS = {
    "g": 1.0, "gram": 1.0, "grams": 1.0, "gm": 1.0, "gs": 1.0,
    "kg": 1000.0, "kilo": 1000.0, "kilos": 1000.0, "kilogram": 1000.0, "kilograms": 1000.0,
    "mg": 0.001,
    "oz": 28.3495, "ounce": 28.3495, "ounces": 28.3495,
    "lb": 453.592, "lbs": 453.592, "pound": 453.592, "pounds": 453.592,
}

# ── Volume measures → millilitres ────────────────────────────────────────
_VOLUME_UNITS = {
    "cup": 240.0, "cups": 240.0,
    "tbsp": 15.0, "tablespoon": 15.0, "tablespoons": 15.0,
    "tsp": 5.0, "teaspoon": 5.0, "teaspoons": 5.0,
    "ml": 1.0, "millilitre": 1.0, "milliliter": 1.0,
    "l": 1000.0, "litre": 1000.0, "liter": 1000.0, "litres": 1000.0, "liters": 1000.0,
    "fl oz": 29.5735, "floz": 29.5735, "fluid ounce": 29.5735,
}

# Grams per milliliter. Cooked grains and stews are near water; oils are lighter;
# leafy volumes are mostly air. Keyed by substring match on the food name.
_DENSITY_G_PER_ML = {
    "oil": 0.92, "butter": 0.91, "honey": 1.42, "syrup": 1.33,
    "water": 1.0, "milk": 1.03, "juice": 1.05, "soup": 1.02, "broth": 1.0,
    "stew": 1.0, "sauce": 1.05, "yoghurt": 1.03, "yogurt": 1.03,
    "rice": 0.66, "jollof": 0.66, "couscous": 0.63, "pasta": 0.58,
    "beans": 0.72, "lentil": 0.75, "porridge": 0.90, "pap": 0.95, "ogi": 0.95,
    "flour": 0.53, "sugar": 0.85, "salt": 1.20,
    "lettuce": 0.25, "spinach": 0.30, "salad": 0.28, "cabbage": 0.32,
    "cereal": 0.35, "granola": 0.45,
}
_DEFAULT_DENSITY = 0.85  # mixed cooked food

# Grams for one typical unit of a food, before size adjustment.
_UNIT_WEIGHTS_G = {
    "egg": 50, "eggs": 50,
    "banana": 118, "plantain": 180, "apple": 182, "orange": 131, "mango": 200,
    "avocado": 150, "tomato": 123, "onion": 110, "carrot": 61, "potato": 173,
    "sweet potato": 130, "yam": 200, "cassava": 250, "corn": 90, "maize": 90,
    "bread": 28, "slice of bread": 28, "toast": 28, "chapati": 60, "roti": 45,
    "tortilla": 45, "pancake": 77, "waffle": 75,
    "chicken breast": 174, "chicken thigh": 130, "drumstick": 90, "wing": 34,
    "egg roll": 89, "samosa": 55, "meat pie": 150, "puff puff": 30,
    "akara": 35, "moi moi": 120, "fish": 150, "tilapia": 218, "sardine": 25,
    "biscuit": 12, "cookie": 16, "cracker": 3,
}

# Multipliers for size words.
_SIZE_MULTIPLIERS = {
    "tiny": 0.5, "very small": 0.55, "small": 0.7, "little": 0.7,
    "medium": 1.0, "average": 1.0, "regular": 1.0, "standard": 1.0,
    "large": 1.4, "big": 1.4, "extra large": 1.7, "xl": 1.7,
    "huge": 1.9, "very large": 1.8, "jumbo": 1.9,
}

# Vague container words → grams of typical served food.
_CONTAINER_G = {
    "plate": 350, "bowl": 300, "cup": 200, "mug": 250, "glass": 240,
    "handful": 30, "pinch": 1, "serving": 200, "portion": 200,
    "scoop": 60, "ladle": 120, "spoon": 15, "wrap": 220, "sandwich": 200,
}

# Written numbers and fractions the models actually emit.
_WORD_NUMBERS = {
    "a": 1.0, "an": 1.0, "one": 1.0, "two": 2.0, "three": 3.0, "four": 4.0,
    "five": 5.0, "six": 6.0, "seven": 7.0, "eight": 8.0, "nine": 9.0, "ten": 10.0,
    "half": 0.5, "quarter": 0.25, "third": 1 / 3,
}
_UNICODE_FRACTIONS = {"½": 0.5, "¼": 0.25, "¾": 0.75, "⅓": 1 / 3, "⅔": 2 / 3, "⅛": 0.125}

MIN_G, MAX_G = 1.0, 5000.0  # sanity clamp: no meal item is 6 kg


@dataclass
class PortionEstimate:
    grams: float | None
    confidence: float       # 0..1
    basis: str              # which rule fired — shown to the user, logged for tuning
    source_text: str

    def as_dict(self) -> dict:
        return {
            "estimated_grams": round(self.grams, 1) if self.grams is not None else None,
            "grams_confidence": round(self.confidence, 2),
            "grams_basis": self.basis,
        }


def _normalize(text: str) -> str:
    # Substitute vulgar fractions BEFORE NFKC. NFKC rewrites "½" to "1⁄2" using
    # U+2044 FRACTION SLASH — not the ASCII "/" the quantity regexes look for —
    # so normalising first silently turned "½ cup" into a full cup.
    text = (text or "")
    for glyph, value in _UNICODE_FRACTIONS.items():
        text = text.replace(glyph, f" {value} ")
    text = unicodedata.normalize("NFKC", text).lower().strip()
    text = text.replace("⁄", "/")   # any fraction slash that survived
    return re.sub(r"\s+", " ", text)


def _leading_quantity(text: str) -> float:
    """Pull the count out of '2 medium eggs' / 'half a plate' / '1 1/2 cups'."""
    m = re.match(r"^\s*(\d+)\s+(\d+)\s*/\s*(\d+)", text)          # 1 1/2
    if m:
        whole, num, den = (float(g) for g in m.groups())
        return whole + (num / den if den else 0)
    m = re.match(r"^\s*(\d+)\s*/\s*(\d+)", text)                   # 3/4
    if m:
        num, den = float(m.group(1)), float(m.group(2))
        return num / den if den else 1.0
    m = re.match(r"^\s*(\d+(?:\.\d+)?)", text)                     # 2 or 1.5
    if m:
        return float(m.group(1))
    for word, value in _WORD_NUMBERS.items():                      # "half a plate"
        if re.match(rf"^\s*{word}\b", text):
            return value
    return 1.0


def _size_multiplier(text: str) -> float:
    for word, mult in sorted(_SIZE_MULTIPLIERS.items(), key=lambda kv: -len(kv[0])):
        if re.search(rf"\b{re.escape(word)}\b", text):
            return mult
    return 1.0


def _density_for(food_name: str) -> float:
    name = _normalize(food_name)
    for key, density in _DENSITY_G_PER_ML.items():
        if key in name:
            return density
    return _DEFAULT_DENSITY


def _lookup_unit_weight(text: str, food_name: str) -> float | None:
    """Grams for one unit, matching the longest key first ('sweet potato' before 'potato')."""
    haystack = f"{_normalize(food_name)} {_normalize(text)}"
    for key in sorted(_UNIT_WEIGHTS_G, key=len, reverse=True):
        if re.search(rf"\b{re.escape(key)}\b", haystack):
            return float(_UNIT_WEIGHTS_G[key])
    return None


def _clamp(grams: float) -> float:
    return max(MIN_G, min(MAX_G, grams))


def estimate_grams(
    portion_text: str | None,
    food_name: str = "",
    learned_g: float | None = None,
) -> PortionEstimate:
    """Best-effort grams for a portion phrase.

    `learned_g` is a user-corrected serving weight for this food and wins
    outright — a real correction beats any heuristic here.
    """
    text = _normalize(portion_text or "")
    qty = _leading_quantity(text) if text else 1.0

    if learned_g is not None and learned_g > 0:
        return PortionEstimate(
            _clamp(learned_g * qty), 0.95, "learned from your correction", portion_text or "")

    if not text:
        return PortionEstimate(None, 0.0, "no portion given", "")

    # 1. Explicit mass — "150 g", "6 oz". Trust it.
    for unit in sorted(_MASS_UNITS, key=len, reverse=True):
        m = re.search(rf"(\d+(?:\.\d+)?)\s*{re.escape(unit)}\b", text)
        if m:
            grams = float(m.group(1)) * _MASS_UNITS[unit]
            return PortionEstimate(_clamp(grams), 0.95, f"stated weight ({m.group(0).strip()})", portion_text or "")

    # 2. Household volume × density.
    for unit in sorted(_VOLUME_UNITS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(unit)}\b", text):
            ml = qty * _VOLUME_UNITS[unit]
            density = _density_for(food_name)
            grams = ml * density
            return PortionEstimate(
                _clamp(grams), 0.6,
                f"{_fmt(qty)} {unit} × {density:g} g/ml", portion_text or "")

    # 3. Per-food unit weight — "1 medium carrot", "2 eggs".
    unit_weight = _lookup_unit_weight(text, food_name)
    if unit_weight is not None:
        grams = qty * unit_weight * _size_multiplier(text)
        return PortionEstimate(
            _clamp(grams), 0.55,
            f"{_fmt(qty)} × {unit_weight:g} g typical unit", portion_text or "")

    # 4. Container/serving words — vague, low confidence, but better than nothing.
    for word in sorted(_CONTAINER_G, key=len, reverse=True):
        if re.search(rf"\b{re.escape(word)}\b", text):
            grams = qty * _CONTAINER_G[word] * _size_multiplier(text)
            return PortionEstimate(
                _clamp(grams), 0.35, f"{_fmt(qty)} {word} (typical)", portion_text or "")

    # 5. A bare number with no unit ("3") most likely means 3 pieces.
    if re.match(r"^\s*\d", text):
        grams = qty * 100.0
        return PortionEstimate(_clamp(grams), 0.2, "assumed ~100 g per piece", portion_text or "")

    return PortionEstimate(None, 0.0, "could not interpret portion", portion_text or "")


def _fmt(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:.2f}".rstrip("0").rstrip(".")
