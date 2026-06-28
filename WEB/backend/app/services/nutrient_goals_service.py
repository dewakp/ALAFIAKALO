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

    Accepts any objects/dicts exposing ``category``, ``condition_name`` and
    ``stage`` (e.g. ChronicCondition rows or HealthCondition rows). Matching is
    by category enum value *and* free-text keywords so it works whether the
    diagnosis was structured or typed in.
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
        name = _txt(c, "condition_name")
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
    today: date | None = None,
) -> dict[str, Any]:
    """Return personalized daily nutrient goals.

    Returns a dict: {goals: [...], energy_kcal: float, flags: {...},
    profile_complete: bool}. Each goal: key, name, unit, goal, kind, priority,
    rationale.
    """
    flags = detect_condition_flags(conditions or [])
    age = _calc_age(date_of_birth, today)
    male = _is_male(sex)
    wt = current_weight_kg
    # Protein/needs use actual body weight; fall back to a 70 kg reference adult.
    ref_wt = wt or 70.0

    energy = _energy_target(
        age=age, male=male, height_cm=height_cm, weight_kg=wt,
        target_weight_kg=target_weight_kg, activity=activity_level,
    )
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

    # ── Protein ─────────────────────────────────────────────────────────────
    if flags["dialysis"]:
        add("protein_g", "Protein", "g", 1.1 * ref_wt, "target", 1,
            "Dialysis raises protein needs (KDOQI ~1.0–1.2 g/kg/day).")
    elif flags["ckd"]:
        add("protein_g", "Protein", "g", 0.8 * ref_wt, "limit", 1,
            "Non-dialysis CKD: limit protein (~0.6–0.8 g/kg/day) to ease kidney load.")
    else:
        add("protein_g", "Protein", "g", max(0.8 * ref_wt, 50), "target", 20,
            "RDA ~0.8 g/kg/day for general health.")

    # ── Carbohydrate / Fat (energy distribution) ────────────────────────────
    add("carbs_g", "Carbohydrate", "g", energy * 0.50 / 4, "target", 60,
        "≈50% of calories. " + ("Spread evenly and monitor for diabetes." if flags["diabetes"] else "Primary energy source."))
    add("fat_g", "Total Fat", "g", energy * 0.30 / 9, "target", 70,
        "≈30% of calories (DGA).")

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

    # ── Potassium (target normally, LIMIT for renal) ────────────────────────
    if flags["ckd"]:
        add("potassium_mg", "Potassium", "mg", 2500, "limit", 2,
            "CKD: limit potassium (~2,000–3,000 mg/day) to protect heart rhythm.")
    else:
        add("potassium_mg", "Potassium", "mg", 3400 if male else 2600, "target", 90,
            "Adequate Intake supports healthy blood pressure.")

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
        "profile_complete": profile_complete,
    }
