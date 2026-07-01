# Nutrition Intelligence — believability, locale, learning & goals

Nutrient estimates and clinical goals must be **believable**: in production, an
implausible value (rice at 503 kcal/100 g, a supplement drink at 522 kcal per
serving, a 2500 mg flat potassium cap) causes real harm. This suite replaces
per-food patching with a **generalized, self-correcting, locale-aware** pipeline
that validates input *and* output against known-correct references and **learns**
from corrections. It is guarded by a regression corpus so old failures can't return.

---

## 1. Reference-driven believability (by category, not per-food)

`app/services/nutrition_reference.py` — a small, data-driven KB of food **category
bands**: expected kcal/100 g range, typical serving grams, and plausible unit kinds
per category (grain/cooked, legume, lean/fatty meat, oil, vegetable, fruit,
beverage/water, dairy, nut/seed, prepared dish, …). A keyword classifier
`classify(food_name)` maps a name → category; `expected_kcal_band()`,
`typical_serving_g()`, `plausible_unit_kinds()`, and `kcal_in_band(name, kcal, tol)`
expose the bands. This is what catches a *wrong match by category* generically.

`app/services/plausibility.py`
- `review(food_name, nutrients)` → `(corrected, warnings, believable)`: Atwater
  calorie consistency, macro/sodium/sugar bounds (`MAX_KCAL_100G=902`,
  `SALT_NA_100G=38758`), and the **category-band** check (out-of-band → flag).
- `validate_parse(food_name, qty_g)`: input-side guard — caps an implausible parsed
  portion (a count misread as grams, e.g. "100 of chicken thigh") to
  `max(2000, typical_serving×15)`.

## 2. Self-correcting lookup

`app/services/nutrient_estimator.py` `_estimate_nutrients_impl` resolves a food
through a priority chain and **skips out-of-band candidates**:

1. **Learned** correction (`learned_food_nutrients`) — highest authority.
2. **Curated** dish catalog (§4).
3. **Cache**.
4. **USDA** → 5. **Branded** (MCP: USDA Branded → Open Food Facts) → 6. **AI**.
   Each candidate must pass `_in_band()`; an out-of-band match falls through to the
   next source instead of being returned.
7. If no source fits the band, return the best candidate **flagged low-confidence**
   (`confidence ≤ 0.4`, `out_of_band=True`), **not** cached as authoritative, and
   **logged to the review queue** (§5).

## 3. Authoritative input (trust the label when it's given)

When a user pastes real nutrition facts ("8 fl oz Boost Glucose Control, 190 Cal,
7 g protein, 16 g carb, 7 g fat, 210 mg sodium"), the pipeline must use those values,
not re-estimate. `meal_parser.extract_nutrition_facts(text)` detects explicit facts +
serving size; `estimate_meal_nutrients` short-circuits to them (`source="user_provided"`)
and **persists them to the learning model** (`learned_nutrient_service.record_correction`,
`source="label"`) so a later bare "Boost Glucose Control" resolves to the learned value.

## 4. Curated dishes as data

`app/data/regional_dishes.json` + `app/services/curated_foods.py`: composite/regional
dishes USDA matches poorly (suya, jollof, rice & beans, tomato stew) and generic
beverages/eggs live as **data**. Each entry has a match spec (`all_of` with OR-groups,
`any_of`, or exact-phrase `exact`), a canonical label, a `locale` hint, and a per-100 g
profile. **Add a new dish by editing the JSON — no code change.** (Plain water keeps a
dedicated modifier-aware rule in code.)

## 5. Flagged-estimate review queue (the learning loop)

`app/models/flagged_estimate.py` (`flagged_estimates`, migration `ii001_flagged_estimates`)
+ `app/services/flagged_estimate_service.py`. Every out-of-band miss is logged (deduped
by normalized name, `occurrences` bumped) with the candidate, its kcal, the violated
band, source, and confidence. Admin endpoints (`app/api/nutrition.py`):
- `GET /nutrition/admin/flagged-estimates?include_reviewed=&limit=` — review queue.
- `POST /nutrition/admin/flagged-estimates/{id}/resolve` — mark reviewed and optionally
  **promote** a corrected per-100 g profile into `learned_food_nutrients`.

This closes the loop: implausible outputs become review items become learned corrections.

## 6. Locale sensitivity

- **Food-name aliases** — `app/services/food_aliases.py` `canonicalize(name)` maps
  common non-English / regional terms (Spanish, French, West-African, S./E. Asian) to
  canonical English before USDA lookup (e.g. *arroz con pollo*, *poulet*).
- **Cooking-measure volumes** — `app/services/locale_units.py`: a "cup"/"tbsp"/"tsp"
  differs by locale (US label cup 240 ml, metric 250 ml, AU tablespoon 20 ml).
  `volume_factors(country, preferred_units, locale)` returns scale factors vs the
  parser's 240/15/5 ml baseline. `meal_parser` applies them to cup/tbsp/tsp → grams
  via an async-safe `ContextVar` set by `parse_meal_text(..., vol_factors=...)`.
  `estimate_meal_nutrients(country=, preferred_units=, locale=)` derives them from the
  user (`users.country` / `preferred_units` / `locale`); default = US/label (no change).

## 7. Personalized Daily Nutrient Goals (full profile)

`app/services/nutrient_goals_service.py` `compute_goals` consumes the **whole** profile:
- `fitness_goals` (weight_loss / muscle_gain / endurance / maintenance) → energy ±
  and protein targets.
- `dietary_preferences` (keto / low-carb / mediterranean / high-protein) → macro split.
- `dietary_restrictions` + `allergies` → annotations.
- Condition flags (`detect_condition_flags`) → clinical limits with a **sourced
  rationale** (NIH/DGA/KDOQI). Dialysis potassium is **weight-based** (~40 mg/kg,
  clamped 2000–3000 mg) — not a flat 2500 — per NIH. `notes` carry the rationale.
Call site `app/api/nutrition.py` passes the profile fields through.

## 8. Regression corpus (guard against regressions)

- `tests/test_nutrition_regression.py` (23 cases) — historical failures (water,
  ACV + cold water, rice & beans, suya, Boost, "100 of chicken thigh", banana, jollof,
  tomato stew) + locale cases; asserts believability + kcal ranges + no bad splits.
- `tests/test_nutrient_goals.py` (9 cases) — dialysis K (weight-based), weight-loss
  deficit, keto split, hypertension sodium.
Run the **full** suite green before shipping — see the test-suite note in memory.

---

## Config & operations
- Locale/goals need no toggle. The believability checks are always on.
- The practice-facility geocoder worker is documented in
  `COMMUNITY_HEALTH.md` §5.1 (server-side APScheduler, every 24h).
- Rebuild (no hot reload): `docker compose up -d --build backend`; then
  `docker compose exec backend alembic upgrade head` (revision ids ≤ 32 chars).
