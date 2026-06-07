"""
HEBCS WellnessScore Engine — Python implementation of Wole Akpose's
published trapezoidal/pathway/geometric-mean scoring framework.

Reference: J-BHI 2026, "A Holistic, Evidence-Based Composite Score for
End-Stage Renal Disease" (7-pathway, 9.8-year longitudinal ESRD dataset).

Algorithm:
  1. Per-biomarker: trapezoidal membership function  → score ∈ [0, 1]
  2. Per-pathway:   weighted arithmetic mean          → s_k ∈ [0, 1]
  3. Overall Ω:     weighted geometric mean           → Ω ∈ (0, 1)
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Optional


# ── Biomarker definition ────────────────────────────────────────────────────

@dataclass
class Biomarker:
    name: str          # matches test_name in lab_results
    crit_low: Optional[float]   # a — below this → score 0 (NaN = no lower penalty)
    opt_low: float              # b — below this → linear ramp up
    opt_high: float             # c — above b and ≤ c → score 1
    crit_high: Optional[float]  # d — above this → score 0 (NaN = no upper penalty)
    weight: float = 1.0


@dataclass
class Pathway:
    name: str
    biomarkers: list[Biomarker]
    weight: float = 1.0   # global pathway weight for weighted geometric mean


# ── Trapezoidal membership function ────────────────────────────────────────

def trapezoidal_score(x: float, b: Biomarker) -> float:
    """Map raw biomarker value to [0, 1] via trapezoidal membership.

    Args:
        x: observed biomarker value
        b: Biomarker with (crit_low, opt_low, opt_high, crit_high) thresholds

    Returns:
        Score in [0.0, 1.0].  1.0 = optimal, 0.0 = critical.
    """
    a, lo, hi, d = b.crit_low, b.opt_low, b.opt_high, b.crit_high

    # Below optimal range
    if x <= lo:
        if a is None:
            return 1.0              # no lower penalty
        if x <= a:
            return 0.0
        return (x - a) / (lo - a)  # linear ramp [a → lo]

    # Within optimal window
    if x <= hi:
        return 1.0

    # Above optimal range
    if d is None:
        return 1.0                  # no upper penalty
    if x >= d:
        return 0.0
    return (d - x) / (d - hi)      # linear ramp [hi → d]


# ── Pathway scoring ─────────────────────────────────────────────────────────

def pathway_score(values: dict[str, float], pathway: Pathway) -> Optional[float]:
    """Weighted average of biomarker scores within a pathway.

    Missing biomarkers are excluded gracefully (HEBCS partial-data policy).
    Returns None if no biomarkers have observed values.
    """
    total_w = 0.0
    total_s = 0.0
    for b in pathway.biomarkers:
        if b.name not in values or values[b.name] is None:
            continue
        s = trapezoidal_score(values[b.name], b)
        total_s += b.weight * s
        total_w += b.weight
    if total_w == 0:
        return None
    return total_s / total_w


# ── Overall Ω — weighted geometric mean ─────────────────────────────────────

def omega_score(pathway_scores: dict[str, Optional[float]],
                pathways: list[Pathway]) -> float:
    """Weighted geometric mean of available pathway scores.

    Ω = exp( Σ w_k·ln(s_k) / Σ w_k )   for pathways with scores.
    Clipped to (0.001, 0.999) per open-interval principle.
    """
    log_sum = 0.0
    w_sum = 0.0
    for p in pathways:
        s = pathway_scores.get(p.name)
        if s is None or s <= 0:
            continue
        log_sum += p.weight * math.log(max(s, 1e-6))
        w_sum += p.weight
    if w_sum == 0:
        return 0.5
    raw = math.exp(log_sum / w_sum)
    return max(0.001, min(0.999, raw))


# ── ESRD / HEBCS 7-Pathway Definition ──────────────────────────────────────
#
# Weights from the J-BHI 2026 paper (Table 3):
#   Metabolic 0.20 | Hematologic 0.15 | Bone_Mineral 0.15
#   Cardiovascular 0.15 | Nutritional 0.15 | Dialysis_Adequacy 0.10
#   Inflammatory 0.10
#
# Biomarker thresholds derived from appendixD.tex / pathway_definitions_15.m
# and KDIGO/NKF-KDOQI 2023 guidelines for ESRD.

ESRD_PATHWAYS: list[Pathway] = [

    Pathway(name="Metabolic", weight=0.20, biomarkers=[
        Biomarker("Glucose",    crit_low=40,  opt_low=70,  opt_high=130, crit_high=300,  weight=0.30),
        Biomarker("Sodium",     crit_low=120, opt_low=136, opt_high=145, crit_high=160,  weight=0.25),
        Biomarker("Potassium",  crit_low=2.5, opt_low=3.5, opt_high=5.5, crit_high=6.5, weight=0.25),
        # Bicarbonate — ESRD patients often mildly elevated (bicarbonate loading)
        Biomarker("CO2 (Bicarbonate)", crit_low=15, opt_low=22, opt_high=29, crit_high=35, weight=0.20),
    ]),

    Pathway(name="Hematologic", weight=0.15, biomarkers=[
        Biomarker("Hemoglobin",          crit_low=7.0, opt_low=10.0, opt_high=12.0, crit_high=17.5, weight=0.30),
        Biomarker("Hematocrit",          crit_low=21,  opt_low=30,   opt_high=36,   crit_high=52,   weight=0.20),
        Biomarker("RBC",                 crit_low=2.0, opt_low=3.0,  opt_high=4.5,  crit_high=6.0,  weight=0.15),
        Biomarker("MCV",                 crit_low=60,  opt_low=80,   opt_high=96,   crit_high=115,  weight=0.10),
        Biomarker("RDW",                 crit_low=None,opt_low=0,    opt_high=14.5, crit_high=20,   weight=0.10),
        Biomarker("Ferritin",            crit_low=10,  opt_low=200,  opt_high=800,  crit_high=2000, weight=0.15),
        # TSAT target for HD: 20-50%
        Biomarker("Iron Saturation (TSAT)", crit_low=5, opt_low=20, opt_high=50, crit_high=80, weight=0.20),
        Biomarker("WBC",                 crit_low=2.0, opt_low=4.5, opt_high=11.0, crit_high=30,   weight=0.10),
        Biomarker("LDH",                 crit_low=None,opt_low=0,   opt_high=280,  crit_high=600,  weight=0.10),
    ]),

    Pathway(name="Bone_Mineral", weight=0.15, biomarkers=[
        # PTH target for ESRD stage 5D: 150–600 pg/mL (KDIGO).
        # crit_low=15: PTH < 15 → adynamic bone disease (score 0); 15–150 → linear ramp.
        Biomarker("PTH (Intact)",  crit_low=15,   opt_low=150,  opt_high=600,  crit_high=3000, weight=0.40),
        # Phosphorus KDIGO target: 3.5–5.5 mg/dL (ESRD relaxed)
        Biomarker("Phosphorus",    crit_low=1.5,  opt_low=3.5,  opt_high=5.5,  crit_high=9.0,  weight=0.30),
        # Calcium
        Biomarker("Calcium",       crit_low=6.5,  opt_low=8.5,  opt_high=10.0, crit_high=12.0, weight=0.20),
        # CaxP product target: <55 mg²/dL²
        Biomarker("CaxP Product",  crit_low=None, opt_low=0,    opt_high=55.0, crit_high=80.0, weight=0.10),
    ]),

    Pathway(name="Cardiovascular", weight=0.15, biomarkers=[
        Biomarker("Iron (Serum)",  crit_low=10, opt_low=60,  opt_high=170, crit_high=300, weight=0.30),
        # LDH as indirect proxy for hemolysis/cardiac stress in ESRD
        # (Separated since LDH is already in Hematologic)
        # Use Albumin as indirect CV marker (hypoalbuminemia ↑ CV risk)
        Biomarker("Albumin",       crit_low=1.5, opt_low=4.0, opt_high=5.0, crit_high=None, weight=0.70),
    ]),

    Pathway(name="Nutritional", weight=0.15, biomarkers=[
        Biomarker("Albumin",       crit_low=1.5,  opt_low=4.0,  opt_high=5.0,  crit_high=None, weight=0.40),
        Biomarker("nPCR (Protein Catabolic Rate)", crit_low=0.5, opt_low=1.0, opt_high=1.4, crit_high=2.0, weight=0.40),
        Biomarker("BUN",           crit_low=None, opt_low=0,    opt_high=80,   crit_high=150,  weight=0.20),
    ]),

    Pathway(name="Dialysis_Adequacy", weight=0.10, biomarkers=[
        # KtV target ≥ 1.4 (NKF-KDOQI): optimal 1.4–1.8
        Biomarker("KtV (Dialysis Adequacy)", crit_low=0.8, opt_low=1.4, opt_high=1.8, crit_high=None, weight=0.50),
        # URR target ≥ 65%
        Biomarker("URR (Urea Reduction Ratio)", crit_low=40, opt_low=65, opt_high=80, crit_high=None, weight=0.30),
        # nPCR secondary role in dialysis adequacy
        Biomarker("nPCR (Protein Catabolic Rate)", crit_low=0.5, opt_low=1.0, opt_high=1.4, crit_high=2.0, weight=0.20),
    ]),

    Pathway(name="Inflammatory", weight=0.10, biomarkers=[
        # No CRP in current dataset; use LDH + WBC as proxies for inflammation/hemolysis
        Biomarker("WBC",   crit_low=2.0, opt_low=4.5, opt_high=9.0, crit_high=20.0, weight=0.50),
        Biomarker("LDH",   crit_low=None,opt_low=0,   opt_high=280, crit_high=500,  weight=0.30),
        Biomarker("RDW",   crit_low=None,opt_low=0,   opt_high=15,  crit_high=20,   weight=0.20),
    ]),
]


# ── Public API ───────────────────────────────────────────────────────────────

def compute_hebcs(biomarker_values: dict[str, float],
                  pathways: list[Pathway] = None) -> dict:
    """Compute HEBCS Ω and per-pathway scores from a dict of {test_name: value}.

    Args:
        biomarker_values: {test_name: numeric_value}
        pathways: pathway definitions (defaults to ESRD_PATHWAYS)

    Returns:
        dict with keys:
          omega          — overall wellness score ∈ (0, 1)
          omega_pct      — Ω × 100, as 0–100 scale
          pathways       — {pathway_name: {"score": float|None, "weight": float, "biomarkers": [...]}}
          data_coverage  — fraction of expected biomarkers that had values
    """
    if pathways is None:
        pathways = ESRD_PATHWAYS

    all_expected = sum(len(p.biomarkers) for p in pathways)
    all_present = sum(
        1 for p in pathways for b in p.biomarkers
        if b.name in biomarker_values and biomarker_values[b.name] is not None
    )

    pathway_results = {}
    for p in pathways:
        s = pathway_score(biomarker_values, p)
        biomarker_detail = []
        for b in p.biomarkers:
            val = biomarker_values.get(b.name)
            bs = trapezoidal_score(val, b) if val is not None else None
            biomarker_detail.append({
                "name": b.name,
                "value": val,
                "score": round(bs, 4) if bs is not None else None,
                "weight": b.weight,
                "opt_range": [b.opt_low, b.opt_high],
            })
        pathway_results[p.name] = {
            "score": round(s, 4) if s is not None else None,
            "weight": p.weight,
            "biomarkers": biomarker_detail,
        }

    omega = omega_score(
        {k: v["score"] for k, v in pathway_results.items()},
        pathways,
    )

    return {
        "omega": round(omega, 4),
        "omega_pct": round(omega * 100, 2),
        "pathways": pathway_results,
        "data_coverage": round(all_present / all_expected, 3) if all_expected else 0,
    }
