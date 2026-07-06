"""Reference knowledge base for nutrition believability — the "what is correct".

Instead of hardcoding fixes per food, we classify a food into a coarse **category**
and keep an expected per-100 g calorie band (+ macro sanity, typical serving grams,
plausible units) for that category. The believability layer tests every resolved
estimate against its category band, so a bad USDA/branded/AI match (e.g. plain
"rice" resolving to 360 kcal/100 g dry/fortified, or "Boost" to 522 kcal/serving)
is caught **generically** — no per-item code.

Bands are intentionally wide (catch gross mismatches, not nuance) and are used to
*flag + re-rank sources*, not to fabricate values.
"""
from __future__ import annotations

import re

# category -> (kcal/100g min, kcal/100g max, typical serving g, plausible unit kinds)
# Unit kinds: "mass" (g/oz/lb), "volume" (ml/l/cup/tbsp/tsp), "count" (each/slice/piece).
_CATEGORIES: dict[str, dict] = {
    "water":            {"kcal": (0, 5),     "serving": 240, "units": {"volume"}},
    "tea_coffee":       {"kcal": (0, 15),    "serving": 240, "units": {"volume"}},
    "diet_beverage":    {"kcal": (0, 10),    "serving": 355, "units": {"volume"}},
    "beverage":         {"kcal": (10, 130),  "serving": 240, "units": {"volume"}},   # juice/milk/soda/sports
    "nutrition_drink":  {"kcal": (50, 160),  "serving": 240, "units": {"volume"}},   # Boost/Ensure (~67/100ml)
    "alcohol":          {"kcal": (30, 300),  "serving": 150, "units": {"volume"}},
    "vegetable":        {"kcal": (8, 130),   "serving": 100, "units": {"mass", "count"}},
    "fruit_fresh":      {"kcal": (20, 110),  "serving": 120, "units": {"mass", "count"}},
    "fruit_dried":      {"kcal": (230, 360), "serving": 40,  "units": {"mass"}},
    "grain_cooked":     {"kcal": (80, 200),  "serving": 150, "units": {"mass", "volume"}},  # rice/pasta cooked
    "bread_baked":      {"kcal": (210, 360), "serving": 50,  "units": {"mass", "count"}},
    "cereal_dry":       {"kcal": (330, 420), "serving": 40,  "units": {"mass", "volume"}},
    "legume_cooked":    {"kcal": (70, 180),  "serving": 130, "units": {"mass", "volume"}},
    "lean_meat":        {"kcal": (90, 250),  "serving": 120, "units": {"mass", "count"}},   # chicken/fish/lean beef
    "fatty_meat":       {"kcal": (200, 420), "serving": 100, "units": {"mass", "count"}},   # bacon/sausage/suya
    "egg":              {"kcal": (130, 200), "serving": 50,  "units": {"count", "mass"}},
    "cheese":           {"kcal": (230, 450), "serving": 30,  "units": {"mass", "count"}},
    "dairy":            {"kcal": (30, 160),  "serving": 200, "units": {"mass", "volume"}},   # milk/yogurt
    "nut_seed":         {"kcal": (400, 700), "serving": 30,  "units": {"mass"}},
    "oil_fat":          {"kcal": (700, 902), "serving": 14,  "units": {"volume", "mass"}},
    "sugar_sweet":      {"kcal": (250, 550), "serving": 30,  "units": {"mass", "volume"}},
    "snack_processed":  {"kcal": (300, 600), "serving": 40,  "units": {"mass", "count"}},
    "soup_stew":        {"kcal": (25, 180),  "serving": 245, "units": {"mass", "volume"}},
    "prepared_dish":    {"kcal": (60, 320),  "serving": 200, "units": {"mass", "volume", "count"}},
    "condiment":        {"kcal": (10, 700),  "serving": 16,  "units": {"volume", "mass"}},
    "unknown":          {"kcal": (10, 600),  "serving": 100, "units": {"mass", "volume", "count"}},
}

# Ordered (specific -> general); first keyword hit wins.
_RULES: list[tuple[tuple[str, ...], str]] = [
    (("diet soda", "diet coke", "zero sugar", "sugar free soda"), "diet_beverage"),
    (("boost", "ensure", "glucerna", "nutrition shake", "meal replacement", "protein shake", "slimfast"), "nutrition_drink"),
    (("coffee", "espresso", "americano", "latte", "tea ", " tea", "matcha"), "tea_coffee"),
    (("water",), "water"),
    (("beer", "wine", "vodka", "whiskey", "liquor", "cocktail", "cider beer"), "alcohol"),
    (("juice", "milk", "soda", "cola", "smoothie", "lemonade", "gatorade", "kombucha", "soft drink"), "beverage"),
    (("raisin", "dried fruit", "dried apricot", "date ", "prune", "dried mango"), "fruit_dried"),
    (("oil", "butter", "lard", "ghee", "tallow", "shortening", "margarine"), "oil_fat"),
    (("peanut butter", "almond butter", "tahini", "nut", "seed", "almond", "cashew", "walnut", "pecan", "pistachio"), "nut_seed"),
    (("cheese", "cheddar", "mozzarella", "parmesan", "feta", "paneer"), "cheese"),
    (("yogurt", "yoghurt", "milk", "kefir", "cream "), "dairy"),
    (("egg",), "egg"),
    (("bacon", "sausage", "salami", "pepperoni", "suya", "ribs", "pork belly", "chorizo", "hot dog"), "fatty_meat"),
    (("chicken", "turkey", "fish", "salmon", "tuna", "tilapia", "shrimp", "beef", "steak", "pork", "lamb", "goat", "meat", "tofu"), "lean_meat"),
    (("bean", "lentil", "chickpea", "pea", "legume", "dal", "hummus"), "legume_cooked"),
    (("cereal", "granola", "muesli", "oats dry"), "cereal_dry"),
    (("bread", "toast", "bagel", "roll", "bun", "tortilla", "naan", "pita", "cracker"), "bread_baked"),
    (("rice", "pasta", "noodle", "spaghetti", "quinoa", "couscous", "porridge", "oatmeal", "grain", "fufu", "ugali"), "grain_cooked"),
    (("candy", "chocolate", "sugar", "syrup", "honey", "jam", "cake", "cookie", "donut", "ice cream", "dessert"), "sugar_sweet"),
    (("chip", "crisp", "fries", "popcorn", "pretzel", "snack"), "snack_processed"),
    (("soup", "stew", "broth", "chowder", "curry", "gumbo"), "soup_stew"),
    (("salt", "pepper", "sauce", "ketchup", "mayo", "mustard", "dressing", "vinegar", "spice", "seasoning"), "condiment"),
    (("apple", "banana", "orange", "berry", "grape", "melon", "mango", "pear", "peach", "pineapple", "fruit"), "fruit_fresh"),
    (("salad", "broccoli", "spinach", "carrot", "tomato", "onion", "pepper", "lettuce", "cabbage", "vegetable", "kale", "cucumber"), "vegetable"),
    (("stew", "jollof", "casserole", "pilaf", "biryani", "dish", "plate", "combo"), "prepared_dish"),
]


# Preparation clauses name the cooking medium, not the food — "beans cooked in
# palm oil" must classify as beans (legume), never as palm oil (oil_fat).
_PREP_CLAUSE = re.compile(
    r"\b(cooked in|fried in|sauteed in|sautéed in|made with|prepared with|topped with|"
    r"served with|with|in)\b",
    re.IGNORECASE,
)


def _classify_full(name: str) -> str:
    n = " " + name + " "
    for keywords, category in _RULES:
        if any(k in n for k in keywords):
            return category
    return "unknown"


def head_phrase(food_name: str) -> str:
    """The food itself, before any preparation clause ("beans cooked in palm
    oil with ground peppers" → "beans"). The cooking medium and seasonings must
    never decide a food's category or default portion."""
    name = (food_name or "").lower().strip()
    head = _PREP_CLAUSE.split(name, maxsplit=1)[0].strip()
    return head or name


def classify(food_name: str) -> str:
    name = (food_name or "").lower().strip()
    # Head-noun first: the food before any preparation clause decides the
    # category ("beans cooked in palm oil" → beans → legume_cooked).
    head = head_phrase(name)
    if head != name:
        cat = _classify_full(head)
        if cat != "unknown":
            return cat
    return _classify_full(name)


def band(category: str) -> dict:
    return _CATEGORIES.get(category, _CATEGORIES["unknown"])


def expected_kcal_band(food_name: str) -> tuple[float, float]:
    return tuple(band(classify(food_name))["kcal"])  # (min, max) per 100 g


def typical_serving_g(food_name: str) -> float:
    return float(band(classify(food_name))["serving"])


def plausible_unit_kinds(food_name: str) -> set[str]:
    return set(band(classify(food_name))["units"])


def kcal_in_band(food_name: str, kcal_per_100g: float, tol: float = 0.5) -> bool:
    """Is a per-100 g calorie value within the food's category band (± tolerance)?"""
    lo, hi = expected_kcal_band(food_name)
    return (lo * (1 - tol)) <= kcal_per_100g <= (hi * (1 + tol))
