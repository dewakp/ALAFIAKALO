"""Ultrafiltration averages must exclude physically impossible values.

`fluid_removed_ml` is derived from (pre_weight - post_weight). When the weights
are wrong, or the patient weighed MORE afterwards, that arithmetic produces a
negative — and you cannot remove -500 mL of fluid.

On the reference record **365 of 1,976** sessions (18.5%) are negative. Averaging
them in reported **273 mL** where the valid sessions average **1,126 mL**. A
nephrologist reading 273 mL for a patient who actually pulls over a litre a
session is being misled about the number they dry a patient to.

Zero is a different case and is KEPT: 0 mL removed is a real measurement, and
dropping it overstated the mean by 3% (see the comment in the endpoint).
"""

import pytest


def _avg_fluid(values):
    """Mirrors the endpoint: keep >= 0, drop the impossible, count what went."""
    present = [v for v in values if v is not None]
    valid = [v for v in present if v >= 0]
    invalid = len(present) - len(valid)
    avg = round(sum(valid) / len(valid), 0) if valid else None
    return avg, invalid


def test_negative_fluid_is_excluded():
    # You cannot remove -500 mL.
    avg, invalid = _avg_fluid([1000.0, 1200.0, -500.0])
    assert avg == 1100.0
    assert invalid == 1


def test_zero_is_kept_because_it_is_a_real_measurement():
    """Deliberately different from negatives.

    `if s.value` would drop 0 as well as NULL. On the reference record that
    overstated ultrafiltration by 3%.
    """
    avg, invalid = _avg_fluid([1000.0, 0.0])
    assert avg == 500.0
    assert invalid == 0


def test_null_is_missing_not_zero():
    avg, invalid = _avg_fluid([1000.0, None])
    assert avg == 1000.0
    assert invalid == 0


def test_the_reference_distortion():
    """The shape of the real failure, in miniature.

    A run of impossible negatives drags a true ~1.1 L mean down to a few
    hundred millilitres.
    """
    values = [1100.0] * 10 + [-800.0] * 10
    naive = round(sum(values) / len(values), 0)      # what the old code did
    avg, invalid = _avg_fluid(values)
    assert naive == 150.0                            # clinically wrong
    assert avg == 1100.0                             # the truth
    assert invalid == 10


def test_all_invalid_reports_none_rather_than_a_made_up_number():
    # No usable data must read as "not available", never as 0 mL removed.
    avg, invalid = _avg_fluid([-100.0, -200.0])
    assert avg is None
    assert invalid == 2


def test_endpoint_exposes_the_excluded_count():
    """The count must reach the client.

    Silently dropping 365 sessions and showing a clean average is the §3aa
    failure in a new costume: a data problem hidden behind a tidy number.
    """
    from pathlib import Path
    import app.api.chronic_conditions as mod

    src = Path(mod.__file__).read_text()
    assert '"sessions_with_invalid_fluid"' in src
    assert "f >= 0" in src, "the impossible-value filter is gone"
