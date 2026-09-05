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
from dataclasses import dataclass, replace
from typing import Optional


# ── Biomarker definition ────────────────────────────────────────────────────

@dataclass
class Biomarker:
    name: str          # matches test_name in lab_results
    crit_low: Optional[float]   # a — below this → score 0 (None = no lower penalty)
    opt_low: float              # b — below this → linear ramp up
    opt_high: float             # c — above b and ≤ c → score 1
    crit_high: Optional[float]  # d — above this → score 0 (None = no upper penalty)
    weight: float = 1.0
    #: True when a LOW value is itself a clinical finding, so the lower bound
    #: must be anchored to the reporting lab's reference range rather than left
    #: open. Without this a marker declared `crit_low=None, opt_low=0` scores
    #: any value up to `opt_high` as perfect — including zero.
    low_is_deficiency: bool = False


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
                pathways: list[Pathway]) -> Optional[float]:
    """Weighted geometric mean of available pathway scores, or None.

    Ω = exp( Σ w_k·ln(s_k) / Σ w_k )   for pathways with scores.
    Clipped to (0.001, 0.999) per open-interval principle.

    Returns **None** when no pathway scored. This used to return 0.5, so a
    patient with no labs at all was shown a wellness score of 50% — a number
    that describes nobody, sitting where a clinician reads a measurement. Found
    on the deployed service, against an account holding zero results.
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
        return None
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
        # BUN is a TOXICITY marker. Above 21 mg/dL urea is considered toxic, so
        # that is the top of the optimal window — not the lab's reference
        # ceiling of 23, and emphatically not 80.
        #
        # Three wrong bands preceded this one:
        #   crit_low=None, opt_low=0, opt_high=80  — any BUN 0-80 was perfect;
        #                                            a BUN of 5 is starvation.
        #   opt_low=23,  opt_high=80               — asserted a PRE-dialysis 70
        #                                            is optimal. 70 is uraemia.
        #   opt_high=23                            — scored a residual 22 as
        #                                            optimal. 22 is toxic.
        #
        # `resolve_biomarkers` prefers the POST-dialysis draw because the
        # RESIDUAL is what the patient lives with between sessions. Clearing
        # urea is not the same as clearing enough of it: pre-minus-post measures
        # clearance, and URR/Kt/V already score that in Dialysis_Adequacy. A
        # session can hit its adequacy target and still leave a toxic patient —
        # on this record 2025-08-18 had URR 74% and a post-dialysis BUN of 25,
        # and 8 of 11 post draws sit above 21.
        #
        # These numbers are a FALLBACK, used only when the lab reported no
        # reference range. There is no single optimal BUN: 7-20 in children,
        # 6-21 in adult females, 8-24 in adult males, and this record's lab
        # states 9-23. `apply_reference_range` replaces the optimal window with
        # whatever the lab actually reported for this patient, and scales the
        # critical bounds with it — so the general-adult 7-20 below is a
        # starting point, never an assertion about a particular person.
        #
        # `crit_high` is the one figure not taken from a stated range: twice the
        # upper bound, so that exceeding it registers. With the classical
        # uraemia ceiling of 100 the ramp spans 80 units and a residual of 31
        # scored 0.87 — a band that calls the top of range a threshold and then
        # treats 50% above it as near-perfect is not saying anything.
        Biomarker("BUN", crit_low=3, opt_low=7, opt_high=20, crit_high=40,
                  weight=0.20, low_is_deficiency=True),
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

# ── Matching stored lab names to biomarkers ────────────────────────────────
#
# `compute_hebcs` used to look up `b.name` in the caller's dict verbatim, and the
# caller keys that dict by the RAW `lab_results.test_name`. Seven of the 23
# biomarkers could therefore never match on real data — the values were in the
# table the whole time under a different spelling:
#
#     HEBC expects                      actually stored
#     KtV (Dialysis Adequacy)           spKt/V, eKt/V, stdKt/V …
#     URR (Urea Reduction Ratio)        URR, URR%
#     nPCR (Protein Catabolic Rate)     nPCR, NPCR
#     CO2 (Bicarbonate)                 CO2
#     Iron (Serum)                      Iron
#     Iron Saturation (TSAT)            Iron Saturation
#
# The effect was worst where it matters most: **Dialysis_Adequacy matched
# nothing at all** on a patient with 730 sessions, so the one pathway that says
# whether dialysis is working was silently dropped from a score still presented
# as whole. Nutritional lost nPCR — 40% of its weight — leaving albumin and BUN
# to renormalise to ~100% for a patient who may well be malnourished.
#
# Matching is by shape, not by a per-name list: a name is normalised to its
# letters and digits, and each biomarker is also indexed by its pre-parenthesis
# base and its parenthetical. Only genuinely different WORDS need an alias.

_OVERGENERIC = {"serum", "intact", "dialysisadequacy", "ureareductionratio",
                "proteincatabolicrate"}

#: Different words for the same analyte. Deliberately small.
_SYNONYMS = {
    # Delivered single-pool Kt/V. NOT `KT/V PRESCRIBED` (that is the
    # prescription, not what the patient received — the same trap as
    # therapy_sessions.blood_flow_rate being a flat 350), and NOT eKt/V or
    # stdKt/V, whose adequacy targets are different numbers on different scales.
    # The POST-dialysis draw is the value comparable to a normal reference
    # range; the pre-dialysis one is the uraemic burden before treatment.
    "bunpost": "BUN",
    "bunp": "BUN",
    "spktv": "KtV (Dialysis Adequacy)",
    "ktv": "KtV (Dialysis Adequacy)",
    "tsat": "Iron Saturation (TSAT)",
    "transferrinsaturation": "Iron Saturation (TSAT)",
    "hco3": "CO2 (Bicarbonate)",
    "bicarbonate": "CO2 (Bicarbonate)",
    "pcr": "nPCR (Protein Catabolic Rate)",
}


def _norm(name: str) -> str:
    """Letters and digits only, lowercased: 'URR%' and 'urr' become one key."""
    return "".join(ch for ch in str(name).lower() if ch.isalnum())


def resolve_biomarkers(raw: dict[str, float],
                       pathways: list[Pathway] | None = None) -> dict[str, float]:
    """Map stored lab names onto canonical biomarker names.

    An unrecognised name is passed through unchanged rather than dropped, so a
    caller that already speaks canonical names is unaffected. Where several
    stored names resolve to one biomarker the first is kept — callers hand us
    the most recent value per analyte already.
    """
    if pathways is None:
        pathways = ESRD_PATHWAYS

    index: dict[str, str] = {}
    for p in pathways:
        for b in p.biomarkers:
            base, sep, rest = b.name.partition("(")
            keys = {_norm(b.name), _norm(base)}
            if sep:
                paren = _norm(rest.rstrip(")"))
                if paren and paren not in _OVERGENERIC:
                    keys.add(paren)
            for k in keys:
                if k and k not in _OVERGENERIC:
                    index.setdefault(k, b.name)
    for alias, canonical in _SYNONYMS.items():
        index.setdefault(alias, canonical)

    #: Where two stored names resolve to one biomarker, these win. Order in the
    #: caller's dict is arbitrary, so `setdefault` alone would pick whichever
    #: happened to come first — and for BUN that decides whether the score sees
    #: 71.6 (pre-dialysis uraemia) or 20.4 (post, inside the reference range).
    preferred = {"bunpost", "bunp"}

    resolved: dict[str, float] = {}
    claimed_by_preferred: set[str] = set()
    for name, value in (raw or {}).items():
        if value is None:
            continue
        key = _norm(name)
        canonical = index.get(key, name)
        if key in preferred:
            resolved[canonical] = value
            claimed_by_preferred.add(canonical)
        elif canonical not in claimed_by_preferred:
            resolved.setdefault(canonical, value)
    return resolved


def apply_reference_range(b: Biomarker,
                          ref: tuple[float | None, float | None]) -> Biomarker:
    """Re-anchor a biomarker's optimal window to a REPORTED reference range.

    There is no single optimal BUN. The normal range is 7-20 in children, 6-21
    in adult females and 8-24 in adult males, and a reporting lab states its own
    (9-23 on this record). Writing one number into the band picks a population
    the patient may not belong to — an earlier attempt used 21, which is the
    adult FEMALE ceiling, for a male patient.

    So the lab's own range becomes the optimal window, and the critical bounds
    scale with it, preserving the margins the static band expressed. A biomarker
    with no reported range keeps its published definition.
    """
    low, high = ref
    if low is None or high is None or low <= 0 or high <= low:
        return b

    crit_low = b.crit_low
    if crit_low is not None and b.opt_low:
        crit_low = round(low * (b.crit_low / b.opt_low), 3)
    crit_high = b.crit_high
    if crit_high is not None and b.opt_high:
        crit_high = round(high * (b.crit_high / b.opt_high), 3)

    return replace(b, crit_low=crit_low, opt_low=float(low),
                   opt_high=float(high), crit_high=crit_high)


def compute_hebcs(biomarker_values: dict[str, float],
                  pathways: list[Pathway] = None,
                  derived_values: dict[str, float] | None = None,
                  reference_ranges: dict[str, tuple[float | None, float | None]] | None = None) -> dict:
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

    biomarker_values = resolve_biomarkers(biomarker_values, pathways)

    # Values COMPUTED from other labs rather than reported by one — nPCR from
    # urea kinetics, for instance, which this lab prints as N/A on every date.
    # They are scored, because a pathway missing 40% of its weight is worse than
    # one carrying a clearly-labelled estimate. They are NOT counted as measured:
    # `coverage` keeps meaning "how much of this was actually reported", and each
    # biomarker carries its own `source`.
    derived = {k: v for k, v in (derived_values or {}).items() if v is not None}
    derived = resolve_biomarkers(derived, pathways)
    for name, value in derived.items():
        biomarker_values.setdefault(name, value)

    # Ca×P is a PRODUCT, never a row in a lab report — derive it when both
    # factors are present. Bone_Mineral was scoring without it for that reason
    # alone, on the pathway where it is the marker of vascular calcification
    # risk.
    if ("CaxP Product" not in biomarker_values
            and biomarker_values.get("Calcium") is not None
            and biomarker_values.get("Phosphorus") is not None):
        biomarker_values["CaxP Product"] = (
            biomarker_values["Calcium"] * biomarker_values["Phosphorus"])

    all_expected = sum(len(p.biomarkers) for p in pathways)
    all_present = sum(
        1 for p in pathways for b in p.biomarkers
        if b.name in biomarker_values and biomarker_values[b.name] is not None
    )

    # A range the LAB reported for this patient beats a number written here.
    ranges = resolve_biomarkers(
        {k: v for k, v in (reference_ranges or {}).items() if v},
        pathways,
    ) if reference_ranges else {}
    if ranges:
        pathways = [
            Pathway(name=p.name, weight=p.weight, biomarkers=[
                apply_reference_range(b, ranges[b.name]) if b.name in ranges else b
                for b in p.biomarkers
            ])
            for p in pathways
        ]

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
                # Where the band came from. "reported" = a range the lab printed
                # for this patient or their population; "published_band" = the
                # framework's own figure, which is a constant and therefore not
                # specific to anyone. Visible so a constant can never pass for a
                # measurement.
                "band_source": ("reported" if b.name in ranges
                                else "published_band"),
                # "measured" | "derived" — a computed marker must never be
                # shown to a clinician as though a lab had reported it.
                "source": ("derived" if b.name in derived and val is not None
                           else ("measured" if val is not None else None)),
            })
        # How much of this pathway's evidence was actually measured. A score
        # renormalised over 20% of its biomarkers is not the same claim as one
        # computed from all of them, and presenting both as a bare number is how
        # "Nutritional 100%" reached a malnourished patient: with nPCR unmatched,
        # albumin and BUN carried the whole pathway.
        total_w = sum(b.weight for b in p.biomarkers) or 1.0
        measured_w = sum(b.weight for b in p.biomarkers
                         if biomarker_values.get(b.name) is not None
                         and b.name not in derived)
        derived_w = sum(b.weight for b in p.biomarkers
                        if b.name in derived and biomarker_values.get(b.name) is not None)
        pathway_results[p.name] = {
            "score": round(s, 4) if s is not None else None,
            "weight": p.weight,
            "coverage": round(measured_w / total_w, 3),
            #: Coverage once computed markers are allowed to count. Reported
            #: separately so "measured" never quietly absorbs an estimate.
            "coverage_with_derived": round((measured_w + derived_w) / total_w, 3),
            "measured": sum(1 for b in p.biomarkers
                            if biomarker_values.get(b.name) is not None
                            and b.name not in derived),
            "derived": sum(1 for b in p.biomarkers
                           if b.name in derived and biomarker_values.get(b.name) is not None),
            "expected": len(p.biomarkers),
            "biomarkers": biomarker_detail,
        }

    omega = omega_score(
        {k: v["score"] for k, v in pathway_results.items()},
        pathways,
    )

    # Name the pathways that contributed NOTHING. Omega is a weighted geometric
    # mean over the pathways that scored, so an unmeasured one simply vanishes
    # from a number still presented as whole-patient. Saying which ones were
    # blank is the difference between a score and a claim (canon 3aa).
    unscored = [name for name, r in pathway_results.items() if r["score"] is None]

    return {
        "omega": round(omega, 4) if omega is not None else None,
        "omega_pct": round(omega * 100, 2) if omega is not None else None,
        "pathways": pathway_results,
        "data_coverage": round(all_present / all_expected, 3) if all_expected else 0,
        "unscored_pathways": unscored,
    }
