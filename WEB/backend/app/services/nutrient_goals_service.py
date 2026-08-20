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

    def add(key, name, unit, goal, kind, priority, rationale):
        goals.append({
            "key": key, "name": name, "unit": unit,
            "goal": round(float(goal), 1), "kind": kind,
            "priority": priority, "rationale": rationale,
        })

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
    sodium_reason = "Stay under 2,300 mg/day (DGA upper limit)."
    if flags["hypertension"] or flags["heart_failure"]:
        sodium_limit = 1500
        sodium_reason = "Hypertension/heart failure: aim under 1,500 mg/day."
    elif flags["ckd"] or flags["cardiovascular"]:
        sodium_limit = 2000
        sodium_reason = "CKD/cardiovascular: aim under ~2,000 mg/day."
    add("sodium_mg", "Sodium", "mg", sodium_limit, "limit",
        2 if (flags["hypertension"] or flags["ckd"] or flags["heart_failure"]) else 80,
        sodium_reason)

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

    # ── Saturated fat / sugar / cholesterol (limits) ────────────────────────
    add("saturated_fat_g", "Saturated Fat", "g", energy * 0.10 / 9, "limit", 100,
        "Keep under ~10% of calories (DGA).")
    sugar_pct = 0.05 if flags["diabetes"] else 0.10
    add("sugar_g", "Sugars", "g", energy * sugar_pct / 4, "limit",
        10 if flags["diabetes"] else 95,
        ("Diabetes: minimize added sugars (~5% of calories)." if flags["diabetes"]
         else "Keep added sugars under ~10% of calories."))
    chol_limit = 200 if (flags["cardiovascular"] or flags["ckd"]) else 300
    add("cholesterol_mg", "Cholesterol", "mg", chol_limit, "limit", 120,
        f"Keep dietary cholesterol under {chol_limit} mg/day.")

    # ── Calcium / Iron / Vitamin D (targets) ────────────────────────────────
    calcium = 1200 if (age and age >= 50 and not male) or (age and age >= 70) else 1000
    add("calcium_mg", "Calcium", "mg", calcium, "target", 130,
        "Bone health RDA (1,000–1,200 mg/day by age/sex).")
    iron = 18 if (not male and (age is None or age < 51)) else 8
    add("iron_mg", "Iron", "mg", iron, "target", 140,
        "RDA 18 mg (menstruating women) / 8 mg otherwise.")
    vit_d = 800 if (age and age > 70) else 600
    add("vitamin_d_iu", "Vitamin D", "IU", vit_d, "target", 150,
        "RDA 600 IU (≤70 yr) / 800 IU (>70 yr).")

    goals.sort(key=lambda g: g["priority"])
    return {
        "goals": goals,
        "energy_kcal": energy,
        "flags": flags,
        "notes": notes,
        "profile_complete": profile_complete,
    }
