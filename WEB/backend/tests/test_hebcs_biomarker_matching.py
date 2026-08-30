"""HEBCS matched stored lab names verbatim, so seven biomarkers never scored.

`compute_hebcs` looked up `Biomarker.name` in a dict the caller keys by the raw
`lab_results.test_name`. The values were in the table the whole time under a
different spelling:

    HEBC expects                     actually stored
    KtV (Dialysis Adequacy)          spKt/V, eKt/V, stdKt/V, KT/V PRESCRIBED
    URR (Urea Reduction Ratio)       URR, URR%
    nPCR (Protein Catabolic Rate)    nPCR, NPCR
    CO2 (Bicarbonate)                CO2
    Iron (Serum)                     Iron
    Iron Saturation (TSAT)           Iron Saturation

The damage was worst where it mattered most. **Dialysis_Adequacy matched
nothing**, so on a patient with 730 sessions the one pathway that says whether
dialysis is working was dropped from a score still presented as whole-patient —
and on the reference record the delivered spKt/V had fallen to 0.9, far below
the KDOQI target. A score cannot warn about a pathway it never evaluated.
"""

import pytest

from app.services.hebcs_engine import compute_hebcs, resolve_biomarkers


def test_stored_names_resolve_to_biomarkers():
    resolved = resolve_biomarkers({
        "spKt/V": 1.4, "URR%": 69.8, "CO2": 26.7,
        "Iron": 74.0, "Iron Saturation": 26.0, "NPCR": 1.1,
    })
    assert resolved["KtV (Dialysis Adequacy)"] == 1.4
    assert resolved["URR (Urea Reduction Ratio)"] == 69.8
    assert resolved["CO2 (Bicarbonate)"] == 26.7
    assert resolved["Iron (Serum)"] == 74.0
    assert resolved["Iron Saturation (TSAT)"] == 26.0
    assert resolved["nPCR (Protein Catabolic Rate)"] == 1.1


def test_prescribed_ktv_is_not_treated_as_delivered():
    """The prescription is not what the patient received.

    Same trap as `therapy_sessions.blood_flow_rate` being a flat 350: reading
    the ordered value and calling it the outcome. On the reference record the
    prescription read 1.1 while the delivered spKt/V was 0.9.
    """
    resolved = resolve_biomarkers({"KT/V PRESCRIBED": 1.53})
    assert "KtV (Dialysis Adequacy)" not in resolved
    assert resolved["KT/V PRESCRIBED"] == 1.53


def test_other_ktv_scales_are_not_conflated():
    """eKt/V and stdKt/V have different adequacy targets on different scales."""
    resolved = resolve_biomarkers({"eKt/V": 0.75, "stdKt/V (Dial)": 3.97})
    assert "KtV (Dialysis Adequacy)" not in resolved


def test_inadequate_dialysis_is_actually_scored():
    """The regression: this pathway used to contribute nothing at all."""
    result = compute_hebcs({"spKt/V": 0.9, "URR%": 81.0})
    adequacy = result["pathways"]["Dialysis_Adequacy"]

    assert adequacy["score"] is not None, "the pathway must not vanish"
    # 0.9 sits between crit_low 0.8 and opt_low 1.4 — a low score, not a blank.
    assert adequacy["score"] < 0.6
    assert "Dialysis_Adequacy" not in result["unscored_pathways"]


def test_a_pathway_reports_how_much_of_it_was_measured():
    """A score renormalised over part of its evidence must say so.

    Nutritional is albumin (0.40) + nPCR (0.40) + BUN (0.20). With nPCR
    unmatched, albumin and BUN carried the whole pathway to 100% — which is how
    a malnourished patient was shown "Nutrition 100%".
    """
    result = compute_hebcs({"Albumin": 4.1, "BUN": 20.0})
    nutritional = result["pathways"]["Nutritional"]

    # Both present markers are normal, so the pathway reads 100% — on 60% of
    # its evidence. (This case used to pass with BUN 70, which the old band
    # scored as optimal; it is now 0.39, so the fixture uses a genuinely
    # normal BUN to isolate what this test is about: coverage reporting.)
    assert nutritional["score"] == 1.0
    # …but the number now travels with the fact that 40% of it is missing.
    assert nutritional["coverage"] == pytest.approx(0.6, abs=0.01)
    assert nutritional["measured"] == 2
    assert nutritional["expected"] == 3


def test_an_unmeasured_pathway_is_named_not_silently_dropped():
    """Omega is a geometric mean over what scored; blanks must be visible."""
    result = compute_hebcs({"Albumin": 4.1})
    assert "Dialysis_Adequacy" in result["unscored_pathways"]
    assert result["pathways"]["Dialysis_Adequacy"]["score"] is None
    assert result["pathways"]["Dialysis_Adequacy"]["coverage"] == 0.0


def test_caxp_is_derived_from_its_factors():
    """Ca×P is a product, never a row in a lab report."""
    result = compute_hebcs({"Calcium": 9.0, "Phosphorus": 5.5})
    bone = result["pathways"]["Bone_Mineral"]
    caxp = next(b for b in bone["biomarkers"] if b["name"] == "CaxP Product")
    assert caxp["value"] == pytest.approx(49.5)


def test_canonical_names_still_work():
    """A caller already speaking canonical names must be unaffected."""
    resolved = resolve_biomarkers({"Albumin": 4.1, "Potassium": 5.0})
    assert resolved["Albumin"] == 4.1
    assert resolved["Potassium"] == 5.0


def test_an_unknown_analyte_is_passed_through_not_dropped():
    resolved = resolve_biomarkers({"Some Novel Assay": 42.0})
    assert resolved["Some Novel Assay"] == 42.0


# ── BUN: judged against the lab's own reference range ─────────────────────

def test_bun_is_scored_against_the_reference_range_not_the_disease_state():
    """Two wrong bands preceded this one.

    `crit_low=None, opt_low=0` scored ANY BUN from 0 to 80 as perfect — a BUN of
    5 is starvation, not health. Widening the optimum to 23-80 then asserted the
    opposite: that a pre-dialysis BUN of 70 is optimal. It is not. Normal is
    7-20 mg/dL (6-21 female, 8-24 male), and this record's own labs report 7-23.
    """
    from app.services.hebcs_engine import ESRD_PATHWAYS, trapezoidal_score

    bun = next(b for p in ESRD_PATHWAYS for b in p.biomarkers if b.name == "BUN")
    assert bun.low_is_deficiency is True
    assert bun.crit_low is not None, "a BUN of zero cannot be optimal"

    # The FALLBACK band is the general-adult range, 7-20. It applies only when
    # no lab range was reported; see the reference-range tests below.
    assert (bun.opt_low, bun.opt_high) == (7.0, 20.0)

    assert trapezoidal_score(15.0, bun) == 1.0     # squarely normal
    assert trapezoidal_score(5.0, bun) < 1.0       # undernutrition, not health

    # Above the range urea is toxic, and the score has to say so. Earlier bands
    # scored 22 — and even 70 — as perfect.
    assert trapezoidal_score(22.0, bun) < 1.0
    assert trapezoidal_score(31.0, bun) < 0.6      # the worst residual observed
    assert trapezoidal_score(70.0, bun) == 0.0     # marked uraemia


def test_clearance_happening_is_not_the_same_as_a_safe_residual():
    """Pre-minus-post measures CLEARANCE. It does not mean the result is safe.

    URR and Kt/V score the reduction, and a session can hit its adequacy target
    while still leaving the patient toxic: on this record 2025-08-18 had URR 74%
    and a post-dialysis BUN of 25, and 8 of 11 post draws sit above 21. The
    residual is what the patient lives with between sessions, so it is scored on
    its own terms rather than credited for the drop.
    """
    from app.services.hebcs_engine import ESRD_PATHWAYS, trapezoidal_score

    bun = next(b for p in ESRD_PATHWAYS for b in p.biomarkers if b.name == "BUN")
    adequate_clearance_but_toxic = trapezoidal_score(25.0, bun)
    genuinely_clear = trapezoidal_score(17.0, bun)

    assert genuinely_clear == 1.0
    assert adequate_clearance_but_toxic < genuinely_clear


def test_the_post_dialysis_draw_is_the_one_that_gets_scored():
    """Pre-dialysis BUN is the uraemic burden BEFORE treatment.

    On this record pre averages 71.6 (range 15-115) while post averages
    20.4-22.6 — inside the lab's 7-23. Scoring the pre value against a normal
    range would mark every dialysis patient critically abnormal for not yet
    having been dialysed, and would double-count clearance, which URR and Kt/V
    already measure in Dialysis_Adequacy.

    Dict order in the caller is arbitrary, so without an explicit preference
    this silently depended on which name happened to come first.
    """
    from app.services.hebcs_engine import resolve_biomarkers

    resolved = resolve_biomarkers({
        "BUN": 70.0, "BUN Post": 31.0, "BUN-P": 22.0, "BUN - Post": 25.0})
    assert resolved["BUN"] in (22.0, 31.0, 25.0), "the post draw must win"
    assert resolved["BUN"] != 70.0

    # …and the preference holds whichever order the caller supplies.
    reversed_order = resolve_biomarkers({"BUN-P": 22.0, "BUN": 70.0})
    assert reversed_order["BUN"] == 22.0


def test_a_pre_dialysis_only_record_still_scores():
    """A patient with no post draw must not lose the biomarker entirely."""
    from app.services.hebcs_engine import resolve_biomarkers

    assert resolve_biomarkers({"BUN": 70.0})["BUN"] == 70.0


def test_the_optimal_window_comes_from_the_reported_range_not_a_constant():
    """There is no single optimal BUN, so the engine must not name one.

    Normal is 7-20 in children, 6-21 in adult females and 8-24 in adult males,
    and a reporting lab states its own — 9-23 on this record. An earlier band
    wrote 21 into the engine, which is the adult FEMALE ceiling, and applied it
    to a male patient.
    """
    from app.services.hebcs_engine import (
        ESRD_PATHWAYS, apply_reference_range, trapezoidal_score,
    )

    bun = next(b for p in ESRD_PATHWAYS for b in p.biomarkers if b.name == "BUN")
    lab = apply_reference_range(bun, (9.0, 23.0))
    male = apply_reference_range(bun, (8.0, 24.0))

    assert (lab.opt_low, lab.opt_high) == (9.0, 23.0)
    assert (male.opt_low, male.opt_high) == (8.0, 24.0)
    # The critical margins scale with the window rather than staying fixed.
    assert lab.crit_high > bun.crit_high
    assert lab.crit_low > bun.crit_low

    # 23 is the top of THIS lab's range and abnormal under the child range.
    assert trapezoidal_score(23.0, lab) == 1.0
    assert trapezoidal_score(23.0, bun) < 1.0


def test_a_biomarker_with_no_reported_range_keeps_its_published_band():
    from app.services.hebcs_engine import ESRD_PATHWAYS, apply_reference_range

    bun = next(b for p in ESRD_PATHWAYS for b in p.biomarkers if b.name == "BUN")
    for junk in ((None, 23.0), (9.0, None), (None, None), (0.0, 23.0), (23.0, 9.0)):
        assert apply_reference_range(bun, junk) == bun, junk


def test_reference_ranges_reach_the_score():
    from app.services.hebcs_engine import compute_hebcs

    strict = compute_hebcs({"Albumin": 4.1, "BUN": 22.0})
    per_lab = compute_hebcs({"Albumin": 4.1, "BUN": 22.0},
                            reference_ranges={"BUN": (9.0, 23.0)})
    assert per_lab["pathways"]["Nutritional"]["score"] > \
        strict["pathways"]["Nutritional"]["score"]


def test_a_patient_with_no_labs_gets_no_score_rather_than_fifty():
    """omega_score returned 0.5 when nothing scored, so an account holding zero
    results was shown a wellness score of 50% — a number describing nobody,
    where a clinician reads a measurement.

    Found on the DEPLOYED service against a real account, not by a unit test.
    """
    from app.services.hebcs_engine import compute_hebcs

    empty = compute_hebcs({})
    assert empty["omega"] is None
    assert empty["omega_pct"] is None
    assert len(empty["unscored_pathways"]) == 7

    # …and a patient who does have results still scores.
    scored = compute_hebcs({"Albumin": 4.1, "BUN": 17.0})
    assert scored["omega_pct"] is not None
