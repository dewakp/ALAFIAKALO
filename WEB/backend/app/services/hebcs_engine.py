# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""
HEBCS WellnessScore Engine — Python implementation of Wole Akpose's
published trapezoidal/pathway/geometric-mean scoring framework.

Reference: J-BHI 2026, "A Holistic, Evidence-Based Composite Score for
End-Stage Renal Disease" (7-pathway, 9.8-year longitudinal ESRD dataset).

Algorithm:
  1. Per-biomarker: trapezoidal membership function  → score ∈ [0, 1]
  2. Per-pathway:   weighted GEOMETRIC mean          → s_k ∈ (0, 1]
  3. Overall Ω:     weighted geometric mean          → Ω ∈ (0, 1)

Step 2 was an ARITHMETIC mean until 2026-10-12, which contradicted step 3's
whole justification one level down — see `pathway_score`.

⚠️ **What this engine is, and what it is not.** It is a transparent scoring
RUBRIC: every number is traceable to a published band and a clinician can check
it by hand. It is **not a model of a coupled physiological system**, and four
of its assumptions are false of one:

  * **Separability.** `trapezoidal_score(x, b)` is a function of ONE variable,
    so no interaction can be expressed. Ferritin 197 scores 1.0 while the same
    draw's TSAT of 14% says the iron is not available — functional iron
    deficiency is the PAIR, and neither value alone carries it.
  * **Indifference inside the band.** Every value in [opt_low, opt_high] scores
    exactly 1.0, so a patient moving 12.0 → 10.1 shows no change at all and
    then falls off a cliff.
  * **Linear ramps.** Mortality against potassium is U-shaped and steep; a
    straight line from 5.5 to 6.5 is a convenience, not a physiology.
  * **No time.** There is no derivative term. Ferritin fell 1,033 → 24 across
    this record, and a score reading only the latest value cannot tell 197
    rising from 197 falling.

Weights (0.30 glucose, 0.20 metabolic …) are hand-assigned, not fitted to an
outcome. Replacing them with fitted ones needs a non-tautological target, which
is exactly what the 12 risk classifiers do not have (§3av: every one restates a
threshold on its own input and reports AUC 1.000). See OPEN_ITEMS 27.
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
    #:
    #: ⚠️ Until 2026-10-12 this was declared, set on BUN, and **read nowhere** —
    #: §3ar's dead control, on the one field written to prevent this exact bug.
    #: `closed_band()` is its first reader.
    low_is_deficiency: bool = False
    #: The same statement about the upper side, for a marker where ABOVE the
    #: band is a finding and `crit_high` was left open.
    high_is_excess: bool = False
    #: Where a GUIDELINE says to hold a patient WITH THIS DISEASE, as
    #: (crit_low, opt_low, opt_high, crit_high). This is a MANAGEMENT band and
    #: it scores Α, never Ω.
    #:
    #: ⚠️ **On 2026-10-12 these numbers were put in the band above**, under
    #: `is_treatment_target`, so Ω scored the patient against KDIGO's targets.
    #: That made the conflation worse, not better: haemoglobin 11.3 scores
    #: **1.000** against the ESRD target of 10-12 and **0.614** against a well
    #: adult's 14-18. The first says the anaemia is well managed; the second
    #: says the patient is anaemic. Both are true, and only the second is a
    #: statement about health. See `compute_alpha`.
    target_band: Optional[tuple] = None
    #: Which guideline states `target_band`. Required alongside it — an uncited
    #: target is a number someone typed (§3az, §3bc).
    authority: str = ""
    #: Condition hints that make this marker EXPECTED. Empty means everyone is
    #: expected to have it — a basic chemistry or blood count.
    #:
    #: A marker present is ALWAYS scored. This governs only whether its
    #: ABSENCE counts against coverage. PTH, ferritin, TSAT and nPCR are renal
    #: monitoring tests: a well person has no reason to have them drawn, and
    #: counting their absence as missing evidence reported a healthy record as
    #: incomplete — "measured as if they have conditions".
    indicated_by: tuple = ()
    #: Which score this marker can appear in.
    #:
    #:   "health"      a well person has one of these and it says how they are
    #:   "management"  a well person has NO value at all — Kt/V, URR. These
    #:                 measure the TREATMENT, so they are Α-only; scoring them
    #:                 in Ω is how "needs dialysis six days a week" came to
    #:                 contribute 97% to a wellness score.
    #:   "both"        carries a health meaning AND a disease target
    scope: str = "health"


@dataclass
class Pathway:
    name: str
    biomarkers: list[Biomarker]
    weight: float = 1.0   # global pathway weight for weighted geometric mean
    #: "health" | "management" | "both" — see `Biomarker.scope`.
    #:
    #: `Dialysis_Adequacy` is **management**: it measures the TREATMENT, not the
    #: patient. A well person has no Kt/V because they have kidneys. Scored in
    #: Ω it reported 97%, so "needs dialysis six days a week" read as near-perfect
    #: wellness — and once Kt/V and URR were moved to Α it still scored 0.86 off
    #: nPCR alone, which `Nutritional` already counts. A pathway that measures a
    #: therapy belongs to Α whole.
    scope: str = "health"


# ── Trapezoidal membership function ────────────────────────────────────────

def closed_band(b: Biomarker) -> tuple[float | None, float, float, float | None]:
    """The band actually scored, with a flagged open side given a bound.

    **`None` on a side means "no penalty", and `trapezoidal_score` answers 1.0
    for the whole of it.** That is correct for a marker where one direction
    genuinely carries no finding — a low LDH is unremarkable — and it is an
    assertion of perfect health where it is not. Measured 2026-10-12, with the
    reporting lab's own interval already applied:

        RDW   0.1 -> 1.000     band (None, 11.0, 15.0, 20.7)
        RDW   5.0 -> 1.000
        RDW  21.3 -> 0.000

    Operator: *"high or low rdw are not sign of health. one suggests hemolysis
    or worse."* Exactly §3ba's one-sided band — `if systolic < 130 and
    diastolic < 80: bp_score = 100.0`, which could only penalise high pressure
    and scored 54/30 as perfect — alive inside HEBCS on five markers.

    **The replacement bound is the band's OWN declared margin, mirrored**, not a
    number chosen here: a band saying `crit_high / opt_high = 20.0 / 14.5` has
    stated how far outside itself it tolerates, and that ratio is applied to the
    other side. `apply_reference_range` already re-anchors by exactly this
    reasoning, so the rule is the one this module uses, not a new one. A marker
    with no margin on either side cannot be closed and is left open.
    """
    a, lo, hi, d = b.crit_low, b.opt_low, b.opt_high, b.crit_high
    if b.low_is_deficiency and a is None and d is not None and hi:
        margin = d / hi                       # how far above the band it allows
        a = lo / margin if margin > 0 else None
    if b.high_is_excess and d is None and a is not None and lo:
        margin = lo / a if a > 0 else None     # how far below the band it allows
        d = hi / margin if margin else None
    return a, lo, hi, d


def trapezoidal_score(x: float, b: Biomarker) -> float:
    """Map raw biomarker value to [0, 1] via trapezoidal membership.

    Args:
        x: observed biomarker value
        b: Biomarker with (crit_low, opt_low, opt_high, crit_high) thresholds

    Returns:
        Score in [0.0, 1.0].  1.0 = optimal, 0.0 = critical.
    """
    a, lo, hi, d = closed_band(b)

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

#: Open-interval floor, the same one `omega_score` applies to Ω. A biomarker at
#: 0 would otherwise annihilate its pathway outright; clipped, it dominates the
#: product without erasing what else the pathway measured.
_SCORE_FLOOR = 0.001


def pathway_score(values: dict[str, float], pathway: Pathway) -> Optional[float]:
    """Weighted GEOMETRIC mean of biomarker scores within a pathway.

    Missing biomarkers are excluded gracefully (HEBCS partial-data policy).
    Returns None if no biomarkers have observed values.

    ⚠️ **This was an arithmetic mean until 2026-10-12, and that contradicted the
    framework one level up.** `omega_score` is geometric for one stated reason —
    `ln(0) = -∞`, so *failure in any single pathway cannot be masked*. Inside a
    pathway the arithmetic mean masked it freely. Measured on the reference
    record, whose Glucose scores **0.000** at weight 0.30:

        arithmetic  0.30(0) + 0.25(.750) + 0.25(.784) + 0.20(1)  = 0.584
        geometric   exp(0.30·ln(.001) + 0.25·ln(.750) + …)       = 0.110

    A marker at the bottom of its own trapezoid — the band's own definition of
    critical — moved Metabolic from 0.11 to 0.58, and the UI said so out loud:
    *"A pathway score is an average, so these do not show in it."* Printing the
    defect beside the number is not the same as not having it.

    The argument for geometric aggregation does not change with the level it is
    applied at, so it is applied at both.
    """
    return _pathway_score(values, pathway, band="health")


def _pathway_score(values: dict[str, float], pathway: Pathway,
                   band: str) -> Optional[float]:
    """`band="health"` scores Ω, `band="management"` scores Α.

    A marker is skipped when it has nothing to say about the band being
    scored: Kt/V has no health meaning (a well person has no Kt/V), and
    creatinine has no management target (nobody treats a dialysis patient TO a
    creatinine).
    """
    log_sum = 0.0
    total_w = 0.0
    for b in pathway.biomarkers:
        if b.name not in values or values[b.name] is None:
            continue
        scored = scoring_marker(b, band)
        if scored is None:
            continue
        s = trapezoidal_score(values[b.name], scored)
        log_sum += b.weight * math.log(max(s, _SCORE_FLOOR))
        total_w += b.weight
    if total_w == 0:
        return None
    return math.exp(log_sum / total_w)


def scoring_marker(b: Biomarker, band: str) -> Optional[Biomarker]:
    """The biomarker as it should be scored for `band`, or None if it does not
    belong to that score at all.

    This is the whole Ω/Α separation in one function. Operator, 2026-10-12:

      *"The HEBCS and wellness score MUST not be how well a condition is being
      managed. Management can have it's own measurement, but wellness is about
      the state of health. Someone with perfect overall conditions, perfect
      genetics, nutrition, blood test results, urine results, bowel state and
      currently on zero medication or therapy etc will score 100% (meaning they
      will live forever). A dead person scores 0 (they are dead). So we need a
      different measure for how well condition is managed (say Alpha) from
      Overall wellness/health (Omega). So far this work has been conflating
      both. That is the core failure."*
    """
    if band == "health":
        if b.scope == "management":
            return None            # no health analogue exists for this marker
        return b                   # the primary band IS the health band
    if band == "management":
        if b.target_band is None:
            return None            # nothing is being treated TO here
        a, lo, hi, d = b.target_band
        return replace(b, crit_low=a, opt_low=lo, opt_high=hi, crit_high=d)
    raise ValueError(f"unknown band {band!r}")


# ── Overall Ω — weighted geometric mean ─────────────────────────────────────

#: Below this fraction of a pathway's own biomarkers, its score is EVIDENCE,
#: not a measurement, and it carries weight in proportion to what was actually
#: measured rather than its full share.
#:
#: Measured 2026-10-12 on two production accounts, both with ZERO conditions:
#:
#:   user 60    46 labs, coverage 0.276   Omega 27.38%
#:              Hematologic 0.001 off ONE of nine markers, carrying the full
#:              0.15 — four other pathways scored 1.000 and were buried.
#:   user 158    5 labs, coverage 0.069   Omega 99.90%
#:              Metabolic alone, on 2 of 5 markers, reported as near-perfect
#:              health: "you will live forever", from five numbers.
#:
#: The two failures are opposite and have one cause: **coverage was computed,
#: reported, and never used.** A score built on 7% of its evidence was
#: presented identically to one built on all of it (§3aa — unmeasured and good
#: are not the same fact).
_FULL_EVIDENCE = 0.5


def evidence_weight(pathway: Pathway, measured: int) -> float:
    """A pathway's share of Omega, scaled by how much of it was measured.

    At or above `_FULL_EVIDENCE` of its markers a pathway carries its declared
    weight. Below that it carries proportionally less, so one lonely marker
    cannot speak for a pathway of nine — in either direction.
    """
    expected = len(pathway.biomarkers)
    if not expected:
        return pathway.weight
    fraction = measured / expected
    if fraction >= _FULL_EVIDENCE:
        return pathway.weight
    return pathway.weight * (fraction / _FULL_EVIDENCE)


def omega_score(pathway_scores: dict[str, Optional[float]],
                pathways: list[Pathway],
                measured_counts: dict[str, int] | None = None) -> Optional[float]:
    """Weighted geometric mean of available pathway scores, or None.

    Ω = exp( Σ w_k·ln(s_k) / Σ w_k )   for pathways with scores.
    Clipped to (0.001, 0.999) per open-interval principle.

    Returns **None** when no pathway scored. This used to return 0.5, so a
    patient with no labs at all was shown a wellness score of 50% — a number
    that describes nobody, sitting where a clinician reads a measurement. Found
    on the deployed service, against an account holding zero results.

    ⚠️ **A pathway that scored ZERO used to be SKIPPED**, through the same
    `s is None or s <= 0` clause that drops an unmeasured one. Total failure of
    an organ system therefore RAISED Ω, by removing the worst term from the
    mean. Nothing reached 0 while `pathway_score` was an arithmetic mean, so it
    never fired — making the geometric fix one level down the thing that would
    have activated it. **Unmeasured and catastrophic are opposite facts and must
    never share a branch** (§3aa). Only `None` is skipped now; a real 0 is
    scored at the open-interval floor.
    """
    log_sum = 0.0
    w_sum = 0.0
    for p in pathways:
        s = pathway_scores.get(p.name)
        if s is None:
            continue
        w = (evidence_weight(p, measured_counts[p.name])
             if measured_counts and p.name in measured_counts else p.weight)
        if w <= 0:
            continue
        log_sum += w * math.log(max(s, _SCORE_FLOOR))
        w_sum += w
    if w_sum == 0:
        return None

    # ── A majority of the construct must be evidenced ────────────────────
    #
    # Scaling every weight by its evidence does NOT make Omega honest on its
    # own: the mean renormalises by `w_sum`, so a uniform reduction cancels
    # out. Measured 2026-10-12 — user 158, five labs, two markers, coverage
    # 0.069, reported **Omega 99.9%**. "You will live forever", from five
    # numbers.
    #
    # The quorum is not a tuned threshold (§3az): it is "more than half of the
    # declared construct", expressed in the framework's own weights. Below it
    # Omega is a claim about a minority of the patient and is WITHHELD — the
    # same decision already taken for a patient with no labs at all, where
    # returning 0.5 described nobody.
    declared = sum(p.weight for p in pathways)
    if declared > 0 and w_sum / declared <= 0.5:
        return None

    raw = math.exp(log_sum / w_sum)
    return max(0.001, min(0.999, raw))


# ── ESRD / HEBCS 7-Pathway Definition ──────────────────────────────────────
#
# ⚠️ These are NOT the paper's Table 3, and the comment here claimed they were
# until 2026-10-04. Measured against `docs/HEBCS_medRxiv_draft.md` §2.3:
#
#   Table 3   Metabolic 0.20 | Hemolytical 0.22 | Endocrinology 0.15
#             Digestive 0.12 | Immunological 0.11 | Bone Formation 0.10
#             Neurological 0.10                        — 48 biomarkers
#
#   here      Metabolic 0.20 | Hematologic 0.15 | Bone_Mineral 0.15
#             Cardiovascular 0.15 | Nutritional 0.15 | Dialysis_Adequacy 0.10
#             Inflammatory 0.10                        — 23 biomarkers
#
# Only `Metabolic 0.20` agrees. The pathway SETS are different, not merely the
# weights: the paper has no Dialysis_Adequacy or Inflammatory pathway and this
# file has no Digestive or Neurological one. Citing Table 3 above a different
# decomposition is the kind of claim §0 exists to stop — a reader checking the
# score against the published framework would have found neither matched.
#
# The implemented set is kept deliberately (operator decision, 2026-10-04): it
# is the one this product has always scored, ESRD-specific, and re-anchoring to
# the paper would move Ω for every patient and make the stored history
# non-comparable. What changes is that it no longer claims to be something it
# is not.
#
# Biomarker thresholds derived from appendixD.tex / pathway_definitions_15.m
# and KDIGO/NKF-KDOQI 2023 guidelines for ESRD. Where a lab reports a range for
# this patient, `apply_reference_range` replaces the band with theirs.

ESRD_PATHWAYS: list[Pathway] = [

    Pathway(name="Metabolic", weight=0.20, biomarkers=[
        # ⚠️ CREATININE was absent from this engine until 2026-10-12, though the
        # published Table 3 lists it in Metabolic and the record holds it on
        # every panel. It is the single largest health fact about a dialysis
        # patient — 8.23 mg/dL against a well adult's 0.6-1.3 scores **0.000** —
        # and Ω had no term for it at all, while `Dialysis_Adequacy` scored the
        # TREATMENT for it at 97%. Operator, 2026-10-12: *"wellness is about the
        # state of health"*. Needing dialysis six days a week is not 97%
        # wellness; it is near-zero renal function, and now it scores as such.
        #
        # Health-only: there is no guideline target for a dialysis patient's
        # creatinine. It is not something anyone treats TO.
        Biomarker("Creatinine", crit_low=0.3, opt_low=0.6, opt_high=1.3, crit_high=3.0,
                  weight=0.30, scope="health"),
        Biomarker("Glucose",    crit_low=40,  opt_low=70,  opt_high=130, crit_high=300,  weight=0.30),
        Biomarker("Sodium",     crit_low=120, opt_low=136, opt_high=145, crit_high=160,  weight=0.25),
        Biomarker("Potassium",  crit_low=2.5, opt_low=3.5, opt_high=5.5, crit_high=6.5, weight=0.25),
        # Bicarbonate — ESRD patients often mildly elevated (bicarbonate loading)
        Biomarker("CO2 (Bicarbonate)", crit_low=15, opt_low=22, opt_high=29, crit_high=35, weight=0.20),
    ]),

    Pathway(name="Hematologic", weight=0.15, biomarkers=[
        # TARGET, not a reference interval: KDIGO 2012 anaemia-in-CKD holds
        # haemoglobin at 10-12 g/dL on ESA. The lab prints the healthy-adult
        # 14-18, and chasing that is what the TREAT and CHOIR trials showed
        # raises mortality — so the lab band is the DANGEROUS one here.
        # HEALTH band is a well adult's haemoglobin; the ESRD target lives in
        # `target_band` and scores Α. 11.3 -> Ω 0.614 (anaemic), Α 1.000
        # (treated to target). Both true; only the first is about health.
        Biomarker("Hemoglobin",          crit_low=7.0, opt_low=13.5, opt_high=17.5, crit_high=22.0, weight=0.30,
                  scope="both", target_band=(7.0, 10.0, 12.0, 17.5),
                  authority="KDIGO 2012 Anemia in CKD, 3.4.3"),
        Biomarker("Hematocrit",          crit_low=21,  opt_low=30,   opt_high=36,   crit_high=52,   weight=0.20),
        Biomarker("RBC",                 crit_low=2.0, opt_low=3.0,  opt_high=4.5,  crit_high=6.0,  weight=0.15),
        Biomarker("MCV",                 crit_low=60,  opt_low=80,   opt_high=96,   crit_high=115,  weight=0.10),
        # Operator, 2026-10-12: "high or low rdw are not sign of health. one
        # suggests hemolysis or worse." Left open-low this scored RDW 0.1 as
        # perfect. `closed_band` mirrors the band's own 20/14.5 margin.
        Biomarker("RDW",                 crit_low=None,opt_low=0,    opt_high=14.5, crit_high=20,   weight=0.10,
                  low_is_deficiency=True),
        # TARGET: KDOQI holds ferritin >200 ng/mL on haemodialysis. The lab
        # prints 11-307, under which a ferritin of 57 — iron deficiency on
        # dialysis — scored 1.000.
        Biomarker("Ferritin",            crit_low=5,   opt_low=24,   opt_high=336,  crit_high=1000, weight=0.15,
                  indicated_by=("renal",), scope="both", target_band=(10, 200, 800, 2000),
                  authority="KDOQI 2006 Anemia, CPR 3.2"),
        # TSAT target for HD: 20-50%
        Biomarker("Iron Saturation (TSAT)", crit_low=5, opt_low=20, opt_high=50, crit_high=80, weight=0.20,
                  indicated_by=("renal",), scope="both", target_band=(5, 20, 50, 80),
                  authority="KDOQI 2006 Anemia, CPR 3.2 (TSAT >20% on HD)"),
        Biomarker("WBC",                 crit_low=2.0, opt_low=4.5, opt_high=11.0, crit_high=30,   weight=0.10),
        Biomarker("LDH",                 crit_low=None,opt_low=0,   opt_high=280,  crit_high=600,  weight=0.10),
    ]),

    Pathway(name="Bone_Mineral", weight=0.15, biomarkers=[
        # PTH target for ESRD stage 5D: 150–600 pg/mL (KDIGO).
        # crit_low=15: PTH < 15 → adynamic bone disease (score 0); 15–150 → linear ramp.
        # TARGET: KDIGO CKD-MBD holds iPTH at 2-9x the assay upper limit on
        # stage 5D. Overridden by the lab's healthy-adult 18-80, a PTH of 24 —
        # adynamic bone disease — scored 1.000 and Bone Mineral read 100%.
        # A well person's PTH is 15-65; a dialysis patient is HELD at 2-9x the
        # assay ceiling to drive bone turnover against skeletal resistance. The
        # two bands barely overlap, which is why one number could not carry it.
        Biomarker("PTH (Intact)",  crit_low=5,    opt_low=15,   opt_high=65,   crit_high=200,  weight=0.40,
                  indicated_by=("renal",), scope="both", target_band=(15, 150, 600, 3000),
                  authority="KDIGO 2017 CKD-MBD, 4.2.1"),
        # Phosphorus KDIGO target: 3.5–5.5 mg/dL (ESRD relaxed)
        Biomarker("Phosphorus",    crit_low=1.5,  opt_low=2.5,  opt_high=4.5,  crit_high=9.0,  weight=0.30,
                  scope="both", target_band=(1.5, 3.5, 5.5, 9.0),
                  authority="KDIGO 2017 CKD-MBD, 4.1.1"),
        # Calcium
        Biomarker("Calcium",       crit_low=6.5,  opt_low=8.5,  opt_high=10.0, crit_high=12.0, weight=0.20),
        # CaxP product target: <55 mg²/dL²
        Biomarker("CaxP Product",  crit_low=None, opt_low=0,    opt_high=55.0, crit_high=80.0, weight=0.10,
                   indicated_by=("renal",)),
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
        Biomarker("nPCR (Protein Catabolic Rate)", crit_low=0.5, opt_low=1.0, opt_high=1.4, crit_high=2.0, weight=0.40,
                  indicated_by=("renal",)),
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

    Pathway(name="Dialysis_Adequacy", weight=0.10, scope="management", biomarkers=[
        # KtV target ≥ 1.4 (NKF-KDOQI): optimal 1.4–1.8
        Biomarker("KtV (Dialysis Adequacy)", crit_low=0.8, opt_low=1.4, opt_high=1.8, crit_high=None, weight=0.50,
                  scope="management", target_band=(0.8, 1.4, 1.8, None),
                  authority="KDOQI 2015 Hemodialysis Adequacy, spKt/V >=1.4"),
        # URR target ≥ 65%
        Biomarker("URR (Urea Reduction Ratio)", crit_low=40, opt_low=65, opt_high=80, crit_high=None, weight=0.30,
                  scope="management", target_band=(40, 65, 80, None),
                  authority="KDOQI 2015 Hemodialysis Adequacy, URR >=65%"),
        # nPCR secondary role in dialysis adequacy
        Biomarker("nPCR (Protein Catabolic Rate)", crit_low=0.5, opt_low=1.0, opt_high=1.4, crit_high=2.0, weight=0.20),
    ]),

    Pathway(name="Inflammatory", weight=0.10, biomarkers=[
        # No CRP in current dataset; use LDH + WBC as proxies for inflammation/hemolysis
        Biomarker("WBC",   crit_low=2.0, opt_low=4.5, opt_high=9.0, crit_high=20.0, weight=0.50),
        Biomarker("LDH",   crit_low=None,opt_low=0,   opt_high=280, crit_high=500,  weight=0.30),
        Biomarker("RDW",   crit_low=None,opt_low=0,   opt_high=15,  crit_high=20,   weight=0.20,
                  low_is_deficiency=True),
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

#: At or below this, a biomarker is at the bottom of its own trapezoid — the
#: value is at or past the critical bound the band itself declares. It is not a
#: threshold invented here: 0 is what `trapezoidal_score` returns outside
#: `crit_low`/`crit_high`, and the small margin admits a value sitting just
#: inside the ramp (TSAT 6% against a 21-49% band scores 0.048).
_CRITICAL_SCORE = 0.2

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


def canonical_name(stored_name: str,
                   pathways: list[Pathway] | None = None) -> str:
    """The biomarker a stored `test_name` belongs to, or the name unchanged.

    Exposed because the CALLER has to dedupe by analyte, and could not.
    `resolve_biomarkers`' docstring says "callers hand us the most recent value
    per analyte already" — which was false. `/wellness/omega` kept one row per
    raw `test_name`, so `FERRITIN` and `Ferritin` were two analytes and the
    stale spelling won whichever way the dict happened to iterate. Measured on
    the reference record 2026-10-12, under a card reading "Latest labs:
    9/30/2026":

        Ferritin   scored  57  from 2026-02-09   (245d)   latest 197
        PTH        scored  24  from 2025-09-03   (404d)   latest  17
        BUN        scored  20  from 2025-09-03   (404d)   latest  53
        URR        scored  81  from 2025-07-17   (452d)   latest  74

    **13 of the 23 scored biomarkers were not the patient's current values.**
    §3ax, in the wellness score.
    """
    return _resolution_index(pathways).get(_norm(stored_name), stored_name)


def _resolution_index(pathways: list[Pathway] | None = None) -> dict[str, str]:
    """Normalised stored spelling → canonical biomarker name."""
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
    return index


def resolve_biomarkers(raw: dict[str, float],
                       pathways: list[Pathway] | None = None) -> dict[str, float]:
    """Map stored lab names onto canonical biomarker names.

    An unrecognised name is passed through unchanged rather than dropped, so a
    caller that already speaks canonical names is unaffected. Where several
    stored names resolve to one biomarker the first is kept — callers hand us
    the most recent value per analyte already.
    """
    index = _resolution_index(pathways)

    preferred = PREFERRED_SPELLINGS   # see its definition for why it exists

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


#: Analytes whose NAME is the same in blood and in urine. §3ab names the
#: authority — LOINC `SYSTEM` *"separates serum from urine glucose (two rows
#: both named 'Glucose' today)"* — and it is not available: `loinc_code` is
#: populated on **34 of 9,871** rows, `category` on 1,018 and holds panel names
#: rather than specimens. So the panel itself is the evidence.
AMBIGUOUS_SPECIMEN = {"rbc", "wbc", "glucose", "protein", "ph", "bilirubin",
                      "ketones", "nitrite", "creatinine"}

#: Names that appear ONLY on a urinalysis. Two or more of these on one draw
#: identify the panel, and an ambiguous analyte drawn with them is a urine
#: finding — not a blood count.
_URINALYSIS_MARKERS = {
    "specificgravity", "leukocyteesterase", "nitrite", "urobilinogen",
    "amorphoussediment", "hyalinecast", "granularcast", "crystals",
    "calciumoxalatecrystals", "triplephosphatecrystals", "uricacidcrystals",
    "renalepithelialcells", "squamousepithelialcells",
    "transitionalepithelialcells", "bacteria", "occultblood", "appearance",
    "color", "mucus", "yeast",
}

#: How many urinalysis-only markers on one draw identify the panel. Two, not
#: one: a lone "BACTERIA" or "COLOR" could be a stray row, and mis-identifying
#: a blood panel as urine would DISCARD a real haemoglobin.
_URINALYSIS_QUORUM = 2


def urinalysis_draws(rows) -> set:
    """The draw dates whose panel is a urinalysis.

    Found 2026-10-12 on a production account holding **46 labs and zero
    conditions**, scored at **Ω 27.38%**:

        RBC = 0   no reference range, drawn beside AMORPHOUS SEDIMENT,
                  BACTERIA, GRANULAR CAST, NITRITE, SPECIFIC GRAVITY,
                  LEUKOCYTE ESTERASE, SQUAMOUS EPITHELIAL CELLS …

    That is **zero red blood cells per high-power field in the URINE** — the
    ideal urinalysis result. It resolved to the Hematologic `RBC` biomarker
    (blood count, band 4.6-6.2) and scored **0.000**: no red blood cells in the
    body. Being the only Hematologic value present it carried the pathway alone
    to 0.001, and a healthy person's normal urine test reported them at 27%
    wellness.

    Operator, 2026-10-12: *"omega must be responsive to patient and not force
    people without conditions to be measured as if they have conditions."* This
    is that, in its sharpest form — a well person's best possible result read as
    a catastrophic one.
    """
    by_draw: dict = {}
    for name, _value, test_date, *_rest in rows:
        key = test_date.date() if hasattr(test_date, "date") else test_date
        by_draw.setdefault(key, set()).add(_norm(name))
    return {
        draw for draw, names in by_draw.items()
        if len(names & _URINALYSIS_MARKERS) >= _URINALYSIS_QUORUM
    }


#: Where two stored spellings resolve to one biomarker, these win OUTRIGHT —
#: ahead of recency, not after it. For BUN that decides whether the score sees
#: the PRE-dialysis draw (uraemia, 53 on this record) or the POST one (14, the
#: residual the patient actually lives with between sessions). Both are drawn
#: the same day, so a newest-wins rule alone picks whichever the dict iterates
#: first — which is exactly the arbitrariness this module already had.
PREFERRED_SPELLINGS = {"bunpost", "bunp"}


def select_latest_per_analyte(
        rows, pathways: list[Pathway] | None = None) -> dict[str, tuple]:
    """One row per ANALYTE from `(name, value, date, ref_low, ref_high)` rows.

    Returns `{canonical_name: (date, value, ref_low, ref_high)}`.

    Deduplication has to happen HERE because two of its rules disagree and only
    one module knows both:

      * **Recency.** The caller used to keep one row per raw `test_name`, so
        `FERRITIN` and `Ferritin` survived as two analytes and
        `resolve_biomarkers`' `setdefault` then picked by dict order. 13 of the
        23 scored biomarkers carried a stale value — Ferritin 57 from February
        over 197 from October, PTH 24 from 404 days earlier over 17.
      * **Provenance beats recency.** `BUN Post` and `BUN` are drawn the same
        day, and the post draw is the one that matters. Fixing recency alone
        silently broke this, which is how the rule got written down.
    """
    urine = urinalysis_draws(rows)

    best: dict[str, tuple] = {}
    for name, value, test_date, ref_low, ref_high in rows:
        if value is None:
            continue
        draw = test_date.date() if hasattr(test_date, "date") else test_date
        if draw in urine and _norm(name) in AMBIGUOUS_SPECIMEN:
            # A urine finding under a blood analyte's name. Skipped, never
            # scored as the blood one — see `urinalysis_draws`.
            continue
        analyte = canonical_name(name, pathways)
        wins = _norm(name) in PREFERRED_SPELLINGS
        prior = best.get(analyte)
        if prior is None:
            best[analyte] = (test_date, value, ref_low, ref_high, wins)
            continue
        prior_wins = prior[4]
        if wins and not prior_wins:
            best[analyte] = (test_date, value, ref_low, ref_high, wins)
        elif wins == prior_wins and test_date > prior[0]:
            best[analyte] = (test_date, value, ref_low, ref_high, wins)
    return {k: v[:4] for k, v in best.items()}


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

    ⚠️ **A TREATMENT TARGET is refused, and that exception is the whole point.**
    A reference interval describes where 95% of healthy people fall; a target
    says where THIS patient should be held. On ESRD the two diverge sharply and
    in both directions, which is what proves the override was the wrong
    mechanism rather than the wrong numbers:

        PTH    KDIGO 5D target 150-600   lab's healthy adult 18-80
               -> PTH 24 scored 1.000 instead of 0.067, and 24 pg/mL in a
                  dialysis patient is adynamic bone disease. Bone Mineral
                  read 100%.
        Hgb    KDIGO anaemia target 10-12 (above 13 raises mortality)
               lab's healthy adult male 14-18
               -> Hgb 12.0 scored 0.524 instead of 1.000.

    §3am already states this for nutrients — *a generic RDA must never be handed
    over as the patient's target*, potassium 4,700 against a renal patient's
    2,800 — and §3az for the thresholds that were looser than the patient's own
    limits. This is the same error in the biological score.
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


#: Condition words that indicate the renal monitoring panel. Matched
#: case-folded against the patient's own condition names; it only ever makes a
#: marker EXPECTED, never changes how one is scored.
RENAL = ("renal", "kidney", "dialysis", "esrd", "ckd", "nephro")


def pathways_for(conditions=None,
                 pathways: list[Pathway] | None = None) -> list[Pathway]:
    """The decomposition THIS patient should be measured against.

    Operator, 2026-10-12: *"Also omega must be responsive to patient and not
    force people without conditions to be measured as if they have conditions.
    This is the wheelhouse of adaptive, intelligent mathematical modeling."*

    **The pathway set and the WEIGHTS deliberately do not vary.** Ω is an
    absolute scale and the operator fixed both its ends — *"perfect … will score
    100% (meaning they will live forever). A dead person scores 0."* Two people
    with identical biology must receive the same Ω, so a decomposition that
    re-weighted itself per diagnosis would make the number incomparable between
    two patients and between one patient and their own past. Weighting by
    disease is what Α is for.

    What adapts is which markers are **expected**. A well person has no reason
    to have PTH, ferritin, TSAT or nPCR drawn, and counting their absence as
    missing evidence both reported a healthy record as incomplete and — now
    that coverage bounds Ω — would withhold their score for not holding tests
    nobody should have ordered.

    A marker present is always scored. This governs absence only.
    """
    if pathways is None:
        pathways = ESRD_PATHWAYS

    text = " ".join(
        f" {(getattr(c, 'name', '') or '').lower()} "
        f"{(getattr(c, 'icd11_title', '') or '').lower()} "
        for c in (conditions or [])
    )
    indications = {"renal"} if any(h in text for h in RENAL) else set()

    return [
        replace(p, biomarkers=[
            b for b in p.biomarkers
            if not b.indicated_by or (set(b.indicated_by) & indications)
        ])
        for p in pathways
    ]


def compute_alpha(biomarker_values: dict[str, float],
                  pathways: list[Pathway] | None = None,
                  derived_values: dict[str, float] | None = None,
                  has_managed_condition: bool = True) -> dict:
    """Α — how well the CONDITIONS are being managed. Not a health score.

    Operator, 2026-10-12, naming the core failure:

      *"The HEBCS and wellness score MUST not be how well a condition is being
      managed. Management can have it's own measurement, but wellness is about
      the state of health. … So we need a different measure for how well
      condition is managed (say Alpha) from Overall wellness/health (Omega). So
      far this work has been conflating both. That is the core failure."*

    Ω and Α answer different questions and routinely disagree. On the reference
    record, from one panel:

        Haemoglobin 11.3   Ω 0.614 against a well adult's 13.5-17.5
                           Α 1.000 against KDIGO's 10-12 for ESRD on ESA
        Kt/V 1.47          Ω   n/a — a well person has no Kt/V
                           Α 1.000
        Creatinine 8.23    Ω 0.000 against 0.6-1.3
                           Α   n/a — nobody treats a patient TO a creatinine

    A patient can be gravely ill AND impeccably managed. Collapsing that into
    one number loses the only pair a clinician can act on, and the number it
    produced was the managed one wearing the word "wellness".

    **Α is scored ONLY where a guideline states a target** (`target_band` with
    its `authority`). A patient with no managed condition has no Α — which is
    correct, and is NOT a zero: `None` means there is nothing to manage, the
    §3aa distinction between unmeasured and bad.
    """
    if not has_managed_condition:
        # Operator, 2026-10-12: *"A healthy person with zero conditions and
        # demonstrated health records need no management score. A cancer
        # patient or someone with luekamia require management score."*
        #
        # Without this gate Α scored ANYONE holding a haemoglobin, because the
        # targets hang off the biomarkers rather than off the patient — which
        # is the same error as Ω measuring a well person against an ESRD
        # decomposition. **No condition, no Α.** This is `None`, never 0: there
        # is nothing to manage, which is not bad management (§3aa).
        return {"alpha": None, "alpha_pct": None, "pathways": {},
                "off_target": [],
                "reason": "no condition on record requires management"}

    if pathways is None:
        pathways = ESRD_PATHWAYS

    values = resolve_biomarkers(biomarker_values, pathways)
    for name, value in resolve_biomarkers(
            {k: v for k, v in (derived_values or {}).items() if v is not None},
            pathways).items():
        values.setdefault(name, value)

    pathway_results: dict[str, dict] = {}
    scores: dict[str, float | None] = {}
    off_target: list[dict] = []
    scored_any = False

    for p in pathways:
        managed = [b for b in p.biomarkers if b.target_band is not None]
        if not managed:
            continue
        score = _pathway_score(values, p, band="management")
        scores[p.name] = score
        if score is None:
            continue
        scored_any = True
        rows = []
        for b in managed:
            if b.name not in values:
                continue
            m = scoring_marker(b, "management")
            bs = trapezoidal_score(values[b.name], m)
            rows.append({"name": b.name, "value": values[b.name],
                         "score": round(bs, 4), "weight": b.weight,
                         "target_range": [m.opt_low, m.opt_high],
                         "authority": b.authority})
            if bs <= _CRITICAL_SCORE:
                off_target.append({"name": b.name, "pathway": p.name,
                                   "value": values[b.name],
                                   "score": round(bs, 4),
                                   "target_range": [m.opt_low, m.opt_high],
                                   "authority": b.authority})
        pathway_results[p.name] = {
            "score": round(score, 4), "weight": p.weight, "biomarkers": rows}

    if not scored_any:
        return {"alpha": None, "alpha_pct": None, "pathways": {},
                "off_target": [],
                "reason": "no managed condition has a guideline target on file"}

    alpha = omega_score(scores, [p for p in pathways if p.name in scores])
    off_target.sort(key=lambda r: r["score"])
    return {
        "alpha": round(alpha, 4) if alpha is not None else None,
        "alpha_pct": round(alpha * 100, 2) if alpha is not None else None,
        "pathways": pathway_results,
        "off_target": off_target,
    }


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
            # `scope=` is NOT optional here. Rebuilding a Pathway without it
            # silently resets it to "health", so `Dialysis_Adequacy` would have
            # come back into Ω the moment a lab range was passed — which is
            # every real call. A field set in one place and dropped in another
            # is §3ar with the dead control one layer down.
            Pathway(name=p.name, weight=p.weight, scope=p.scope, biomarkers=[
                apply_reference_range(b, ranges[b.name]) if b.name in ranges else b
                for b in p.biomarkers
            ])
            for p in pathways
        ]

    # Ω is HEALTH. A pathway that measures a therapy belongs to Α whole.
    pathways = [p for p in pathways if p.scope != "management"]

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

    # Evidence-weighted: a pathway scored on a fraction of its markers carries
    # a fraction of its weight. `measured` counts REPORTED values only, so a
    # derived estimate cannot buy a pathway its full share of Omega.
    omega = omega_score(
        {k: v["score"] for k, v in pathway_results.items()},
        pathways,
        measured_counts={k: v["measured"] + v["derived"]
                         for k, v in pathway_results.items()},
    )

    # Name the pathways that contributed NOTHING. Omega is a weighted geometric
    # mean over the pathways that scored, so an unmeasured one simply vanishes
    # from a number still presented as whole-patient. Saying which ones were
    # blank is the difference between a score and a claim (canon 3aa).
    unscored = [name for name, r in pathway_results.items() if r["score"] is None]

    # ── A failing marker must survive its own pathway ────────────────────
    #
    # The framework's argument for product aggregation is that "failure in any
    # single pathway cannot be masked by others" — and that holds BETWEEN
    # pathways. Inside one, `pathway_score` is a weighted ARITHMETIC mean, so a
    # marker at zero is averaged up by its neighbours and the masking the
    # design forbids happens one level below where it was prevented.
    #
    # Measured on the reference record 2026-10-04:
    #
    #   Metabolic    0.549   Glucose 273 mg/dL -> 0.000   (a diabetic patient)
    #   Hematologic  0.627   TSAT 6%           -> 0.048
    #
    # Ω read 0.777 — "relatively well-managed" — on a record whose glucose
    # scores zero and whose transferrin saturation is near it. Changing the
    # within-pathway mean would alter every stored Ω and make the series
    # non-comparable, so the aggregation is left exactly as published and the
    # markers are NAMED instead. The number keeps its meaning; it stops being
    # the only thing the reader gets.
    # `weight` travels too. The mobile clients decode these through the
    # EXISTING `HEBCSBiomarkerScore`, where `weight` is non-optional — omitting
    # it fails the iOS decode for the whole response and silently gives Android
    # 0.0. One shape for every client beats loosening two models.
    critical_biomarkers = [
        {"name": b["name"], "pathway": pname, "value": b["value"],
         "score": b["score"], "weight": b["weight"], "opt_range": b["opt_range"]}
        for pname, r in pathway_results.items()
        for b in r["biomarkers"]
        if b["score"] is not None and b["score"] <= _CRITICAL_SCORE
    ]
    critical_biomarkers.sort(key=lambda b: b["score"])

    return {
        "omega": round(omega, 4) if omega is not None else None,
        "omega_pct": round(omega * 100, 2) if omega is not None else None,
        "pathways": pathway_results,
        "data_coverage": round(all_present / all_expected, 3) if all_expected else 0,
        "unscored_pathways": unscored,
        "critical_biomarkers": critical_biomarkers,
    }
