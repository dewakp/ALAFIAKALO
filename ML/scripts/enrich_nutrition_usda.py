#!/usr/bin/env python3
"""
USDA FoodData Central Nutrient Mapper for HEBCS Nutrition Data — FULL SPECTRUM

Maps free-text food descriptions from nutrition logs to USDA SR Legacy nutrient
profiles using TF-IDF + cosine similarity matching.

ALL 149 USDA SR Legacy nutrients are captured — not just macros. The full
haystack is essential because less-discussed nutrients (magnesium, choline,
chloride, manganese, selenium, copper, etc.) have direct impact on:
  - Blood health (iron forms, B12, folate, copper, zinc → erythropoiesis)
  - Blood pressure (sodium, potassium, magnesium, calcium, chloride)
  - GI function (fiber types, organic acids, sugar alcohols)
  - Neuropathways (choline, B-vitamins, magnesium, omega-3 DHA/EPA)
  - G6PD interactions (fava beans → vicine, oxidative stress compounds)
  - Dialysis clearance (water-soluble vitamins, electrolytes, amino acids)

Strategy:
  1. Build a nutrient lookup from ALL 149 USDA nutrients (not filtered)
  2. TF-IDF index of 7,793 food descriptions
  3. Parse multi-ingredient meal entries into individual items
  4. Fuzzy-match via cosine similarity with domain-specific aliases
  5. Scale by estimated portion, sum across meal components
"""

import pandas as pd
import numpy as np
import os
import re
import json
from pathlib import Path
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# ── Paths ──
ML = Path(__file__).resolve().parent.parent  # scripts/ → ML/
USDA_DIR = ML / 'data' / 'usda' / 'sr_legacy' / 'FoodData_Central_sr_legacy_food_csv_2018-04'
NUTRITION_CSV = ML / 'data' / 'processed' / 'unified_nutrition.csv'
OUTPUT_CSV = ML / 'data' / 'processed' / 'unified_nutrition_enriched.csv'
MATCH_LOG = ML / 'data' / 'usda' / 'food_match_log.csv'
USDA_LOOKUP = ML / 'data' / 'usda' / 'usda_nutrient_lookup.csv'
NUTRIENT_META = ML / 'data' / 'usda' / 'nutrient_metadata.json'

# ══════════════════════════════════════════════════════════════════════════════
# NUTRIENT ID → COLUMN NAME MAPPING
# All 149 nutrients with data in USDA SR Legacy.
# Column names are snake_case, grouped by physiological relevance.
# ══════════════════════════════════════════════════════════════════════════════

NUTRIENT_MAP = {
    # ── Energy ──
    1008: 'energy_kcal',
    1062: 'energy_kj',

    # ── Macronutrients ──
    1003: 'protein_g',
    1004: 'total_fat_g',
    1005: 'carbohydrate_g',
    1051: 'water_g',
    1007: 'ash_g',
    1018: 'alcohol_g',

    # ── Carbohydrate Detail ──
    1079: 'fiber_total_g',
    1082: 'fiber_soluble_g',
    1084: 'fiber_insoluble_g',
    2000: 'sugars_total_g',
    1063: 'sugars_nlea_g',
    1009: 'starch_g',
    1010: 'sucrose_g',
    1011: 'glucose_g',
    1012: 'fructose_g',
    1013: 'lactose_g',
    1014: 'maltose_g',
    1075: 'galactose_g',

    # ── Minerals ──
    1087: 'calcium_mg',
    1088: 'chlorine_mg',
    1089: 'iron_mg',
    1090: 'magnesium_mg',
    1091: 'phosphorus_mg',
    1092: 'potassium_mg',
    1093: 'sodium_mg',
    1094: 'sulfur_mg',
    1095: 'zinc_mg',
    1096: 'chromium_ug',
    1098: 'copper_mg',
    1099: 'fluoride_ug',
    1100: 'iodine_ug',
    1101: 'manganese_mg',
    1102: 'molybdenum_ug',
    1103: 'selenium_ug',

    # ── Iron Forms (critical for anemia/G6PD) ──
    1141: 'iron_heme_mg',
    1142: 'iron_nonheme_mg',

    # ── Vitamins — Fat Soluble ──
    1106: 'vitamin_a_rae_ug',
    1104: 'vitamin_a_iu',
    1105: 'retinol_ug',
    1107: 'beta_carotene_ug',
    1108: 'alpha_carotene_ug',
    1109: 'vitamin_e_mg',
    1114: 'vitamin_d_ug',
    1110: 'vitamin_d_iu',
    1111: 'vitamin_d2_ug',
    1112: 'vitamin_d3_ug',
    1185: 'vitamin_k_phylloquinone_ug',
    1183: 'vitamin_k_menaquinone4_ug',
    1184: 'vitamin_k_dihydrophylloquinone_ug',

    # ── Vitamins — Water Soluble ──
    1162: 'vitamin_c_mg',
    1165: 'thiamin_mg',
    1166: 'riboflavin_mg',
    1167: 'niacin_mg',
    1170: 'pantothenic_acid_mg',
    1175: 'vitamin_b6_mg',
    1176: 'biotin_ug',
    1177: 'folate_total_ug',
    1186: 'folic_acid_ug',
    1187: 'folate_food_ug',
    1190: 'folate_dfe_ug',
    1178: 'vitamin_b12_ug',

    # ── Choline & Betaine (neuro, liver, methylation) ──
    1180: 'choline_total_mg',
    1194: 'choline_free_mg',
    1195: 'choline_phosphocholine_mg',
    1196: 'choline_phosphatidylcholine_mg',
    1197: 'choline_glycerophosphocholine_mg',
    1199: 'choline_sphingomyelin_mg',
    1198: 'betaine_mg',

    # ── Carotenoids ──
    1120: 'cryptoxanthin_beta_ug',
    1122: 'lycopene_ug',
    1123: 'lutein_zeaxanthin_ug',

    # ── Tocopherols & Tocotrienols (antioxidant defense) ──
    1125: 'tocopherol_beta_mg',
    1126: 'tocopherol_gamma_mg',
    1127: 'tocopherol_delta_mg',
    1128: 'tocotrienol_alpha_mg',
    1129: 'tocotrienol_beta_mg',
    1130: 'tocotrienol_gamma_mg',
    1131: 'tocotrienol_delta_mg',

    # ── Lipids ──
    1253: 'cholesterol_mg',
    1258: 'fatty_acids_saturated_g',
    1292: 'fatty_acids_monounsaturated_g',
    1293: 'fatty_acids_polyunsaturated_g',
    1257: 'fatty_acids_trans_g',

    # ── Key Fatty Acids (omega-3, omega-6 — neuro, inflammation) ──
    1404: 'ala_18_3n3_g',
    1278: 'epa_20_5n3_g',
    1272: 'dha_22_6n3_g',
    1280: 'dpa_22_5n3_g',
    1269: 'linoleic_18_2_g',
    1271: 'arachidonic_20_4_g',
    1270: 'linolenic_18_3_g',

    # ── Saturated Fatty Acid Detail ──
    1259: 'sfa_4_0_g',
    1260: 'sfa_6_0_g',
    1261: 'sfa_8_0_g',
    1262: 'sfa_10_0_g',
    1263: 'sfa_12_0_g',
    1264: 'sfa_14_0_g',
    1265: 'sfa_16_0_g',
    1266: 'sfa_18_0_g',
    1267: 'sfa_20_0_g',
    1273: 'sfa_22_0_g',
    1299: 'sfa_15_0_g',
    1300: 'sfa_17_0_g',
    1301: 'sfa_24_0_g',

    # ── Monounsaturated Detail ──
    1268: 'mufa_18_1_g',
    1275: 'mufa_16_1_g',
    1277: 'mufa_20_1_g',
    1274: 'mufa_14_1_g',
    1279: 'mufa_22_1_g',

    # ── Polyunsaturated Detail ──
    1276: 'pufa_18_4_g',
    1321: 'pufa_18_3n6_g',

    # ── Trans Fat Detail ──
    1329: 'trans_monoenoic_g',
    1304: 'tfa_18_1t_g',

    # ── Amino Acids (dialysis clearance, muscle, neuro) ──
    1210: 'tryptophan_g',
    1211: 'threonine_g',
    1212: 'isoleucine_g',
    1213: 'leucine_g',
    1214: 'lysine_g',
    1215: 'methionine_g',
    1216: 'cystine_g',
    1217: 'phenylalanine_g',
    1218: 'tyrosine_g',
    1219: 'valine_g',
    1220: 'arginine_g',
    1221: 'histidine_g',
    1222: 'alanine_g',
    1223: 'aspartic_acid_g',
    1224: 'glutamic_acid_g',
    1225: 'glycine_g',
    1226: 'proline_g',
    1227: 'serine_g',
    1228: 'hydroxyproline_g',

    # ── Phytosterols ──
    1283: 'phytosterols_mg',

    # ── Caffeine & Theobromine ──
    1057: 'caffeine_mg',
    1058: 'theobromine_mg',

    # ── Isoflavones ──
    1340: 'daidzein_mg',
    1341: 'genistein_mg',
    1342: 'glycitein_mg',
    1343: 'isoflavones_mg',
}

# ══════════════════════════════════════════════════════════════════════════════
# BACKWARD COMPATIBILITY: map new column names → old CSV column names
# so existing unified_nutrition columns get populated too
# ══════════════════════════════════════════════════════════════════════════════
OLD_COL_MAP = {
    'energy_kcal': 'calories',
    'protein_g': 'protein',
    'carbohydrate_g': 'carbs',
    'total_fat_g': 'fat',
    'fiber_total_g': 'fiber',
    'sugars_total_g': 'sugar',
    'sodium_mg': 'sodium',
    'potassium_mg': 'potassium',
    'calcium_mg': 'calcium',
    'iron_mg': 'iron',
    'phosphorus_mg': 'phosphorus',
    'vitamin_d_ug': 'vitamin_d',
    'vitamin_b12_ug': 'vitamin_b12',
    'folate_dfe_ug': 'folic_acid',
    'cholesterol_mg': 'cholesterol',
}

# ══════════════════════════════════════════════════════════════════════════════
# FOOD ALIASES — user vocabulary → USDA-friendly search terms
# Each food is DISTINCT. eba ≠ garri ≠ cassava.
# ══════════════════════════════════════════════════════════════════════════════
# Items to SKIP — not food (restaurant names, activities, artifacts)
SKIP_ITEMS = {
    # Non-food entries
    'medication', 'medicatiom', 'excercise', 'exercise',
    'colonography prep', '#name?', 'nan', '',
    'left overs', 'left over', 'left overs',
    'sandwiches', 'ribbs',
    # Restaurant / source names (no food info when standalone)
    'raf', 'lcm', 'firebird', 'sabai sabai', 'sabai',
    "mosun's kitchen", 'nick knack', 'res', 'ldm restaurant', 'ldm',
    'ldm restuarant', "nando's", 'tous les jours',
    'coastal flats', 'coasta flats', 'hagen daazs',
    'fire', 'rio grande', 'rio', 'poki dc', 'mcdonalds',
    'md', 'sst', 'ihop', 'patagonia', 'don pollo',
    'panera', 'doyin adu', 'sports & social',
    'african resuruarant', 'carnation', 'ttr tom yum',
    'seasons 52 flatbrea', 'mobi dick', 'mdhk',
    'chic file', 'sundry', 'mk', 'fb', 'rak',
    "mosun's kitchen pps", 'perfeit', 'mine',
    # misc non-food
    'finish', 'ghpp', 'o',
    'trader joes', 'african palace', 'baquet', 'mj', 'bags',
    'colonography prep',
}

# ══════════════════════════════════════════════════════════════════════════════
# RECIPE CODES — user's Jan-Feb 2025 shorthand → ingredient expansion
# Each code expands to a description the parser can break into individual items.
# ══════════════════════════════════════════════════════════════════════════════
# Authoritative recipe codes from RecordsN.xlsx FoodLog2025 Column Q → Column S
# Last updated: 2026-02-20
# ══════════════════════════════════════════════════════════════════════════════

RECIPE_CODES = {
    # ── Soups / Stews ──
    'soup01': 'stew(tomatoes, onions, ata rodo, five spices, thyme, knorr cubes, salt, peanut oil, baby goat, beef sirloin, oxtail, chicken)',
    'soup02': 'stew(pasta sauce, beef, oxtail, pork belly, salt, knorr cubes, fried chicken)',
    'soup03': 'soup01 + baked liver + home fried chicken + fresh shrimp + crushed tomatoes',
    'soup04': 'okra(365 okra, baby spinach, dried crayfish, smoked shrimp, fresh shrimp, knorr, salt, fried chicken, olive oil, thyme)',
    'soup05': 'pepper soup(ripe plantain, oxtail, shrimp, thyme, peppersoup mix, salt)',
    'soup06': 'stew(halal oxtail, beef liver, fresh chicken wings, pureed tomatoes, sliced onions, salt, olive oil)',
    'soup07': 'stew(gizzards, oxtail, baby goat, sliced onions, tomatoes, boiled spinach, peppersoup spices)',
    'soup08': 'stew(halal beef liver, gizzards, tomatoes, onions, salt, olive oil)',

    # ── Rice ──
    'rice01': 'long grain white rice, grilled liver, sardines, olive oil, salt',
    'rice02': 'long grain white rice, olive oil, salt',
    'rice03': 'long grain white rice, peanut oil, salt',
    'rice04': 'long grain rice, beans, palm oil, olive oil, peanut oil, gizzards, salt, tomato cherries',
    'rice05': 'jollof rice nigerian rice',
    'rice08': 'long grain white rice, banana, cashew nuts, salt, olive oil',
    'rice08b': 'rice in well cooked halal chicken',  # second rice08 from spreadsheet
    'rice01r4': 'long grain white rice, grilled liver, sardines, olive oil, salt',  # alias for rice01

    # ── Breads ──
    'bread01': 'bread white wheat enriched',
    'bread02': 'brioche bread',
    'bread03': 'brioche bread cinnamon raisin slices',
    'bread04': 'agege bread',
    'bread05': 'brioche bread hot dog bun',

    # ── Proteins / Meats ──
    'bakedm01': 'oven baked beef baby back rib',
    'sausage01': 'chicken sausage cooked',
    'hd01': 'beef hot dog frankfurter',
    'marrow': 'bone marrow cooked',
    'mutton': 'goat meat cooked',

    # ── Eggs ──
    'egg01': 'egg whole hard-boiled',
    'egg02': 'scrambled eggs(diced onions, tomatoes, sardines, olive oil, salt)',
    'egg03': 'egg whole boiled',
    'egg04': 'scrambled eggs(diced onions, tomatoes, sardines, olive oil, kerrygold butter)',
    'egg05': 'omelette(2-3 eggs, onions, sardines, butter, olive oil, salt)',
    'egg06': 'omelette(onions, sardines, cherry tomatoes, olive oil)',
    'omlet01': 'omelette(2 eggs, 1 beef sausage, onions, tomatoes, sardines, peanut oil, salt)',
    'omle': 'omelette(eggs, onions, sardines, olive oil)',  # shorthand used in older food logs

    # ── Drinks ──
    'drink01': 'ribena blackcurrant juice drink',
    'drink02': 'ribena blackcurrant juice, poukha tea, hot water',
    'drink03': 'organic 365 coconut water',
    'drink04': 'iberia mango nectar juice',

    # ── Tea ──
    'tea01': 'twining english breakfast tea, whole milk',
    'tea02': 'lipton tea x2, whole milk, honey',
    'tea03': 'twining english breakfast tea, condensed milk',
    'tea04': 'twining english breakfast tea, green height whole dry powder, honey',

    # ── Snacks ──
    'snack01': 'roasted corn flour',
    'snack02': 'cashew nuts',
    'snack03.01': 'snack pack chocolate pudding',
    'snack03.02': 'snack pack banana cream pie',
    'snack03.03': 'snack pack vanilla flavored pudding',
    'snack04': 'chin chin fried dough snack',
    'snack04.02': 'chin chin fried dough snack',

    # ── Boost / Supplements ──
    'boost01': 'boost plus very vanilla nutritional drink',
    'boost02': 'boost plus rich chocolate nutritional drink',
    'boost03': 'carnation breakfast essential rich chocolate',
    'boost04': 'premier caramel nutritional drink',
    'boost05': 'boost fiber rich chocolate',

    # ── Yoghurt ──
    'yog01': 'organic 365 vanilla whole milk yogurt',

    # ── Fufu / Staples ──
    'fufu01': 'eba garri in hot water cassava flakes',
    'yam01': 'boiled yam, fried eggs, peanut oil, red onions, salt',
    'yam02': 'yam porridge, canned squid, peanut oil',
    'oat01': 'oatmeal cooked in 1.5 cups whole milk + 2 boiled eggs',

    # ── Sandwiches ──
    'sw01': 'bread, kerrygold butter, boiled eggs',
    'sw02': 'sandwich(brioche bread, 1 egg, 2 sausages, kerrygold butter)',
    'sw02.1': 'sandwich(brioche bread, 2 sausages)',

    # ── Fruits ──
    'fruit01': 'lemon',
    'fruit02': 'banana',

    # ── Cereal ──
    'cereal01': '365 peanut butter cocoa cereal balls',

    # ── Cooked items ──
    'cook01': 'crackers wheat',
    'cook02': 'simple mills almond flour crackers',
    'recipe01': 'pan seared chilean seabass, tomatoes, fried plantain, salt, olive oil',

    # ── Plantain ──
    'plt': 'fried plantain',
    'plt.1': 'oven baked ripe plantain slices olive oil',

    # ── LCM (Lancaster Market) items ──
    'lcm01': 'fried chicken',
    'lcm03': 'baked gizzard, baked liver, salt, olive oil',
    'lcm04': 'pretzel, sausage, american cheese',
    'lcm05': 'pretzel, sausage, swiss cheese',
    'lcm06': 'rotisserie chicken',

    # ── Restaurant meals ──
    'rest01': 'sabai thai tom yum soup',
    'rest01.1': 'sabai thai fried rice',
    'rest01.2': 'sabai thai pork',
    'rest02': 'rahama tuwo safi rice flour paste, goat meat',
    'rest02.1': 'rahama ayoyo soup, stew, mutton',
    'rest02.2': 'rahama banku fermented corn dough',
    'rest02.3': 'rahama fried fish',
    'rest02.4': 'rahama bitter leaf soup',
    'rest02.5': 'rahama okra soup',
    'rest03': 'akwaba egusi soup, okra soup, hibiscus juice, pounded yam',
    'rest03.1': 'akwaba egusi soup',
    'rest04': 'chipotle burrito bowl',
    'rest04.1': 'rainbow african omotuo rice balls, jute leaves soup',
    'rest04.2': 'rainbow african red stew, white rice',
    'rest04.3': 'rainbow african fried plantain',
    'rest04.4': 'rainbow african ginger drink',
    'rest04.5': 'rainbow african egusi, jollof rice, fried mutton',
    'rest05.01': 'suburban tilapia grilled',
    'rest05.02': 'suburban herb crusted salmon baked',
    'rest05.03': 'suburban white rice cooked',
    'rest05.04': 'suburban grilled chicken',
    'rest05.05': 'suburban pasta with shrimp',
    'rest05.06': 'suburban tomato basil soup',
    'rest05.07': 'suburban pork sausage',
    'rest05.08': 'suburban chicken sausage',
    'rest05.09': 'suburban biscuit baked',
    'rest05.1': 'carrabbas italian restaurant meal',
    'rest05.10': 'suburban pesto sauce',
    'rest06': 'chipotle(honey chicken, beef, white rice, pinto beans, tomato salsa)',

    # ── Chocolate ──
    'choc': 'chocolate, milk, honey',

    # ── Mutton Tomatoes (compound) ──
    'mutton tomatoes': 'goat meat tomato stew soup',
}

FOOD_ALIASES = {
    # ── Nigerian / West African foods (each is distinct) ──
    'eba': 'cassava dough cooked paste stiff',
    'garri': 'cassava flakes fermented dried granules',
    'cassava': 'cassava raw',
    'fufu': 'plantain yam flour dough pounded',
    'pounded yam': 'yam flour pounded cooked',
    'amala': 'yam flour dried cooked',
    'semovita': 'semolina wheat flour',
    'semo': 'semolina wheat flour',

    # ── Nigerian soups/stews ──
    'ogbonor': 'seeds wild mango dika',
    'ogbono': 'seeds wild mango dika',
    'ogbono soup': 'seeds wild mango dika soup palm oil',
    'ogbonor soup': 'seeds wild mango dika soup palm oil',
    'eforiro': 'spinach stew collard greens palm oil',
    'efo riro': 'spinach stew collard greens palm oil',
    'egusi': 'melon seeds ground',
    'egusi soup': 'melon seeds ground soup palm oil',
    'okro': 'okra cooked',
    'okro soup': 'okra soup cooked',
    'okra soup': 'okra soup cooked',
    'pepper soup': 'soup broth pepper spiced meat',
    'peppersoup': 'soup broth pepper spiced meat',
    'stew': 'tomatoes stew onions peppers oil',
    'jollof rice': 'rice tomato stew cooked',
    'jollof': 'rice tomato stew cooked',
    'nigerian fried rice': 'rice fried vegetables oil mixed',

    # ── Nigerian proteins ──
    'suya': 'beef skewered grilled spiced peanut',
    'moi moi': 'cowpeas steamed cake',
    'moi-moi': 'cowpeas steamed cake',
    'akara': 'cowpeas fritter fried',
    'ponmo': 'cowhide skin boiled',
    'cow tail': 'beef tail oxtail cooked',
    'cow tripe': 'beef tripe cooked',
    'cow kidney': 'beef kidney cooked',
    'cowfeet': 'beef feet cooked stewed',
    'cow feet': 'beef feet cooked stewed',
    'goat meat': 'goat meat cooked roasted',
    'gizzard': 'chicken gizzard cooked simmered',
    'kinni fish': 'fish stockfish dried smoked',
    'kiny fish': 'fish stockfish dried smoked',
    'dried crayfish': 'crustaceans crayfish dried',
    'smoked fish': 'fish smoked',

    # ── Nigerian breads/snacks ──
    'agege bread': 'bread white wheat enriched soft',
    'agege': 'bread white wheat enriched soft',
    'agegge bread': 'bread white wheat enriched soft',
    'agge bread': 'bread white wheat enriched soft',
    'agwge bread': 'bread white wheat enriched soft',
    'chinchin': 'doughnut fried wheat flour sugar',
    'puff puff': 'doughnut fried sweet yeast',
    'meat pie': 'pie meat pastry baked',

    # ── Nigerian drinks ──
    'zobo': 'hibiscus tea drink',
    'kunu': 'millet drink fermented',
    'palm wine': 'wine palm toddy',
    'power malt': 'malt beverage nonalcoholic',
    'malta guiness': 'malt beverage nonalcoholic',
    'malt': 'malt beverage nonalcoholic',
    'acai malt': 'malt beverage nonalcoholic',
    'lucozade': 'carbonated beverage glucose energy drink',

    # ── Nigerian staples ──
    'ewa oloyin': 'beans honey kidney cooked',
    'honey beans': 'beans kidney red cooked',
    'brown beans': 'beans kidney red cooked',
    'plantain': 'plantain raw',
    'plantains': 'plantain raw',
    'dodo': 'plantain ripe fried',
    'fried plantain': 'plantain ripe fried',
    'yam': 'yam cooked boiled drained',
    'boiled yam': 'yam cooked boiled drained',
    'ugwu': 'pumpkin leaves fluted cooked',
    'ata rodo': 'peppers hot chili red raw',
    'shombo': 'peppers sweet red raw',
    'scotch bonnet': 'peppers hot chili red raw',

    # ── Roasted corn flour (RCF — user's custom supplement) ──
    'rcf': 'cornmeal whole-grain yellow',
    'rcf(c)': 'cornmeal whole-grain yellow',
    'roasted corn flour': 'cornmeal whole-grain yellow',

    # ── Common Western foods ──
    'bagel': 'bagels plain enriched',
    'brioche bread': 'bread egg enriched',
    'brioche': 'bread egg enriched',
    'japanese milk bread': 'bread white enriched milk',
    'white bread': 'bread white commercially prepared',
    'wheat bread': 'bread whole-wheat commercially prepared',
    'challah bread': 'bread egg challah',
    'challa bread': 'bread egg challah',
    'naan': 'bread naan whole wheat',
    'tandori': 'bread naan whole wheat',
    'baguette': 'bread french baguette',
    'soft baguette': 'bread french baguette',
    'ramen noodles': 'noodles ramen cooked',
    'ramen': 'noodles ramen cooked',

    # ── Eggs ──
    'boiled egg': 'egg whole hard-boiled',
    'boiled eggs': 'egg whole hard-boiled',
    'fried egg': 'egg whole fried',
    'fried eggs': 'egg whole fried',
    'scrambled eggs': 'egg whole scrambled',
    'scrambled egg': 'egg whole scrambled',
    'eggs': 'egg whole cooked',
    'brown eggs': 'egg whole hard-boiled',

    # ── Dairy ──
    'whole milk': 'milk whole 3.25% fat',
    'milk': 'milk whole 3.25% fat',
    '2% milk': 'milk reduced fat 2%',
    'peak milk': 'milk dry whole',
    'peak powdered milk': 'milk dry whole',
    'kefir': 'milk kefir plain whole',
    'keifer': 'milk kefir plain whole',
    'vanilla kefir': 'milk kefir flavored',
    'yogurt': 'yogurt plain whole milk',
    'yoghurt': 'yogurt plain whole milk',
    'cashewnuts yoghurt': 'yogurt plant-based cashew',
    'cream cheese': 'cheese cream',
    'butter': 'butter unsalted',
    'kuerig butter': 'butter salted',
    'keurig butter': 'butter salted',
    'maple hill butter': 'butter unsalted',

    # ── Beverages ──
    'black tea': 'tea brewed prepared with tap water',
    'lipton black tea': 'tea brewed prepared with tap water',
    'lipton tea': 'tea brewed prepared with tap water',
    'twinning black tea': 'tea brewed prepared with tap water',
    'english breakfast tea': 'tea brewed prepared with tap water',
    'tetley': 'tea brewed prepared with tap water',
    'tetley tea': 'tea brewed prepared with tap water',
    'tea': 'tea brewed prepared with tap water',
    'coffee': 'coffee brewed',
    'orange juice': 'orange juice raw',
    'apple juice': 'apple juice unsweetened',
    'lemonade': 'lemonade prepared',
    'tonic water': 'tonic water',
    'ginger ale': 'ginger ale',
    'coconut water': 'coconut water',
    'pepsi': 'carbonated beverage cola',
    'coke': 'carbonated beverage cola',
    'caprisun': 'fruit juice drink',

    # ── Beverages (additional) ──
    'oj': 'orange juice raw',
    'ribena': 'beverage juice drink blackcurrant',
    'ovaltin': 'beverage cocoa mix powder',
    'ovaltine': 'beverage cocoa mix powder',
    'lucozade': 'carbonated beverage glucose energy drink',
    'milo': 'beverage cocoa mix powder',
    'fanta': 'carbonated beverage orange',

    # ── Nigerian foods (additional) ──
    'ewedu': 'greens turnip cooked boiled jute leaves',
    'ewedu soup': 'greens turnip cooked boiled jute leaves',
    'iyan': 'yam flour pounded cooked',
    'iyan isu': 'yam flour pounded cooked',
    'oxtail': 'beef variety meats oxtail cooked braised',
    'ox tail': 'beef variety meats oxtail cooked braised',
    'maggi': 'soup bouillon cubes dry',
    'knoor': 'soup bouillon cubes dry',
    'knorr': 'soup bouillon cubes dry',
    'tumeric': 'spices turmeric ground',
    'turmeric': 'spices turmeric ground',

    # ── Misc foods (additional) ──
    'wings': 'chicken wing meat and skin roasted',
    'fajita': 'beef fajita seasoned grilled peppers onions',
    'vanila': 'vanilla extract',
    'vanilla': 'vanilla extract',
    'chipotle': 'peppers hot chili red dried',
    'boos': 'nutritional supplement liquid ready to drink',
    'wallnuts': 'nuts walnuts english',
    'walnuts': 'nuts walnuts english',
    'frui': 'fruit salad raw',
    'fruit': 'fruit salad raw',
    'frank': 'frankfurter beef',
    'franks': 'frankfurter beef',
    'te': 'tea brewed prepared with tap water',

    'wallnuts': 'nuts walnuts english',
    'wallnut': 'nuts walnuts english',
    'walnuts': 'nuts walnuts english',

    # ── Nut butters & nuts ──
    'cashew butter': 'cashew butter plain',
    'cashew nuts': 'nuts cashew dry roasted',
    'cashewnuts': 'nuts cashew dry roasted',
    'peanut butter': 'peanut butter smooth',
    'peanuts': 'peanuts all types dry-roasted',
    'roasted peanut': 'peanuts all types dry-roasted',
    'roasted peanuts': 'peanuts all types dry-roasted',

    # ── Oils ──
    'olive oil': 'oil olive salad cooking',
    'sunflower oil': 'oil sunflower linoleic',
    'peanut oil': 'oil peanut salad cooking',
    'palm oil': 'oil palm',
    'coconut oil': 'oil coconut',
    'sesame oil': 'oil sesame salad cooking',

    # ── Proteins: Poultry ──
    'chicken wings': 'chicken wing meat and skin roasted',
    'baked chicken wings': 'chicken wing meat and skin roasted',
    'chicken patties': 'chicken patty breaded cooked',
    'chicken sausages': 'sausage chicken cooked',
    'chicken': 'chicken broiler or fryer breast meat only roasted',
    'rotisserie chicken': 'chicken broiler or fryer meat only roasted',
    'rotisorrie chicken': 'chicken broiler or fryer meat only roasted',
    'grilled chicken': 'chicken broiler or fryer breast meat only roasted',
    'chicken heart': 'chicken heart cooked simmered',
    'turkey wing': 'turkey wing meat and skin roasted',
    'grilled turkey wing': 'turkey wing meat and skin roasted',
    'turkey': 'turkey whole meat and skin roasted',

    # ── Proteins: Red Meat ──
    'beef': 'beef ground 85% lean cooked',
    'mutton': 'lamb shoulder arm whole lean cooked',
    'lamb chop': 'lamb loin chop lean cooked',
    'lamb leg': 'lamb leg whole lean cooked roasted',
    'lamb cutlet': 'lamb loin chop lean cooked',
    'lamb shank': 'lamb shank lean cooked braised',
    'pork chop': 'pork loin chop boneless lean cooked',
    'pork': 'pork loin whole lean cooked',
    'baked pork chop': 'pork loin chop boneless lean cooked',
    'ham': 'ham sliced regular',
    'bacon': 'pork cured bacon cooked',
    'beef hot dog': 'frankfurter beef',
    'cornbeef': 'beef cured corned beef brisket cooked',
    'baby back rib': 'pork spareribs lean cooked braised',
    'beef liver': 'beef liver cooked braised',
    'beef tripe': 'beef tripe cooked',
    'beef skirt': 'beef plate outside skirt steak cooked',

    # ── Proteins: Fish/Seafood ──
    'sardines': 'sardine atlantic canned in oil drained',
    'mackerel': 'fish mackerel atlantic cooked dry heat',
    'grilled mackerel': 'fish mackerel atlantic cooked dry heat',
    'baked whole mackerel': 'fish mackerel atlantic cooked dry heat',
    'cod': 'fish cod atlantic cooked dry heat',
    'tilapia': 'fish tilapia cooked dry heat',
    'salmon': 'fish salmon atlantic cooked dry heat',
    'grilled salmon': 'fish salmon atlantic cooked dry heat',
    'catfish': 'fish catfish channel cooked breaded fried',
    'shrimp': 'crustaceans shrimp mixed species cooked moist heat',
    'shrimps': 'crustaceans shrimp mixed species cooked moist heat',
    'scallops': 'mollusks scallop mixed species cooked',
    'fish': 'fish mixed species cooked dry heat',

    # ── Vegetables ──
    'red onion': 'onions raw',
    'red onions': 'onions raw',
    'onions': 'onions raw',
    'onion': 'onions raw',
    'garlic': 'garlic raw',
    'tomatoes': 'tomatoes red ripe raw',
    'tomato': 'tomatoes red ripe raw',
    'vine tomatoes': 'tomatoes red ripe raw',
    'avocado': 'avocado raw all commercial varieties',
    'avocados': 'avocado raw all commercial varieties',
    'zucchini': 'squash summer zucchini cooked boiled',
    'celery': 'celery raw',
    'lettuce': 'lettuce iceberg raw',
    'cucumber': 'cucumber peeled raw',
    'sweet potato': 'sweet potato cooked baked',
    'baked sweet potato': 'sweet potato cooked baked',
    'potatoes': 'potatoes boiled cooked without skin',
    'baked potatoes': 'potatoes baked flesh and skin',
    'fries': 'potatoes french fried frozen oven-heated',
    'potatoe chips': 'potato chips plain salted',
    'mixed vegetables': 'vegetables mixed frozen cooked',
    'collard green': 'collards cooked boiled drained',
    'collard greens': 'collards cooked boiled drained',
    'bitter leaf': 'greens turnip cooked',
    'bok choi': 'cabbage chinese bok choy cooked',
    'buk choi': 'cabbage chinese bok choy cooked',
    'scallion': 'onions spring or scallions raw',
    'scanlon': 'onions spring or scallions raw',
    'jalapeno pepper': 'peppers jalapeno raw',
    'jallapeno pepper': 'peppers jalapeno raw',
    'yellow pepper': 'peppers sweet yellow raw',
    'ginger': 'ginger root raw',
    'coslaw mix': 'coleslaw home-prepared',
    'coslaw': 'coleslaw home-prepared',
    'italian salad': 'salad vegetable tossed without dressing',

    # ── Fruits ──
    'banana': 'bananas raw',
    'dates': 'dates deglet noor',
    'pitted dates': 'dates deglet noor',
    'strawberries': 'strawberries raw',
    'lemon': 'lemons raw without peel',
    'pumelo': 'grapefruit raw',
    'apple': 'apples raw with skin',
    'pineapple': 'pineapple raw all varieties',
    'peach': 'peaches raw',
    'mango': 'mangos raw',
    'blueberry': 'blueberries raw',

    # ── Grains/Rice ──
    'rice': 'rice white long-grain regular cooked',
    'white rice': 'rice white long-grain regular cooked',
    'basmati rice': 'rice white long-grain regular cooked',
    'long grain rice': 'rice white long-grain regular cooked',
    'long grain white rice': 'rice white long-grain regular cooked',
    'brown rice': 'rice brown long-grain cooked',
    'beans': 'beans kidney red cooked boiled',

    # ── Condiments/Spices ──
    'salt': 'salt table',
    'honey': 'honey',
    'ketchup': 'catsup',
    'mustard': 'mustard prepared yellow',
    'mayonnaise': 'mayonnaise light',
    'mayonaise': 'mayonnaise light',
    'mayonnnaise': 'mayonnaise light',
    'ranch': 'salad dressing ranch regular',
    'salad cream': 'salad dressing mayonnaise light',
    'sauerkraut': 'sauerkraut canned solids and liquids',
    'sourkraut': 'sauerkraut canned solids and liquids',
    'old bay spice': 'spices poultry seasoning',
    'cinnamon': 'spices cinnamon ground',
    'cinamon': 'spices cinnamon ground',

    # ── Supplements/Meal replacements ──
    'boost fiber protein': 'nutritional supplement liquid ready to drink',
    'boost fiber rich chocolate': 'nutritional supplement liquid ready to drink',
    'boost fiber protein rich chocolate': 'nutritional supplement liquid ready to drink',
    'boost fiber chocolate': 'nutritional supplement liquid ready to drink',
    'boost fiber': 'nutritional supplement liquid ready to drink',
    'boost glucose': 'glucose oral supplement',
    'nestle boost': 'nutritional supplement liquid ready to drink',
    'noka smoothie': 'fruit smoothie juice blend',

    # ── Snacks/Cookies ──
    'cookies': 'cookies oatmeal commercially prepared',
    'mcvities': 'cookies shortbread commercially prepared',
    'ginger nuts digestives': 'cookies gingersnaps',
    'allen scotish shortbread': 'cookies shortbread commercially prepared',
    'wafer': 'cookies wafer vanilla',
    'noosa yoghurt lemon': 'yogurt fruit flavored whole milk',
    '365 organic yoghurt': 'yogurt plain whole milk',
    '365 organic strawberr yoghurt': 'yogurt fruit flavored whole milk',

    # ── Fast food ──
    '5 guys': 'hamburger large patty with condiments',
    'bacon burger': 'hamburger large patty with condiments bacon',
    'piza': 'pizza cheese regular crust',
    'pizza': 'pizza cheese regular crust',

    # ── Typo corrections (from unmatched items audit) ──
    'zuchini': 'squash summer zucchini cooked boiled',
    'celleray': 'celery raw',
    'onons': 'onions raw',
    'tomoatoes': 'tomatoes red ripe raw',
    'tomaoes': 'tomatoes red ripe raw',
    'tmatoes': 'tomatoes red ripe raw',
    'pawpaw': 'papaya raw',
    'cofee': 'coffee brewed',
    'smootie': 'yogurt fruit smoothie blend banana',
    'smothie': 'yogurt fruit smoothie blend banana',
    'smmothie': 'yogurt fruit smoothie blend banana',
    'smmothies flakseed': 'yogurt fruit smoothie flaxseed',
    'collard creens': 'collards cooked boiled drained',
    'mellon': 'watermelon raw',
    'muttn': 'lamb shoulder arm whole lean cooked',
    'muton': 'lamb shoulder arm whole lean cooked',
    'focacia sandwtch': 'bread focaccia wheat',
    'focacia': 'bread focaccia wheat',
    'potatoe porridge': 'potatoes boiled cooked vegetables mixed yam',
    'angel hair': 'pasta dry enriched',
    'scanlion': 'onions spring or scallions raw',
    'scanlion)': 'onions spring or scallions raw',
    'scalions': 'onions spring or scallions raw',
    'scalion': 'onions spring or scallions raw',
    'bismatti rice mix': 'rice white long-grain regular cooked',
    'jasmin rice': 'rice white long-grain regular cooked',
    'jasmin': 'rice white jasmine long-grain regular cooked',
    'bismatti': 'rice white long-grain regular cooked basmati',
    'cilntro': 'coriander leaves cilantro raw',
    'cillantro': 'coriander leaves cilantro raw',
    'bannanas': 'bananas raw',
    'lemobade': 'lemonade prepared',
    'lemnade': 'lemonade prepared',
    'lemnade)': 'lemonade prepared',
    'peak mlk': 'milk dry whole',
    'cashews': 'nuts cashew dry roasted',
    'sausages': 'sausage pork cooked',
    'snails': 'snail raw',
    'snals': 'snail raw',
    'peperoni': 'sausage pepperoni pork beef',
    'proscuito': 'ham prosciutto dry cured',
    'poscuto': 'ham prosciutto dry cured',
    'proscuto': 'ham prosciutto dry cured',
    'proschuito': 'ham prosciutto dry cured',
    'rotolini': 'pasta dry enriched rotini',
    'rotlini': 'pasta dry enriched rotini',
    'buger': 'hamburger large patty with condiments',
    'galic': 'garlic raw',
    'buscuit': 'cookies biscuit plain',
    'buiscit': 'cookies biscuit plain',
    'buiscuit': 'cookies biscuit plain',
    'cuccumber': 'cucumber peeled raw',
    'parsely': 'parsley fresh',
    'raddishes': 'radishes raw',
    'spinnach': 'spinach raw',
    'mackrel': 'fish mackerel atlantic cooked dry heat',
    'cowskin': 'cowhide beef skin boiled',
    'cowleg': 'beef feet cooked stewed',
    'cow leg': 'beef feet cooked stewed',
    'german brawturst': 'sausage bratwurst pork cooked',
    'mangello': 'mangos raw',
    'hhoney': 'honey',
    'hney': 'honey',
    'massala': 'spices curry powder',
    'olves': 'olives ripe canned',
    'plantian': 'plantain raw',
    'pease': 'peas green cooked boiled',
    'psylium': 'psyllium husk fiber supplement',
    'satl': 'salt table',
    'tarziki': 'yogurt dip cucumber',
    'caprison': 'fruit juice drink',
    'caprsun': 'fruit juice drink',
    'lucozde': 'carbonated beverage glucose energy drink',
    'sneakers': 'candy bar chocolate milk nougat peanut',
    'sneaker': 'candy bar chocolate milk nougat peanut',
    'snicker': 'candy bar chocolate milk nougat peanut',
    'schwepp': 'carbonated water mineral sparkling',
    'nescaffe': 'coffee instant prepared',
    'nescafe': 'coffee instant prepared',
    'appricot jam': 'jam fruit apricot preserve',
    'challotts': 'shallots raw',
    'scot bonnet': 'peppers hot chili red habanero raw',
    'habenaro': 'peppers hot chili red habanero raw',
    'tortia breads': 'tortilla flour wheat',
    'tortia': 'tortilla flour wheat',
    'sandwitch': 'sandwich bread wheat',
    'beasns': 'beans kidney red cooked boiled',
    'garr': 'cassava flakes fermented dried granules',
    'gizzrd': 'chicken gizzard cooked simmered',
    'chin chin': 'doughnut fried wheat flour sugar',
    'potatoe wedgy': 'potatoes french fried frozen oven-heated wedge',
    'potatoe wdges': 'potatoes french fried frozen oven-heated wedge',
    'poka': 'poke bowl rice fish raw',
    'chcken bullion': 'soup bouillon cubes dry chicken',
    'safeway chcken': 'chicken broiler or fryer meat only roasted',
    'safeway': 'chicken broiler or fryer meat only roasted',
    '1% mlk': 'milk lowfat 1%',
    'cobalt': 'beer lager',
    'petzel': 'pretzels soft',
    'shak': 'milkshake thick vanilla',
    'barbeque': 'sauce barbecue',
    'avocado)': 'avocado raw all commercial varieties',
    'lemon)': 'lemons raw without peel',
    'coconut water)': 'coconut water ready-to-drink',

    # ── Nigerian / West African (additional) ──
    'uziza': 'peppers black pepper spice leaf',
    'efirin': 'basil fresh sweet herbs',
    'aadun': 'cornmeal roasted palm oil sugar snack',
    'luru': 'greens turnip cooked boiled jute leaves',
    'derika': 'peppers dried red cayenne ground',
    'ehiri': 'palm kernel seeds oil',
    'ila asepo': 'okra raw cooked',
    'eru': 'spinach greens wild raw',
    'asun': 'goat meat grilled spiced peppered',
    'ofada': 'rice brown short-grain cooked',
    'ofada rice': 'rice brown short-grain cooked',
    'tuwo': 'rice flour cooked paste thick',
    'dawadawa': 'fermented locust bean condiment bouillon',
    'geisha': 'fish mackerel canned',
    'leek': 'leeks cooked boiled drained',

    # ── Brands / Products ──
    'biscoff': 'cookies speculoos biscuit spiced',
    'rueben': 'sandwich reuben corned beef sauerkraut rye',
    'olipop': 'carbonated beverage prebiotic soda',
    'premier': 'nutritional supplement protein drink',
    'orgain': 'nutritional supplement protein drink organic',
    'jarritos': 'carbonated beverage fruit flavored soda',
    'arnold palmer': 'tea iced lemonade beverage',
    'digestives': 'cookies digestive biscuit wheat',
    'donut': 'doughnut cake type plain',
    'donuts': 'doughnut cake type plain',
    'talenti': 'ice cream gelato',
    'talenti gelato': 'ice cream gelato',
    'horlics': 'beverage malt cocoa mix powder',
    'cornflakes': 'cereals corn flakes',
    'choc': 'chocolate dark',
    'crush': 'carbonated beverage orange',
    'persimon': 'persimmons native raw',
    'peak': 'milk dry whole',
    'meatpie': 'pie meat beef pastry baked',
    'o2 hydration': 'water electrolyte sports drink',
    'lassi': 'yogurt drink cultured',
    "lassi '": 'yogurt drink cultured',
    'booas': 'nutritional supplement liquid ready to drink',
    'noka': 'fruit smoothie juice blend',
    'lobster': 'crustaceans lobster northern cooked moist heat',
    'lobster tail': 'crustaceans lobster northern cooked moist heat',
    'caseroll': 'casserole mixed dish baked',
    'casserol': 'casserole mixed dish baked',
    'porridge': 'oats oatmeal cooked regular',
    'tom yum': 'soup thai spicy shrimp lemongrass',
    'tum yum': 'soup thai spicy shrimp lemongrass',
    'thum youm': 'soup thai spicy shrimp lemongrass',
    'tom yum soup': 'soup thai spicy shrimp lemongrass',
    'barei kebob': 'lamb kebab grilled skewered',
    'kebob': 'lamb kebab grilled skewered',
    'flo mignon': 'beef tenderloin steak cooked broiled',
    'corbia': 'fish cobia cooked dry heat',
    'yogi': 'yogurt plain whole milk',
    'empenada': 'empanada beef meat pastry baked',
    'empenadas': 'empanada beef meat pastry baked',
    'empeneda': 'empanada beef meat pastry baked',
    'dmv empenada': 'empanada beef meat pastry baked',
    'rfc': 'cornmeal whole-grain yellow',
    'ecf': 'cornmeal whole-grain yellow',
    'bistro md': 'restaurant meal mixed',
    'hagen daazs': 'ice cream vanilla',
    'pistacio gelato': 'ice cream gelato pistachio',
    'bismatti wr': 'rice white long-grain regular cooked',

    # ── Short codes (user abbreviations) ──
    'cw': 'chicken wing meat and skin roasted',
    'ts': 'tomatoes stew onions peppers oil',
    'fp': 'plantain ripe fried',
    'bwr': 'rice white long-grain regular cooked basmati',
    'rc': 'cornmeal whole-grain yellow',
    'plt': 'plantain ripe fried',
    'plt.1': 'plantain ripe fried',
    'vy': 'yogurt vanilla flavored whole milk',
    'pps': 'soup broth pepper spiced meat',
    'ccw': 'chicken wing meat and skin roasted',
}

# ══════════════════════════════════════════════════════════════════════════════
# DRUG INTERACTION PROFILES
# Pharmacological effects beyond simple adherence:
#   - Nutrient depletion/loading
#   - Dialysis clearance/buildup
#   - G6PD contraindications
#   - Cross-drug interactions
#   - Electrolyte effects
#   - GI/Neuro side effects
# ══════════════════════════════════════════════════════════════════════════════

DRUG_PROFILES = {
    'epogen': {
        'generic': 'Epoetin alfa',
        'class': 'Erythropoiesis-stimulating agent (ESA)',
        'pathway_effects': ['Lab Results', 'Dialysis Metrics'],
        'nutrient_interactions': {
            'iron_depletion': True,
            'folate_depletion': True,
            'vitamin_b12_depletion': True,
            'potassium_increase': True,
        },
        'dialysis_interaction': 'Given SQ during treatment; dose depends on Hgb/Hct response',
        'g6pd_relevance': 'ESA demands functional RBCs; G6PD deficiency reduces RBC lifespan → blunted response',
        'adverse_effects': ['hypertension', 'thrombosis', 'seizure', 'pure_red_cell_aplasia'],
        'lab_markers': ['hemoglobin', 'hematocrit', 'reticulocyte_count', 'iron', 'ferritin', 'TSAT'],
    },
    'venofer': {
        'generic': 'Iron sucrose',
        'class': 'IV iron supplement',
        'pathway_effects': ['Lab Results', 'Nutrition'],
        'nutrient_interactions': {
            'iron_loading': True,
            'oxidative_stress': True,
        },
        'dialysis_interaction': 'Given IV during dialysis; 50-200 mg per session',
        'g6pd_relevance': 'IV iron generates oxidative stress → hemolysis risk in G6PD-deficient RBCs',
        'adverse_effects': ['hypotension', 'nausea', 'cramping', 'iron_overload', 'anaphylaxis'],
        'lab_markers': ['iron', 'ferritin', 'TSAT', 'TIBC'],
    },
    'sodium_citrate': {
        'generic': 'Sodium citrate (anticoagulant)',
        'class': 'Regional anticoagulant',
        'pathway_effects': ['Dialysis Metrics'],
        'nutrient_interactions': {
            'calcium_chelation': True,
            'magnesium_chelation': True,
            'sodium_loading': True,
            'metabolic_alkalosis': True,
        },
        'dialysis_interaction': 'Regional anticoagulant in circuit; replaces heparin',
        'g6pd_relevance': 'Minimal direct; but hypocalcemia can trigger arrhythmia',
        'adverse_effects': ['hypocalcemia', 'metabolic_alkalosis', 'paresthesia', 'muscle_cramping'],
        'lab_markers': ['calcium', 'ionized_calcium', 'magnesium', 'bicarbonate', 'sodium'],
    },
    'doxercalciferol': {
        'generic': 'Doxercalciferol (Hectorol)',
        'class': 'Vitamin D analog (active)',
        'pathway_effects': ['Lab Results', 'Nutrition'],
        'nutrient_interactions': {
            'calcium_absorption_increase': True,
            'phosphorus_absorption_increase': True,
            'pth_suppression': True,
        },
        'dialysis_interaction': 'Given IV during treatment for secondary hyperparathyroidism',
        'g6pd_relevance': 'Indirect; calcium/phosphorus balance affects bone and RBC membrane stability',
        'adverse_effects': ['hypercalcemia', 'hyperphosphatemia', 'oversuppression_of_PTH', 'soft_tissue_calcification'],
        'lab_markers': ['PTH', 'calcium', 'phosphorus', 'calcium_phosphorus_product', 'vitamin_d'],
    },
    'calcitriol': {
        'generic': 'Calcitriol (1,25-dihydroxyvitamin D3)',
        'class': 'Active vitamin D',
        'pathway_effects': ['Nutrition', 'Lab Results'],
        'nutrient_interactions': {
            'calcium_absorption_increase': True,
            'phosphorus_absorption_increase': True,
            'pth_suppression': True,
            'magnesium_requirements_increase': True,
        },
        'dialysis_interaction': 'Oral; not cleared by dialysis but effects modulate electrolyte balance',
        'g6pd_relevance': 'Vitamin D status affects immune function and bone marrow',
        'adverse_effects': ['hypercalcemia', 'hyperphosphatemia', 'nausea', 'constipation', 'weakness'],
        'lab_markers': ['calcium', 'phosphorus', 'PTH', 'vitamin_d'],
    },
    'calcium_carbonate': {
        'generic': 'Calcium carbonate (TUMS)',
        'class': 'Phosphate binder / Calcium supplement',
        'pathway_effects': ['Nutrition', 'Lab Results'],
        'nutrient_interactions': {
            'phosphorus_binding': True,
            'calcium_loading': True,
            'iron_absorption_inhibit': True,
            'zinc_absorption_inhibit': True,
            'magnesium_absorption_inhibit': True,
            'constipation': True,
        },
        'dialysis_interaction': 'Not dialyzed; taken with meals to bind phosphorus',
        'g6pd_relevance': 'Iron absorption inhibition worsens anemia in G6PD deficiency',
        'adverse_effects': ['hypercalcemia', 'constipation', 'bloating', 'renal_calculi', 'milk_alkali_syndrome'],
        'lab_markers': ['calcium', 'phosphorus', 'calcium_phosphorus_product', 'PTH'],
    },
    'folic_acid': {
        'generic': 'Folic acid (Vitamin B9)',
        'class': 'B-vitamin supplement',
        'pathway_effects': ['Nutrition', 'Lab Results'],
        'nutrient_interactions': {
            'rbc_synthesis': True,
            'homocysteine_lowering': True,
            'b12_masking': True,
        },
        'dialysis_interaction': 'Water-soluble → dialysis clearance; needs daily replacement',
        'g6pd_relevance': 'Critical for RBC production; deficiency compounds G6PD anemia',
        'adverse_effects': ['nausea', 'bloating', 'b12_deficiency_masking'],
        'lab_markers': ['folate', 'homocysteine', 'MCV', 'hemoglobin', 'vitamin_b12'],
    },
    'cetirizine': {
        'generic': 'Cetirizine HCl (Zyrtec)',
        'class': 'H1 antihistamine',
        'pathway_effects': ['Symptoms'],
        'nutrient_interactions': {
            'anticholinergic_gi_effects': True,
        },
        'dialysis_interaction': 'Minimally dialyzable; protein-bound',
        'g6pd_relevance': 'Generally safe in G6PD deficiency',
        'adverse_effects': ['drowsiness', 'dry_mouth', 'constipation', 'urinary_retention'],
        'lab_markers': [],
    },
    'tramadol': {
        'generic': 'Tramadol HCl',
        'class': 'Opioid analgesic (weak)',
        'pathway_effects': ['Symptoms', 'Mental Health'],
        'nutrient_interactions': {
            'gi_disruption': True,
            'serotonin_modulation': True,
            'sodium_hyponatremia_risk': True,
        },
        'dialysis_interaction': 'Partially cleared; active metabolite M1 accumulates in renal failure',
        'g6pd_relevance': 'Generally safe but CNS depression compounds fatigue from anemia',
        'adverse_effects': ['nausea', 'constipation', 'dizziness', 'seizure', 'serotonin_syndrome'],
        'lab_markers': ['sodium'],
    },
    'cyclobenzaprine': {
        'generic': 'Cyclobenzaprine (Flexeril)',
        'class': 'Muscle relaxant (tricyclic)',
        'pathway_effects': ['Symptoms'],
        'nutrient_interactions': {
            'anticholinergic_effects': True,
            'cns_depression': True,
        },
        'dialysis_interaction': 'Not dialyzable; hepatically metabolized',
        'g6pd_relevance': 'No known direct interaction; sedation exacerbates anemia fatigue',
        'adverse_effects': ['drowsiness', 'dry_mouth', 'constipation', 'dizziness', 'tachycardia'],
        'lab_markers': [],
    },
    'ondansetron': {
        'generic': 'Ondansetron (Zofran)',
        'class': '5-HT3 receptor antagonist (antiemetic)',
        'pathway_effects': ['Symptoms', 'Nutrition'],
        'nutrient_interactions': {
            'constipation': True,
            'qt_prolongation': True,
            'magnesium_sensitivity': True,
            'potassium_sensitivity': True,
        },
        'dialysis_interaction': 'Not significantly dialyzed',
        'g6pd_relevance': 'Generally safe; enables nutrition intake by controlling nausea/vomiting',
        'adverse_effects': ['headache', 'constipation', 'qt_prolongation', 'dizziness'],
        'lab_markers': ['magnesium', 'potassium'],
    },
    'diclofenac_topical': {
        'generic': 'Diclofenac sodium (topical gel)',
        'class': 'NSAID (topical)',
        'pathway_effects': ['Symptoms'],
        'nutrient_interactions': {
            'renal_prostaglandin_inhibition': True,
        },
        'dialysis_interaction': 'Topical; negligible systemic absorption',
        'g6pd_relevance': 'Some NSAIDs are oxidative; topical reduces risk vs oral',
        'adverse_effects': ['skin_irritation', 'gi_bleeding_if_systemic'],
        'lab_markers': ['creatinine', 'BUN'],
    },
    'tylenol': {
        'generic': 'Acetaminophen',
        'class': 'Analgesic/Antipyretic',
        'pathway_effects': ['Symptoms'],
        'nutrient_interactions': {
            'glutathione_depletion': True,
            'hepatotoxicity_risk': True,
        },
        'dialysis_interaction': 'Partially dialyzable; metabolites cleared',
        'g6pd_relevance': 'CAUTION: Depletes glutathione → oxidative stress; G6PD patients have reduced glutathione regeneration',
        'adverse_effects': ['hepatotoxicity', 'nephrotoxicity_at_high_doses', 'rash'],
        'lab_markers': ['AST', 'ALT', 'bilirubin'],
    },
    'percocet': {
        'generic': 'Oxycodone/Acetaminophen',
        'class': 'Opioid analgesic + Acetaminophen',
        'pathway_effects': ['Symptoms'],
        'nutrient_interactions': {
            'glutathione_depletion': True,
            'gi_disruption': True,
            'constipation_severe': True,
        },
        'dialysis_interaction': 'Oxycodone partially dialyzable; acetaminophen partially cleared',
        'g6pd_relevance': 'HIGH CONCERN: Acetaminophen depletes glutathione; oxycodone respiratory depression + anemia fatigue',
        'adverse_effects': ['respiratory_depression', 'constipation', 'nausea', 'hepatotoxicity', 'dependence'],
        'lab_markers': ['AST', 'ALT'],
    },
    'docusate': {
        'generic': 'Docusate sodium (Colace)',
        'class': 'Stool softener',
        'pathway_effects': ['Symptoms', 'Nutrition'],
        'nutrient_interactions': {
            'fat_soluble_vitamin_absorption_decrease': True,
            'electrolyte_loss_if_diarrhea': True,
        },
        'dialysis_interaction': 'Not dialyzable; acts locally in GI tract',
        'g6pd_relevance': 'No direct interaction',
        'adverse_effects': ['diarrhea', 'cramping', 'electrolyte_imbalance'],
        'lab_markers': [],
    },
    'methocarbamol': {
        'generic': 'Methocarbamol (Robaxin)',
        'class': 'Muscle relaxant (central acting)',
        'pathway_effects': ['Symptoms'],
        'nutrient_interactions': {
            'cns_depression': True,
            'gi_effects': True,
        },
        'dialysis_interaction': 'Partially dialyzable; dose adjustment may be needed',
        'g6pd_relevance': 'No known direct interaction',
        'adverse_effects': ['drowsiness', 'dizziness', 'nausea', 'blurred_vision'],
        'lab_markers': [],
    },
    'fentanyl': {
        'generic': 'Fentanyl',
        'class': 'Opioid analgesic (potent)',
        'pathway_effects': ['Symptoms'],
        'nutrient_interactions': {
            'severe_gi_disruption': True,
            'respiratory_depression': True,
        },
        'dialysis_interaction': 'Highly protein-bound; not significantly dialyzed',
        'g6pd_relevance': 'Respiratory depression + chronic anemia fatigue = high risk',
        'adverse_effects': ['respiratory_depression', 'constipation', 'nausea', 'sedation', 'dependence'],
        'lab_markers': [],
    },
    'vitamin_d_supplement': {
        'generic': 'Cholecalciferol (Vitamin D3)',
        'class': 'Vitamin D supplement (inactive form)',
        'pathway_effects': ['Nutrition'],
        'nutrient_interactions': {
            'calcium_absorption_increase': True,
            'phosphorus_absorption_increase': True,
        },
        'dialysis_interaction': 'Not dialyzed; fat-soluble',
        'g6pd_relevance': 'Supports immune function and bone marrow health',
        'adverse_effects': ['hypercalcemia_at_high_doses'],
        'lab_markers': ['vitamin_d_25OH', 'calcium', 'phosphorus'],
    },
    'multivitamin': {
        'generic': 'Vitafusion MultiVites',
        'class': 'Multivitamin supplement',
        'pathway_effects': ['Nutrition'],
        'nutrient_interactions': {
            'b_vitamin_replacement': True,
            'vitamin_c': True,
        },
        'dialysis_interaction': 'Water-soluble components cleared each session → daily replacement essential',
        'g6pd_relevance': 'Vitamin C in high doses can be oxidative in G6PD deficiency; standard MVI doses are safe',
        'adverse_effects': ['nausea', 'gi_upset'],
        'lab_markers': ['folate', 'B12', 'vitamin_d'],
    },
    'sodium_carbonate': {
        'generic': 'Sodium bicarbonate',
        'class': 'Alkalinizing agent',
        'pathway_effects': ['Lab Results', 'Dialysis Metrics'],
        'nutrient_interactions': {
            'sodium_loading': True,
            'potassium_lowering': True,
            'calcium_binding': True,
            'metabolic_alkalosis': True,
        },
        'dialysis_interaction': 'Corrects metabolic acidosis between treatments',
        'g6pd_relevance': 'Acidosis correction can improve RBC stability',
        'adverse_effects': ['metabolic_alkalosis', 'sodium_overload', 'edema', 'hypokalemia'],
        'lab_markers': ['bicarbonate', 'CO2', 'sodium', 'potassium'],
    },
    'laxative': {
        'generic': 'Senna/Docusate (stimulant + softener)',
        'class': 'Stimulant laxative',
        'pathway_effects': ['Symptoms', 'Nutrition'],
        'nutrient_interactions': {
            'electrolyte_depletion': True,
            'dehydration_risk': True,
            'fat_soluble_vitamin_loss': True,
        },
        'dialysis_interaction': 'Electrolyte losses compound dialysis clearance',
        'g6pd_relevance': 'Dehydration can concentrate RBCs and trigger hemolytic crisis',
        'adverse_effects': ['cramping', 'diarrhea', 'hypokalemia', 'dehydration'],
        'lab_markers': ['potassium', 'magnesium', 'sodium'],
    },
    'diltiazem_topical': {
        'generic': 'Diltiazem 2% (topical)',
        'class': 'Calcium channel blocker (topical)',
        'pathway_effects': ['Symptoms'],
        'nutrient_interactions': {},
        'dialysis_interaction': 'Topical; negligible systemic absorption',
        'g6pd_relevance': 'No direct interaction',
        'adverse_effects': ['local_irritation'],
        'lab_markers': [],
    },
}


# ══════════════════════════════════════════════════════════════════════════════
# BUILD USDA LOOKUP — ALL NUTRIENTS
# ══════════════════════════════════════════════════════════════════════════════

def build_usda_lookup():
    """Build a flat nutrient-per-food lookup table from ALL USDA nutrients."""
    print("Building USDA nutrient lookup table (ALL nutrients)...")
    food = pd.read_csv(USDA_DIR / 'food.csv')
    fn = pd.read_csv(USDA_DIR / 'food_nutrient.csv')
    portions = pd.read_csv(USDA_DIR / 'food_portion.csv')

    target_ids = set(NUTRIENT_MAP.keys())
    fn_filtered = fn[fn['nutrient_id'].isin(target_ids)][['fdc_id', 'nutrient_id', 'amount']].copy()

    pivot = fn_filtered.pivot_table(
        index='fdc_id', columns='nutrient_id', values='amount', aggfunc='first'
    )

    col_map = {nid: name for nid, name in NUTRIENT_MAP.items() if nid in pivot.columns}
    pivot = pivot.rename(columns=col_map)

    keep_cols = [c for c in NUTRIENT_MAP.values() if c in pivot.columns]
    lookup = pivot[keep_cols].copy()

    lookup = lookup.join(food.set_index('fdc_id')[['description', 'food_category_id']])

    default_portions = portions.groupby('fdc_id')['gram_weight'].first()
    lookup = lookup.join(default_portions)
    lookup['gram_weight'] = lookup['gram_weight'].fillna(100.0)

    lookup = lookup.reset_index()

    os.makedirs(USDA_LOOKUP.parent, exist_ok=True)
    lookup.to_csv(USDA_LOOKUP, index=False)
    print(f"  Built lookup: {len(lookup)} foods x {len(keep_cols)} nutrients")
    print(f"  Saved to {USDA_LOOKUP}")
    return lookup


def build_tfidf_index(lookup):
    """Build TF-IDF index for food description matching."""
    print("Building TF-IDF search index...")
    descriptions = lookup['description'].str.lower().fillna('')
    vectorizer = TfidfVectorizer(
        analyzer='word', ngram_range=(1, 3), max_features=50000,
        stop_words=None, min_df=1,
    )
    tfidf_matrix = vectorizer.fit_transform(descriptions)
    print(f"  TF-IDF matrix: {tfidf_matrix.shape}")
    return vectorizer, tfidf_matrix


# ══════════════════════════════════════════════════════════════════════════════
# MEAL PARSING & MATCHING
# ══════════════════════════════════════════════════════════════════════════════

def parse_meal_items(text):
    """Split a meal description into individual food items."""
    if not isinstance(text, str) or not text.strip():
        return []

    text = text.strip()

    # Strip artifact "nan" prefix from NaN values that became string "nan"
    text = re.sub(r'^nan\s+', '', text, flags=re.I)
    text = text.strip()
    if not text:
        return []

    # Step 1: Split on + (primary meal-component separator)
    parts = re.split(r'\s*\+\s*', text)

    items = []
    for part in parts:
        part = part.strip()
        if not part:
            continue

        # Step 2: Extract main food name, drop parenthetical ingredient lists
        main_match = re.match(r'^([^(]+?)(?:\((.+)\))?$', part)
        if main_match:
            main = main_match.group(1).strip().rstrip(',').strip()
            paren_content = main_match.group(2)

            if paren_content is None and len(main) < 120:
                sub_items = [s.strip() for s in main.split(',')]
                items.extend(sub_items)
            else:
                if main:
                    items.append(main)
                if paren_content:
                    paren_foods = [s.strip() for s in paren_content.split(',')]
                    for pf in paren_foods:
                        pf_lower = pf.strip().lower()
                        if pf_lower in FOOD_ALIASES or len(pf_lower) > 3:
                            skip_words = ['salt', 'pepper', 'spice', 'spices', 'seasoning',
                                          'powder', 'bullion', 'stock', 'mix', 'old bay',
                                          '5 spices', '7 spices', 'poultry mix', 'knorr',
                                          'yaji', 'zartar']
                            if not any(sw == pf_lower or pf_lower.startswith(sw) for sw in skip_words):
                                items.append(pf.strip())
        else:
            items.append(part)

    # Step 3: Split on " and " connector
    expanded = []
    for item in items:
        if ' and ' in item.lower() and len(item) < 80:
            expanded.extend(re.split(r'\s+and\s+', item, flags=re.I))
        else:
            expanded.append(item)

    # Step 4: Clean each item
    clean_items = []
    for item in expanded:
        item = item.strip().strip(',').strip('.').strip()
        if not item or len(item) < 2:
            continue
        # Preserve items that match known aliases before digit-stripping
        if item.lower() not in FOOD_ALIASES:
            item = re.sub(
                r'^\d+\.?\d*\s*(cups?|tablespoons?|teaspoons?|tbsp|tsp|fl\.?\s*oz|oz|'
                r'slices?|pieces?|g|grams?|ml|liters?|lbs?|pounds?|servings?|'
                r'ounces?|handfull?|medium|large|small)\b\s*(of\s+)?',
                '', item, flags=re.I
            )
            item = re.sub(r'^\d+\.?\d*\s+', '', item)
        item = re.sub(r'\s*[@at]+\s*\d+[:\d]*\s*(am|pm)?\s*$', '', item, flags=re.I)
        item = item.strip()
        if item and len(item) >= 2:
            clean_items.append(item)

    # Filter out non-food items (restaurants, activities, artifacts)
    clean_items = [it for it in clean_items if it.lower().strip() not in SKIP_ITEMS]

    # Step 5: Expand recipe codes → ingredient descriptions
    # If an item matches a RECIPE_CODES key, replace it with the expanded ingredients
    final_items = []
    for item in clean_items:
        code = item.lower().strip()
        if code in RECIPE_CODES:
            # Expand the recipe code, then recursively parse the expansion
            expansion = RECIPE_CODES[code]
            sub_items = parse_meal_items(expansion)
            if sub_items:
                final_items.extend(sub_items)
            else:
                final_items.append(expansion)
        else:
            final_items.append(item)

    return final_items


def match_food_item(item_text, vectorizer, tfidf_matrix, lookup, threshold=0.12):
    """Match a single food item to the best USDA entry."""
    item_lower = item_text.lower().strip()

    if item_lower in FOOD_ALIASES:
        search_text = FOOD_ALIASES[item_lower]
    else:
        search_text = item_lower
        for alias, replacement in sorted(FOOD_ALIASES.items(), key=lambda x: -len(x[0])):
            if alias in search_text:
                search_text = search_text.replace(alias, replacement)
                break

    query_vec = vectorizer.transform([search_text.lower()])
    similarities = cosine_similarity(query_vec, tfidf_matrix).flatten()

    best_idx = similarities.argmax()
    best_score = similarities[best_idx]

    if best_score < threshold:
        return None, best_score, ''

    best_food = lookup.iloc[best_idx]
    return best_food, best_score, best_food['description']


def estimate_portion_grams(item_text, default_grams=150.0):
    """Estimate portion size in grams from text context."""
    text = item_text.lower()

    patterns = [
        (r'(\d+\.?\d*)\s*(cups?|c\.)\b', lambda m: float(m.group(1)) * 240),
        (r'(\d+\.?\d*)\s*(tablespoons?|tbsp)\b', lambda m: float(m.group(1)) * 15),
        (r'(\d+\.?\d*)\s*(teaspoons?|tsp)\b', lambda m: float(m.group(1)) * 5),
        (r'(\d+\.?\d*)\s*(fl\.?\s*oz)\b', lambda m: float(m.group(1)) * 30),
        (r'(\d+\.?\d*)\s*(oz|ounces?)\b', lambda m: float(m.group(1)) * 28.35),
        (r'(\d+\.?\d*)\s*(g|grams?)\b', lambda m: float(m.group(1))),
        (r'(\d+\.?\d*)\s*slices?\b', lambda m: float(m.group(1)) * 30),
    ]
    for pat, calc in patterns:
        m = re.search(pat, text)
        if m:
            return calc(m)

    portion_defaults = {
        'eba': 250, 'garri': 50, 'fufu': 250, 'pounded yam': 250,
        'amala': 250, 'semovita': 250, 'semo': 250,
        'rice': 200, 'brown rice': 200, 'jollof': 250,
        'pasta': 200, 'noodle': 200, 'ramen': 200,
        'yam': 200, 'boiled yam': 200, 'sweet potato': 200,
        'plantain': 150, 'dodo': 150,
        'bread': 60, 'agege': 80, 'bagel': 100, 'brioche': 60,
        'baguette': 80, 'naan': 90,
        'fries': 150, 'potato': 150,
        'egg': 50, 'eggs': 100,
        'chicken': 120, 'turkey': 120,
        'beef': 120, 'goat': 120, 'lamb': 120, 'mutton': 120,
        'pork': 120, 'bacon': 30, 'ham': 60,
        'fish': 120, 'mackerel': 150, 'salmon': 120, 'tilapia': 120,
        'sardines': 85, 'shrimp': 85, 'catfish': 120,
        'tripe': 85, 'kidney': 85, 'gizzard': 85, 'liver': 85,
        'cow tail': 100, 'cowfeet': 100, 'ponmo': 80,
        'soup': 200, 'stew': 150, 'sauce': 60,
        'egusi': 200, 'ogbono': 200, 'ogbonor': 200,
        'okro': 200, 'eforiro': 200, 'efo riro': 200,
        'pepper soup': 250, 'peppersoup': 250,
        'porridge': 300,
        'milk': 240, 'whole milk': 240, 'kefir': 240,
        'yogurt': 170, 'yoghurt': 170,
        'juice': 240, 'tea': 240, 'coffee': 240,
        'water': 240, 'tonic': 355,
        'boost': 240, 'malt': 330,
        'oil': 15, 'butter': 14, 'cream cheese': 28,
        'peanut butter': 32, 'cashew butter': 32,
        'salt': 2, 'honey': 21, 'mayo': 15,
        'peanuts': 40, 'cashew': 30,
        'rcf': 30, 'roasted corn flour': 30,
        'beans': 200, 'ewa': 200, 'moi moi': 150,
    }

    for keyword, grams in sorted(portion_defaults.items(), key=lambda x: -len(x[0])):
        if keyword in text:
            return grams

    return default_grams


# ══════════════════════════════════════════════════════════════════════════════
# MAIN ENRICHMENT PIPELINE
# ══════════════════════════════════════════════════════════════════════════════

def enrich_nutrition():
    """Main pipeline: match food logs to USDA and fill ALL nutrient columns."""
    # Build or load USDA lookup
    if USDA_LOOKUP.exists():
        print(f"Loading cached USDA lookup from {USDA_LOOKUP}")
        lookup = pd.read_csv(USDA_LOOKUP)
        meta_cols = {'fdc_id', 'description', 'food_category_id', 'gram_weight'}
        nutrient_cols = [c for c in lookup.columns if c not in meta_cols]
        print(f"  {len(lookup)} foods x {len(nutrient_cols)} nutrients")
    else:
        lookup = build_usda_lookup()
        meta_cols = {'fdc_id', 'description', 'food_category_id', 'gram_weight'}
        nutrient_cols = [c for c in lookup.columns if c not in meta_cols]

    vectorizer, tfidf_matrix = build_tfidf_index(lookup)

    nutr = pd.read_csv(NUTRITION_CSV)
    print(f"\nNutrition data: {len(nutr)} rows")

    # Ensure all nutrient columns exist
    for col in nutrient_cols:
        if col not in nutr.columns:
            nutr[col] = np.nan
    for new_col, old_col in OLD_COL_MAP.items():
        if old_col not in nutr.columns:
            nutr[old_col] = np.nan

    # Identify rows needing enrichment
    food_text = nutr['food_item'].fillna('') + ' ' + nutr['description'].fillna('')
    food_text = food_text.str.strip()
    cal_col = 'calories' if 'calories' in nutr.columns else 'energy_kcal'
    needs_enrichment = nutr[cal_col].isna() & (food_text.str.len() > 3)
    print(f"Rows needing enrichment: {needs_enrichment.sum()}")

    match_log = []
    enriched_count = 0

    for idx in nutr.index[needs_enrichment]:
        row = nutr.loc[idx]
        text = str(row.get('food_item', '') or '') + ' ' + str(row.get('description', '') or '')
        text = text.strip()
        # Strip artifact "nan" prefix at source
        text = re.sub(r'^nan\s+', '', text, flags=re.I).strip()
        if len(text) < 3:
            continue
        # Skip rows that are entirely non-food descriptions
        if text.lower() in SKIP_ITEMS:
            continue

        items = parse_meal_items(text)
        if not items:
            # Only fall back to raw text if it's not a skip item
            if text.lower() not in SKIP_ITEMS:
                items = [text]
            else:
                continue

        meal_nutrients = {col: 0.0 for col in nutrient_cols}
        matched_any = False
        item_matches = []

        for item in items:
            food_match, score, usda_desc = match_food_item(
                item, vectorizer, tfidf_matrix, lookup
            )

            if food_match is not None:
                portion_g = estimate_portion_grams(item)
                scale = portion_g / 100.0

                for col in nutrient_cols:
                    if col in food_match.index and pd.notna(food_match[col]):
                        try:
                            meal_nutrients[col] += float(food_match[col]) * scale
                        except (ValueError, TypeError):
                            pass

                matched_any = True
                item_matches.append({
                    'item': item,
                    'usda_match': usda_desc,
                    'score': round(score, 3),
                    'portion_g': portion_g,
                })
            else:
                item_matches.append({
                    'item': item,
                    'usda_match': 'NO_MATCH',
                    'score': round(score, 3),
                    'portion_g': 0,
                })

        if matched_any:
            for col, val in meal_nutrients.items():
                if val > 0:
                    nutr.at[idx, col] = round(val, 4)
            for new_col, old_col in OLD_COL_MAP.items():
                if new_col in meal_nutrients and meal_nutrients[new_col] > 0:
                    nutr.at[idx, old_col] = round(meal_nutrients[new_col], 2)
            enriched_count += 1

        match_log.append({
            'row_idx': idx,
            'date': row.get('date', ''),
            'original_text': text[:250],
            'n_items': len(items),
            'n_matched': sum(1 for m in item_matches if m['usda_match'] != 'NO_MATCH'),
            'n_unmatched': sum(1 for m in item_matches if m['usda_match'] == 'NO_MATCH'),
            'matches': json.dumps(item_matches),
        })

    # Save enriched nutrition
    nutr.to_csv(OUTPUT_CSV, index=False)
    print(f"\nEnriched {enriched_count} rows -> {OUTPUT_CSV}")

    # Save match log
    os.makedirs(MATCH_LOG.parent, exist_ok=True)
    log_df = pd.DataFrame(match_log)
    log_df.to_csv(MATCH_LOG, index=False)
    print(f"Match log: {MATCH_LOG} ({len(log_df)} entries)")

    # Save drug profiles + nutrient metadata
    with open(NUTRIENT_META, 'w') as f:
        json.dump({
            'nutrient_map': {str(k): v for k, v in NUTRIENT_MAP.items()},
            'old_col_map': OLD_COL_MAP,
            'drug_profiles': DRUG_PROFILES,
            'n_foods_in_lookup': len(lookup),
            'n_nutrients': len(nutrient_cols),
        }, f, indent=2, default=str)
    print(f"Metadata + drug profiles: {NUTRIENT_META}")

    # Coverage comparison
    print(f"\n{'='*70}")
    print(f"COVERAGE COMPARISON (original -> enriched)")
    print(f"{'='*70}")
    orig = pd.read_csv(NUTRITION_CSV)

    key_cols = list(OLD_COL_MAP.values())
    for col in key_cols:
        if col in orig.columns and col in nutr.columns:
            before = orig[col].notna().sum()
            after = nutr[col].notna().sum()
            pct_before = before / len(orig) * 100
            pct_after = after / len(nutr) * 100
            delta = after - before
            print(f"  {col:20s}  {before:>5} ({pct_before:>5.1f}%) -> {after:>5} ({pct_after:>5.1f}%)  +{delta}")

    print(f"\nNEW NUTRIENT COLUMNS (not in original):")
    new_cols = [c for c in nutrient_cols if c not in orig.columns and c not in OLD_COL_MAP]
    for col in sorted(new_cols):
        filled = nutr[col].notna().sum()
        if filled > 0:
            print(f"  {col:45s}  {filled:>5} rows")

    # Unmatched items summary
    all_unmatched = []
    for entry in match_log:
        matches = json.loads(entry['matches'])
        for m in matches:
            if m['usda_match'] == 'NO_MATCH':
                all_unmatched.append(m['item'])

    if all_unmatched:
        from collections import Counter
        unmatched_counts = Counter(item.lower() for item in all_unmatched)
        print(f"\nTOP UNMATCHED ITEMS ({len(unmatched_counts)} unique):")
        for item, count in unmatched_counts.most_common(25):
            print(f"  {count:>4}x  {item}")

    return nutr


if __name__ == '__main__':
    enrich_nutrition()
