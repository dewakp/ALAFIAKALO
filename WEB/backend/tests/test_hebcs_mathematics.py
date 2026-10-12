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
    omega_score,
    pathway_score,
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

def test_a_TREATMENT_TARGET_refuses_the_labs_healthy_adult_band():
    pth = next(b for p in ESRD_PATHWAYS if p.name == "Bone_Mineral"
               for b in p.biomarkers if b.name == "PTH (Intact)")
    assert pth.is_treatment_target and pth.authority
    assert apply_reference_range(pth, (18, 80)) is pth


def test_PTH_24_on_dialysis_is_not_perfect_health():
    """24 pg/mL in a stage-5D patient is adynamic bone disease. Under the lab's
    18-80 it scored 1.000, and Bone Mineral reported 100%."""
    pth = next(b for p in ESRD_PATHWAYS if p.name == "Bone_Mineral"
               for b in p.biomarkers if b.name == "PTH (Intact)")
    assert trapezoidal_score(24.0, apply_reference_range(pth, (18, 80))) < 0.1


def test_the_override_was_wrong_in_BOTH_directions():
    """Which is what makes it the mechanism's fault, not the numbers'.

    Haemoglobin 12.0 is AT the KDIGO 10-12 target; against the lab's
    healthy-adult 14-18 it scored 0.524, and chasing 14-18 on ESA is what the
    TREAT and CHOIR trials showed raises mortality.
    """
    hgb = next(b for p in ESRD_PATHWAYS if p.name == "Hematologic"
               for b in p.biomarkers if b.name == "Hemoglobin")
    assert trapezoidal_score(12.0, apply_reference_range(hgb, (14, 18))) == 1.0


def test_an_ordinary_analyte_still_takes_the_labs_own_range():
    """The exception must stay narrow. There is no single optimal sodium, and
    the reporting lab's interval is better evidence than a constant."""
    na = next(b for p in ESRD_PATHWAYS if p.name == "Metabolic"
              for b in p.biomarkers if b.name == "Sodium")
    assert not na.is_treatment_target
    assert apply_reference_range(na, (134, 148)).opt_high == 148.0


def test_every_declared_target_cites_its_guideline():
    """§3bc: an uncited quota is REFUSED. A target with no authority is a
    number someone typed."""
    for p in ESRD_PATHWAYS:
        for b in p.biomarkers:
            if b.is_treatment_target:
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
    paths = [Pathway("X", [], weight=0.5), Pathway("Y", [], weight=0.5)]
    both_fine = omega_score({"X": 1.0, "Y": 1.0}, paths)
    one_dead = omega_score({"X": 1.0, "Y": 0.0}, paths)
    one_absent = omega_score({"X": 1.0, "Y": None}, paths)
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
