# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""An ordered dry weight the rest of the record disagrees with.

This exists because the alternative shipped. Session 2776 arrived from a DaVita
Treatment Details Report ordering a target weight of **50.0 kg**, against the
38 treatments before it recording 53.2-54.8. The discrepancy was preserved by
typing a paragraph into `patient_notes` — with the comparison, an instruction
to raise it with the care team, and a note about which columns had been left
NULL and why. Operator, 2026-10-12: *"this is not patient notes but your own
debate."*

Two things were wrong with that, and only the first is about tidiness:

1. A chart field held an analysis of the chart. No query can reach it, it
   cannot update when the record does, and it reads as though the unit wrote
   it.
2. **The arithmetic in it was wrong.** It said "3.3-4.4 kg below" while citing
   the range 53.2-54.8 — which gives 3.2 and 4.8. A figure nobody can
   recompute is a figure nobody can correct, and that is the whole argument
   for deriving it (§3av: run the scan, never the arithmetic).

The target weight is what the machine's ultrafiltration volume is computed
from, so this is not bookkeeping: an order 3.2 kg low asks the treatment to
remove three extra litres from a patient whose record already shows 35 of 37
treatments dropping below 90 mmHg systolic.
"""

from app.services.health_score import (
    MIN_DRY_WEIGHTS_TO_COMPARE,
    _dry_weight_disagreement,
    dialysis_component,
)

#: The real shape, read off production 2026-10-12: 38 treatments since
#: 2026-07-01 ranging 53.2-54.8, then session 2776 ordering 50.0.
_PRODUCTION_RANGE = [53.2, 53.3, 53.2, 53.5, 53.6, 53.8, 54.0, 54.8]


def _series(values, start_day=1):
    return [(f"2026-09-{start_day + i:02d}", v) for i, v in enumerate(values)]


# ── It fires on the case that caused this ───────────────────────────────────

def test_the_production_order_of_50_against_53_2_to_54_8_is_reported():
    out = _dry_weight_disagreement(
        _series([*_PRODUCTION_RANGE, 50.0]), window_days=90)
    assert out is not None, "a 50.0 kg order against a 53.2-54.8 record is the finding"
    finding, detail = out
    assert finding.kind == "dry_weight_disagrees_with_record"
    assert finding.domain == "dialysis"
    assert detail["ordered"] == 50.0
    assert detail["usual_range"] == [53.2, 54.8]


def test_the_difference_is_COMPUTED_and_the_hand_typed_one_was_wrong():
    """The note in the chart said "3.3-4.4 kg below" of a 53.2-54.8 range.

    53.2 - 50.0 is **3.2**, and 54.8 - 50.0 is 4.8. Both ends of the typed
    figure were wrong, in a field no query could check. This pins the computed
    answer rather than the remembered one.
    """
    finding, detail = _dry_weight_disagreement(
        _series([*_PRODUCTION_RANGE, 50.0]), window_days=90)
    assert detail["difference"] == 3.2
    assert finding.facts["usual_lowest"] == 53.2
    assert finding.facts["usual_highest"] == 54.8
    assert "3.3" not in finding.fallback and "4.4" not in finding.fallback


def test_the_finding_names_its_window_and_its_sample():
    """§3an: a count with no period is not a finding, and "the record" is not
    a denominator a reader can weigh."""
    finding, _ = _dry_weight_disagreement(
        _series([*_PRODUCTION_RANGE, 50.0]), window_days=90)
    assert finding.facts["window_days"] == 90
    assert finding.facts["treatments_compared"] == len(_PRODUCTION_RANGE)
    assert finding.facts["ordered_on"] == "2026-09-09"


def test_both_the_order_and_the_bound_are_ESSENTIAL():
    """Drop either and the sentence states no disagreement — "the dry weight
    ordered is 50 kg" is not a finding, and neither is "below the usual"."""
    finding, _ = _dry_weight_disagreement(
        _series([*_PRODUCTION_RANGE, 50.0]), window_days=90)
    assert set(finding.essential) == {"ordered_dry_weight", "usual_lowest"}


# ── And stays quiet on everything that is not it ────────────────────────────

def test_a_DELIBERATE_TAPER_is_silent():
    """A dry weight being reduced on purpose moves in steps well inside its own
    historical spread. A finding that fires on ordinary clinical management is
    one its reader learns to tick past (§3ab), and it would fire on every
    treatment of a patient being dried out."""
    tapering = [55.0, 54.8, 54.6, 54.4, 54.2, 54.0, 53.8, 53.6]
    assert _dry_weight_disagreement(_series(tapering), window_days=90) is None


def test_a_figure_INSIDE_the_range_is_silent():
    assert _dry_weight_disagreement(
        _series([*_PRODUCTION_RANGE, 54.0]), window_days=90) is None


def test_outside_the_range_but_by_LESS_than_its_width_is_silent():
    """The range here is 1.6 kg wide; 52.7 is 0.5 below it. Further than the
    record has been is not the same as further than it has ever travelled."""
    assert _dry_weight_disagreement(
        _series([*_PRODUCTION_RANGE, 52.7]), window_days=90) is None


def test_too_few_earlier_treatments_to_have_a_spread_is_silent():
    """Two points have a spread by arithmetic, not by observation."""
    short = [(f"2026-09-0{i + 1}", v) for i, v in enumerate([54.0, 54.2, 50.0])]
    assert _dry_weight_disagreement(short, window_days=90) is None
    assert len(short) < MIN_DRY_WEIGHTS_TO_COMPARE + 1


def test_no_dry_weights_at_all_is_silent_not_an_error():
    assert _dry_weight_disagreement(None, window_days=90) is None
    assert _dry_weight_disagreement([], window_days=90) is None


def test_an_order_ABOVE_the_record_is_reported_too():
    """A guard that only fires one way is not a guard (§3ac). A target weight
    set too HIGH under-removes fluid, which is how a patient arrives at the
    next treatment overloaded."""
    finding, detail = _dry_weight_disagreement(
        _series([*_PRODUCTION_RANGE, 58.0]), window_days=90)
    assert detail["direction"] == "above"
    assert finding.facts["difference"] == 3.2        # 58.0 - 54.8
    assert set(finding.essential) == {"ordered_dry_weight", "usual_highest"}


# ── It is a statement, not a measurement ────────────────────────────────────

def test_the_finding_does_not_move_the_DIALYSIS_SCORE():
    """A mis-ordered target weight is a disagreement between a prescription and
    a record. It says nothing about how well the patient is, and scoring it
    would make the number mean two things at once (§3ba)."""
    common = dict(sessions_in_window=36, window_days=90, baseline_per_week=2.9,
                  sessions_with_pressure=37, sessions_below_floor=35,
                  lowest_nadir=39.0, hypotension_floor=90.0)
    without = dialysis_component(**common)
    with_dw = dialysis_component(
        **common, dry_weights=_series([*_PRODUCTION_RANGE, 50.0]))
    assert with_dw.score == without.score
    kinds = [f.kind for f in with_dw.critical]
    assert "dry_weight_disagrees_with_record" in kinds
    assert "dry_weight_disagrees_with_record" not in [
        f.kind for f in without.critical]
