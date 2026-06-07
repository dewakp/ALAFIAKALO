---
applyTo: "WEB/backend/app/services/meal_parser.py,WEB/backend/app/services/nutrient_estimator.py,WEB/backend/app/services/nlm_food_extractor.py,WEB/backend/app/api/nutrition.py,WEB/backend/app/api/fda_recalls.py"
description: "Nutrition NLM pipeline rules — use when working on meal parsing, nutrient estimation, food extraction, or FDA integration in ALAFIA."
---

# ALAFIA Nutrition NLM Pipeline — Domain Instructions

## Core Contract

Every free-text meal → nutrients path **must** follow this sequence:

```
text → meal_parser.parse_meal_text() → [FoodComponent(food_name, qty_g)]
                    ↓ for each component
     nutrient_estimator.estimate_nutrients(db, food_name)
          → Cache → USDA FDC → AI fallback (per 100 g)
                    ↓
     scale: nutrients × (qty_g / 100)
                    ↓
     aggregate: sum all components → meal totals
```

Never shortcut this chain. The cascade order (Cache → USDA → AI) is mandatory.

## meal_parser.py Rules

- `parse_meal_text(description)` is the only public function; do not expose internals.
- Parenthetical ingredients use type-classified default quantities:
  - seasoning (salt, msg) → ½ tsp (2.85 g)
  - strong spice (ginger, turmeric) → ½ tsp (1.25 g)
  - mild spice (pepper, cumin) → 1 tsp (2.5 g)
  - spread (peanut butter, tahini) → 1 tbsp (16 g)
  - oil → 1 tbsp (14 g)
- New food densities go in `_CUP_DENSITY_G`, `_TSP_DENSITY_G`, `_PIECE_WEIGHTS_G`.
- New default weights go in `_NO_QTY_DEFAULTS_G`.

## nutrient_estimator.py Rules

- The AI system prompt returns **per 100 g** values — never per serving.
- `estimate_meal_nutrients()` delegates parsing to `meal_parser`, do not duplicate parsing logic.
- Cache every USDA and AI result — check `_save_to_cache()`.
- All new AI calls need: `# TODO(alafia-model): replace with ALAFIAModel.NLM`

## nlm_food_extractor.py Rules

- West African / Nigerian food aliases belong in `_ALIAS_MAP`.
- The extractor strips quantities — `meal_parser` handles quantity parsing.
- Do not duplicate `_ALIAS_MAP` in `meal_parser.py`.

## Schema Rules

- New request/response schemas go in `WEB/backend/app/schemas/nutrition.py`.
- `MealEstimateResponse` must always include both `components` and `aggregate_nutrients`.

## Security

- `food_name` is a user-supplied string — normalize with `_normalize_food_name()` before cache lookup.
- Never interpolate `food_name` into SQL directly.
