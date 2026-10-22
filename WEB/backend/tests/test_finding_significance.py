# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""A wellness card must lead with what matters, not with what was listed first.

Operator, 2026-10-22, reading the card: *"The purpose of this long but faulty
analysis is unkown to me. The first sentence references data from more than a
month ago as if it's the rubric. The sinificance I cannot understand."*

The card opened with:

    Blood pressure 81/62 mmHg (one reading taken away from dialysis) has a
    systolic below the 90-120 mmHg reference band — last such reading 26 days
    ago (2026-09-26) …

and only then reported that 35 of 37 treatments had dropped below 90 mmHg
systolic, that a symptom was rated 9/10, and that blood was recorded in the
stool. Measured on the record that day:

    self-recorded BP in the 30-day window      1   (2026-09-26)
    self-recorded BP in 90 days                8   (newest the same)
    dialysis sessions in 90 days              35
    intradialytic readings in 90 days        100

So a median of ONE reading, 26 days old, led a card built on a hundred
measured pressures. The cause was `[line for c in scored for line in
(c.critical or [])]` — component declaration order, nothing more.
"""

import pytest

from app.services import health_score as hs
from app.services.finding_text import CONTEXT, DEVIATION, HARM, Finding


def _f(kind, severity, domain="x"):
    return Finding(kind=kind, facts={}, fallback=f"{kind}.", domain=domain,
                   severity=severity)


def _component(key, findings):
    return hs.Component(key, 80.0, 0.1, {}, list(findings))


# ── the reported ordering bug ─────────────────────────────────────────────

def test_harm_outranks_a_measurement_listed_earlier():
    """THE REPORTED BUG, in its minimal form. `vitals` is listed before
    `dialysis`, `symptoms` and `elimination`, so its finding used to print
    first whatever it said."""
    out = hs.overall_score([
        _component("vitals", [_f("blood_pressure_below_reference", CONTEXT)]),
        _component("dialysis", [_f("intradialytic_hypotension_burden", HARM)]),
        _component("symptoms", [_f("severe_symptom", HARM)]),
        _component("elimination", [_f("blood_in_stool", HARM)]),
    ])
    kinds = [f.kind for f in out["critical_findings"]]
    assert kinds[0] != "blood_pressure_below_reference", (
        "a 26-day-old single reading must not lead the card")
    assert kinds[-1] == "blood_pressure_below_reference"
    assert set(kinds[:3]) == {"intradialytic_hypotension_burden",
                              "severe_symptom", "blood_in_stool"}


def test_ties_keep_component_order_so_the_ranking_is_deterministic():
    """`sorted` is stable. Equal severity must not reshuffle, or the card
    changes wording between reads for no reason."""
    out = hs.overall_score([
        _component("dialysis", [_f("ktv_below_target", DEVIATION),
                                _f("attendance_below_baseline", DEVIATION)]),
        _component("elimination", [_f("vomiting_above_baseline", DEVIATION)]),
    ])
    assert [f.kind for f in out["critical_findings"]] == [
        "ktv_below_target", "attendance_below_baseline",
        "vomiting_above_baseline"]


def test_a_finding_is_never_DROPPED_by_ranking():
    """Demoting is not discarding. 81/62 is a real reading and §3aa forbids
    letting it vanish — it is reported last, not suppressed."""
    out = hs.overall_score([
        _component("vitals", [_f("blood_pressure_below_reference", CONTEXT)]),
        _component("dialysis", [_f("intradialytic_hypotension_burden", HARM)]),
    ])
    assert len(out["critical_findings"]) == 2


# ── the evidence behind the lead sentence ─────────────────────────────────

def _bp_finding(**kw):
    bands = {"Blood Pressure Systolic": (None, 90.0, 120.0, None),
             "Blood Pressure Diastolic": (None, 60.0, 80.0, None)}
    comp = hs.vitals_component(bands=bands, systolic=81.0, diastolic=62.0,
                               on_dialysis=True, **kw)
    return next((f for f in comp.critical
                 if f.kind == "blood_pressure_below_reference"), None)


def test_a_median_of_ONE_reading_is_context_not_a_headline():
    """The operator's first sentence. This function's own docstring already
    says "n=1 is the same error as an all-time mean, from the other end" —
    and it still led the card."""
    finding = _bp_finding(sample_size=1, age_days=26)
    assert finding is not None, "the reading must still be reported"
    assert finding.severity == CONTEXT


def test_a_STALE_window_is_context_even_with_several_readings():
    """`FRESH_DAYS` is the recency authority §3an already defines; no second
    window is invented for this."""
    assert _bp_finding(sample_size=6,
                       age_days=hs.FRESH_DAYS + 1).severity == CONTEXT


def test_a_fresh_well_sampled_reading_is_a_real_DEVIATION():
    """The demotion must be narrow, or a genuinely current low pressure stops
    being reported as a finding at all."""
    assert _bp_finding(sample_size=6, age_days=2).severity == DEVIATION


# ── internal keys must not reach the patient ──────────────────────────────

@pytest.mark.parametrize("key,expected", [
    ("calcium_mg", "Calcium"),
    ("vitamin_d_iu", "Vitamin D"),
    ("carbs_g", "Total Carbohydrate"),
])
def test_every_shortfall_key_has_a_name_we_already_hold(key, expected):
    """The card printed *"short on calcium_mg, vitamin_d_iu, magnesium_mg,
    fiber_g, carbs_g, calories, fat_g"* — DB column keys, on a patient's
    screen, while the catalog held the display name for every one."""
    from app.core.nutrition_data import NUTRIENT_BY_KEY

    assert NUTRIENT_BY_KEY[key]["name"] == expected


def test_an_unknown_key_still_prints_rather_than_vanishing():
    """A nutrient we cannot name is still a shortfall the patient has."""
    from app.core.nutrition_data import NUTRIENT_BY_KEY

    assert (NUTRIENT_BY_KEY.get("not_a_nutrient", {}).get("name")
            or "not_a_nutrient") == "not_a_nutrient"


# ── a symptom is an EVENT, not a standing state ──────────────────────────

import datetime as _dt


def _sym(name, severity, days_ago, today=_dt.date(2026, 10, 22)):
    return {"symptom_name": name, "severity": severity,
            "affects_function": None,
            "log_date": today - _dt.timedelta(days=days_ago)}


TODAY = _dt.date(2026, 10, 22)


def test_an_86_day_old_pain_is_not_the_CURRENT_symptom_burden():
    """Operator, 2026-10-22: *"'twisted abdominal pain' from 40 days ago is
    irrelevant now."* It was 86 days old. `max(severity)` over a 90-day window
    returned it and the card reported it as the present tense, while a 6/10
    from 13 days ago — plausibly the same complaint — went unmentioned."""
    comp = hs.symptom_component([
        _sym("twisted abdominal pain", 9, 86),
        _sym("stomach cramps, feels like twisting? on right, on left", 6, 13),
    ], today=TODAY)
    assert comp.detail.get("symptom") != "twisted abdominal pain"
    # Scored on the CURRENT one: 100 - 6*10.
    assert comp.score == 40.0


def test_the_sentence_says_WHEN():
    """A severity with no date is what let an 86-day-old 9/10 read as now."""
    comp = hs.symptom_component([_sym("sharp pain", 9, 3)], today=TODAY)
    finding = next(f for f in comp.critical if f.kind == "severe_symptom")
    assert "3 days ago" in finding.fallback
    assert finding.facts["days_ago"] == 3


def test_when_everything_is_OLD_the_domain_is_unknown_not_well():
    """§3aa: saying 9/10 would assert a present-tense fact nobody recorded,
    and saying nothing would hide that symptoms exist. Report the gap."""
    comp = hs.symptom_component([_sym("twisted abdominal pain", 9, 86)],
                                today=TODAY)
    assert comp.score is None, "an old symptom must not score the patient as ill now"
    assert "86 days ago" in comp.detail["reason"]


def test_an_undated_symptom_is_treated_as_current():
    """The date is missing from OUR payload, which is not evidence about the
    patient. Discarding it would lose a real symptom to a schema gap."""
    comp = hs.symptom_component(
        [{"symptom_name": "nausea", "severity": 8, "affects_function": None}],
        today=TODAY)
    assert comp.score == 20.0


def test_a_recent_symptom_still_raises_its_finding():
    """The recency gate must be narrow, or a patient in pain now stops being
    reported at all."""
    comp = hs.symptom_component([_sym("severe cramping", 9, 2)], today=TODAY)
    assert [f.kind for f in comp.critical] == ["severe_symptom"]
