"""A haematocrit of 338% is impossible. A creatinine of 11.91 is Tuesday.

THE ROW THIS EXISTS FOR. A production record carried

    HGBX   338.4 %   reference 42 - 52     shown to the patient as "Normal"

The true value is 38.4%. The analyte is HCT CALC (HGBX3) — haematocrit
calculated as haemoglobin x 3 — and that day's haemoglobin was 12.8, so
12.8 x 3 = 38.4 exactly. A literal "3" had moved from the end of the NAME to the
front of the VALUE upstream, leaving the stored figure exactly 300 too high.
Three rows on that record carry the same signature, every one confirmed against
the source PDF:

    2025-01-27   stored 327.3   true 27.3   (HGB 9.1)
    2025-03-21   stored 324.6   true 24.6   (HGB 8.2)
    2025-07-17   stored 338.4   true 38.4   (HGB 12.8)

THE BOUNDARY THIS FILE DEFENDS. The tempting guard is "flag anything far outside
its reference range". On the same record that flags creatinine 11.91 against a
0.7-1.3 range — 9.2x over, and exactly what end-stage renal disease looks like.
Fifteen legitimate creatinines sit between 5x and 9.2x. A guard that cries wolf
over a dialysis patient's creatinine teaches its reader to tick past it, which
is precisely how the 338.4 got approved in the first place.

So `test_real_clinical_extremes_are_accepted` is the half that matters.
"""

import pytest

from app.services.plausibility import review_lab_value


# ── Impossible: must never arrive pre-accepted ───────────────────────────────

@pytest.mark.parametrize("name,value,unit,lo,hi", [
    # The three real rows, exactly as stored.
    ("HGBX", 338.4, "%", 42.0, 52.0),
    ("HGBX", 327.3, "%", 42.0, 52.0),
    ("HGBX", 324.6, "%", 42.0, 52.0),
    # The unit column often has the status welded onto it.
    ("GRAN%", 640.0, "%Final", None, None),
])
def test_a_proportion_above_100_percent_is_refused(name, value, unit, lo, hi):
    warnings, believable = review_lab_value(name, value, unit, lo, hi)
    assert believable is False, f"{value}{unit} was accepted without comment"
    assert warnings, "a refusal that cannot explain itself gets ticked past"
    assert "100%" in " ".join(warnings)


def test_a_negative_result_is_refused():
    warnings, believable = review_lab_value("Potassium", -4.2, "mEq/L", 3.5, 5.5)
    assert believable is False
    assert "negative" in " ".join(warnings).lower()


def test_a_value_far_above_its_own_printed_ceiling_is_refused():
    """PTH-I 8,478 against 18-80 — 106x. The unified importer already singles
    this row out in prose; here it is refused instead of merely mentioned."""
    warnings, believable = review_lab_value("PTH-I", 8478.0, "pg/mL", 18.0, 80.0)
    assert believable is False
    assert warnings


# ── The half that matters: real clinical extremes must pass ──────────────────

@pytest.mark.parametrize("name,value,unit,lo,hi,why", [
    (
        "CRE", 11.91, "mg/dL", 0.7, 1.3,
        "9.2x over — end-stage renal disease, and the single most common "
        "out-of-range value on this whole record",
    ),
    ("Creatinine", 10.69, "mg/dL", 0.7, 1.3, "the same patient, a different month"),
    ("BUN", 115.0, "mg/dL", 7.0, 20.0, "5.75x — ordinary pre-dialysis urea"),
    ("K+", 6.7, "mEq/L", 3.5, 5.5, "hyperkalemia: dangerous, and entirely real"),
    ("LDH", 378.0, "U/L", 120.0, 246.0, "abnormal, not impossible"),
    ("HGB", 9.4, "g/dL", 11.7, 15.5, "anaemia — BELOW range, never suspicious"),
    ("HGBX", 38.4, "%", 42.0, 52.0, "the TRUE haematocrit, low but possible"),
    ("ISAT", 28.0, "%", 21.0, 49.0, "an ordinary percentage"),
    ("URR%", 72.0, "%", 65.0, None, "dialysis adequacy, a percentage in range"),
])
def test_real_clinical_extremes_are_accepted(name, value, unit, lo, hi, why):
    warnings, believable = review_lab_value(name, value, unit, lo, hi)
    assert believable is True, f"{name} {value} refused, but: {why}"
    assert warnings == [], f"{name} {value} warned about, but: {why}"


def test_a_missing_value_is_not_judged():
    """A qualitative result carries no number; that is not implausible."""
    assert review_lab_value("Hep B Ag", None, "", None, None) == ([], True)


def test_no_reference_range_means_no_range_check():
    """Most rows on a flowsheet print no range. Absence must not read as zero."""
    warnings, believable = review_lab_value("WEIGHT - PRE", 57.5, "kg", None, None)
    assert (warnings, believable) == ([], True)
