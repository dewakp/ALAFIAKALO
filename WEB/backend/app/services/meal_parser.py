"""NLM Meal Text Parser — extracts (food, qty_g) pairs from free-text meal descriptions.

This module implements the NLM (Nutritional Language Matching) layer that:
  1. Splits a meal description into individual food segments (respecting parentheses)
  2. Extracts quantity + unit for each segment
  3. Expands parenthetical recipe sub-ingredients with type-based default quantities
  4. Converts all quantities to grams using food-aware unit density tables

Per-item nutrients are NOT computed here — this module only returns parsed
(food_name, qty_g, qty_text) triples. Nutrient lookup + scaling is done by
``nutrient_estimator.estimate_meal_nutrients()``.

Example
-------
Input:
    "1.5 cup of beef suya(peanut butter, pepper, salt, ginger, turmeric),
     onion slices, 1 chicken thigh, 1 cup of garri, half cup of whole milk"

Output (FoodComponent list):
    FoodComponent("beef",          qty_g=169.5, qty_text="1.5 cup")
    FoodComponent("peanut butter", qty_g=16.0,  qty_text="1 tablespoon")
    FoodComponent("pepper",        qty_g=2.5,   qty_text="1 teaspoon")
    FoodComponent("salt",          qty_g=2.85,  qty_text="1/2 teaspoon")
    FoodComponent("ginger",        qty_g=1.25,  qty_text="1/2 teaspoon")
    FoodComponent("turmeric",      qty_g=1.25,  qty_text="1/2 teaspoon")
    FoodComponent("onion slices",  qty_g=30.0,  qty_text="default")
    FoodComponent("chicken thigh", qty_g=116.0, qty_text="1 piece")
    FoodComponent("garri",         qty_g=140.0, qty_text="1 cup")
    FoodComponent("whole milk",    qty_g=122.0, qty_text="half cup")
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class FoodComponent:
    """A parsed food item with its estimated gram weight."""

    food_name: str         # clean food name sent to the nutrient estimator
    qty_g: float           # estimated weight in grams
    qty_text: str          # original or inferred quantity text (human-readable)
    source_text: str = field(default="")  # raw segment from the input string


# ── Word-number map ───────────────────────────────────────────────────────────

_WORD_NUMBERS: dict[str, float] = {
    "a": 1.0, "an": 1.0,
    "half": 0.5, "quarter": 0.25,
    "one": 1.0, "two": 2.0, "three": 3.0, "four": 4.0,
    "five": 5.0, "six": 6.0, "seven": 7.0, "eight": 8.0,
}


# ── Food-density lookup tables ────────────────────────────────────────────────

# Grams per cup (240 ml volume) for common foods.
# Override the default water-density (240 g/cup) for items with different packing.
_CUP_DENSITY_G: dict[str, float] = {
    # Proteins / meat (shredded or diced, cooked)
    "beef": 113.0,        # 4 oz per cup — USDA cooked ground/diced reference
    "chicken": 140.0,
    "pork": 140.0,
    "lamb": 140.0,
    "fish": 150.0,
    "shrimp": 145.0,
    "tuna": 154.0,
    # Grains / starches
    "garri": 140.0,       # cassava granules, dry
    "cassava flour": 140.0,
    "cassava": 140.0,
    "rice": 185.0,        # cooked
    "oats": 90.0,         # dry rolled oats
    "flour": 120.0,
    "cornmeal": 122.0,
    "semolina": 167.0,
    "millet": 200.0,      # cooked
    "sorghum": 192.0,     # cooked
    # Legumes (cooked)
    "beans": 177.0,
    "lentils": 198.0,
    "chickpeas": 164.0,
    "cowpeas": 171.0,
    # Dairy
    "whole milk": 244.0,
    "milk": 244.0,
    "skim milk": 245.0,
    "yogurt": 245.0,
    "cream": 238.0,
    # Nuts / spreads
    "peanut butter": 258.0,  # 1 cup pb ≈ 258 g → 1 tbsp ≈ 16 g
    "almond butter": 250.0,
    "tahini": 240.0,
    # Oils (volume to mass, avg density ~0.91 g/ml)
    "oil": 218.0,
    "palm oil": 218.0,
    "groundnut oil": 216.0,
    "olive oil": 216.0,
    "coconut oil": 218.0,
    # Vegetables (chopped)
    "onion": 160.0,
    "tomato": 180.0,
    "spinach": 30.0,    # raw leaves
    "kale": 67.0,
    "cabbage": 89.0,
    # Soups / stews (liquid-dominant)
    "soup": 240.0,
    "broth": 240.0,
    "stew": 240.0,
}

# Grams per teaspoon for high-density powders/crystals.
# These override the 2.5 g/tsp default used for ground spices.
_TSP_DENSITY_G: dict[str, float] = {
    "salt": 5.7,
    "sugar": 4.2,
    "baking powder": 4.6,
    "baking soda": 6.0,
    "cornstarch": 2.7,
}

# Standard piece/unit weights (grams per single item, no unit stated).
_PIECE_WEIGHTS_G: dict[str, float] = {
    "chicken thigh": 116.0,    # bone-in, skin-on — USDA reference
    "chicken breast": 174.0,
    "chicken wing": 72.0,
    "chicken drumstick": 94.0,
    "chicken leg": 185.0,
    "egg": 50.0,
    "banana": 118.0,
    "apple": 182.0,
    "orange": 131.0,
    "pear": 178.0,
    "peach": 150.0,
    "kiwi": 69.0,
    "grapefruit": 123.0,
    "lemon": 58.0,
    "lime": 67.0,
    "shrimp": 6.0, "prawn": 15.0, "scallop": 15.0, "oyster": 25.0,
    "carrot": 61.0,
    "potato": 173.0,
    "sweet potato": 130.0,
    "cucumber": 120.0,
    "bell pepper": 119.0,
    "tomato": 123.0,
    "toast": 28.0,            # 1 slice
    "bread": 28.0,            # 1 slice
    "bread slice": 28.0,
    "slice of bread": 28.0,
    "tortilla": 45.0,
    "pancake": 40.0,
    "waffle": 75.0,
    "cookie": 16.0,
    "muffin": 113.0,
    "sausage": 50.0,
    "hot dog": 50.0,
    "meatball": 30.0,
    "yam": 100.0,             # 1 medium chunk
    "plantain": 115.0,        # 1 medium
    "avocado": 150.0,
    # Nuts / small items — "N pieces of cashews" must not become N×100 g.
    "cashew": 1.5, "almond": 1.2, "peanut": 0.9, "walnut": 5.0, "pecan": 5.0,
    "pistachio": 0.7, "hazelnut": 1.0, "macadamia": 2.5, "brazil nut": 5.0,
    "raisin": 0.5, "grape": 5.0, "blueberry": 1.0, "raspberry": 2.0,
    "blackberry": 2.0, "strawberry": 12.0, "cherry": 8.0, "olive": 4.0,
    "date": 24.0, "fig": 50.0, "apricot": 35.0, "plum": 66.0, "prune": 9.5,
}

# Grams per SLICE, food-aware (a "slice" varies wildly: bread ~28 g, pizza ~107 g).
_SLICE_WEIGHTS_G: dict[str, float] = {
    "bread": 28.0, "toast": 28.0, "white bread": 25.0, "whole wheat": 28.0,
    "rye": 32.0, "sourdough": 36.0, "baguette": 20.0,
    "cheese": 22.0, "american cheese": 19.0, "cheddar": 28.0,
    "pizza": 107.0, "cake": 80.0, "cheesecake": 80.0, "pie": 125.0,
    "ham": 28.0, "turkey": 28.0, "chicken": 28.0, "salami": 12.0,
    "bacon": 10.0, "prosciutto": 15.0,
    "tomato": 20.0, "onion": 14.0, "cucumber": 7.0, "lemon": 7.0, "lime": 7.0,
    "bell pepper": 15.0, "pepper": 15.0, "avocado": 50.0, "mango": 30.0,
    "watermelon": 286.0, "pineapple": 84.0, "orange": 30.0, "apple": 25.0,
}

# Default gram weights for items where no quantity is stated.
_NO_QTY_DEFAULTS_G: dict[str, float] = {
    # Garnishes / vegetables
    "onion slices": 30.0,
    "onion": 30.0,
    "tomato slices": 60.0,
    "tomato": 60.0,
    "lettuce": 20.0,
    "cucumber": 40.0,
    "pepper slices": 20.0,
    # Seasonings — default ½ tsp
    "salt": 2.85,
    "sea salt": 2.85,
    # Ground spices — default ½ tsp
    "ginger": 1.25,
    "turmeric": 1.25,
    "cumin": 1.25,
    "cinnamon": 1.25,
    "cardamom": 1.25,
    "nutmeg": 1.25,
    "allspice": 1.25,
    "cloves": 1.25,
    "fenugreek": 1.25,
    # Ground spices — default 1 tsp
    "pepper": 2.5,
    "black pepper": 2.3,
    "white pepper": 2.3,
    "paprika": 2.5,
    "coriander": 2.5,
    "curry powder": 2.5,
    "chili powder": 2.5,
    "garlic powder": 2.5,
    "yaji": 2.5,
    "suya spice": 2.5,
    "thyme": 1.5,
    "oregano": 1.5,
    "basil": 2.5,
    "garlic": 3.0,   # 1 clove
    # Spreads/pastes — default 1 tbsp
    "peanut butter": 16.0,
    "tahini": 15.0,
    "almond butter": 16.0,
    "butter": 14.0,
    "margarine": 14.0,
    # Oils — default 1 tbsp
    "palm oil": 14.0,
    "groundnut oil": 14.0,
    "coconut oil": 14.0,
    "olive oil": 14.0,
    "oil": 14.0,
}


# ── Ingredient type classification ────────────────────────────────────────────

_SEASONING_KW = frozenset({"salt", "sea salt", "kosher salt", "table salt", "msg", "stock cube", "bouillon"})
_SPICE_STRONG_KW = frozenset({
    "ginger", "turmeric", "cinnamon", "cloves", "cardamom", "nutmeg",
    "cayenne", "saffron", "allspice", "mace", "fenugreek",
    "uda", "ehuru", "uziza", "grains of selim",
})
_SPICE_MILD_KW = frozenset({
    "pepper", "paprika", "coriander", "cumin", "thyme", "oregano",
    "basil", "rosemary", "bay", "chili powder", "curry powder",
    "garlic powder", "onion powder", "yaji", "suya spice",
})
_SPREAD_KW = frozenset({"butter", "margarine", "paste", "tahini", "hummus"})
_OIL_KW = frozenset({"oil", "fat"})


def _classify_ingredient(name: str) -> str:
    """Return a coarse type label used to pick a default condiment quantity."""
    n = name.lower()
    if any(kw in n for kw in _SEASONING_KW):
        return "seasoning"
    if any(kw in n for kw in _SPICE_STRONG_KW):
        return "spice_strong"
    if any(kw in n for kw in _SPICE_MILD_KW):
        return "spice_mild"
    if any(kw in n for kw in _SPREAD_KW):
        return "spread"
    if any(kw in n for kw in _OIL_KW):
        return "oil"
    return "other"


# (qty_g, qty_text) defaults by ingredient type (for parenthetical expansions)
_TYPE_DEFAULTS: dict[str, tuple[float, str]] = {
    "seasoning":    (2.85,  "1/2 teaspoon"),
    "spice_strong": (1.25,  "1/2 teaspoon"),
    "spice_mild":   (2.5,   "1 teaspoon"),
    "spread":       (16.0,  "1 tablespoon"),
    "oil":          (14.0,  "1 tablespoon"),
    "other":        (30.0,  "default"),
}


# ── Preparation word stripping ────────────────────────────────────────────────

_PREP_PREFIXES_SET = frozenset({
    "grilled", "boiled", "fried", "baked", "steamed", "scrambled",
    "smoked", "organic", "fresh", "cooked", "plain", "raw",
    "roasted", "barbecued", "bbq", "braised", "sauteed", "sautéed",
    "deep-fried", "pan-fried", "poached", "seasoned", "marinated",
})

# Dish-style suffixes that do not meaningfully change the core food identity
# for nutrient lookup purposes (marinade components are listed separately).
_PREP_SUFFIXES_SET = frozenset({
    "suya", "kebab", "skewer", "tikka", "shawarma",
})


# Brand / store / marketing tokens to drop so a logged item resolves to its
# generic food (e.g. "Whole Foods Market 365 Organic orange juice" → "orange juice").
_BRAND_PHRASES = (
    "whole foods market", "whole foods", "trader joe's", "trader joes",
    "great value", "market 365",
)
_BRAND_WORDS = frozenset({
    "organic", "natural", "premium", "gourmet", "brand", "store", "365",
    "applegate", "kirkland", "kroger", "signature", "market",
})


def _strip_brands(s: str) -> str:
    out = s
    for ph in _BRAND_PHRASES:
        out = out.replace(ph, " ")
    toks = [t for t in out.split() if t not in _BRAND_WORDS and not t.isdigit()]
    cleaned = " ".join(toks).strip()
    return cleaned or s  # never blank out the whole name


def _clean_food_name(raw: str) -> str:
    """Strip preparation prefixes/suffixes to get the core food item name."""
    s = raw.lower().strip()
    # Strip leading preparation words
    changed = True
    while changed:
        changed = False
        for prep in _PREP_PREFIXES_SET:
            if s.startswith(prep + " "):
                s = s[len(prep) + 1:].strip()
                changed = True
    # Strip trailing preparation-style suffixes
    for suffix in _PREP_SUFFIXES_SET:
        if s.endswith(" " + suffix):
            s = s[:-(len(suffix) + 1)].strip()
    return _strip_brands(s)


# ── Regex patterns ────────────────────────────────────────────────────────────

# Leading quantity value in a segment
_SEG_QTY_RE = re.compile(
    r"^(?P<qty>"
    r"\d+(?:\.\d+)?\s+(?:and\s+)?(?:a\s+)?(?:\d+/\d+|half)"   # "1 1/2", "1 and a half"
    r"|\d+/\d+"                                                   # "1/2"
    r"|\d+(?:\.\d+)?"                                             # "1.5", "1"
    r"|half|quarter"                                              # word fractions
    r")\s*",
    re.IGNORECASE,
)

# Unit token following the quantity
_SEG_UNIT_RE = re.compile(
    r"^(?P<unit>"
    r"cups?|tablespoons?|tbsps?|teaspoons?|tsps?|"
    r"fl\.?\s*oz(?:s)?|fluid\s+ounces?|"         # fluid ounces — must precede bare oz
    r"ounces?|oz|"
    r"(?:kilo)?grams?|kgs?|g|"          # incl. bare "g" ("150g", "50 g")
    r"ml|milliliters?|liters?|litres?|"
    r"pounds?|lbs?|"
    r"pieces?|slices?|pinch(?:es)?|handfuls?|cloves?|strips?|"
    r"sticks?|cans?|bottles?|scoops?|wedges?|bunch(?:es)?|cuts?|chips?"
    r")\b\s*",
    re.IGNORECASE,
)


# ── Unit → gram conversion ────────────────────────────────────────────────────

def _qty_str_to_float(s: str) -> float:
    """Convert a quantity string (e.g. '1/2', 'half', '1 1/2') to float."""
    s = s.strip().lower()
    if s in _WORD_NUMBERS:
        return _WORD_NUMBERS[s]
    # "1 and a half" / "1 and half"
    m = re.match(r"^(\d+(?:\.\d+)?)\s+(?:and\s+)?(?:a\s+)?half$", s)
    if m:
        return float(m.group(1)) + 0.5
    # "1 1/2" mixed number
    m = re.match(r"^(\d+(?:\.\d+)?)\s+(\d+)/(\d+)$", s)
    if m:
        return float(m.group(1)) + int(m.group(2)) / int(m.group(3))
    # simple fraction
    m = re.match(r"^(\d+)/(\d+)$", s)
    if m:
        return int(m.group(1)) / int(m.group(2))
    try:
        return float(s)
    except ValueError:
        return 1.0


def _to_grams(value: float, unit: str, food_name: str) -> float:
    """Convert a quantity value + unit to grams, using food-aware density tables."""
    u = unit.lower().strip() if unit else ""
    fn = food_name.lower()

    # ── Dry/solid mass units ──
    if u in ("g", "gram", "grams"):
        return round(value, 1)
    if u in ("kg", "kilogram", "kilograms"):
        return round(value * 1000.0, 1)
    if u in ("ounce", "ounces", "oz"):
        return round(value * 28.35, 1)
    if u in ("pound", "pounds", "lb", "lbs"):
        return round(value * 453.59, 1)

    # ── Liquid volume units (1 ml ≈ 1 g at water density) ──
    if u in ("ml", "milliliter", "milliliters"):
        return round(value, 1)
    if u in ("liter", "liters", "litre", "litres"):
        return round(value * 1000.0, 1)

    # ── Fluid ounces (1 fl oz = 29.574 mL) ──
    # Nutritional supplement drinks (Boost, Ensure, Carnation) have a
    # density of ~1.03–1.05 g/mL → use 30.6 g/fl oz as the default.
    # Plain water-density beverages (juice, milk, broth) use 29.6 g/fl oz.
    if re.match(r"^fl\.?\s*oz|fluid\s+ounces?", u, re.IGNORECASE):
        density_g_per_floz = 29.6  # water-density default
        for key in ("boost", "ensure", "carnation", "supplement",
                    "formula", "nutritional", "protein shake"):
            if key in fn:
                density_g_per_floz = 30.6  # supplement drinks ≈ 1.03 g/mL
                break
        return round(value * density_g_per_floz, 1)

    # ── Volume units requiring food-density adjustment ──
    if u in ("cup", "cups"):
        for key, density in _CUP_DENSITY_G.items():
            if key in fn or fn in key:
                return round(value * density, 1)
        return round(value * 240.0, 1)  # default water density

    if u in ("tablespoon", "tablespoons", "tbsp", "tbsps"):
        for key, density in _CUP_DENSITY_G.items():
            if key in fn or fn in key:
                return round(value * density / 16.0, 1)  # 1 cup = 16 tbsp
        return round(value * 15.0, 1)  # default liquid ~15 g/tbsp

    if u in ("teaspoon", "teaspoons", "tsp", "tsps"):
        for key, tsp_g in _TSP_DENSITY_G.items():
            if key in fn or fn in key:
                return round(value * tsp_g, 1)
        for key, density in _CUP_DENSITY_G.items():
            if key in fn or fn in key:
                return round(value * density / 48.0, 1)  # 1 cup = 48 tsp
        return round(value * 2.5, 1)  # default spice/powder ~2.5 g/tsp

    if u in ("pinch", "pinches"):
        return round(value * 0.3, 1)
    if u in ("handful", "handfuls"):
        return round(value * 30.0, 1)

    # ── Slices (food-aware: bread ~28 g vs pizza ~107 g) ──
    if u in ("slice", "slices"):
        for key, weight in _SLICE_WEIGHTS_G.items():
            if key in fn or fn in key:
                return round(value * weight, 1)
        return round(value * 30.0, 1)  # generic slice ≈ 30 g (bread-like)

    # ── Cloves (garlic) ──
    if u in ("clove", "cloves"):
        return round(value * 3.0, 1)  # 1 garlic clove ≈ 3 g

    # ── Strips (bacon etc.) ──
    if u in ("strip", "strips"):
        return round(value * (10.0 if "bacon" in fn else 15.0), 1)

    # ── Sticks (butter, celery, cinnamon, string cheese) ──
    if u in ("stick", "sticks"):
        if "butter" in fn or "margarine" in fn:
            return round(value * 113.0, 1)   # 1 US stick = 1/2 cup
        if "celery" in fn:
            return round(value * 4.0, 1)
        if "cinnamon" in fn:
            return round(value * 2.0, 1)
        if "cheese" in fn:
            return round(value * 28.0, 1)
        return round(value * 30.0, 1)

    # ── Cans ──
    if u in ("can", "cans"):
        if any(k in fn for k in ("soda", "cola", "coke", "pepsi", "sprite", "soft drink", "pop", "beer")):
            return round(value * 355.0, 1)
        if "tuna" in fn:
            return round(value * 145.0, 1)
        if "bean" in fn:
            return round(value * 425.0, 1)
        if any(k in fn for k in ("tomato", "corn", "soup", "coconut milk")):
            return round(value * 400.0, 1)
        return round(value * 355.0, 1)

    # ── Bottles ──
    if u in ("bottle", "bottles"):
        if "wine" in fn:
            return round(value * 750.0, 1)
        if "beer" in fn:
            return round(value * 355.0, 1)
        return round(value * 500.0, 1)

    # ── Scoops (protein powder, ice cream) ──
    if u in ("scoop", "scoops"):
        return round(value * (66.0 if "ice cream" in fn else 30.0), 1)

    # ── Wedges ──
    if u in ("wedge", "wedges"):
        if any(k in fn for k in ("lemon", "lime")):
            return round(value * 7.0, 1)
        if "watermelon" in fn:
            return round(value * 280.0, 1)
        return round(value * 30.0, 1)

    # ── Cuts / chips (small pieces of a larger food) ──
    if u in ("cut", "cuts", "chip", "chips"):
        return round(value * 10.0, 1)  # ~10 g per fried plantain cut / chip

    # ── Bunch (leafy/herb) ──
    if u in ("bunch", "bunches"):
        if any(k in fn for k in ("herb", "parsley", "cilantro", "coriander", "basil",
                                 "mint", "dill", "scallion", "green onion", "chive")):
            return round(value * 50.0, 1)
        if any(k in fn for k in ("spinach", "kale", "chard", "lettuce", "greens",
                                 "bitter leaf", "ugu", "spinach")):
            return round(value * 150.0, 1)
        return round(value * 150.0, 1)  # leek/celery/other bunch default

    # ── Other count/piece units ──
    if u in ("piece", "pieces"):
        # Small "cuts/chips/bites" of a larger food (e.g. fried plantain cuts).
        if any(w in fn for w in ("chip", "cut", "crisp", "nugget", "bite", "cube", "crouton")):
            return _count_to_grams(value, 10.0)
        for key, weight in _PIECE_WEIGHTS_G.items():
            if key in fn or fn in key:
                return _count_to_grams(value, weight)
        return _count_to_grams(value, 100.0)  # generic 100 g fallback

    # ── No unit stated — try piece weight then default ──
    for key, weight in _PIECE_WEIGHTS_G.items():
        if key in fn or fn in key:
            return _count_to_grams(value, weight)
    return _default_g(fn)


def _count_to_grams(value: float, weight_per_item: float) -> float:
    """Grams from a COUNT × per-item weight, with a sanity cap. A count implying
    >1500 g of a single item (e.g. "100 of chicken thigh" → 100×116 g) is almost
    certainly grams the user wrote without the unit — fall back to treating the
    number as grams."""
    grams = value * weight_per_item
    if grams > 1500 and value > 12:
        return round(value, 1)
    return round(grams, 1)


def _default_g(food_name: str) -> float:
    """Return a sensible default gram weight when no quantity is stated."""
    fn = food_name.lower()
    # Direct match
    if fn in _NO_QTY_DEFAULTS_G:
        return _NO_QTY_DEFAULTS_G[fn]
    # Substring match
    for key, weight in _NO_QTY_DEFAULTS_G.items():
        if key in fn:
            return weight
    # Classify by type
    t = _classify_ingredient(fn)
    if t != "other":
        return _TYPE_DEFAULTS[t][0]
    return 100.0  # generic 100 g serving


# ── Segment splitting ─────────────────────────────────────────────────────────

# Split on a top-level " and "/" & "/" plus ", but NOT when it's part of a numeric
# quantity ("1 and a half", "1 and 1/2") — guarded by the negative lookahead.
_AND_SPLIT_RE = re.compile(r"\s+(?:and|&|plus)\s+(?!(?:a\s+)?half\b|\d)", re.IGNORECASE)


def _split_top_level(text: str) -> list[str]:
    """Split on commas/semicolons (and top-level conjunctions) outside parentheses."""
    parts: list[str] = []
    depth = 0
    buf: list[str] = []
    for ch in text:
        if ch == "(":
            depth += 1
            buf.append(ch)
        elif ch == ")":
            depth = max(depth - 1, 0)
            buf.append(ch)
        elif ch in ",;\n\r" and depth == 0:
            seg = "".join(buf).strip()
            if seg:
                parts.append(seg)
            buf = []
        else:
            buf.append(ch)
    seg = "".join(buf).strip()
    if seg:
        parts.append(seg)

    # Secondary pass: split each paren-free segment on a top-level conjunction so
    # "2 tbsp apple cider vinegar and cold water" → two foods. Segments containing
    # parentheses are left intact (their sub-ingredients are expanded separately).
    expanded: list[str] = []
    for p in parts:
        if "(" in p:
            expanded.append(p)
        else:
            expanded.extend(s.strip() for s in _AND_SPLIT_RE.split(p) if s.strip())
    return expanded


# ── Segment parser ────────────────────────────────────────────────────────────

def _parse_segment(segment: str) -> tuple[str, float, str, str | None]:
    """Parse a single food segment into (food_name, qty_g, qty_text, parens).

    Returns:
        food_name  — cleaned food name (preparation words stripped)
        qty_g      — estimated gram weight
        qty_text   — human-readable quantity string
        parens     — raw content of parentheses if present, else None
    """
    seg = segment.strip()

    # Extract trailing parenthetical content
    parens: str | None = None
    m_p = re.search(r"\(([^)]+)\)\s*$", seg)
    if m_p:
        parens = m_p.group(1)
        seg = seg[: m_p.start()].strip()

    # Try to match a leading quantity value
    m_qty = _SEG_QTY_RE.match(seg)
    if m_qty:
        qty_str = m_qty.group("qty").strip()
        qty_val = _qty_str_to_float(qty_str)
        rest = seg[m_qty.end():].strip()
        # Skip a size adjective between the number and the unit ("1 large cup of …").
        rest = re.sub(r"^(?:large|small|medium|big|whole)\s+", "", rest, flags=re.IGNORECASE).strip()

        # Try to match a unit token immediately after
        m_unit = _SEG_UNIT_RE.match(rest)
        if m_unit:
            unit_str = m_unit.group("unit").strip()
            after_unit = rest[m_unit.end():].strip()
            # Strip optional "of" connector ("cup of ...")
            after_unit = re.sub(r"^of\s+", "", after_unit, flags=re.IGNORECASE).strip()
            food_name = _clean_food_name(after_unit)
            qty_text = f"{qty_str} {unit_str}"
        else:
            # No unit — e.g. "1 chicken thigh"
            unit_str = ""
            rest_no_of = re.sub(r"^of\s+", "", rest, flags=re.IGNORECASE).strip()
            food_name = _clean_food_name(rest_no_of)
            qty_text = qty_str

        qty_g = _to_grams(qty_val, unit_str, food_name)
        return food_name, qty_g, qty_text, parens

    # No leading quantity. If the parentheses hold a QUANTITY (e.g.
    # "Organic Leek(0.1 bunch)", "mushrooms (0.8 Ounce)") use it as the item's
    # amount instead of expanding it as sub-ingredients.
    food_name = _clean_food_name(seg)
    if parens:
        pq = _parse_quantity_phrase(parens, food_name)
        if pq is not None:
            qty_g, qty_text = pq
            return food_name, qty_g, qty_text, None  # parens consumed as quantity
    qty_g = _default_g(food_name)
    return food_name, qty_g, "default", parens


def _parse_quantity_phrase(text: str, food_name: str) -> tuple[float, str] | None:
    """Parse a standalone 'N unit' phrase (no trailing food words) → (grams, label).
    Returns None if `text` isn't a pure quantity (e.g. a sub-ingredient list)."""
    s = text.strip()
    if "," in s:  # ingredient list, not a quantity
        return None
    m_qty = _SEG_QTY_RE.match(s)
    if not m_qty:
        return None
    qty_val = _qty_str_to_float(m_qty.group("qty").strip())
    rest = s[m_qty.end():].strip()
    m_unit = _SEG_UNIT_RE.match(rest)
    if m_unit:
        if rest[m_unit.end():].strip():  # extra words after unit → not pure quantity
            return None
        unit = m_unit.group("unit").strip()
        return _to_grams(qty_val, unit, food_name), f"{m_qty.group('qty').strip()} {unit}"
    if not rest:  # bare count
        return _to_grams(qty_val, "", food_name), m_qty.group("qty").strip()
    return None


# ── Public API ────────────────────────────────────────────────────────────────

def parse_meal_text(description: str) -> list[FoodComponent]:
    """Extract food components with estimated gram weights from a meal description.

    Handles:
    - Fractional / word quantities ("half cup", "1/2 cup", "1.5 cup")
    - Mixed number quantities ("1 1/2 cups", "1 and a half cups")
    - Unit-less counts ("1 chicken thigh", "2 eggs")
    - Items with no quantity ("onion slices") → sensible defaults
    - Parenthetical ingredient expansions:
        "beef suya(peanut butter, pepper, salt)" →
            beef + peanut_butter(1 tbsp) + pepper(1 tsp) + salt(½ tsp)
    - West African / ethnic food names via the NLM alias map in nlm_food_extractor

    Returns a list of FoodComponent(food_name, qty_g, qty_text, source_text).
    """
    if not description or not description.strip():
        return []

    segments = _split_top_level(description)
    components: list[FoodComponent] = []
    seen: set[str] = set()

    for seg in segments:
        seg = seg.strip()
        if not seg:
            continue

        food_name, qty_g, qty_text, parens = _parse_segment(seg)

        if len(food_name) < 2:
            continue

        if food_name not in seen:
            seen.add(food_name)
            components.append(
                FoodComponent(
                    food_name=food_name,
                    qty_g=qty_g,
                    qty_text=qty_text,
                    source_text=seg,
                )
            )

        # Expand parenthetical sub-ingredients with default condiment quantities
        if parens:
            paren_items = [p.strip() for p in parens.split(",") if p.strip()]
            for item_raw in paren_items:
                # Check if this paren item has its own explicit quantity
                item_food, item_qty_g, item_qty_text, _ = _parse_segment(item_raw)
                if len(item_food) < 2 or item_food in seen:
                    continue

                # If no explicit quantity was found, assign type-based default
                if item_qty_text == "default":
                    ing_type = _classify_ingredient(item_food)
                    item_qty_g, item_qty_text = _TYPE_DEFAULTS[ing_type]

                seen.add(item_food)
                components.append(
                    FoodComponent(
                        food_name=item_food,
                        qty_g=item_qty_g,
                        qty_text=item_qty_text,
                        source_text=item_raw,
                    )
                )

    return components
