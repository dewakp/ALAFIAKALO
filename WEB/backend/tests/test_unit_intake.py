"""A value may travel with its unit; the backend converts. Never the patient.

The requirement: the patient's locale sets their default system, they choose a
preferred system in Profile and may toggle it freely, and a reading can arrive
in whatever unit the facility's device printed. The patient is not expected to
do the arithmetic.

What the code did instead: `PATCH /users/me` took a bare `height_cm: float`
with no unit and no bounds, and `core/units.py`'s `inches_to_cm` /
`pounds_to_kg` had **no callers anywhere in the codebase**. A patient entering
a height of 70 (inches) was stored as 70 cm, which then fed BMI and every
weight-derived nutrient target.
"""

import pytest

from app.core import units


# ── the conversion itself ──────────────────────────────────────────────


def test_height_in_inches_becomes_centimetres():
    # The value that was actually stored on a production record.
    assert units.to_canonical(70, "length", "in") == pytest.approx(177.8, abs=0.01)


def test_weight_in_pounds_becomes_kilograms():
    assert units.to_canonical(154, "mass", "lb") == pytest.approx(69.85, abs=0.01)


def test_no_unit_means_the_value_is_already_canonical():
    # The field name carries the unit. A client sending no unit is taken at its
    # word — NOT reinterpreted against the user's display preference, which
    # would turn a correct 170 cm into 431 cm the moment they toggled to
    # imperial.
    assert units.to_canonical(170, "length", None) == 170
    assert units.to_canonical(62, "mass", None) == 62


def test_canonical_unit_passes_through_unchanged():
    assert units.to_canonical(170, "length", "cm") == 170
    assert units.to_canonical(62, "mass", "kg") == 62


@pytest.mark.parametrize("spelling", ["in", "In", "INCH", "inches", '"'])
def test_unit_spellings_a_client_might_send(spelling):
    assert units.to_canonical(70, "length", spelling) == pytest.approx(177.8, abs=0.01)


@pytest.mark.parametrize("spelling", ["lb", "lbs", "Pounds", "POUND"])
def test_mass_spellings(spelling):
    assert units.to_canonical(154, "mass", spelling) == pytest.approx(69.85, abs=0.01)


def test_temperature_and_volume_route_through_the_same_door():
    assert units.to_canonical(98.6, "temperature", "F") == pytest.approx(37.0, abs=0.01)
    assert units.to_canonical(8, "volume", "fl oz") == pytest.approx(236.59, abs=0.01)


# ── an unreadable unit must fail, not be assumed ───────────────────────


def test_an_unrecognised_unit_raises_rather_than_assuming_metric():
    with pytest.raises(units.UnknownUnitError):
        units.to_canonical(70, "length", "furlongs")


def test_the_error_names_what_was_expected():
    with pytest.raises(units.UnknownUnitError) as exc:
        units.to_canonical(70, "length", "furlongs")
    assert "cm" in str(exc.value) and "in" in str(exc.value)


def test_none_value_stays_none():
    assert units.to_canonical(None, "length", "in") is None


# ── the helpers finally have callers ───────────────────────────────────


def test_locale_still_picks_the_default_system():
    assert units.units_for_locale("en-US") == units.IMPERIAL
    assert units.units_for_locale("en-GB") == units.METRIC
    assert units.units_for_locale(None, "United States") == units.IMPERIAL
    assert units.units_for_locale(None, "Nigeria") == units.METRIC


def test_round_trip_is_stable_enough_to_toggle_units_repeatedly():
    """A user toggling display units must not watch their height drift."""
    cm = 177.8
    for _ in range(5):
        inches = units.cm_to_inches(cm)
        cm = units.inches_to_cm(inches)
    assert cm == pytest.approx(177.8, abs=0.05)


# ── age decides, not a constant ────────────────────────────────────────


def test_70_is_a_real_height_for_a_toddler_and_impossible_for_an_adult():
    low, high = units.plausible_height_range_cm(1)
    assert low <= 70 <= high
    low, high = units.plausible_height_range_cm(52)
    assert not (low <= 70 <= high)


def test_a_bare_70_on_an_adult_is_read_as_inches():
    # The production row: a 52-year-old stored at 70 cm. 70 in = 177.8 cm.
    assert units.infer_length_unit(70, 52) == "in"


def test_the_same_70_on_a_one_year_old_is_left_alone():
    assert units.infer_length_unit(70, 1) is None


def test_an_ordinary_adult_height_is_never_reinterpreted():
    for cm in (150, 170, 177.8, 195):
        assert units.infer_length_unit(cm, 52) is None


def test_a_number_that_makes_sense_as_neither_is_not_guessed_at():
    # 400 is not a height in cm and not one in inches either. Silence is the
    # right answer; the endpoint rejects it separately.
    assert units.infer_length_unit(400, 52) is None


def test_unknown_age_falls_back_to_the_permissive_range():
    low, high = units.plausible_height_range_cm(None)
    assert low <= 70 <= high          # cannot rule it out without an age
    assert units.infer_length_unit(70, None) is None
