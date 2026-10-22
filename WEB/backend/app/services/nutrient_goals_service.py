# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""Personalized daily nutrient goals.

Computes per-nutrient daily targets and limits from a patient's biology
(age, sex, height, current/target weight, activity level) and active chronic
conditions, grounded in NIH/USDA Dietary Reference Intakes (DRI), the FDA Daily
Values, and standard clinical nutrition guidance for chronic disease.

Each goal is either:
  - kind="target"  → aim to *reach* this amount (e.g. protein, fiber, calcium)
  - kind="limit"   → aim to *stay under* this amount (e.g. sodium, sat-fat,
                     and — for renal patients — potassium and phosphorus)

Condition adjustments are deliberately conservative and education-oriented; they
are NOT a substitute for a renal dietitian's prescription. Key references:
  - KDOQI 2020 clinical practice guideline for nutrition in CKD
  - 2020-2025 Dietary Guidelines for Americans
  - FDA Daily Values (21 CFR 101.9)
"""

from __future__ import annotations

from datetime import date
from typing import Any, Iterable

from app.core.nutrition_data import NUTRIENT_CATALOG
from app.services import free_sugars

#: RDA / FDA Daily Value by nutrient key, read from the same 116-entry catalog
#: the estimator, the diary and the AI tools use. Sourced rather than re-typed:
#: a figure typed here is one that silently disagrees with the catalog the
#: moment either side changes, and this module is already fourteen hand-typed
#: numbers deep.
_CATALOG_RDA: dict[str, Any] = {n["key"]: n.get("rda") for n in NUTRIENT_CATALOG}

# Activity multipliers applied to BMR (Mifflin-St Jeor) → TDEE.
_ACTIVITY_FACTORS = {
    "sedentary": 1.2,
    "lightly_active": 1.375,
    "moderately_active": 1.55,
    "very_active": 1.725,
    "extremely_active": 1.9,
}
_DEFAULT_ENERGY = 2000.0  # FDA reference when biology is incomplete


def _calc_age(dob: str | None, today: date | None = None) -> int | None:
    """Parse a 'YYYY-MM-DD' DOB string into whole years."""
    if not dob:
        return None
    try:
        y, m, d = (int(x) for x in dob[:10].split("-"))
        born = date(y, m, d)
    except (ValueError, TypeError):
        return None
    ref = today or date.today()
    return ref.year - born.year - ((ref.month, ref.day) < (born.month, born.day))


def _is_male(sex: str | None) -> bool:
    return bool(sex) and sex.strip().lower() in ("male", "m", "man")


def detect_condition_flags(conditions: Iterable[Any]) -> dict[str, bool]:
    """Derive dietary-relevant flags from a user's active conditions.

    Accepts any objects/dicts exposing ``category``, ``condition_name``/``name``
    and ``stage`` (e.g. ChronicCondition rows, HealthCondition rows, or the
    canonical ``clinical_sources.ConditionView``). Matching is by category enum
    value *and* free-text keywords so it works whether the diagnosis was
    structured or typed in.

    The ``name`` alias matters: ConditionView — the only sanctioned way to read
    conditions (canon §3aa) — calls the field ``name``. Without the alias a
    caller using the canonical reader detects ``ckd`` from the category but
    never ``dialysis``, which lives in the diagnosis text.
    """
    flags = {
        "ckd": False,        # chronic kidney disease (any stage)
        "dialysis": False,   # on dialysis → higher protein, tight K/PO4
        "diabetes": False,
        "hypertension": False,
        "cardiovascular": False,
        "heart_failure": False,
    }

    def _txt(obj: Any, attr: str) -> str:
        val = obj.get(attr) if isinstance(obj, dict) else getattr(obj, attr, None)
        if val is None:
            return ""
        # Enums → their value
        return str(getattr(val, "value", val)).lower()

    for c in conditions or []:
        name = _txt(c, "condition_name") or _txt(c, "name")
        category = _txt(c, "category")
        stage = _txt(c, "stage")
        notes = _txt(c, "notes")
        blob = " ".join((name, stage, notes))

        if category == "renal" or any(k in blob for k in ("kidney", "renal", "ckd", "nephro", "esrd")):
            flags["ckd"] = True
        if any(k in blob for k in ("dialysis", "hemodialysis", "haemodialysis", "peritoneal", "esrd", "end stage", "end-stage")):
            flags["ckd"] = True
            flags["dialysis"] = True
        if category == "diabetes" or "diabet" in blob:
            flags["diabetes"] = True
        if "hypertension" in blob or "high blood pressure" in blob:
            flags["hypertension"] = True
        if category == "cardiovascular" or any(k in blob for k in ("heart", "cardiac", "coronary", "cardiovascular")):
            flags["cardiovascular"] = True
        if "heart failure" in blob or "chf" in blob:
            flags["heart_failure"] = True

    return flags


def _energy_target(
    *, age: int | None, male: bool, height_cm: float | None,
    weight_kg: float | None, target_weight_kg: float | None, activity: str | None,
) -> float:
    """Mifflin-St Jeor BMR × activity, nudged toward the weight goal."""
    if not (age and height_cm and weight_kg):
        return _DEFAULT_ENERGY
    bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age + (5 if male else -161)
    tdee = bmr * _ACTIVITY_FACTORS.get((activity or "").lower(), 1.2)

    # Steer ±toward target weight: ~500 kcal deficit to lose, ~350 surplus to gain.
    if target_weight_kg:
        if target_weight_kg < weight_kg - 1:
            tdee -= 500
        elif target_weight_kg > weight_kg + 1:
            tdee += 350
    floor = 1500 if male else 1200  # never recommend below a safe floor
    return round(max(tdee, floor))


def compute_goals(
    *,
    date_of_birth: str | None = None,
    sex: str | None = None,
    height_cm: float | None = None,
    current_weight_kg: float | None = None,
    target_weight_kg: float | None = None,
    activity_level: str | None = None,
    conditions: Iterable[Any] | None = None,
    fitness_goals: Iterable[str] | None = None,
    dietary_preferences: Iterable[str] | None = None,
    dietary_restrictions: Iterable[str] | None = None,
    allergies: Iterable[str] | None = None,
    today: date | None = None,
    quotas: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return personalized daily nutrient goals from the user's full profile.

    Returns {goals, energy_kcal, flags, notes, profile_complete}. Each goal:
    key, name, unit, goal, kind, priority, rationale. Conditions take precedence
    over fitness/diet preferences (clinical safety first).
    """
    flags = detect_condition_flags(conditions or [])
    age = _calc_age(date_of_birth, today)
    male = _is_male(sex)
    wt = current_weight_kg
    # Protein/needs use actual body weight; fall back to a 70 kg reference adult.
    ref_wt = wt or 70.0

    def _norm(items):
        return {str(s).strip().lower().replace(" ", "_") for s in (items or []) if s}
    fg, dp, dr, alg = _norm(fitness_goals), _norm(dietary_preferences), _norm(dietary_restrictions), _norm(allergies)
    notes: list[str] = []

    energy = _energy_target(
        age=age, male=male, height_cm=height_cm, weight_kg=wt,
        target_weight_kg=target_weight_kg, activity=activity_level,
    )
    # Fitness-goal energy nudge when an explicit target weight didn't already steer it.
    floor = 1500 if male else 1200
    if not target_weight_kg:
        if fg & {"weight_loss", "lose_weight", "fat_loss"}:
            energy = round(max(energy - 500, floor)); notes.append("Weight-loss goal: ~500 kcal/day deficit.")
        elif fg & {"muscle_gain", "bulk", "gain_weight", "weight_gain"}:
            energy = round(energy + 300); notes.append("Muscle-gain goal: ~300 kcal/day surplus.")

    profile_complete = bool(age and height_cm and wt)

    goals: list[dict[str, Any]] = []

    # A CITED quota from `condition_nutrient_quotas` supersedes the ladder for
    # any nutrient it covers. The override lives inside `add()` rather than
    # beside one branch, so it reaches all thirteen nutrients and every one
    # added later — the point being that this stops being a ladder someone has
    # to extend per condition.
    #
    # `quotas` is passed IN rather than read here. This function is
    # synchronous with eighteen call sites across nutrition, wellness,
    # personalization, the AI tools and the dialysis adjustment; making it
    # async to reach the database would change every nutrition surface at
    # once. A caller holding a session supplies the overrides
    # (`nutrient_quota_service.quotas_for_conditions(...).as_goal_overrides()`);
    # a caller without one gets byte-identical behaviour to before.
    supplied: dict[str, Any] = quotas or {}

    def add(key, name, unit, goal, kind, priority, rationale, authority=None):
        # `authority` names the guideline a LADDER figure came from. It used to
        # be settable only by a cited `condition_nutrient_quotas` row, so every
        # figure typed into this function reached the patient with
        # `authority: None` — indistinguishable from "no guideline claims
        # this", whether it was WHO's own percentage or a number somebody
        # remembered. Saturated fat really is WHO's <10%; dietary cholesterol's
        # 200 mg was not anybody's. A reader could not tell them apart.
        quota = supplied.get(key)
        if quota:
            goal = quota["amount"]
            unit = quota.get("unit") or unit
            kind = quota.get("kind") or kind
            authority = quota.get("source")
            rationale = quota.get("rationale") or rationale
        entry = {
            "key": key, "name": name, "unit": unit,
            "goal": round(float(goal), 1), "kind": kind,
            "priority": priority, "rationale": rationale,
            # Per-goal provenance. None means "this came from the general
            # reference ladder below", which is a different claim from "a
            # guideline says this about your condition" and must be readable
            # apart from it (§3am: a generic RDA must never be handed over as
            # the patient's own target).
            "authority": authority,
        }
        if quota:
            entry["quota"] = {
                "cited_text": quota.get("cited_text"),
                "citation_url": quota.get("citation_url"),
                "evidence_level": quota.get("evidence_level"),
                "includes_supplements": quota.get("includes_supplements"),
                "time_course": quota.get("time_course"),
                "condition_label": quota.get("condition_label"),
                "tension": bool(quota.get("tension")),
            }
        goals.append(entry)

    # ── Energy ──────────────────────────────────────────────────────────────
    add("calories", "Calories", "kcal", energy, "target", 50,
        "Estimated daily energy need (Mifflin-St Jeor × activity"
        + (", adjusted toward your target weight)" if target_weight_kg else ")"))

    # ── Protein (clinical first, then fitness/diet goals) ───────────────────
    if flags["dialysis"]:
        add("protein_g", "Protein", "g", 1.1 * ref_wt, "target", 1,
            "Dialysis raises protein needs (KDOQI ~1.0–1.2 g/kg/day).")
    elif flags["ckd"]:
        add("protein_g", "Protein", "g", 0.8 * ref_wt, "limit", 1,
            "Non-dialysis CKD: limit protein (~0.6–0.8 g/kg/day) to ease kidney load.")
    elif fg & {"muscle_gain", "bulk"} or dp & {"high-protein", "high_protein"}:
        add("protein_g", "Protein", "g", 1.6 * ref_wt, "target", 15,
            "Muscle gain / high-protein goal: ~1.6 g/kg/day (ISSN).")
    elif fg & {"endurance"}:
        add("protein_g", "Protein", "g", 1.4 * ref_wt, "target", 15,
            "Endurance training: ~1.2–1.4 g/kg/day.")
    else:
        add("protein_g", "Protein", "g", max(0.8 * ref_wt, 50), "target", 20,
            "RDA ~0.8 g/kg/day for general health.")

    # ── Carbohydrate / Fat split (diet preference, unless renal already drove it) ──
    carb_pct, fat_pct, split_note = 0.50, 0.30, "≈50% carbs / 30% fat of calories (DGA)."
    if dp & {"keto", "ketogenic"}:
        carb_pct, fat_pct, split_note = 0.05, 0.70, "Ketogenic: ~5% carbs / ~70% fat of calories."
    elif dp & {"low-carb", "low_carb"}:
        carb_pct, fat_pct, split_note = 0.25, 0.45, "Low-carb: ~25% carbs / ~45% fat of calories."
    elif dp & {"mediterranean"}:
        carb_pct, fat_pct, split_note = 0.45, 0.35, "Mediterranean: ~45% carbs / ~35% fat (more unsaturated)."
    if flags["diabetes"]:
        split_note += " Spread carbs evenly and favor low-GI for glucose control."
    add("carbs_g", "Carbohydrate", "g", energy * carb_pct / 4, "target", 60, split_note)
    add("fat_g", "Total Fat", "g", energy * fat_pct / 9, "target", 70, split_note)

    # ── Dietary-restriction / allergy annotations (no fabricated limits) ────
    if dr & {"vegan", "vegetarian"}:
        notes.append("Plant-based: watch vitamin B12, iron, and omega-3 intake.")
    if alg:
        notes.append("Allergies on file: " + ", ".join(sorted(alg)).replace("_", " ") + " — avoid these foods.")

    # ── Fiber ───────────────────────────────────────────────────────────────
    add("fiber_g", "Fiber", "g", max(round(14 * energy / 1000), 25), "target",
        15 if flags["diabetes"] else 40,
        "14 g per 1,000 kcal (DGA); supports glycemic and cardiovascular health.")

    # ── Sodium (limit) ──────────────────────────────────────────────────────
    sodium_limit = 2300
    # Each figure names the body that publishes it. WHO and the FDA do not
    # agree here and the disagreement is stated rather than averaged away:
    # WHO advises under 2,000 mg for everyone, the FDA's Daily Value and the
    # DGA's upper limit are 2,300.
    sodium_reason = ("FDA Daily Value and DGA upper limit: stay under 2,300 "
                     "mg/day. WHO advises under 2,000 mg/day.")
    sodium_authority = "FDA DV (21 CFR 101.9); DGA 2020-2025"
    if flags["hypertension"] or flags["heart_failure"]:
        sodium_limit = 1500
        sodium_reason = ("American Heart Association: an ideal limit of 1,500 "
                         "mg/day for most adults with high blood pressure.")
        sodium_authority = "AHA"
    elif flags["ckd"] or flags["cardiovascular"]:
        sodium_limit = 2000
        sodium_reason = ("WHO: under 2,000 mg/day of sodium (under 5 g of "
                         "salt), the figure WHO applies to all adults.")
        sodium_authority = "WHO sodium intake guideline"
    add("sodium_mg", "Sodium", "mg", sodium_limit, "limit",
        2 if (flags["hypertension"] or flags["ckd"] or flags["heart_failure"]) else 80,
        sodium_reason, authority=sodium_authority)

    # ── Potassium (NIH AI normally; individualized restriction for renal) ────
    # KDOQI 2020 individualizes potassium to keep serum K in range rather than a
    # fixed cap; renal dietetics commonly uses ~40 mg/kg/day, i.e. ~2,000–3,000
    # mg/day. NIH Adequate Intake (general) is 3,400 mg (men) / 2,600 mg (women).
    if flags["dialysis"]:
        pot = max(2000.0, min(3000.0, 40.0 * ref_wt))
        add("potassium_mg", "Potassium", "mg", pot, "limit", 2,
            f"Dialysis: individualized ~40 mg/kg/day (≈{pot:.0f} mg for your weight; KDOQI), "
            "typically 2,000–3,000 mg/day, adjusted to keep serum potassium 3.5–5.5 mmol/L.")
    elif flags["ckd"]:
        pot = max(2000.0, min(3000.0, 40.0 * ref_wt))
        add("potassium_mg", "Potassium", "mg", pot, "limit", 3,
            "CKD: KDOQI individualizes potassium to serum levels — restrict toward "
            "~2,000–3,000 mg/day only if prone to high potassium.")
    else:
        add("potassium_mg", "Potassium", "mg", 3400 if male else 2600, "target", 90,
            "NIH Adequate Intake (3,400 mg men / 2,600 mg women) supports healthy blood pressure.")

    # ── Phosphorus (target normally, LIMIT for renal) ───────────────────────
    if flags["ckd"]:
        add("phosphorus_mg", "Phosphorus", "mg", 900, "limit", 3,
            "CKD: limit phosphorus (~800–1,000 mg/day) to protect bones & vessels.")
    else:
        add("phosphorus_mg", "Phosphorus", "mg", 700, "target", 110,
            "RDA 700 mg/day for adults.")

    # ── Saturated fat / trans fat / sugar / cholesterol (limits) ───────────
    #
    # Saturated fat's FIGURE was already right and its citation was not. WHO's
    # 2023 guideline on saturated and trans-fatty acid intake makes <10% of
    # total energy a STRONG recommendation, and the FDA's 20 g Daily Value is
    # the same figure at 2,000 kcal — the same agreement between the two
    # authorities that the free-sugar limit rests on. It was attributed to the
    # DGA and carried no `authority`, so it was indistinguishable from a number
    # nobody could source.
    add("saturated_fat_g", "Saturated Fat", "g", energy * 0.10 / 9, "limit", 100,
        "WHO (2023): keep saturated fat under 10% of total energy — a strong "
        "recommendation. The FDA's 20 g Daily Value is the same figure at "
        "2,000 kcal.",
        authority="WHO 2023 saturated/trans fatty acid guideline; FDA DV "
                  "(21 CFR 101.9)")

    # ⚠️ TRANS FAT HAD NO LIMIT AT ALL — measured, zero occurrences of
    # `trans_fat` in this module — while WHO's 2023 guideline makes <1% of
    # total energy a STRONG recommendation and the catalog has carried
    # `trans_fat_g` (usda 1257) with `rda: None` the whole time. A nutrient
    # with a published ceiling and no goal is one the patient is never warned
    # about: §3ar's dead control, by omission rather than by a flag nobody
    # reads. This is the gap the operator meant by "every other nutrient".
    add("trans_fat_g", "Trans Fat", "g", energy * 0.01 / 9, "limit", 105,
        "WHO (2023): keep trans fat under 1% of total energy — a strong "
        "recommendation. Industrially-produced trans fat has no known safe "
        "level and WHO calls for its elimination from the food supply.",
        authority="WHO 2023 saturated/trans fatty acid guideline")
    # ── Sugar: the limit charges FREE sugars, which is what WHO legislates ──
    #
    # This line used to quote WHO's free-sugars rule and charge it against
    # `sugar_g` — USDA 2000, TOTAL sugars. WHO's definition expressly excludes
    # the sugars in fresh fruit, vegetables and milk, so a 1,688 kcal diabetic
    # with a 21.1 g allowance had it spent by TWO BANANAS (~30 g of total
    # sugar, 0 g of free sugar). That is the "overestimating sugar values,
    # conflating natural, added and carbs values as sugar" the operator
    # reported on 2026-10-21.
    #
    # `added_sugars_g` was measured as the replacement and cannot carry a
    # limit: USDA serves nutrient 1235 for Branded foods only, so it is absent
    # from every FNDDS and SR Legacy food and read zero on every meal in
    # July, September and October 2026. A limit on it would have reported
    # perfect compliance to a diabetic every day (§3ar).
    #
    # So `free_sugars_g` is DERIVED per food from WHO's and the FDA's own
    # definitions (`services/free_sugars.py`), and a composite dish whose
    # sugars nobody apportions is carried as UNASSESSED rather than as zero.
    add("free_sugars_g", "Free Sugars", "g",
        free_sugars.who_free_sugar_limit_g(energy, diabetes=flags["diabetes"]),
        "limit", 10 if flags["diabetes"] else 95,
        ("Diabetes: WHO's conditional recommendation — keep FREE sugars under "
         "~5% of calories. Free sugars are those added to food plus the sugars "
         "in honey, syrups and fruit juice; the sugars in whole fruit, "
         "vegetables and milk do not count."
         if flags["diabetes"] else
         "WHO: keep FREE sugars under ~10% of calories (the FDA's 50 g "
         "added-sugars Daily Value is the same figure at 2,000 kcal). Free "
         "sugars are those added to food plus the sugars in honey, syrups and "
         "fruit juice; the sugars in whole fruit, vegetables and milk do not "
         "count."),
        # ⚠️ Added 2026-10-22. Yesterday's change wrote WHO all through the
        # rationale and left `authority` None, so the one limit rebuilt around
        # a guideline looked exactly like a number nobody could source. The
        # ratchet below found it; reading the code had not.
        authority="WHO 2015 free sugars guideline; FDA added-sugars DV "
                  "(21 CFR 101.9)")
    # ── Cholesterol: the stricter figure was from a WITHDRAWN guideline ────
    #
    # This read `200 if (cardiovascular or ckd) else 300`, with a rationale
    # that cited nothing at all — "Keep dietary cholesterol under 200 mg/day."
    # Checked against what the authorities actually say now:
    #
    #   DGA   The 2015-2020 Dietary Guidelines REMOVED the 300 mg/day limit
    #         and state that cholesterol is not a nutrient of concern for
    #         overconsumption; 2020-2025 keeps no numeric limit either, only
    #         "eat as little dietary cholesterol as possible".
    #   WHO   sets NO numeric dietary cholesterol limit.
    #   FDA   keeps a 300 mg Daily Value for LABELLING (21 CFR 101.9) — which
    #         is where the 300 came from, not from the DGA it was credited to.
    #   200   was NCEP ATP III's high-risk figure. ATP III was superseded by
    #         the 2013 ACC/AHA cholesterol guideline, which sets no dietary
    #         cholesterol number, and AHA's 2021 dietary guidance sets none.
    #
    # So the condition branch asserted a clinical threshold that no current
    # authority publishes — §3az's exact failure, with the sign reversed: its
    # hardcoded potassium was LOOSER than the patient's real limit, and this
    # was STRICTER than anything anyone could cite. Both are the same defect,
    # a number in the code with nobody behind it.
    #
    # ⚠️ **This LOOSENS the figure for cardiovascular and CKD patients, 200 ->
    # 300 mg.** Said plainly rather than buried, because it is a clinical
    # change: the system now states the FDA's labelling DV and attributes it
    # correctly, instead of a number from a retired guideline. A condition
    # SHOULD be able to tighten it — that is what `condition_nutrient_quotas`
    # is for (§3bc), where a figure arrives with the sentence it came from and
    # supersedes this line through `add()`. Re-introducing it here would be
    # re-introducing the thing this removes.
    add("cholesterol_mg", "Cholesterol", "mg", 300, "limit", 120,
        "The FDA's Daily Value for dietary cholesterol is 300 mg (21 CFR "
        "101.9). Neither WHO nor the current Dietary Guidelines sets a numeric "
        "limit — the DGA removed its 300 mg cap in 2015 and advises keeping "
        "intake as low as possible within a healthy eating pattern.",
        authority="FDA DV (21 CFR 101.9)")

    # ── Calcium / Iron / Vitamin D (targets) ────────────────────────────────
    # ⚠️ This is the GENERAL-POPULATION reference and nothing more. Unlike
    # sodium, potassium, phosphorus and cholesterol, calcium has no condition
    # branch here, and deliberately still does not get one: the guideline
    # answer is not a 16th `if`. For CKD it is 800–1,000 mg/day of TOTAL
    # ELEMENTAL calcium counting calcium-based phosphate binders (KDOQI 2020);
    # for dialysis KDOQI and KDIGO state no figure at all; after a
    # parathyroidectomy with hungry bone syndrome it is 3.2 g/day tapering to
    # 2.4 g; in hypoparathyroidism it is 2–3 g/day with a ≤500 mg per-dose
    # ceiling; and for calcium oxalate stones it must NOT be restricted.
    # Those live in `condition_nutrient_quotas` with the sentence each came
    # from, and arrive through `quotas` above. The rationale says "general" so
    # that a figure nobody scoped to this patient cannot read as one that was.
    calcium = 1200 if (age and age >= 50 and not male) or (age and age >= 70) else 1000
    add("calcium_mg", "Calcium", "mg", calcium, "target", 130,
        "General bone-health RDA (1,000–1,200 mg/day by age/sex) — not scoped "
        "to your conditions. A guideline figure for a diagnosis supersedes it.")
    iron = 18 if (not male and (age is None or age < 51)) else 8
    add("iron_mg", "Iron", "mg", iron, "target", 140,
        "RDA 18 mg (menstruating women) / 8 mg otherwise.")
    vit_d = 800 if (age and age > 70) else 600
    add("vitamin_d_iu", "Vitamin D", "IU", vit_d, "target", 150,
        "RDA 600 IU (≤70 yr) / 800 IU (>70 yr).")

    # ── Magnesium (target) ──────────────────────────────────────────────────
    # This goal was MISSING, and its absence silently discarded real work. The
    # dialysis model computes magnesium transfer on every treatment day — it
    # has a coefficient, a serum field, a bath default and a full gradient
    # calculation — and `apply_to_totals` then dropped the result on the floor,
    # because `GOAL_KEY` maps it to "magnesium_mg" and `by_key.get()` returned
    # None. Worse, `day.modelled` is populated BEFORE that join, so the API
    # reported a magnesium mass in `modelled_mg` and no balance anywhere: a
    # number in one field of the response and nothing in the other.
    #
    # The module even apologises for the opposite case — "No recent blood test
    # for magnesium, so the effect of treatment could not be worked out" — and
    # says nothing when it computes the answer and throws it away (§3aa).
    add("magnesium_mg", "Magnesium", "mg", _CATALOG_RDA.get("magnesium_mg") or 420,
        "target", 145,
        "FDA Daily Value 420 mg/day. Dialysis moves magnesium across the "
        "membrane — out of the blood, or in from the bath, depending on the "
        "dialysate — so the treatment-day balance is what matters here.")

    goals.sort(key=lambda g: g["priority"])
    return {
        "goals": goals,
        "energy_kcal": energy,
        "flags": flags,
        "notes": notes,
        "profile_complete": profile_complete,
    }
