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

MAX_KCAL_100G = 902.0   # pure fat ≈ 900 kcal/100 g — nothing edible exceeds this
SALT_NA_100G = 38758.0  # sodium in 100 g of table salt — hard ceiling


def _num(v) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def review(food_name: str, nutrients: dict) -> tuple[dict, list[str], bool]:
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

    return n, warnings, believable


def review_meal(total_weight_g: float | None, aggregate: dict) -> list[str]:
    """Sanity-check meal-level aggregates (energy density)."""
    warnings: list[str] = []
    cal = _num((aggregate or {}).get("calories"))
    w = _num(total_weight_g)
    if cal and w and w > 0 and (cal / w * 100.0) > MAX_KCAL_100G:
        warnings.append("meal energy density exceeds pure fat — check portions/items")
    return warnings
