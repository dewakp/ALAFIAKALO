"""
NB04 ↔ NB06 Feature Bridge
═══════════════════════════════════════════════════════════

Maps the 284-feature daily space (NB04/NB07) to the 141-feature
session-level space (NB06) so that the What-If simulator and
predict.py can query BOTH model sets from a single input.

The two feature sets have ZERO name overlap because they were
engineered independently with different naming conventions and
different temporal granularity (daily aggregates vs per-session).

Strategy:
  1. Direct semantic mappings (same data, different name)
  2. Computed mappings (NB06 feature derivable from NB04 features)
  3. Unmapped features filled with NB06 training medians
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd


# ═══════════════════════════════════════════════════════════════════════════════
#  Semantic mapping: NB06_feature → NB04_feature (or lambda)
#
#  For each NB06 feature, we specify either:
#    - A string: the NB04 feature name (direct rename)
#    - A tuple ("compute", callable): derived from NB04 features dict
#    - None: no mapping, use NB06 training median
# ═══════════════════════════════════════════════════════════════════════════════

# NB06 feature → NB04 feature (direct renames — same underlying data)
DIRECT_MAP: dict[str, str] = {
    # ── Dialysis vitals ──
    "pre_bp_sys":              "dial_pre_bp_sys",
    "pre_bp_dia":              "dial_pre_bp_dia",
    "post_bp_sys":             "dial_post_bp_sys",
    "post_bp_dia":             "dial_post_bp_dia",
    "pre_pulse":               "dial_intra_pulse_mean",    # closest proxy
    "avg_blood_flow_rate":     "dial_avg_blood_flow_rate",
    "dial_avg_bfr":            "dial_avg_blood_flow_rate",
    "n_readings":              "dial_n_readings",
    "rdg_n_readings":          "dial_n_readings",
    "rdg_bfr_mean":            "dial_avg_blood_flow_rate",
    "weight_loss_kg":          "dial_weight_loss_kg",
    "dial_wt_loss_kg":         "dial_weight_loss_kg",
    "dial_fluid_removed_kg":   "dial_total_uf_kg",
    "today_weight_kg":         "dial_pre_weight",
    "post_weight_kg":          "dial_post_weight",

    # ── Dialysis session details ──
    "rdg_bp_sys_mean":         "dial_pre_bp_sys",        # session mean ≈ pre
    "rdg_bp_dia_mean":         "dial_pre_bp_dia",
    "rdg_bp_sys_std":          "dial_intra_bp_sys_std",
    "rdg_bp_dia_std":          "dial_intra_bp_dia_std",
    "rdg_bp_sys_range":        "dial_intra_bp_sys_range",
    "rdg_pulse_mean":          "dial_intra_pulse_mean",

    # ── Labs (NB06 uses Title case, NB04 uses lower_case) ──
    "lab_Albumin":             "lab_albumin",
    "lab_BUN":                 "lab_bun",
    "lab_CO2":                 "lab_co2",
    "lab_Calcium":             "lab_calcium",
    "lab_CaxP":                "lab_ca_x_po4",
    "lab_Creatinine":          "lab_creatinine_90d",     # no lab_creatinine base, use 90d
    "lab_Ferritin":            "lab_ferritin",
    "lab_Glucose":             "lab_glucose",
    "lab_Hematocrit":          "lab_hematocrit",
    "lab_Hemoglobin":          "lab_hemoglobin",
    "lab_ISAT":                "lab_isat",
    "lab_Iron":                "lab_iron",
    "lab_LDH":                 "lab_ldh",
    "lab_MCV":                 "lab_mcv",
    "lab_PTH":                 "lab_pth",
    # lab_Phosphorus has no NB04 equivalent — use median (NB04 lacks phosphorus base)
    "lab_Potassium":           "lab_potassium",
    "lab_RBC":                 "lab_rbc",
    "lab_RDW":                 "lab_rdw",
    "lab_Reticulocyte":        "lab_reticulocyte",
    "lab_Sodium":              "lab_sodium",
    "lab_WBC":                 "lab_wbc",

    # ── Nutrition (NB06 stores in dg/cg units, NB04 in mg/g — need scale) ──
    # These are direct maps; scaling handled in SCALE_FACTORS below.
    "nutr_calories_today":     "nutr_calories",
    "nutr_protein_today":      "nutr_protein_g",
    "nutr_sodium_today":       "nutr_sodium_mg",
    "nutr_potassium_today":    "nutr_potassium_mg",
    "nutr_phosphorus_today":   "nutr_phosphorus_mg",
    "nutr_calcium_today":      "nutr_calcium_mg",
    "nutr_fat_today":          "nutr_fat_g",
    "nutr_carbs_today":        "nutr_carbs_g",
    "nutr_fiber_today":        "nutr_fiber_g",
    "nutr_iron_today":         "nutr_iron_mg",
    "nutr_sugar_today":        "nutr_sugar_g",
    "nutr_cholesterol_today":  "nutr_cholesterol",

    # 3d averages use today's value as proxy
    "nutr_calories_3d_avg":    "nutr_calories",
    "nutr_protein_3d_avg":     "nutr_protein_g",
    "nutr_sodium_3d_avg":      "nutr_sodium_mg",
    "nutr_potassium_3d_avg":   "nutr_potassium_mg",
    "nutr_phosphorus_3d_avg":  "nutr_phosphorus_mg",
    "nutr_calcium_3d_avg":     "nutr_calcium_mg",
    "nutr_fat_3d_avg":         "nutr_fat_g",
    "nutr_carbs_3d_avg":       "nutr_carbs_g",
    "nutr_fiber_3d_avg":       "nutr_fiber_g",
    "nutr_iron_3d_avg":        "nutr_iron_mg",
    "nutr_sugar_3d_avg":       "nutr_sugar_g",
    "nutr_cholesterol_3d_avg": "nutr_cholesterol",

    # prev-day uses today as proxy (single-day input)
    "nutr_prev_calories":      "nutr_calories",
    "nutr_prev_protein":       "nutr_protein_g",
    "nutr_prev_sodium":        "nutr_sodium_mg",
    "nutr_prev_potassium":     "nutr_potassium_mg",
    "nutr_prev_phosphorus":    "nutr_phosphorus_mg",
    "nutr_prev_calcium":       "nutr_calcium_mg",
    "nutr_prev_fat":           "nutr_fat_g",
    "nutr_prev_carbs":         "nutr_carbs_g",
    "nutr_prev_fiber":         "nutr_fiber_g",
    "nutr_prev_iron":          "nutr_iron_mg",
    "nutr_prev_sugar":         "nutr_sugar_g",
    "nutr_prev_cholesterol":   "nutr_cholesterol",

    # ── Medications (NB06: binary, NB04: dose counts) ──
    "med_count":               "med_doses_today",
    "med_calcitriol":          "med_calcitriol_doses",
    "med_Calcitriol":          "med_calcitriol_doses",
    "med_Calcium Carbonate":   "med_calcium_carbonate_doses",
    "med_Folic Acid":          "med_folic_acid_doses",
    "med_Tramadol":            "med_tramadol_doses",
    "med_Oedesetron":          "med_oedesetron_doses",
    "med_Docusolate":          "med_logged",             # binary proxy
    "med_Sodium Carbonate":    "med_sodium_carbonate_doses",
    "med_Marine Bone Discovery": "med_marine_bone_discovery_doses",
    "med_Cetirizine Hydrochloride": "med_cetirizine_hydrochloride_doses",
    "med_Cyclobenzeprine":     "med_cyclobenzeprine_doses",
    "med_Rugby Stimulant Laxative Plus Stool Softener": "med_rugby_stimulant_laxative__doses",
    "med_any_binder":          "med_calcium_carbonate_doses",  # binder ≈ CaCO3

    # ── Risk flags (NB06 uses HEBCS pathway scores) ──
    # These are HEBCS pathway scores; NB04 has risk_* binary flags
    # Direct map where semantically close
    "pw_Metabolic":            "risk_metabolic_acidosis",     # proxy
    "pw_Hemolytical":          "risk_anemia",                  # proxy
    "pw_Bone_Formation":       "risk_hyperparathyroid",       # proxy

    # ── Vomit/GI — no NB04 equivalent; use medians (both default 0.0) ──

    # ── Temporal ──
    "day_of_week":             "temp_day_of_week",
    "month":                   "temp_month",

    # ── Lag proxies (use current value as estimate for previous session) ──
    "pre_bp_sys_lag1":         "dial_pre_bp_sys",
    "pre_bp_dia_lag1":         "dial_pre_bp_dia",
    "pre_pulse_lag1":          "dial_intra_pulse_mean",
    "weight_loss_kg_lag1":     "dial_weight_loss_kg",

    # ── Heart rate / pulse ──
    "dial_pre_hr":             "dial_intra_pulse_mean",    # closest proxy
    "dial_post_hr":            "dial_intra_pulse_mean",    # closest proxy
    "post_pulse":              "dial_intra_pulse_mean",    # closest proxy

    # ── Activity ──
    "dial_sessions_count":     "dial_sessions_count",
}

# Note: lab_Phosphorus intentionally unmapped — NB04 has no phosphorus base feature.
# Phosphorus (median 4.8 mg/dL) is chemically distinct from potassium (median 4.3 mEq/L).

# ── Scale factors (VERIFIED 2026-02-19) ──
# NB06 stores raw API daily sums (≈ unified_nutrition.csv daily totals).
# NB04 applied a further ~10-30× normalization per-nutrient.
# Ratios below are NB06_nonzero_median / NB04_nonzero_median, computed from
# 591+ NB06 sessions and 1844+ NB04 days with logged nutrition.
# The variation (12–31×) is intrinsic — NB04 normalisation differs per nutrient.
NUTR_SCALE = {
    "nutr_calories_today":      16.4320,
    "nutr_protein_today":       16.0699,
    "nutr_sodium_today":        30.6386,
    "nutr_potassium_today":     14.7644,
    "nutr_phosphorus_today":    21.6878,
    "nutr_calcium_today":       20.6704,
    "nutr_fat_today":           12.0744,
    "nutr_carbs_today":         17.9866,
    "nutr_fiber_today":         13.5980,
    "nutr_iron_today":          15.8495,
    "nutr_sugar_today":         11.0381,
    "nutr_cholesterol_today":   14.4720,
}
# Apply same scales to 3d_avg and prev_ variants
for k, v in list(NUTR_SCALE.items()):
    base = k.replace("_today", "")
    NUTR_SCALE[f"{base}_3d_avg"] = v
    NUTR_SCALE[f"nutr_prev_{base.replace('nutr_', '')}"] = v


# ═══════════════════════════════════════════════════════════════════════════════
#  NB06 Training Medians (fallback for unmapped features)
# ═══════════════════════════════════════════════════════════════════════════════

# These are the median values from the NB06 training set (1,798 sessions).
# Used as defaults when a feature cannot be derived from NB04 inputs.
NB06_MEDIANS: dict[str, float] = {
    "W_additive": 70.5263, "W_product": 66.4762,
    "avg_blood_flow_rate": 290.8029, "bloody_bm_prev": 0.0, "bloody_bm_today": 0.0,
    "day_of_week": 3.0, "days_since_start": 1685.0,
    "dial_K_bath": 1.0, "dial_avg_bfr": 290.8029, "dial_bp_drop": 17.0,
    "dial_bvp_L": 70.0, "dial_dialysate_vol_L": 30.0, "dial_fluid_removed_kg": 1.6,
    "dial_hr_delta": 2.0, "dial_lactate": 45.0, "dial_post_hr": 104.0,
    "dial_post_temp": 98.8, "dial_pre_hr": 101.0, "dial_pre_temp": 98.5,
    "dial_temp_delta": 0.2, "dial_total_dialysate_L": 40.4, "dial_wt_loss_kg": 0.6,
    "lab_Albumin": 4.2, "lab_BUN": 35.5, "lab_CO2": 32.0, "lab_Calcium": 9.5,
    "lab_CaxP": 55.8, "lab_Creatinine": 7.59, "lab_Ferritin": 490.0,
    "lab_Glucose": 134.0, "lab_Hematocrit": 30.45, "lab_Hemoglobin": 10.0,
    "lab_ISAT": 27.0, "lab_Iron": 63.0, "lab_KtV": 1.4733, "lab_LDH": 209.0,
    "lab_MCV": 92.0, "lab_PTH": 2151.0, "lab_Phosphorus": 4.8, "lab_Potassium": 4.3,
    "lab_RBC": 3.35, "lab_RDW": 15.9, "lab_Reticulocyte": 10.7932,
    "lab_Sodium": 137.0, "lab_URR": 60.0, "lab_WBC": 4.0, "lab_nPCR": 0.93,
    "max_bp": 126.0, "mean_bp": 108.4167,
    "med_Calcitriol": 0.0, "med_Calcium Carbonate": 0.0,
    "med_Cetirizine Hydrochloride": 0.0, "med_Cyclobenzeprine": 0.0,
    "med_Docusolate": 0.0, "med_Folic Acid": 0.0,
    "med_Marine Bone Discovery": 0.0, "med_Oedesetron": 0.0,
    "med_Rugby Stimulant Laxative Plus Stool Softener": 0.0,
    "med_Sodium Carbonate": 0.0, "med_Tramadol": 0.0,
    "med_any_binder": 0.0, "med_calcitriol": 0.0, "med_count": 0.0,
    "min_bp": 87.0, "month": 6.0, "n_readings": 9.0,
    "nutr_calcium_3d_avg": 6841.3333, "nutr_calcium_today": 5550.0,
    "nutr_calories_3d_avg": 21658.6667, "nutr_calories_today": 19932.0,
    "nutr_carbs_3d_avg": 2504.85, "nutr_carbs_today": 2275.3,
    "nutr_cholesterol_3d_avg": 4768.6667, "nutr_cholesterol_today": 3618.0,
    "nutr_fat_3d_avg": 729.0667, "nutr_fat_today": 649.0,
    "nutr_fiber_3d_avg": 157.5333, "nutr_fiber_today": 135.3,
    "nutr_iron_3d_avg": 161.8333, "nutr_iron_today": 147.4,
    "nutr_phosphorus_3d_avg": 16868.5, "nutr_phosphorus_today": 14520.0,
    "nutr_potassium_3d_avg": 27129.0, "nutr_potassium_today": 24376.0,
    "nutr_prev_calcium": 5760.0, "nutr_prev_calories": 20841.0,
    "nutr_prev_carbs": 2378.8, "nutr_prev_cholesterol": 3930.0,
    "nutr_prev_fat": 695.6, "nutr_prev_fiber": 144.4,
    "nutr_prev_iron": 161.6, "nutr_prev_phosphorus": 14958.0,
    "nutr_prev_potassium": 25686.0, "nutr_prev_protein": 1034.75,
    "nutr_prev_sodium": 24271.0, "nutr_prev_sugar": 451.0,
    "nutr_protein_3d_avg": 1123.25, "nutr_protein_today": 965.8,
    "nutr_sodium_3d_avg": 26117.0, "nutr_sodium_today": 22596.0,
    "nutr_sugar_3d_avg": 538.1333, "nutr_sugar_today": 420.0,
    "post_bp_dia": 63.0, "post_bp_sys": 100.0, "post_pulse": 104.0,
    "post_weight_kg": 60.25,
    "pre_bp_dia": 79.0, "pre_bp_dia_lag1": 79.0,
    "pre_bp_sys": 120.0, "pre_bp_sys_lag1": 120.0,
    "pre_pulse": 101.0, "pre_pulse_lag1": 101.0,
    "pw_Bone_Formation": 0.6345, "pw_Digestive": 1.0,
    "pw_Endocrinology": 0.6205, "pw_Hemolytical": 0.8802,
    "pw_Immunological": 0.3941, "pw_Metabolic": 0.79, "pw_Neurological": 0.9333,
    "rdg_art_press_mean": 169.0714, "rdg_bfr_mean": 400.0,
    "rdg_bp_dia_mean": 71.0, "rdg_bp_dia_std": 8.779,
    "rdg_bp_sys_max": 126.0, "rdg_bp_sys_mean": 108.4167,
    "rdg_bp_sys_min": 87.0, "rdg_bp_sys_range": 38.0, "rdg_bp_sys_std": 13.3274,
    "rdg_map_mean": 83.7778, "rdg_n_readings": 9.0,
    "rdg_pulse_max": 109.0, "rdg_pulse_mean": 99.8787, "rdg_pulse_std": 6.111,
    "rdg_uf_rate_max": 1.0, "rdg_uf_rate_mean": 0.8, "rdg_ven_press_mean": 128.8452,
    "today_weight_kg": 61.0, "vomit_today": 0.0, "vomit_yesterday": 0.0,
    "weight_loss_kg": 0.6, "weight_loss_kg_lag1": 0.6,
}


# ═══════════════════════════════════════════════════════════════════════════════
#  Computed features (derived from multiple NB04 features)
# ═══════════════════════════════════════════════════════════════════════════════

def _compute_bp_drop(nb04: dict) -> float:
    """dial_bp_drop = pre_bp_sys - post_bp_sys"""
    return nb04.get("dial_pre_bp_sys", 120) - nb04.get("dial_post_bp_sys", 100)

def _compute_max_bp(nb04: dict) -> float:
    return nb04.get("dial_pre_bp_sys", 120)

def _compute_min_bp(nb04: dict) -> float:
    return nb04.get("dial_post_bp_sys", 100)

def _compute_mean_bp(nb04: dict) -> float:
    return (nb04.get("dial_pre_bp_sys", 120) + nb04.get("dial_post_bp_sys", 100)) / 2

def _compute_map_mean(nb04: dict) -> float:
    """MAP = dia + (sys - dia) / 3"""
    s = (nb04.get("dial_pre_bp_sys", 120) + nb04.get("dial_post_bp_sys", 100)) / 2
    d = (nb04.get("dial_pre_bp_dia", 79) + nb04.get("dial_post_bp_dia", 63)) / 2
    return d + (s - d) / 3

def _compute_rdg_bp_sys_max(nb04: dict) -> float:
    return max(nb04.get("dial_pre_bp_sys", 120), nb04.get("dial_post_bp_sys", 100))

def _compute_rdg_bp_sys_min(nb04: dict) -> float:
    return min(nb04.get("dial_pre_bp_sys", 120), nb04.get("dial_post_bp_sys", 100))

COMPUTED_MAP: dict[str, callable] = {
    "dial_bp_drop":    _compute_bp_drop,
    "max_bp":          _compute_max_bp,
    "min_bp":          _compute_min_bp,
    "mean_bp":         _compute_mean_bp,
    "rdg_map_mean":    _compute_map_mean,
    "rdg_bp_sys_max":  _compute_rdg_bp_sys_max,
    "rdg_bp_sys_min":  _compute_rdg_bp_sys_min,
}


# ═══════════════════════════════════════════════════════════════════════════════
#  Bridge function
# ═══════════════════════════════════════════════════════════════════════════════

def bridge_nb04_to_nb06(
    nb04_features: dict[str, float],
    nb06_feature_names: list[str],
) -> dict[str, float]:
    """
    Translate an NB04 (284-feature) dict into an NB06 (141-feature) dict.

    Strategy for each NB06 feature:
      1. If in COMPUTED_MAP → compute from NB04 features
      2. If in DIRECT_MAP and NB04 has the value → use it (with scale factor)
      3. Otherwise → use NB06 training median
    """
    result = {}
    mapped_count = 0
    computed_count = 0
    default_count = 0

    for feat in nb06_feature_names:
        # 1. Computed features
        if feat in COMPUTED_MAP:
            result[feat] = COMPUTED_MAP[feat](nb04_features)
            computed_count += 1
            continue

        # 2. Direct mapping
        if feat in DIRECT_MAP:
            nb04_name = DIRECT_MAP[feat]
            if nb04_name in nb04_features and not np.isnan(nb04_features.get(nb04_name, np.nan)):
                val = nb04_features[nb04_name]
                # Apply nutrition scale factor if needed
                if feat in NUTR_SCALE:
                    val = val * NUTR_SCALE[feat]
                result[feat] = val
                mapped_count += 1
                continue

        # 3. Fallback to NB06 median
        result[feat] = NB06_MEDIANS.get(feat, 0.0)
        default_count += 1

    return result


def get_bridge_stats(nb06_feature_names: list[str]) -> dict:
    """Report how many NB06 features are mapped vs defaulted."""
    mapped = sum(1 for f in nb06_feature_names if f in DIRECT_MAP)
    computed = sum(1 for f in nb06_feature_names if f in COMPUTED_MAP)
    defaulted = len(nb06_feature_names) - mapped - computed
    return {
        "total": len(nb06_feature_names),
        "direct_mapped": mapped,
        "computed": computed,
        "defaulted_to_median": defaulted,
        "coverage_pct": round((mapped + computed) / len(nb06_feature_names) * 100, 1),
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  CLI test
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import json
    # Load NB06 feature names from manifest
    manifest = json.load(open("models/clinical_risk/manifest.json"))
    nb06_names = manifest[list(manifest.keys())[0]]["features"]

    stats = get_bridge_stats(nb06_names)
    print(f"\nBridge Coverage: {stats['coverage_pct']}%")
    print(f"  Direct mapped:     {stats['direct_mapped']}")
    print(f"  Computed:          {stats['computed']}")
    print(f"  Defaulted (median): {stats['defaulted_to_median']}")
    print(f"  Total NB06:        {stats['total']}")

    # Which features are unmapped?
    unmapped = [f for f in nb06_names if f not in DIRECT_MAP and f not in COMPUTED_MAP]
    print(f"\nUnmapped features ({len(unmapped)}):")
    for f in sorted(unmapped):
        print(f"  {f:45s} → median {NB06_MEDIANS.get(f, 0.0)}")
