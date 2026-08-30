"""The health score measured diligence, not health.

Four faults, each of which changed the number a patient was shown:

1. **Nutrition was `(days_tracked / 30) * 100`** — logging frequency. Log every
   day while malnourished and it reads 100%.
2. **Missing data scored 0 at full weight**, so not tracking a domain looked
   identical to failing at it.
3. **…except mood, where missing data scored full marks**: `(10 - avg_stress)`
   with `avg_stress` defaulting to 0 awarded 30 points for never recording
   stress. A scale that reads best when nothing is known is worse than none.
4. **Vitals was BMI alone**, on dialysis patients, where weight is fluid.

The replacement is arithmetic over measured values against the patient's own
goals — reproducible and explainable, with no model deciding a number.
"""

import pytest

from app.services import health_score as hs


# ── Nutrition is adherence, not attendance ────────────────────────────────

#: Keys are exactly what `compute_goals` emits — `potassium_mg`, not
#: "potassium". The fixture used to invent the short form, which is precisely
#: why a broken translation table passed its tests while dropping potassium
#: from every real score. A fixture that does not match what the producer emits
#: proves nothing about the producer.
_RENAL_GOALS = [
    {"key": "potassium_mg", "goal": 3000.0, "kind": "limit", "unit": "mg", "priority": 2.0},
    {"key": "phosphorus_mg", "goal": 1000.0, "kind": "limit", "unit": "mg", "priority": 2.0},
    {"key": "protein_g", "goal": 84.0, "kind": "target", "unit": "g", "priority": 2.0},
    {"key": "calories", "goal": 2100.0, "kind": "target", "unit": "kcal", "priority": 1.0},
]


def test_the_fixture_keys_are_the_ones_compute_goals_actually_emits():
    """Guards the fixture itself, so this cannot drift back into a lie."""
    from app.services.nutrient_goals_service import compute_goals
    emitted = {g["key"] for g in compute_goals(
        date_of_birth="1962-04-11", sex="female", height_cm=165,
        current_weight_kg=62, conditions=[])["goals"]}
    for goal in _RENAL_GOALS:
        assert goal["key"] in emitted, (
            f"{goal['key']} is not a key compute_goals produces — the fixture "
            "has drifted from the producer")


def test_within_every_goal_scores_full():
    c = hs.nutrition_adherence(
        {"potassium_mg": 2500, "phosphorus_mg": 900, "protein_g": 90, "calories": 2200},
        _RENAL_GOALS)
    assert c.score == 100.0


def test_exceeding_a_limit_lowers_the_score():
    """Double the potassium limit must not read as adherence."""
    c = hs.nutrition_adherence(
        {"potassium_mg": 6000, "phosphorus_mg": 900, "protein_g": 90, "calories": 2200},
        _RENAL_GOALS)
    assert c.score < 75
    assert c.detail["nutrients"]["potassium_mg"]["score"] == 0.0


def test_a_malnourished_patient_does_not_score_100():
    """The complaint that started this: logging daily while undernourished.

    Half the protein and half the energy is poor adherence however diligent the
    logging was — under the old rule this same patient read 100%.

    Staying under the potassium and phosphorus limits must not pay for the
    deficit. Under an arithmetic mean it did: two limits at 100 dragged the
    total to 78 while protein and energy sat at 48.
    """
    well_fed = hs.nutrition_adherence(
        {"potassium_mg": 2500, "phosphorus_mg": 900, "protein_g": 90, "calories": 2200},
        _RENAL_GOALS)
    malnourished = hs.nutrition_adherence(
        {"potassium_mg": 1500, "phosphorus_mg": 500, "protein_g": 40, "calories": 1000},
        _RENAL_GOALS)

    assert malnourished.score is not None
    assert malnourished.score < well_fed.score - 20
    # And the number is never the whole message: the deficits are named.
    assert malnourished.detail["shortfalls"] == ["protein_g", "calories"]


def test_an_unmeasured_nutrient_does_not_count_as_adherence():
    """Never capturing phosphorus must not read as perfect phosphorus control."""
    c = hs.nutrition_adherence(
        {"potassium_mg": 2500, "phosphorus_mg": None, "protein_g": 90, "calories": 2100},
        _RENAL_GOALS)
    assert "phosphorus_mg" not in c.detail["nutrients"]
    assert c.detail["nutrients_scored"] == 3


def test_no_intake_at_all_is_unknown_not_zero():
    c = hs.nutrition_adherence({}, _RENAL_GOALS)
    assert c.score is None


# ── Absence is absence ────────────────────────────────────────────────────

def test_never_recording_stress_earns_nothing():
    """The free-points bug: `(10 - 0) * 10 * 0.3` was worth 30 points."""
    with_stress = hs.mood_component(avg_mood=3.0, avg_energy=3.0, avg_stress=8.0)
    without = hs.mood_component(avg_mood=3.0, avg_energy=3.0, avg_stress=None)

    # Omitting stress must not IMPROVE the score.
    assert without.score <= 30.0
    assert without.score == pytest.approx(30.0, abs=0.1)
    assert with_stress.score < without.score + 1


def test_no_mood_data_is_unknown():
    assert hs.mood_component(None, None, None).score is None


def test_unknown_domains_are_excluded_not_zeroed():
    """A patient tracking two domains well should not be capped by three blanks."""
    components = [
        hs.Component("nutrition", 90.0, 0.30),
        hs.Component("vitals", 80.0, 0.20),
        hs.Component("sleep", None, 0.20),
        hs.Component("mood", None, 0.15),
        hs.Component("fitness", None, 0.15),
    ]
    result = hs.overall_score(components)

    # Weighted over the 0.50 that was measured: (90*.30 + 80*.20)/.50 = 86
    assert result["overall_score"] == pytest.approx(86.0, abs=0.1)
    assert result["components_unknown"] == ["sleep", "mood", "fitness"]
    assert result["confidence"] == 0.5
    # Under the old rule this same patient scored 43 — a failing grade for
    # domains they had simply not logged.
    assert result["grade"] == "B"


def test_nothing_measured_is_no_score_at_all():
    """A 0 for a patient we know nothing about is a claim we cannot support."""
    result = hs.overall_score([
        hs.Component("nutrition", None, 0.30),
        hs.Component("mood", None, 0.15),
    ])
    assert result["overall_score"] is None
    assert result["grade"] is None
    assert result["confidence"] == 0.0


# ── Vitals ────────────────────────────────────────────────────────────────

def test_bmi_is_not_scored_on_dialysis():
    """Weight swings with fluid between sessions; that is not body composition."""
    c = hs.vitals_component(bmi=31.0, systolic=125, diastolic=75, on_dialysis=True)
    assert c.score == 100.0                       # decided by BP alone
    assert "bmi" not in c.detail
    assert "bmi_excluded" in c.detail


def test_bmi_still_counts_off_dialysis():
    c = hs.vitals_component(bmi=31.0, systolic=125, diastolic=75, on_dialysis=False)
    assert c.score < 100.0
    assert c.detail["bmi"] == 31.0


def test_high_blood_pressure_lowers_vitals():
    good = hs.vitals_component(systolic=120, diastolic=75, on_dialysis=True)
    bad = hs.vitals_component(systolic=175, diastolic=105, on_dialysis=True)
    assert bad.score < good.score


def test_no_vitals_is_unknown():
    assert hs.vitals_component().score is None


# ── Medication adherence measures the regimen, not the existence of a row ──

def test_adherence_is_unknown_without_a_prescription():
    """Common and not a failing: an account can hold 943 dose logs and zero
    prescriptions, because prescriptions come from the EHR import while dose
    logs are what the patient took. The old rule scored that 50."""
    c = hs.medication_adherence([], ["Calcium Carbonate", "Calcitriol"])
    assert c.score is None
    assert "nothing to measure adherence against" in c.detail["reason"]


def test_adherence_counts_the_prescribed_drugs_actually_logged():
    c = hs.medication_adherence(
        ["Calcium Carbonate", "Calcitriol", "Sevelamer"],
        ["calcium carbonate", "Calcitriol"])
    assert c.score == pytest.approx(66.7, abs=0.1)
    # Named, because a percentage does not tell a clinician WHICH drug.
    assert c.detail["not_logged"] == ["sevelamer"]


def test_adherence_matching_is_case_insensitive():
    """The same drug arrives as both "Calcium Carbonate" and "Calcium carbonate"."""
    c = hs.medication_adherence(["Calcium Carbonate"], ["calcium carbonate"])
    assert c.score == 100.0


def test_having_a_prescription_and_logging_nothing_is_zero_not_unknown():
    """We know what they were meant to take and saw none of it. That is a
    measurement, and the old rule scored it 80 for merely having the row."""
    c = hs.medication_adherence(["Calcitriol"], [])
    assert c.score == 0.0
