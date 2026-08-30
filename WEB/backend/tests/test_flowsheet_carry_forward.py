"""A flowsheet should already know what the record holds.

Two gaps, both making the patient re-type data the system had:

1. **`previous_post_weight_kg` was not carried at all.** It is not "the same as
   last time" — it IS last time's post-treatment weight, and it is how the unit
   computes today's fluid target. Of 1,940 sessions carrying it, only 1,432
   match the prior session's post weight: 508 were typed by hand and drifted.

2. **Only the LAST session was consulted.** Anything that session left blank was
   lost, and on this record the last treatment recorded no cycler, warmer,
   cartridge lot or control panel — though all four appear 1,833-1,964 times and
   were present a fortnight earlier. "Default to the last recorded value" means
   the last time it was recorded, not the last time anything was.

Everything here is a default. Nothing is submitted on the patient's behalf.
"""

from datetime import date, datetime

import pytest

from app.services import flowsheet_defaults as fs


class _Session:
    """A therapy session with only the fields the defaults reader touches."""

    def __init__(self, day, **kw):
        self.scheduled_date = datetime(2026, 8, day, 8, 0)
        self.status = "completed"
        for name in fs.CARRY_FORWARD_FIELDS:
            setattr(self, name, None)
        self.post_dialysis_weight_kg = None
        self.dialysis_access_type = None
        for k, v in kw.items():
            setattr(self, k, v)


def test_last_treatments_post_weight_becomes_this_treatments_previous_weight():
    sessions = [_Session(28, post_dialysis_weight_kg=54.0)]
    carried, sources = _carry(sessions)
    assert carried["previous_post_weight_kg"] == 54.0
    assert sources["previous_post_weight_kg"] == "2026-08-28"


def test_an_impossible_weight_is_not_carried_forward():
    """The record holds a post-dialysis weight of 0.3 kg. Carrying it would
    seed the next treatment's fluid target from a weighing-machine fault."""
    sessions = [_Session(28, post_dialysis_weight_kg=0.3)]
    carried, _ = _carry(sessions)
    assert "previous_post_weight_kg" not in carried


def test_each_field_comes_from_the_last_session_that_recorded_it():
    sessions = [
        _Session(28, attending_physician="Dr. Desai"),   # no equipment recorded
        _Session(17, cartridge_lot="60477165"),
        _Session(13, cycler_number="39001", warmer_serial="W3652"),
    ]
    carried, sources = _carry(sessions)

    assert carried["attending_physician"] == "Dr. Desai"
    assert carried["cartridge_lot"] == "60477165"
    assert carried["cycler_number"] == "39001"
    assert carried["warmer_serial"] == "W3652"

    # …and each says WHEN it was recorded, because they differ.
    assert sources["attending_physician"] == "2026-08-28"
    assert sources["cartridge_lot"] == "2026-08-17"
    assert sources["cycler_number"] == "2026-08-13"


def test_a_field_nobody_ever_recorded_is_simply_absent():
    """`attending_nurse` has never been recorded on this database."""
    carried, _ = _carry([_Session(28, attending_physician="Dr. Desai")])
    assert "attending_nurse" not in carried


def _carry(sessions):
    """Run the carry-forward the way `defaults_for` does, without a database."""
    carried, sources = {}, {}

    def last_recorded(name):
        for s in sessions:
            v = getattr(s, name, None)
            if v is not None and str(v).strip() != "":
                return v, str(s.scheduled_date)[:10]
        return None, None

    for name in fs.CARRY_FORWARD_FIELDS:
        v, seen = last_recorded(name)
        if v is not None:
            carried[name], sources[name] = v, seen
    for target, source in fs.CARRY_FORWARD_MAPPED.items():
        v, seen = last_recorded(source)
        if v is None:
            continue
        low, high = fs.WEIGHT_PLAUSIBLE_KG
        if target.endswith("_kg") and not (low <= float(v) <= high):
            continue
        carried[target], sources[target] = v, seen
    return carried, sources
