"""Locale-sensitive food-name normalization.

ALAFIA's users are global, so meal text arrives in many languages and regional
names. Before USDA/lookup, we canonicalize known non-English / regional terms to
an English head-noun the rest of the pipeline understands. The map is data (easy
to extend per locale); anything not mapped falls through to the LLM normalizer
(`nutrient_estimator._try_ai`, prompted to translate + canonicalize).
"""
from __future__ import annotations

import re

# alias (lowercase) -> canonical English food term. Phrase aliases are applied
# first (longest-first), then single-word aliases.
_ALIASES: dict[str, str] = {
    # Spanish
    "arroz": "rice", "pollo": "chicken", "frijoles": "beans", "huevo": "egg",
    "huevos": "eggs", "leche": "milk", "pan": "bread", "manzana": "apple",
    "platano": "plantain", "plátano": "plantain", "pescado": "fish", "carne": "beef",
    "queso": "cheese", "arroz con pollo": "rice and chicken",
    # French
    "poulet": "chicken", "riz": "rice", "pain": "bread", "oeuf": "egg",
    "œuf": "egg", "pomme": "apple", "lait": "milk", "haricots": "beans",
    "poisson": "fish", "boeuf": "beef", "fromage": "cheese", "poulet roti": "roast chicken",
    # West African / Nigerian
    "garri": "cassava", "eba": "cassava", "amala": "yam flour swallow",
    "moi moi": "bean pudding", "moimoi": "bean pudding", "akara": "bean fritter",
    "egusi": "egusi soup", "efo riro": "vegetable stew", "ogbono": "ogbono soup",
    "jollof": "jollof rice", "dodo": "fried plantain", "puff puff": "fried dough",
    "pounded yam": "yam", "ewa": "beans", "obe": "stew",
    # East / other African
    "ugali": "maize porridge", "injera": "flatbread", "nyama": "meat", "sukuma": "collard greens",
    # South Asian
    "roti": "flatbread", "chapati": "flatbread", "naan": "naan bread", "dal": "lentils",
    "paneer": "cheese", "dosa": "rice crepe", "idli": "steamed rice cake", "biryani": "rice dish",
    # East Asian
    "pho": "noodle soup", "ramen": "noodle soup", "congee": "rice porridge",
    "miso": "miso soup", "udon": "noodles", "bibimbap": "rice bowl",
}

_PHRASE_ALIASES = {k: v for k, v in _ALIASES.items() if " " in k}
_WORD_ALIASES = {k: v for k, v in _ALIASES.items() if " " not in k}


def canonicalize(food_name: str) -> str:
    """Return the food name with known non-English/regional terms mapped to English."""
    if not food_name:
        return food_name
    s = food_name.lower()
    for phrase in sorted(_PHRASE_ALIASES, key=len, reverse=True):
        if phrase in s:
            s = s.replace(phrase, _PHRASE_ALIASES[phrase])
    out = [_WORD_ALIASES.get(tok, tok) for tok in re.split(r"(\W+)", s)]
    result = "".join(out).strip()
    return result or food_name
