"""Renal ceilings must belong to the patient they are shown for.

The clinician board used one hardcoded tuple for everybody:

    _RENAL_LIMITS = (("potassium_mg", "Potassium", "mg", 2500), ...)

That is wrong twice over. It flagged a patient with healthy kidneys as being in
danger for a potassium intake that is a normal *target* for them, and it capped
potassium at a flat 2500 mg — the number `WEB/docs/NUTRITION_INTELLIGENCE.md`
records as replaced by a weight-based ~40 mg/kg. So the board a nephrologist
reads disagreed with the target the patient was shown for the same day.
"""

import pytest

from app.services.nutrient_goals_service import compute_goals, detect_condition_flags


class _ConditionView:
    """Mirrors clinical_sources.ConditionView — note `name`, not `condition_name`."""

    def __init__(self, name, category=None, severity=None):
        self.name = name
        self.category = category
        self.severity = severity
        self.active = True
        self.source = "chronic"


class TestFlagsFromTheCanonicalReader:
    def test_dialysis_is_detected_from_a_condition_view(self):
        """ConditionView calls the field `name`; the detector must accept it.

        Reading conditions any other way fails the canon §3aa guard, so if the
        detector only understood `condition_name`, every caller doing it
        correctly would silently lose the dialysis flag.
        """
        flags = detect_condition_flags([
            _ConditionView("End-Stage Renal Disease on hemodialysis", category="renal")
        ])
        assert flags["ckd"] is True
        assert flags["dialysis"] is True

    def test_a_healthy_patient_gets_no_renal_flags(self):
        flags = detect_condition_flags([_ConditionView("Seasonal allergies", category="other")])
        assert flags["ckd"] is False
        assert flags["dialysis"] is False

    def test_condition_name_attribute_still_works(self):
        """ChronicCondition rows use `condition_name` — don't regress them."""

        class _Row:
            condition_name = "Chronic Kidney Disease Stage 5"
            category = "renal"
            severity = "severe"

        assert detect_condition_flags([_Row()])["ckd"] is True


class TestPotassiumIsWeightBased:
    @pytest.mark.parametrize(
        "weight_kg,expected",
        [
            (50.0, 2000.0),   # 40 mg/kg = 2000, at the floor
            (62.5, 2500.0),   # the old flat cap — correct only at this weight
            (75.0, 3000.0),   # 40 mg/kg = 3000, at the ceiling
            (95.0, 3000.0),   # clamped, not 3800
        ],
    )
    def test_dialysis_potassium_scales_with_weight(self, weight_kg, expected):
        goals = compute_goals(
            date_of_birth="1974-03-15", sex="male", height_cm=177.8,
            current_weight_kg=weight_kg, activity_level="sedentary",
            conditions=[_ConditionView("ESRD on dialysis", category="renal")],
        )
        potassium = next(g for g in goals["goals"] if g["key"] == "potassium_mg")
        assert potassium["goal"] == expected
        assert potassium["kind"] == "limit"

    def test_a_healthy_adult_gets_a_target_not_a_renal_limit(self):
        goals = compute_goals(
            date_of_birth="1974-03-15", sex="male", height_cm=177.8,
            current_weight_kg=75.0, activity_level="sedentary", conditions=[],
        )
        potassium = next(g for g in goals["goals"] if g["key"] == "potassium_mg")
        assert potassium["kind"] == "target"
        # 3400 mg is the adult AI — far above any renal ceiling.
        assert potassium["goal"] == 3400
