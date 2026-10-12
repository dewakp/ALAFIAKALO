# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""The four ways Ω read 78% on a patient in critical condition.

Operator, 2026-10-12, looking at Ω 0.781 / "78%" beside a Critical ring:
*"The patient is terminally ill, the blood results show severe anemia and
nutrition is hardly ever adequate and HEBCS (a wellness score) is 78%? What
happens to someone in perfect health? … We must surface and fix the underlying
mathematics."*

Four independent faults, each sufficient on its own, measured on the reference
record before anything was changed:

1. **Stale values.** `/wellness/omega` deduplicated on the raw `test_name`, so
   `FERRITIN` and `Ferritin` were two analytes (§3ax) and the stale spelling
   could win. 13 of the 23 scored biomarkers were not the patient's current
   values — Ferritin 57 from February over 197 from October, PTH 24 from 404
   days earlier over 17, BUN 20 over 53 — under a card reading
   "Latest labs: 9/30/2026".
2. **A population reference interval replaced a treatment target.** PTH 24
   scored **1.000** against the lab's healthy-adult 18-80 instead of 0.067
   against KDIGO's 150-600 for stage 5D. Bone Mineral read **100%**.
3. **An arithmetic mean inside each pathway**, under a geometric mean between
   them whose entire justification is that failure cannot be masked.
4. **One-sided bands.** `crit_low=None, opt_low=0` made RDW 0.1 score 1.000 —
   §3ba's `if systolic < 130 and diastolic < 80: bp_score = 100.0` all over
   again. Operator: *"high or low rdw are not sign of health. one suggests
   hemolysis or worse."*

Ω on that record: **0.781 → 0.489.**
"""

from datetime import datetime

import pytest

from app.services.hebcs_engine import (
    ESRD_PATHWAYS,
    Biomarker,
    Pathway,
    apply_reference_range,
    closed_band,
    compute_alpha,
    compute_hebcs,
    omega_score,
    pathway_score,
    scoring_marker,
    select_latest_per_analyte,
    trapezoidal_score,
)


def _marker(name="M", **kw):
    base = dict(crit_low=1.0, opt_low=2.0, opt_high=4.0, crit_high=5.0)
    base.update(kw)
    return Biomarker(name, **base)


# ── 1. The value scored must be the patient's latest ────────────────────────

def test_the_same_analyte_under_two_spellings_is_ONE_analyte():
    """`FERRITIN` 57 from February must not outrank `Ferritin` 197 from
    October. This is the fault that made the score describe a different year."""
    rows = [
        ("FERRITIN", 57.0, datetime(2026, 2, 9), 11, 307),
        ("Ferritin", 197.0, datetime(2026, 10, 1), 11, 307),
    ]
    picked = select_latest_per_analyte(rows)
    assert list(picked) == ["Ferritin"], "two spellings must collapse to one"
    assert picked["Ferritin"][1] == 197.0


def test_order_of_the_rows_cannot_change_the_answer():
    """The old path depended on dict iteration order, which is why it was wrong
    silently rather than consistently."""
    rows = [("PTH", 24.0, datetime(2025, 9, 3), 18, 80),
            ("PTH (Intact)", 17.0, datetime(2026, 10, 1), 18, 80)]
    assert (select_latest_per_analyte(rows)
            == select_latest_per_analyte(list(reversed(rows))))


def test_a_PREFERRED_spelling_beats_recency_not_the_other_way_round():
    """`BUN Post` and `BUN` are drawn the SAME DAY and mean different things:
    53 is pre-dialysis uraemia, 14 is the residual the patient lives with.

    Fixing recency alone broke this — the newest-wins rule had no opinion
    between two same-day rows and took the pre draw, which crashed Nutritional
    to 0.237 for the wrong reason. Both rules had to live in one place.
    """
    rows = [("BUN", 53.0, datetime(2026, 10, 1), 9, 23),
            ("BUN Post", 14.0, datetime(2026, 10, 1), 9, 23)]
    assert select_latest_per_analyte(rows)["BUN"][1] == 14.0
    # …and still wins when the pre draw is NEWER, because it is the better
    # measurement rather than the later one.
    rows = [("BUN", 53.0, datetime(2026, 10, 5), 9, 23),
            ("BUN Post", 14.0, datetime(2026, 10, 1), 9, 23)]
    assert select_latest_per_analyte(rows)["BUN"][1] == 14.0


# ── 2. A treatment target is not a reference interval ───────────────────────

def test_a_marker_carries_BOTH_bands_and_they_disagree():
    """The conflation, in one row. Haemoglobin 11.3 is anaemia on a health
    band and on-target under KDIGO. Ω must say the first, Α the second."""
    hgb = next(b for p in ESRD_PATHWAYS if p.name == "Hematologic"
               for b in p.biomarkers if b.name == "Hemoglobin")
    assert hgb.target_band is not None and hgb.authority
    health = trapezoidal_score(11.3, scoring_marker(hgb, "health"))
    mgmt = trapezoidal_score(11.3, scoring_marker(hgb, "management"))
    assert health < 0.8, "a well adult's haemoglobin is not 11.3"
    assert mgmt == 1.0, "KDIGO holds ESRD at 10-12 and 11.3 is on target"


def test_an_ordinary_analyte_still_takes_the_labs_own_range():
    """There is no single optimal sodium, and the reporting lab's interval is
    better evidence than a constant."""
    na = next(b for p in ESRD_PATHWAYS if p.name == "Metabolic"
              for b in p.biomarkers if b.name == "Sodium")
    assert na.target_band is None
    assert apply_reference_range(na, (134, 148)).opt_high == 148.0


def test_every_declared_target_cites_its_guideline():
    """§3bc: an uncited quota is REFUSED. A target with no authority is a
    number someone typed."""
    for p in ESRD_PATHWAYS:
        for b in p.biomarkers:
            if b.target_band is not None:
                assert b.authority, f"{b.name} claims a target with no source"


# ── 3. A zero cannot be averaged away ───────────────────────────────────────

def test_a_critical_marker_dominates_its_pathway():
    """Glucose scored 0.000 at weight 0.30 and Metabolic still read 0.584."""
    path = Pathway("P", [_marker("A", weight=0.3), _marker("B", weight=0.7)])
    s = pathway_score({"A": 0.0, "B": 3.0}, path)      # A below crit_low
    assert s < 0.15, "an arithmetic mean would have returned 0.70"


def test_a_pathway_scoring_zero_is_not_SKIPPED_by_omega():
    """`s is None or s <= 0: continue` dropped a zeroed pathway, so total
    failure of an organ system RAISED Ω by removing the worst term.

    Unmeasured and catastrophic are opposite facts and must not share a branch.
    """
    # THREE pathways, so dropping one still leaves a majority of the construct
    # evidenced and the evidence quorum does not withhold the score — which is
    # the behaviour under test here, not the quorum.
    paths = [Pathway("X", [], weight=0.4), Pathway("Y", [], weight=0.3),
             Pathway("Z", [], weight=0.3)]
    both_fine = omega_score({"X": 1.0, "Y": 1.0, "Z": 1.0}, paths)
    one_dead = omega_score({"X": 1.0, "Y": 0.0, "Z": 1.0}, paths)
    one_absent = omega_score({"X": 1.0, "Y": None, "Z": 1.0}, paths)
    assert one_dead < both_fine, "a dead pathway must lower the score"
    assert one_dead < one_absent, "catastrophic must not read as unmeasured"
    assert one_absent == pytest.approx(both_fine)


def test_a_pathway_with_nothing_measured_is_still_None():
    assert pathway_score({}, Pathway("P", [_marker("A")])) is None


# ── 4. A band open on one side asserts health it never measured ─────────────

def test_RDW_below_its_range_is_no_longer_perfect():
    """Operator: "high or low rdw are not sign of health."

    Measured before the fix, with the lab's own 11-15 already applied:
    RDW 0.1 -> 1.000, RDW 5.0 -> 1.000.
    """
    rdw = next(b for p in ESRD_PATHWAYS if p.name == "Hematologic"
               for b in p.biomarkers if b.name == "RDW")
    banded = apply_reference_range(rdw, (11, 15))
    assert trapezoidal_score(0.1, banded) == 0.0
    assert trapezoidal_score(5.0, banded) < 0.5
    assert trapezoidal_score(13.0, banded) == 1.0      # inside is still inside
    assert trapezoidal_score(21.3, banded) == 0.0      # and high still counts


def test_the_closing_bound_is_the_bands_OWN_margin():
    """Not a number chosen here: a band allowing crit_high/opt_high = 20/14.5
    has stated its tolerance, and that ratio is mirrored."""
    b = _marker("R", crit_low=None, opt_low=10.0, opt_high=20.0, crit_high=30.0,
                low_is_deficiency=True)
    a, lo, hi, d = closed_band(b)
    assert a == pytest.approx(10.0 / (30.0 / 20.0))     # 6.667


def test_a_marker_NOT_flagged_keeps_its_open_side():
    """A low LDH is unremarkable, and the fix must not invent a finding."""
    ldh = next(b for p in ESRD_PATHWAYS if p.name == "Hematologic"
               for b in p.biomarkers if b.name == "LDH")
    assert not ldh.low_is_deficiency
    assert trapezoidal_score(30.0, apply_reference_range(ldh, (120, 246))) == 1.0


def test_a_marker_with_no_margin_to_mirror_is_left_open():
    b = _marker("R", crit_low=None, opt_low=10.0, opt_high=20.0, crit_high=None,
                low_is_deficiency=True)
    assert closed_band(b)[0] is None


# ── Ω is health, Α is management, and they are not the same question ────────

# Enough of the construct to clear the evidence quorum — a thin panel is now
# answered with None rather than a number, which these tests are not about.
_PANEL = {"Hemoglobin": 11.3, "Ferritin": 197.0, "Iron Saturation (TSAT)": 14.0,
          "PTH (Intact)": 17.0, "Phosphorus": 3.6, "Calcium": 8.9,
          "Creatinine": 8.23, "KtV (Dialysis Adequacy)": 1.47,
          "URR (Urea Reduction Ratio)": 74.0,
          "Glucose": 95.0, "Sodium": 140.0, "Potassium": 4.2,
          "CO2 (Bicarbonate)": 26.0, "Hematocrit": 38.3, "RBC": 4.67,
          "MCV": 88.0, "RDW": 13.0, "WBC": 6.0, "LDH": 180.0,
          "CaxP Product": 32.0, "Iron (Serum)": 90.0, "Albumin": 4.2,
          "BUN": 14.0, "nPCR (Protein Catabolic Rate)": 1.1}


def test_a_MANAGEMENT_pathway_is_not_in_the_health_score():
    """Operator: *"wellness is about the state of health."*

    A well person has no Kt/V — they have kidneys. `Dialysis_Adequacy` scored
    **97%** inside Ω, so "needs dialysis six days a week" read as near-perfect
    wellness.
    """
    omega = compute_hebcs(dict(_PANEL))
    assert "Dialysis_Adequacy" not in omega["pathways"]
    alpha = compute_alpha(dict(_PANEL))
    assert alpha["pathways"]["Dialysis_Adequacy"]["score"] == 1.0


def test_rebuilding_a_pathway_must_not_lose_its_scope():
    """`compute_hebcs` reconstructs every Pathway when a lab range is supplied,
    which is every real call. Dropping `scope=` there silently readmitted
    Dialysis_Adequacy to Ω — a field set in one place and reset in another."""
    omega = compute_hebcs(dict(_PANEL),
                          reference_ranges={"Hemoglobin": (14, 18)})
    assert "Dialysis_Adequacy" not in omega["pathways"]


def test_CREATININE_is_scored_and_is_the_largest_health_deficit():
    """It was absent from the engine entirely, though the published Table 3
    lists it and the record holds it on every panel. 8.23 against a well
    adult's 0.6-1.3 is zero renal function."""
    names = {b.name for p in ESRD_PATHWAYS for b in p.biomarkers}
    assert "Creatinine" in names
    cr = next(b for p in ESRD_PATHWAYS for b in p.biomarkers
              if b.name == "Creatinine")
    assert trapezoidal_score(8.23, scoring_marker(cr, "health")) == 0.0
    assert scoring_marker(cr, "management") is None, "nobody treats TO a creatinine"


def test_a_patient_with_NO_condition_has_no_management_score():
    """Operator: *"A healthy person with zero conditions and demonstrated health
    records need no management score."*

    `None`, never 0 — there is nothing to manage, which is not bad management.
    """
    out = compute_alpha(dict(_PANEL), has_managed_condition=False)
    assert out["alpha"] is None and out["alpha_pct"] is None
    assert out["reason"]


def test_the_two_scores_answer_differently_on_one_panel():
    """The pair is the finding: gravely ill AND impeccably managed is a real
    and common state, and one number could report neither."""
    omega = compute_hebcs(dict(_PANEL))["omega"]
    alpha = compute_alpha(dict(_PANEL))["alpha"]
    assert omega is not None and alpha is not None
    # Kt/V and URR are perfect; creatinine is zero. They must not coincide.
    assert abs(omega - alpha) > 0.01


# ── Ω must be responsive to the patient, not a constant ESRD decomposition ──
#
# Operator, 2026-10-12: *"Also omega must be responsive to patient and not force
# people without conditions to be measured as if they have conditions. This is
# the wheelhouse of adaptive, intelligent mathematical modeling."*

def test_a_urine_RBC_is_not_a_blood_count():
    """The sharpest form of the complaint, found on a production account with
    **46 labs and zero conditions, scored at Ω 27.38%**.

    `RBC = 0` drawn beside AMORPHOUS SEDIMENT, BACTERIA, GRANULAR CAST,
    NITRITE, SPECIFIC GRAVITY and LEUKOCYTE ESTERASE is **zero red cells per
    high-power field in the urine** — the ideal result. It resolved to the
    Hematologic blood count and scored 0.000: no red blood cells in the body.
    Being the only Hematologic value present it carried the pathway alone, and
    a healthy person's best possible urine test reported them at 27% wellness.
    """
    from app.services.hebcs_engine import urinalysis_draws

    draw = datetime(2022, 1, 11)
    panel = [
        ("RBC", 0.0, draw, None, None),
        ("SPECIFIC GRAVITY", 1.013, draw, 1.001, 1.035),
        ("NITRITE", 1.0, draw, None, None),
        ("LEUKOCYTE ESTERASE", 1.0, draw, None, None),
    ]
    assert draw.date() in urinalysis_draws(panel)
    picked = select_latest_per_analyte(panel)
    assert "RBC" not in picked, "a urine microscopy count is not a blood count"


def test_a_BLOOD_panel_still_scores_its_RBC():
    """The guard must not eat a real blood count. Mis-identifying a blood panel
    as urine would discard a genuine haemoglobin — far worse than the bug."""
    draw = datetime(2026, 10, 1)
    panel = [("RBC", 4.67, draw, 4.6, 6.2),
             ("Hemoglobin", 11.3, draw, 14, 18)]
    picked = select_latest_per_analyte(panel)
    assert picked["RBC"][1] == 4.67


def test_ONE_urinalysis_marker_is_not_enough_to_condemn_a_panel():
    """A lone "BACTERIA" or "COLOR" row could be a stray. The quorum is two."""
    from app.services.hebcs_engine import urinalysis_draws

    draw = datetime(2026, 10, 1)
    assert draw.date() not in urinalysis_draws(
        [("RBC", 4.67, draw, 4.6, 6.2), ("COLOR", 1.0, draw, None, None)])


def test_omega_is_WITHHELD_when_most_of_the_construct_is_unmeasured():
    """Measured: user 158, five labs, two markers, coverage 0.069, reported
    **Ω 99.9%** — "you will live forever", from five numbers.

    `None` is the same answer already given for a patient with no labs at all,
    where returning 0.5 described nobody. Scaling weights alone could not fix
    this: the mean renormalises, so a uniform reduction cancels out.
    """
    paths = [Pathway("A", [_marker(f"a{i}") for i in range(5)], weight=0.5),
             Pathway("B", [_marker(f"b{i}") for i in range(5)], weight=0.5)]
    # Only one pathway, on 2 of its 5 markers → a minority of the construct.
    thin = omega_score({"A": 1.0, "B": None}, paths, measured_counts={"A": 2})
    assert thin is None

    # The same pathways, fully measured, still score.
    full = omega_score({"A": 1.0, "B": 1.0}, paths,
                       measured_counts={"A": 5, "B": 5})
    assert full is not None and full > 0.9


def test_a_pathway_on_one_marker_of_nine_does_not_speak_for_all_nine():
    """User 60: Hematologic 0.001 off ONE of nine markers, carrying the full
    0.15 while four other pathways scored 1.000 and were buried."""
    from app.services.hebcs_engine import evidence_weight

    nine = Pathway("H", [_marker(f"m{i}") for i in range(9)], weight=0.15)
    assert evidence_weight(nine, 1) < 0.15
    assert evidence_weight(nine, 9) == 0.15


def test_a_well_person_is_not_EXPECTED_to_hold_renal_monitoring_tests():
    """PTH, ferritin, TSAT, nPCR and Ca×P are renal monitoring markers. A
    patient with no renal condition has no reason to have them drawn, and
    counting their absence as missing evidence reported a healthy record as
    incomplete — and, once coverage began bounding Ω, would withhold their
    score for not holding tests nobody should have ordered."""
    from app.services.hebcs_engine import pathways_for

    class _C:
        def __init__(self, name): self.name = name; self.icd11_title = ""

    well = {b.name for p in pathways_for([]) for b in p.biomarkers}
    renal = {b.name for p in pathways_for([_C("End-Stage Renal Disease")])
             for b in p.biomarkers}
    assert "PTH (Intact)" in renal and "PTH (Intact)" not in well
    assert "Ferritin" in renal and "Ferritin" not in well
    # …and the universal markers are expected of everybody.
    for common in ("Hemoglobin", "Creatinine", "Sodium", "Albumin"):
        assert common in well and common in renal


def test_the_WEIGHTS_do_not_vary_by_condition():
    """Ω is an absolute scale — the operator fixed both ends: perfect health is
    100, a dead person is 0. Two people with identical biology must therefore
    score the same, so a decomposition that re-weighted itself per diagnosis
    would make Ω incomparable between patients and against a patient's own
    past. Weighting by disease is what Α is for."""
    from app.services.hebcs_engine import pathways_for

    class _C:
        def __init__(self, name): self.name = name; self.icd11_title = ""

    well = {p.name: p.weight for p in pathways_for([])}
    renal = {p.name: p.weight for p in pathways_for([_C("ESRD")])}
    assert well == renal


def test_exactly_half_the_construct_is_NOT_a_majority():
    """The quorum is "more than half", so a dead heat is withheld. At exactly
    half, whether the unmeasured half would change the answer is a coin flip,
    and a score that could go either way is not a measurement."""
    paths = [Pathway("X", [], weight=0.5), Pathway("Y", [], weight=0.5)]
    assert omega_score({"X": 1.0, "Y": None}, paths) is None
