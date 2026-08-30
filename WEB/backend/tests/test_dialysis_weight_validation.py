"""Implausible weights must not enter, because everything downstream trusts them.

Nothing bounded these fields, and the record still carries what got in: a
POST-dialysis weight of **0.3 kg**, and pre-dialysis weights of **3.5** and
**4.7 kg**. Those are weighing-machine faults, not people.

`fluid_removed_ml` is (pre - post) x 1000, so a bad weight becomes a bad fluid
figure and then a bad average: the clinician dashboard's "average fluid removed"
reads **608 ml against a true 663 ml** on this record, because nine rows of
garbage sit inside the mean.

These are PHYSICAL plausibility bounds — is this a human being — not clinical
reference ranges. Clinical thresholds are resolved from reported data
(`test_no_hardcoded_thresholds.py`).
"""

from datetime import datetime

import pytest
from pydantic import ValidationError

from app.schemas.chronic_conditions import TherapySessionBase

BASE = dict(therapy_type="hemodialysis", scheduled_date=datetime(2026, 1, 5, 8, 0))


def _session(**kw):
    return TherapySessionBase(**{**BASE, **kw})


def test_an_ordinary_session_is_accepted():
    s = _session(pre_dialysis_weight_kg=61.2, post_dialysis_weight_kg=59.0,
                 fluid_removed_ml=2200)
    assert s.fluid_removed_ml == 2200


def test_saline_return_is_accepted_as_a_negative():
    """365 of 1775 sessions here have net negative fluid. Not an anomaly."""
    s = _session(pre_dialysis_weight_kg=48.0, post_dialysis_weight_kg=49.0,
                 fluid_removed_ml=-1000)
    assert s.fluid_removed_ml == -1000


@pytest.mark.parametrize("kw", [
    dict(post_dialysis_weight_kg=0.3),      # the value actually in the record
    dict(pre_dialysis_weight_kg=4.7),
    dict(pre_dialysis_weight_kg=3.5),
    dict(post_dialysis_weight_kg=901.0),
])
def test_a_weight_that_is_not_a_person_is_refused(kw):
    with pytest.raises(ValidationError):
        _session(**kw)


@pytest.mark.parametrize("fluid", [60900, -59800, 10400, -10200])
def test_fluid_beyond_a_tenth_of_body_mass_is_refused(fluid):
    """Checked against the patient's own weight, not a fixed number of litres,
    and applied in BOTH directions."""
    with pytest.raises(ValidationError):
        _session(pre_dialysis_weight_kg=61.2, post_dialysis_weight_kg=60.0,
                 fluid_removed_ml=fluid)


def test_weights_that_disagree_with_each_other_are_refused():
    with pytest.raises(ValidationError):
        _session(pre_dialysis_weight_kg=69.2, post_dialysis_weight_kg=58.8)


def test_a_session_without_weights_is_still_valid():
    """Most fields are optional; validation must not require them."""
    assert _session().fluid_removed_ml is None
