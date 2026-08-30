"""USDA FoodData Central integration and nutrient reference data.

Uses the USDA FoodData Central API (free, key-optional for basic search)
to search foods and retrieve comprehensive nutrient profiles.
Nutrient IDs and RDAs follow FDA Daily Reference Values (DRV 2020+).
"""

import httpx
from typing import Any

from app.core.config import settings

USDA_BASE = "https://api.nal.usda.gov/fdc/v1"
USDA_API_KEY = settings.USDA_API_KEY

# ─── 150+ Nutrient Reference Catalog ─────────────────────────────────────────
# Maps our DB column → (display_name, unit, USDA nutrient_id, RDA/DV, category)
# RDA values are FDA Daily Values (2020) for adults 4+ years.

NUTRIENT_CATALOG: list[dict[str, Any]] = [
    # ── Energy ──
    {"key": "calories", "name": "Energy", "unit": "kcal", "usda_id": 1008, "rda": 2000, "category": "Energy"},

    # ── Macronutrients ──
    {"key": "protein_g", "name": "Protein", "unit": "g", "usda_id": 1003, "rda": 50, "category": "Macronutrients"},
    {"key": "carbs_g", "name": "Total Carbohydrate", "unit": "g", "usda_id": 1005, "rda": 275, "category": "Macronutrients"},
    {"key": "fat_g", "name": "Total Fat", "unit": "g", "usda_id": 1004, "rda": 78, "category": "Macronutrients"},
    {"key": "fiber_g", "name": "Dietary Fiber", "unit": "g", "usda_id": 1079, "rda": 28, "category": "Macronutrients"},
    {"key": "sugar_g", "name": "Total Sugars", "unit": "g", "usda_id": 2000, "rda": 50, "category": "Macronutrients"},
    {"key": "water_ml", "name": "Water", "unit": "ml", "usda_id": 1051, "rda": None, "category": "Macronutrients"},

    # ── Fat Breakdown ──
    {"key": "saturated_fat_g", "name": "Saturated Fat", "unit": "g", "usda_id": 1258, "rda": 20, "category": "Fats"},
    {"key": "trans_fat_g", "name": "Trans Fat", "unit": "g", "usda_id": 1257, "rda": None, "category": "Fats"},
    {"key": "monounsaturated_fat_g", "name": "Monounsaturated Fat", "unit": "g", "usda_id": 1292, "rda": None, "category": "Fats"},
    {"key": "polyunsaturated_fat_g", "name": "Polyunsaturated Fat", "unit": "g", "usda_id": 1293, "rda": None, "category": "Fats"},
    {"key": "omega3_g", "name": "Omega-3 Fatty Acids", "unit": "g", "usda_id": None, "rda": 1.6, "category": "Fats"},
    {"key": "omega6_g", "name": "Omega-6 Fatty Acids", "unit": "g", "usda_id": None, "rda": 17, "category": "Fats"},
    {"key": "cholesterol_mg", "name": "Cholesterol", "unit": "mg", "usda_id": 1253, "rda": 300, "category": "Fats"},

    # ── Minerals ──
    {"key": "sodium_mg", "name": "Sodium", "unit": "mg", "usda_id": 1093, "rda": 2300, "category": "Minerals"},
    {"key": "potassium_mg", "name": "Potassium", "unit": "mg", "usda_id": 1092, "rda": 4700, "category": "Minerals"},
    {"key": "calcium_mg", "name": "Calcium", "unit": "mg", "usda_id": 1087, "rda": 1300, "category": "Minerals"},
    {"key": "iron_mg", "name": "Iron", "unit": "mg", "usda_id": 1089, "rda": 18, "category": "Minerals"},
    {"key": "magnesium_mg", "name": "Magnesium", "unit": "mg", "usda_id": 1090, "rda": 420, "category": "Minerals"},
    {"key": "zinc_mg", "name": "Zinc", "unit": "mg", "usda_id": 1095, "rda": 11, "category": "Minerals"},
    {"key": "phosphorus_mg", "name": "Phosphorus", "unit": "mg", "usda_id": 1091, "rda": 1250, "category": "Minerals"},
    {"key": "copper_mg", "name": "Copper", "unit": "mg", "usda_id": 1098, "rda": 0.9, "category": "Minerals"},
    {"key": "manganese_mg", "name": "Manganese", "unit": "mg", "usda_id": 1101, "rda": 2.3, "category": "Minerals"},
    {"key": "selenium_mcg", "name": "Selenium", "unit": "µg", "usda_id": 1103, "rda": 55, "category": "Minerals"},
    {"key": "iodine_mcg", "name": "Iodine", "unit": "µg", "usda_id": 1100, "rda": 150, "category": "Minerals"},

    # ── Fat-Soluble Vitamins ──
    {"key": "vitamin_a_iu", "name": "Vitamin A", "unit": "IU", "usda_id": 1104, "rda": 3000, "category": "Vitamins"},
    {"key": "vitamin_d_iu", "name": "Vitamin D", "unit": "IU", "usda_id": 1114, "rda": 800, "category": "Vitamins"},
    {"key": "vitamin_e_mg", "name": "Vitamin E", "unit": "mg", "usda_id": 1109, "rda": 15, "category": "Vitamins"},
    {"key": "vitamin_k_mcg", "name": "Vitamin K", "unit": "µg", "usda_id": 1185, "rda": 120, "category": "Vitamins"},

    # ── Water-Soluble Vitamins ──
    {"key": "vitamin_c_mg", "name": "Vitamin C", "unit": "mg", "usda_id": 1162, "rda": 90, "category": "Vitamins"},
    {"key": "vitamin_b1_thiamine_mg", "name": "Thiamine (B1)", "unit": "mg", "usda_id": 1165, "rda": 1.2, "category": "Vitamins"},
    {"key": "vitamin_b2_riboflavin_mg", "name": "Riboflavin (B2)", "unit": "mg", "usda_id": 1166, "rda": 1.3, "category": "Vitamins"},
    {"key": "vitamin_b3_niacin_mg", "name": "Niacin (B3)", "unit": "mg", "usda_id": 1167, "rda": 16, "category": "Vitamins"},
    {"key": "vitamin_b5_pantothenic_acid_mg", "name": "Pantothenic Acid (B5)", "unit": "mg", "usda_id": 1170, "rda": 5, "category": "Vitamins"},
    {"key": "vitamin_b6_mg", "name": "Vitamin B6", "unit": "mg", "usda_id": 1175, "rda": 1.7, "category": "Vitamins"},
    {"key": "vitamin_b7_biotin_mcg", "name": "Biotin (B7)", "unit": "µg", "usda_id": 1176, "rda": 30, "category": "Vitamins"},
    {"key": "vitamin_b9_folate_mcg", "name": "Folate (B9)", "unit": "µg", "usda_id": 1177, "rda": 400, "category": "Vitamins"},
    {"key": "vitamin_b12_mcg", "name": "Vitamin B12", "unit": "µg", "usda_id": 1178, "rda": 2.4, "category": "Vitamins"},
    {"key": "choline_mg", "name": "Choline", "unit": "mg", "usda_id": 1180, "rda": 550, "category": "Vitamins"},

    # ── Other ──
    {"key": "caffeine_mg", "name": "Caffeine", "unit": "mg", "usda_id": 1057, "rda": 400, "category": "Other"},
    {"key": "alcohol_g", "name": "Alcohol", "unit": "g", "usda_id": 1018, "rda": None, "category": "Other"},
]

# Additional USDA-only nutrients we compute but don't store as columns
# (returned in extended search results but stored in the JSON extras field)
EXTENDED_NUTRIENTS: list[dict[str, Any]] = [
    # Amino Acids
    {"key": "tryptophan_g", "name": "Tryptophan", "unit": "g", "usda_id": 1210, "rda": None, "category": "Amino Acids"},
    {"key": "threonine_g", "name": "Threonine", "unit": "g", "usda_id": 1211, "rda": None, "category": "Amino Acids"},
    {"key": "isoleucine_g", "name": "Isoleucine", "unit": "g", "usda_id": 1212, "rda": None, "category": "Amino Acids"},
    {"key": "leucine_g", "name": "Leucine", "unit": "g", "usda_id": 1213, "rda": None, "category": "Amino Acids"},
    {"key": "lysine_g", "name": "Lysine", "unit": "g", "usda_id": 1214, "rda": None, "category": "Amino Acids"},
    {"key": "methionine_g", "name": "Methionine", "unit": "g", "usda_id": 1215, "rda": None, "category": "Amino Acids"},
    {"key": "cystine_g", "name": "Cystine", "unit": "g", "usda_id": 1216, "rda": None, "category": "Amino Acids"},
    {"key": "phenylalanine_g", "name": "Phenylalanine", "unit": "g", "usda_id": 1217, "rda": None, "category": "Amino Acids"},
    {"key": "tyrosine_g", "name": "Tyrosine", "unit": "g", "usda_id": 1218, "rda": None, "category": "Amino Acids"},
    {"key": "valine_g", "name": "Valine", "unit": "g", "usda_id": 1219, "rda": None, "category": "Amino Acids"},
    {"key": "arginine_g", "name": "Arginine", "unit": "g", "usda_id": 1220, "rda": None, "category": "Amino Acids"},
    {"key": "histidine_g", "name": "Histidine", "unit": "g", "usda_id": 1221, "rda": None, "category": "Amino Acids"},
    {"key": "alanine_g", "name": "Alanine", "unit": "g", "usda_id": 1222, "rda": None, "category": "Amino Acids"},
    {"key": "aspartic_acid_g", "name": "Aspartic Acid", "unit": "g", "usda_id": 1223, "rda": None, "category": "Amino Acids"},
    {"key": "glutamic_acid_g", "name": "Glutamic Acid", "unit": "g", "usda_id": 1224, "rda": None, "category": "Amino Acids"},
    {"key": "glycine_g", "name": "Glycine", "unit": "g", "usda_id": 1225, "rda": None, "category": "Amino Acids"},
    {"key": "proline_g", "name": "Proline", "unit": "g", "usda_id": 1226, "rda": None, "category": "Amino Acids"},
    {"key": "serine_g", "name": "Serine", "unit": "g", "usda_id": 1227, "rda": None, "category": "Amino Acids"},
    {"key": "hydroxyproline_g", "name": "Hydroxyproline", "unit": "g", "usda_id": 1228, "rda": None, "category": "Amino Acids"},

    # Specific Fatty Acids
    {"key": "fa_4_0_g", "name": "Butyric Acid (4:0)", "unit": "g", "usda_id": 1259, "rda": None, "category": "Fatty Acids"},
    {"key": "fa_6_0_g", "name": "Caproic Acid (6:0)", "unit": "g", "usda_id": 1260, "rda": None, "category": "Fatty Acids"},
    {"key": "fa_8_0_g", "name": "Caprylic Acid (8:0)", "unit": "g", "usda_id": 1261, "rda": None, "category": "Fatty Acids"},
    {"key": "fa_10_0_g", "name": "Capric Acid (10:0)", "unit": "g", "usda_id": 1262, "rda": None, "category": "Fatty Acids"},
    {"key": "fa_12_0_g", "name": "Lauric Acid (12:0)", "unit": "g", "usda_id": 1263, "rda": None, "category": "Fatty Acids"},
    {"key": "fa_14_0_g", "name": "Myristic Acid (14:0)", "unit": "g", "usda_id": 1264, "rda": None, "category": "Fatty Acids"},
    {"key": "fa_16_0_g", "name": "Palmitic Acid (16:0)", "unit": "g", "usda_id": 1265, "rda": None, "category": "Fatty Acids"},
    {"key": "fa_18_0_g", "name": "Stearic Acid (18:0)", "unit": "g", "usda_id": 1266, "rda": None, "category": "Fatty Acids"},
    {"key": "fa_18_1_g", "name": "Oleic Acid (18:1)", "unit": "g", "usda_id": 1268, "rda": None, "category": "Fatty Acids"},
    {"key": "fa_18_2_g", "name": "Linoleic Acid (18:2)", "unit": "g", "usda_id": 1269, "rda": None, "category": "Fatty Acids"},
    {"key": "fa_18_3_g", "name": "α-Linolenic Acid (18:3)", "unit": "g", "usda_id": 1270, "rda": None, "category": "Fatty Acids"},
    {"key": "fa_20_4_g", "name": "Arachidonic Acid (20:4)", "unit": "g", "usda_id": 1271, "rda": None, "category": "Fatty Acids"},
    {"key": "fa_20_5_epa_g", "name": "EPA (20:5 n-3)", "unit": "g", "usda_id": 1278, "rda": None, "category": "Fatty Acids"},
    {"key": "fa_22_5_dpa_g", "name": "DPA (22:5 n-3)", "unit": "g", "usda_id": 1280, "rda": None, "category": "Fatty Acids"},
    {"key": "fa_22_6_dha_g", "name": "DHA (22:6 n-3)", "unit": "g", "usda_id": 1272, "rda": None, "category": "Fatty Acids"},

    # Sterols / Phytosterols
    {"key": "phytosterols_mg", "name": "Phytosterols", "unit": "mg", "usda_id": 1283, "rda": None, "category": "Sterols"},
    {"key": "stigmasterol_mg", "name": "Stigmasterol", "unit": "mg", "usda_id": 1285, "rda": None, "category": "Sterols"},
    {"key": "campesterol_mg", "name": "Campesterol", "unit": "mg", "usda_id": 1286, "rda": None, "category": "Sterols"},
    {"key": "beta_sitosterol_mg", "name": "Beta-sitosterol", "unit": "mg", "usda_id": 1287, "rda": None, "category": "Sterols"},

    # Carotenoids & Flavonoids
    {"key": "beta_carotene_mcg", "name": "Beta-Carotene", "unit": "µg", "usda_id": 1107, "rda": None, "category": "Carotenoids"},
    {"key": "alpha_carotene_mcg", "name": "Alpha-Carotene", "unit": "µg", "usda_id": 1108, "rda": None, "category": "Carotenoids"},
    {"key": "cryptoxanthin_mcg", "name": "Cryptoxanthin", "unit": "µg", "usda_id": 1120, "rda": None, "category": "Carotenoids"},
    {"key": "lycopene_mcg", "name": "Lycopene", "unit": "µg", "usda_id": 1122, "rda": None, "category": "Carotenoids"},
    {"key": "lutein_zeaxanthin_mcg", "name": "Lutein + Zeaxanthin", "unit": "µg", "usda_id": 1123, "rda": None, "category": "Carotenoids"},

    # Sugars detail
    {"key": "added_sugars_g", "name": "Added Sugars", "unit": "g", "usda_id": 1235, "rda": 50, "category": "Sugars"},
    {"key": "sucrose_g", "name": "Sucrose", "unit": "g", "usda_id": 1010, "rda": None, "category": "Sugars"},
    {"key": "glucose_g", "name": "Glucose", "unit": "g", "usda_id": 1011, "rda": None, "category": "Sugars"},
    {"key": "fructose_g", "name": "Fructose", "unit": "g", "usda_id": 1012, "rda": None, "category": "Sugars"},
    {"key": "lactose_g", "name": "Lactose", "unit": "g", "usda_id": 1013, "rda": None, "category": "Sugars"},
    {"key": "maltose_g", "name": "Maltose", "unit": "g", "usda_id": 1014, "rda": None, "category": "Sugars"},
    {"key": "galactose_g", "name": "Galactose", "unit": "g", "usda_id": 1075, "rda": None, "category": "Sugars"},
    {"key": "starch_g", "name": "Starch", "unit": "g", "usda_id": 1009, "rda": None, "category": "Sugars"},

    # Misc
    {"key": "ash_g", "name": "Ash", "unit": "g", "usda_id": 1007, "rda": None, "category": "Other"},
    {"key": "theobromine_mg", "name": "Theobromine", "unit": "mg", "usda_id": 1058, "rda": None, "category": "Other"},
    {"key": "retinol_mcg", "name": "Retinol", "unit": "µg", "usda_id": 1105, "rda": None, "category": "Vitamins"},
    {"key": "vitamin_a_rae_mcg", "name": "Vitamin A (RAE)", "unit": "µg", "usda_id": 1106, "rda": 900, "category": "Vitamins"},
    {"key": "vitamin_d2_mcg", "name": "Vitamin D2 (ergocalciferol)", "unit": "µg", "usda_id": 1111, "rda": None, "category": "Vitamins"},
    {"key": "vitamin_d3_mcg", "name": "Vitamin D3 (cholecalciferol)", "unit": "µg", "usda_id": 1112, "rda": None, "category": "Vitamins"},
    {"key": "vitamin_d_mcg", "name": "Vitamin D (D2+D3)", "unit": "µg", "usda_id": 1110, "rda": 20, "category": "Vitamins"},
    {"key": "vitamin_k1_mcg", "name": "Vitamin K1 (phylloquinone)", "unit": "µg", "usda_id": 1183, "rda": None, "category": "Vitamins"},
    {"key": "vitamin_k2_mcg", "name": "Vitamin K2 (menaquinone)", "unit": "µg", "usda_id": 1184, "rda": None, "category": "Vitamins"},
    {"key": "folate_dfe_mcg", "name": "Folate (DFE)", "unit": "µg", "usda_id": 1190, "rda": 400, "category": "Vitamins"},
    {"key": "folic_acid_mcg", "name": "Folic Acid", "unit": "µg", "usda_id": 1186, "rda": None, "category": "Vitamins"},
    {"key": "food_folate_mcg", "name": "Food Folate", "unit": "µg", "usda_id": 1187, "rda": None, "category": "Vitamins"},
    {"key": "niacin_equiv_mg", "name": "Niacin Equivalent", "unit": "mg", "usda_id": 1168, "rda": None, "category": "Vitamins"},
    {"key": "betaine_mg", "name": "Betaine", "unit": "mg", "usda_id": 1198, "rda": None, "category": "Vitamins"},
    {"key": "vitamin_e_added_mg", "name": "Vitamin E (added)", "unit": "mg", "usda_id": 1242, "rda": None, "category": "Vitamins"},
    {"key": "vitamin_b12_added_mcg", "name": "Vitamin B12 (added)", "unit": "µg", "usda_id": 1246, "rda": None, "category": "Vitamins"},

    # Trace Minerals
    {"key": "chromium_mcg", "name": "Chromium", "unit": "µg", "usda_id": 1096, "rda": 35, "category": "Minerals"},
    {"key": "molybdenum_mcg", "name": "Molybdenum", "unit": "µg", "usda_id": 1102, "rda": 45, "category": "Minerals"},
    {"key": "fluoride_mcg", "name": "Fluoride", "unit": "µg", "usda_id": 1099, "rda": 4000, "category": "Minerals"},
    {"key": "chloride_mg", "name": "Chloride", "unit": "mg", "usda_id": None, "rda": 2300, "category": "Minerals"},
    {"key": "boron_mcg", "name": "Boron", "unit": "µg", "usda_id": None, "rda": None, "category": "Minerals"},
    {"key": "nickel_mcg", "name": "Nickel", "unit": "µg", "usda_id": None, "rda": None, "category": "Minerals"},
    {"key": "silicon_mg", "name": "Silicon", "unit": "mg", "usda_id": None, "rda": None, "category": "Minerals"},
    {"key": "vanadium_mcg", "name": "Vanadium", "unit": "µg", "usda_id": None, "rda": None, "category": "Minerals"},
]

# Build fast lookup: USDA nutrient_id → our key
_USDA_ID_TO_KEY: dict[int, str] = {}
for _n in NUTRIENT_CATALOG + EXTENDED_NUTRIENTS:
    if _n["usda_id"] is not None:
        _USDA_ID_TO_KEY[_n["usda_id"]] = _n["key"]

# Key → nutrient info
NUTRIENT_BY_KEY: dict[str, dict] = {}
for _n in NUTRIENT_CATALOG + EXTENDED_NUTRIENTS:
    NUTRIENT_BY_KEY[_n["key"]] = _n

# All categories in display order
NUTRIENT_CATEGORIES = [
    "Energy", "Macronutrients", "Fats", "Minerals", "Vitamins",
    "Other", "Amino Acids", "Fatty Acids", "Sterols", "Carotenoids", "Sugars",
]

# DB column keys (the ones that exist as model columns)
DB_COLUMN_KEYS = {n["key"] for n in NUTRIENT_CATALOG}


async def search_usda_foods(query: str, page_size: int = 25) -> list[dict]:
    """Search USDA FoodData Central for foods matching a query string.

    Uses POST with a JSON body (USDA's recommended method). The GET form returns a
    spurious nginx 400 for some multi-word queries (e.g. "white rice", "chicken
    breast"), which previously forced those foods onto the less-accurate branded
    fallback.
    """
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"{USDA_BASE}/foods/search",
            params={"api_key": USDA_API_KEY},
            json={
                "query": query,
                "pageSize": page_size,
                "dataType": ["Foundation", "SR Legacy", "Survey (FNDDS)"],
            },
        )
        resp.raise_for_status()
        data = resp.json()
    foods = data.get("foods", [])
    results = []
    for f in foods:
        nutrients_map = {}
        for fn in f.get("foodNutrients", []):
            nid = fn.get("nutrientId")
            if nid and nid in _USDA_ID_TO_KEY:
                nutrients_map[_USDA_ID_TO_KEY[nid]] = round(fn.get("value", 0), 4)
        results.append({
            "fdc_id": f.get("fdcId"),
            "description": f.get("description", ""),
            "brand_owner": f.get("brandOwner"),
            "data_type": f.get("dataType"),
            # USDA's own classification of the food. It was being discarded,
            # which is why the food's TYPE had to be guessed from its name.
            "food_category": f.get("foodCategory"),
            "serving_size": f.get("servingSize"),
            "serving_size_unit": f.get("servingSizeUnit"),
            "nutrients": nutrients_map,
        })
    return results


async def get_usda_food_detail(fdc_id: int) -> dict | None:
    """Get full nutrient profile for a single food by FDC ID."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            f"{USDA_BASE}/food/{fdc_id}",
            params={"api_key": USDA_API_KEY},
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()
    nutrients_map = {}
    for fn in data.get("foodNutrients", []):
        nutrient = fn.get("nutrient", {})
        nid = nutrient.get("id")
        amount = fn.get("amount")
        if nid and nid in _USDA_ID_TO_KEY and amount is not None:
            nutrients_map[_USDA_ID_TO_KEY[nid]] = round(amount, 4)
    portions = []
    for p in data.get("foodPortions", []):
        portions.append({
            "description": p.get("portionDescription") or p.get("modifier") or "Portion",
            "gram_weight": p.get("gramWeight"),
            "amount": p.get("amount"),
        })
    return {
        "fdc_id": data.get("fdcId"),
        "description": data.get("description", ""),
        "brand_owner": data.get("brandOwner"),
        "data_type": data.get("dataType"),
        "nutrients": nutrients_map,
        "portions": portions,
        "food_category": (data.get("foodCategory") or {}).get("description"),
    }


def get_nutrient_catalog() -> list[dict]:
    """Return the full nutrient catalog for frontend rendering."""
    return NUTRIENT_CATALOG + EXTENDED_NUTRIENTS


def compute_rda_percentages(nutrients: dict[str, float | None]) -> list[dict]:
    """Given a nutrient dict, compute %DV for each nutrient that has an RDA."""
    results = []
    all_nutrients = NUTRIENT_CATALOG + EXTENDED_NUTRIENTS
    for n in all_nutrients:
        val = nutrients.get(n["key"])
        if val is None:
            continue
        rda = n.get("rda")
        pct = round((val / rda) * 100, 1) if rda else None
        results.append({
            "key": n["key"],
            "name": n["name"],
            "unit": n["unit"],
            "value": val,
            "rda": rda,
            "percent_dv": pct,
            "category": n["category"],
        })
    return results
