"""NLM-style food description item extractor.

This module normalizes free-text food descriptions into individual food items
that are easier to match against USDA/NLM-aligned food vocabularies.

For full meal parsing with quantity extraction and nutrient aggregation,
see ``app.services.meal_parser`` (the NLM meal parser layer).
"""

from __future__ import annotations

import re

# Common abbreviations / aliases seen in user-entered logs.
# Includes West African / Nigerian food terms mapped to USDA-searchable equivalents.
_ALIAS_MAP = {
    # Original entries
    "rcf": "roasted corn flour",
    "milk break": "milk bread",
    "whole milke": "whole milk",
    "black tea": "tea",
    # West African grains / starches
    "eba": "cassava flour",
    "garri": "cassava flour",
    "gari": "cassava flour",
    "fufu": "cassava flour",
    "amala": "yam flour",
    "semo": "semolina",
    "semovita": "semolina",
    "ogi": "corn porridge",
    "akamu": "corn porridge",
    "pap": "corn porridge",
    "kunu": "millet porridge",
    "fura": "millet balls",
    "tuwo": "rice flour",
    "tuwo masara": "corn flour",
    "tuwo shinkafa": "rice flour",
    # West African proteins
    "suya": "beef, grilled",
    "kilishi": "beef jerky",
    "kpomo": "cow skin",
    "ponmo": "cow skin",
    "shaki": "beef tripe",
    "roundabout": "beef tripe",
    "dodo": "fried plantain",
    "boli": "roasted plantain",
    "bole": "roasted plantain",
    "asun": "smoked goat",
    "nkwobi": "cow foot",
    # West African soups / sauces
    "egusi soup": "melon seed soup",
    "banga soup": "palm nut soup",
    "edikaikong": "vegetable soup",
    "afang": "wild spinach soup",
    "efo riro": "spinach stew",
    "ogbono soup": "african mango seed soup",
    "miyan kuka": "baobab leaf soup",
    "miyan taushe": "pumpkin soup",
    "miyan kubewa": "okra soup",
    # Other regional terms
    "groundnut": "peanut",
    "suya spice": "yaji spice",
    "akara": "bean fritters",
    "moin moin": "steamed bean pudding",
    "moi moi": "steamed bean pudding",
}

# Preparation words that usually do not help term matching.
_PREP_PREFIXES = (
    "grilled",
    "boiled",
    "fried",
    "baked",
    "steamed",
    "scrambled",
    "smoked",
    "organic",
    "fresh",
    "cooked",
    "plain",
)

# Quantity/unit patterns to strip from segments.
_QTY_UNIT_RE = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:oz|ounce|ounces|g|gram|grams|kg|ml|l|cup|cups|tbsp|tsp|slice|slices|fl)\b",
    re.IGNORECASE,
)


def _normalize_text(text: str) -> str:
    normalized = text.lower().strip()
    normalized = normalized.replace("&", " and ")
    normalized = re.sub(r"[;/+]", ",", normalized)
    normalized = re.sub(r"\([^)]*\)", " ", normalized)

    for src, dst in _ALIAS_MAP.items():
        normalized = re.sub(rf"\b{re.escape(src)}\b", dst, normalized)

    # Treat conjunctions as separators for mixed entries.
    normalized = re.sub(r"\b(and|plus|with)\b", ",", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def _clean_segment(segment: str) -> str:
    s = segment.strip(" ,.-")
    if not s:
        return ""

    s = _QTY_UNIT_RE.sub(" ", s)
    s = re.sub(r"\b\d+(?:\.\d+)?\b", " ", s)

    # Remove leading preparation words repeatedly.
    changed = True
    while changed:
        changed = False
        for prefix in _PREP_PREFIXES:
            if s.startswith(prefix + " "):
                s = s[len(prefix) + 1 :]
                changed = True

    s = re.sub(r"\s+", " ", s).strip(" ,.-")
    return s


def extract_food_items_nlm(description: str) -> list[str]:
    """Extract likely food items from a free-text meal description.

    Example:
      "Grilled chicken, potatoes porridge, RCF"
      -> ["chicken", "potatoes porridge", "roasted corn flour"]
    """
    if not description or not description.strip():
        return []

    normalized = _normalize_text(description)
    raw_parts = [p for p in re.split(r",", normalized) if p.strip()]

    items: list[str] = []
    seen: set[str] = set()

    for part in raw_parts:
        cleaned = _clean_segment(part)
        if len(cleaned) < 2:
            continue
        if cleaned in {"tea", "water"} and len(raw_parts) > 1:
            # Keep nutrient-relevant items first; beverages are optional noise in mixed logs.
            continue
        if cleaned not in seen:
            seen.add(cleaned)
            items.append(cleaned)

    return items
