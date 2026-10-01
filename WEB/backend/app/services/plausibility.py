"""Believability guardrail for nutrient analysis (NLM parser + USDA/LLM outputs).

Wrong nutrient data in a health app can cause real harm (e.g. a meal logged at
1,200 kcal that is really 300, or a sodium value off by 100×), so every estimate
is reviewed here before it is persisted or shown. The checks are physiological:

  • non-negativity
  • per-100 g macro bounds (nothing has >100 g of a macro per 100 g)
  • macro sum ≤ 100 g/100 g
  • Atwater energy consistency (kcal ≈ 4·protein + 4·carbs + 9·fat + 7·alcohol)
  • calorie density ≤ ~902 kcal/100 g (pure fat)
  • sub-component sanity (sugar ≤ carbs, saturated ≤ total fat)
  • sodium ≤ pure-salt density

Egregiously impossible values are corrected/clamped; softer inconsistencies are
flagged as warnings. Returns (corrected_nutrients, warnings, believable).
"""
from __future__ import annotations

from app.services import nutrition_reference

MAX_KCAL_100G = 902.0   # pure fat ≈ 900 kcal/100 g — nothing edible exceeds this
SALT_NA_100G = 38758.0  # sodium in 100 g of table salt — hard ceiling


def _num(v) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def review(food_name: str, nutrients: dict,
           category: str | None = None,
           reference_kcal: float | None = None) -> tuple[dict, list[str], bool]:
    """Review a per-100 g nutrient profile. Returns (corrected, warnings, believable)."""
    n = dict(nutrients or {})
    warnings: list[str] = []
    believable = True

    # Non-negativity.
    for k, v in list(n.items()):
        fv = _num(v)
        if fv is not None and fv < 0:
            n[k] = 0.0
            warnings.append(f"{k} was negative → 0")

    protein = _num(n.get("protein_g")) or 0.0
    carbs = _num(n.get("carbs_g")) or 0.0
    fat = _num(n.get("fat_g")) or 0.0
    alcohol = _num(n.get("alcohol_g")) or 0.0
    cal = _num(n.get("calories"))

    # Per-100 g macro ceilings.
    for k in ("protein_g", "carbs_g", "fat_g", "fiber_g", "sugar_g", "saturated_fat_g"):
        v = _num(n.get(k))
        if v is not None and v > 100.0:
            n[k] = 100.0
            warnings.append(f"{k}={v:.0f} g/100g impossible → 100")
            believable = False

    # Sub-component sanity (flag only — don't silently rewrite).
    sugar = _num(n.get("sugar_g"))
    if sugar is not None and sugar > carbs + 0.5:
        warnings.append(f"sugar ({sugar:.0f}) exceeds carbs ({carbs:.0f}) per 100 g")
    satfat = _num(n.get("saturated_fat_g"))
    if satfat is not None and satfat > fat + 0.5:
        warnings.append("saturated fat exceeds total fat")

    # Macro mass can't exceed 100 g per 100 g.
    macro_sum = protein + carbs + fat
    if macro_sum > 100.5:
        warnings.append(f"protein+carbs+fat = {macro_sum:.0f} g/100g (>100)")
        believable = False

    # Atwater energy consistency.
    atwater = 4 * protein + 4 * carbs + 9 * fat + 7 * alcohol
    if cal is None or cal <= 0:
        if atwater > 0:
            n["calories"] = round(atwater, 1)
            warnings.append("calories missing → derived from macros (Atwater)")
    elif cal > MAX_KCAL_100G:
        n["calories"] = MAX_KCAL_100G
        warnings.append(f"calories {cal:.0f}/100g impossible → {MAX_KCAL_100G:.0f}")
        believable = False
    elif atwater > 50 and abs(cal - atwater) > max(60.0, 0.40 * atwater):
        # Calories disagree with the macros by a lot → trust the macros.
        n["calories"] = round(atwater, 1)
        warnings.append(f"calories {cal:.0f} inconsistent with macros (Atwater ≈ {atwater:.0f}) → {atwater:.0f}")
        believable = False

    # Sodium can't exceed pure salt.
    sod = _num(n.get("sodium_mg"))
    if sod is not None and sod > SALT_NA_100G:
        n["sodium_mg"] = SALT_NA_100G
        warnings.append("sodium exceeds pure-salt density → clamped")
        believable = False

    # Category-band check (generalized): does the per-100 g calorie value fit the
    # food's *type*? Catches bad source matches (rice→360 dry, Boost→522/serving,
    # suya→peanut 589) without per-food code. Flag, don't fabricate.
    cal_final = _num(n.get("calories"))
    if cal_final and cal_final > 0:
        # A category RESOLVED from USDA beats one guessed from the name. The
        # keyword fallback is what called "hard boiled eggs" an oil and judged
        # 155 kcal/100 g against 700-902.
        cat = category or nutrition_reference.classify(food_name)
        if reference_kcal:
            # The authority's own figure for THIS food beats a band covering a
            # whole category. Olives at 289 kcal are a correct olive and a
            # failing "vegetable"; judged against USDA's own olive they pass.
            # A wide tolerance still catches a genuinely wrong match (rice at
            # 360 dry, Boost at 522/serving) without punishing a right one.
            lo, hi = reference_kcal * 0.4, reference_kcal * 2.0
        else:
            lo, hi = nutrition_reference.band(cat)["kcal"]
        if cal_final > hi * 1.3 or cal_final < lo * 0.5:
            warnings.append(
                f"{cal_final:.0f} kcal/100g is outside the expected {lo:.0f}–{hi:.0f} "
                f"for '{cat}' foods — likely a wrong match")
            believable = False

    return n, warnings, believable


def validate_parse(food_name: str, qty_g: float) -> tuple[float, list[str]]:
    """Input-side believability: catch an implausibly large parsed portion (usually a
    count misread as grams, e.g. '100 of chicken thigh'). Caps to a category ceiling."""
    warnings: list[str] = []
    q = _num(qty_g) or 0.0
    typ = nutrition_reference.typical_serving_g(food_name)
    ceiling = max(2000.0, typ * 15)
    if q > ceiling:
        warnings.append(
            f"portion {q:.0f} g is implausibly large for '{food_name}' → capped to {ceiling:.0f} g")
        q = ceiling
    return q, warnings


def review_meal(total_weight_g: float | None, aggregate: dict) -> list[str]:
    """Sanity-check meal-level aggregates (energy density)."""
    warnings: list[str] = []
    cal = _num((aggregate or {}).get("calories"))
    w = _num(total_weight_g)
    if cal and w and w > 0 and (cal / w * 100.0) > MAX_KCAL_100G:
        warnings.append("meal energy density exceeds pure fat — check portions/items")
    return warnings


# ── Lab results ──────────────────────────────────────────────────────────────

#: A value this far above its own printed ceiling is worth a human's attention.
#: NOT a smaller multiple, and the figure is measured rather than chosen: on the
#: reference record creatinine reads 11.91 against a 0.7-1.3 range — 9.2x over,
#: and entirely real for a patient on dialysis. Fifteen legitimate creatinines
#: sit between 5x and 9.2x. PTH-I 8,478 against 18-80 is 106x, and the unified
#: importer's own docstring already singles that row out as needing a look.
SUSPECT_RANGE_MULTIPLE = 20.0

#: Proportions cannot exceed the whole. Kept as a WARNING, never a deletion —
#: some assays really do report activity above 100%.
PERCENT_CEILING = 100.0


def _is_percent(unit: str | None) -> bool:
    # Units arrive with the status welded on ("%Final", "InchesFinal") because a
    # narrow unit column absorbs the next one; match the leading symbol.
    return (unit or "").strip().startswith("%")


def review_lab_value(
    test_name: str,
    value: float | None,
    unit: str | None = None,
    ref_low: float | None = None,
    ref_high: float | None = None,
) -> tuple[list[str], bool]:
    """Is this lab value POSSIBLE? Returns (warnings, believable).

    Deliberately NOT "is it abnormal" — that is what `is_abnormal` is for, and
    conflating the two is how a guard ends up shouting about real disease.

    THE ROW THIS EXISTS FOR. A patient's record carried

        HGBX   338.4 %   reference 42 - 52

    and the app rendered it with a green tick. The true value is 38.4 %: the
    analyte is HCT CALC (HGBX3), haematocrit calculated as haemoglobin x 3, and
    that day's haemoglobin was 12.8 — 12.8 x 3 = 38.4 exactly. A literal "3" had
    migrated from the END of the NAME to the FRONT of the VALUE somewhere
    upstream, so the stored figure is exactly 300 too high. Three rows on that
    record carry the same +300 signature, each confirmed against the source PDF.

    We did not invent that number — it arrived that way in a third-party export.
    What we did was accept it without a murmur, and `import_unified_labs.py`
    says so in its own docstring: "Telling them apart needs per-analyte
    plausibility bands ... They are imported and counted in the report so a
    human can look." This is that check, so the human is TOLD rather than
    expected to notice.

    WHY NOT A MULTIPLE OF THE REFERENCE RANGE. Because the range is a
    general-population figure and the patient is not the general population
    (§3an). Creatinine 11.91 against 0.7-1.3 is 9.2x over and is simply what
    end-stage renal disease looks like; a 3x rule would rank fifteen true
    creatinines as more suspicious than an impossible haematocrit.

    NOTHING IS EVER DELETED HERE. `believable=False` means the row must not
    arrive pre-accepted, and must carry its reason. Deleting on a threshold is
    how a real finding is lost (§3am: only what is IMPOSSIBLE gets repaired, and
    even then by a human).
    """
    warnings: list[str] = []
    believable = True
    v = _num(value)
    if v is None:
        return warnings, True

    if _is_percent(unit) and v > PERCENT_CEILING:
        warnings.append(
            f"{v:g}% is above 100% — a proportion cannot exceed the whole. "
            f"Check the value against the report before importing."
        )
        believable = False

    if v < 0:
        warnings.append(f"{v:g} is negative, which no assay reports.")
        believable = False

    hi = _num(ref_high)
    if hi and hi > 0 and v > hi * SUSPECT_RANGE_MULTIPLE:
        warnings.append(
            f"{v:g} is more than {SUSPECT_RANGE_MULTIPLE:g}x the upper reference "
            f"limit of {hi:g} printed on this report — confirm it was read correctly."
        )
        believable = False

    return warnings, believable
