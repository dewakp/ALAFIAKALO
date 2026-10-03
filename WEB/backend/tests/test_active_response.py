# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""New data is judged when it is written, against THIS patient's own figures.

The operator's instruction: *"the db and the model must be alive. Alive means
actively responding to new data. e.g for a diabetese patient send notification
when sugar quota exceeds some threshold. For someone with allergense notify
when allergenes exist in food or medication logged."* And the scope: *"do not
notify retroactively. Notify from when this update lands onward."*

What the production census said before this landed (2026-10-02):

    notifications       21 rows / 4 users / 19 unread
      nutrition_alert    8 rows, ONE user, every one on 2026-06-26
      lab_anomaly        2 rows, one day
    never fired at all:  treatment_anomaly, medication_conflict, therapy_session,
                         record_shared, adherence_alert, calendar, refill_reminder,
                         prescription_created, prescription_ready, dispense_complete
    against              1,056 nutrition logs / 1,022 dose logs / 9,791 labs

The engine was never the problem. Nothing compared a new row to what the record
already knew, and the two thresholds that did exist were population constants
looser than the limits this system computes per patient.

THE TESTS THAT ARE REGRESSION GUARDS, AND THE ONES THAT ARE ONLY COVERAGE
=========================================================================
Run against the pre-fix code first, per §3ay — a capture test that passes
against the broken implementation is not a guard, and calling it one is the
§3al mistake. The red run is recorded in the module docstring of
`app/services/active_response.py`'s commit; the classes below are marked.
"""

from __future__ import annotations

import ast
import json
import pathlib
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.chronic_conditions import (
    ChronicCondition,
    ConditionCategory,
    ConditionSeverity,
)
from app.models.labs import LabResult
from app.models.notifications import (
    Notification,
    NotificationCategory,
    NotificationPreference,
)
from app.models.nutrition import NutritionLog
from app.models.user import User
from app.models.vitals import VitalsLog
from app.services import active_response
from app.services.nutrient_goals_service import compute_goals

#: The constants that used to be hand-typed into `api/nutrition.py`, at BOTH
#: call sites. Kept here only so the tests can assert the new behaviour fires
#: BELOW them — which is the whole point: the old gate was looser than the
#: patient's own limit, so it could not warn the patient it was written for.
OLD_HARDCODED = {"sodium_mg": 2300, "potassium_mg": 4700,
                 "phosphorus_mg": 1000, "sugar_g": 50}

#: The real declared-allergy string on the reference production record. Used
#: verbatim: it is misspelled, it mixes food with drugs and materials, and both
#: facts matter to what this module can and cannot catch.
REAL_ALLERGIES = "Penicilin, Latex, Heparine, Raw Apples, Raw Berries"


async def _patient(db, *, email="alive@example.com", allergies=None,
                   conditions=("End-Stage Renal Disease (ESRD)", "Diabetes")):
    """A patient shaped like the reference record: dialysis + diabetes, 55 kg.

    Three details here are the schema's, not a preference, and getting any of
    them wrong fails every test in this file at teardown rather than at the
    assertion — which is how one broken helper reads as sixteen broken tests:

    * `users.date_of_birth` is **String(10)**, not a Date. `compute_goals`
      parses it, and `api/nutrition.py` passes `str(current_user.date_of_birth)`.
    * `chronic_conditions.severity` is **NOT NULL**.
    * `category` is an enum whose VALUES are lowercase (`renal`), so the member
      is passed rather than a hand-typed string.
    """
    u = User(
        email=email, hashed_password="x", full_name="Alive Test",
        date_of_birth="1974-03-15", gender="Male",
        height_cm=177.8, current_weight_kg=55.0, activity_level="sedentary",
        allergies=allergies,
    )
    db.add(u)
    await db.flush()
    for name in conditions:
        db.add(ChronicCondition(
            user_id=u.id, condition_name=name,
            category=(ConditionCategory.RENAL if "Renal" in name
                      else ConditionCategory.DIABETES if "Diabet" in name
                      else ConditionCategory.OTHER),
            severity=ConditionSeverity.SEVERE,
            is_active=True,
        ))
    await db.flush()
    return u


async def _notes(db, user_id, category=None):
    stmt = select(Notification).where(Notification.user_id == user_id)
    if category:
        stmt = stmt.where(Notification.category == category)
    return (await db.execute(stmt)).scalars().all()


def _limit_for(user_conditions, key, **profile):
    goals = compute_goals(
        date_of_birth="1974-03-15", sex="Male", height_cm=177.8,
        current_weight_kg=55.0, activity_level="sedentary",
        conditions=user_conditions, **profile)
    return next(g for g in goals["goals"] if g["key"] == key)


class TestTheLimitBelongsToThePatient:
    """REGRESSION GUARDS. Every one of these fires at an intake the old
    hardcoded dict would have waved through."""

    @pytest.mark.asyncio
    async def test_potassium_fires_below_the_old_constant_and_above_this_patient(self, db):
        """The case the old gate could not see.

        A dialysis patient at 55 kg is capped at 40 mg/kg = 2200 mg. The old
        dict fired at 4700 — the generic adult RDA, which §3am names as exactly
        the wrong figure for a renal patient. So an intake of 2500 mg endangered
        this patient and was silently fine by the old rule.
        """
        user = await _patient(db)
        log = NutritionLog(user_id=user.id, log_date=date.today(),
                           meal_type="lunch", food_name="Beans and plantain",
                           potassium_mg=2500.0, nutrient_status="done")
        db.add(log)
        await db.flush()

        written = await active_response.evaluate_nutrition_log(db, log, user)
        await db.flush()

        assert 2500 < OLD_HARDCODED["potassium_mg"], (
            "the premise: the old rule would NOT have fired here")
        assert written >= 1
        notes = await _notes(db, user.id, NotificationCategory.NUTRITION_ALERT)
        potassium = [n for n in notes if "otassium" in n.title]
        assert potassium, f"expected a potassium alert, got {[n.title for n in notes]}"
        payload = json.loads(potassium[0].extra_data)
        assert payload["limit"] == 2200.0, "this patient's own computed cap"
        assert payload["authority"].startswith("compute_goals")

    @pytest.mark.asyncio
    async def test_sugar_fires_below_the_old_50g_for_a_diabetic(self, db):
        """The operator's own example: a diabetic exceeding a sugar quota.

        `compute_goals` puts added sugars at 5% of energy for a diabetic and
        10% otherwise, so this patient's cap is ~21 g — well under the 50 g the
        old dict used. A 30 g day is over their limit and under the constant.
        """
        user = await _patient(db, email="sugar@example.com")
        cap = _limit_for([type("C", (), {"name": "Diabetes", "category": "OTHER",
                                         "severity": None, "active": True})()],
                         "sugar_g")["goal"]
        assert cap < OLD_HARDCODED["sugar_g"], (
            f"premise: the diabetic cap {cap} must be under the old 50 g")

        log = NutritionLog(user_id=user.id, log_date=date.today(),
                           meal_type="snack", food_name="Malt drink",
                           sugar_g=30.0, nutrient_status="done")
        db.add(log)
        await db.flush()
        await active_response.evaluate_nutrition_log(db, log, user)
        await db.flush()

        notes = await _notes(db, user.id, NotificationCategory.NUTRITION_ALERT)
        sugar = [n for n in notes if "ugar" in n.title]
        assert sugar, f"expected a sugar alert, got {[n.title for n in notes]}"
        assert 30 < OLD_HARDCODED["sugar_g"]

    @pytest.mark.asyncio
    async def test_the_DAY_is_the_unit_not_the_meal(self, db):
        """A quota is a daily figure.

        Three meals of 900 mg potassium are each unremarkable and together
        exceed this patient's 2200 mg cap. Judging the row in isolation — which
        is what the old inline check did — can never see that.
        """
        user = await _patient(db, email="daily@example.com")
        for n in range(3):
            db.add(NutritionLog(user_id=user.id, log_date=date.today(),
                                meal_type=f"meal{n}", food_name=f"Portion {n}",
                                potassium_mg=900.0, nutrient_status="done"))
        await db.flush()
        last = (await db.execute(
            select(NutritionLog).where(NutritionLog.user_id == user.id)
            .order_by(NutritionLog.id.desc()).limit(1)
        )).scalar_one()

        await active_response.evaluate_nutrition_log(db, last, user)
        await db.flush()
        notes = await _notes(db, user.id, NotificationCategory.NUTRITION_ALERT)
        assert [n for n in notes if "otassium" in n.title], (
            "2700 mg across three meals must be seen as 2700, not as 900")

    @pytest.mark.asyncio
    async def test_a_healthy_patient_is_not_warned_at_a_renal_ceiling(self, db):
        """The other half of the old bug: it flagged a healthy intake.

        With no renal diagnosis, potassium is a TARGET of 3400 mg, not a limit.
        2500 mg is then unremarkable and must produce nothing.
        """
        user = await _patient(db, email="healthy@example.com", conditions=())
        log = NutritionLog(user_id=user.id, log_date=date.today(),
                           meal_type="lunch", food_name="Beans and plantain",
                           potassium_mg=2500.0, nutrient_status="done")
        db.add(log)
        await db.flush()
        await active_response.evaluate_nutrition_log(db, log, user)
        await db.flush()
        notes = await _notes(db, user.id, NotificationCategory.NUTRITION_ALERT)
        assert not [n for n in notes if "otassium" in n.title]


class TestAllergensInWhatWasLogged:
    """REGRESSION GUARDS. `food_safety.violations` existed and was called only
    by the meal planner and the AI prompt — never by anything that writes."""

    @pytest.mark.asyncio
    async def test_a_logged_meal_naming_a_declared_allergy_notifies(self, db):
        user = await _patient(db, email="allergy@example.com",
                              allergies=REAL_ALLERGIES, conditions=())
        log = NutritionLog(user_id=user.id, log_date=date.today(),
                           meal_type="breakfast",
                           food_name="Sliced apples with yoghurt",
                           nutrient_status="done")
        db.add(log)
        await db.flush()
        await active_response.evaluate_nutrition_log(db, log, user)
        await db.flush()

        notes = await _notes(db, user.id, NotificationCategory.NUTRITION_ALERT)
        assert notes, "an apple allergy must be caught in a logged apple"
        assert any("allerg" in (n.title + n.message).lower() for n in notes)

    @pytest.mark.asyncio
    async def test_a_logged_DOSE_matching_a_declared_allergy_notifies(self, db):
        """The half of the instruction with no implementation at all.

        Nothing in `api/medications.py` or `med_dose_validation.py` referenced
        allergies: the dose guard asks whether a dose is physically possible
        (§3aj), never whether the patient may take the drug.
        """
        from app.models.med_nutrient import MedicationDoseLog

        user = await _patient(db, email="heparin@example.com",
                              allergies=REAL_ALLERGIES, conditions=())
        dose = MedicationDoseLog(
            user_id=user.id, medication_name="Heparine",
            log_date=date.today(), dose_amount=5000, dose_unit="unit")
        db.add(dose)
        await db.flush()

        written = await active_response.evaluate_medication_dose(db, dose, user)
        await db.flush()
        assert written >= 1
        notes = await _notes(db, user.id, NotificationCategory.MEDICATION_CONFLICT)
        assert notes, "a declared drug allergy must be caught in a logged dose"
        assert "Heparine" in notes[0].message

    @pytest.mark.asyncio
    async def test_a_FOOD_trigger_is_not_matched_against_a_drug_name(self, db):
        """A diabetic's "avoid added sugars" has nothing to say about a tablet.

        Firing there would be the cry-wolf guard §3ab warns teaches its reader
        to tick past the real ones.
        """
        from app.models.med_nutrient import MedicationDoseLog

        user = await _patient(db, email="trigger@example.com")
        dose = MedicationDoseLog(
            user_id=user.id, medication_name="Calcium carbonate",
            log_date=date.today(), dose_amount=1000, dose_unit="mg")
        db.add(dose)
        await db.flush()
        await active_response.evaluate_medication_dose(db, dose, user)
        await db.flush()
        assert not await _notes(db, user.id, NotificationCategory.MEDICATION_CONFLICT)


class TestWhatThisDeliberatelyCannotDo:
    """COVERAGE, recorded on purpose — not guards.

    The idiom is §3al's `test_a_bare_name_in_passing_is_NOT_redacted`: pin the
    known gap so it is a documented limit rather than a surprise.
    """

    @pytest.mark.asyncio
    async def test_a_misspelled_allergy_does_NOT_match_the_real_drug(self, db):
        """`Penicilin` on the profile vs `Penicillin` in the dose: no match.

        The matcher compares words, and neither spelling is a prefix of the
        other. The spelling is NOT corrected here — rewriting what a patient
        declared about their own body invents a clinical fact, and §3aj settled
        that string similarity is the wrong instrument for drug names
        ("calcium calcitriol" scores 0.63 against "calcium carbonate" and its
        nearest match is a third drug). RxNorm's `approximateTerm` is the right
        instrument and it is a network call, so it cannot sit on a write path.
        """
        from app.models.med_nutrient import MedicationDoseLog

        user = await _patient(db, email="spelling@example.com",
                              allergies=REAL_ALLERGIES, conditions=())
        dose = MedicationDoseLog(
            user_id=user.id, medication_name="Penicillin",
            log_date=date.today(), dose_amount=500, dose_unit="mg")
        db.add(dose)
        await db.flush()
        await active_response.evaluate_medication_dose(db, dose, user)
        await db.flush()
        assert not await _notes(db, user.id, NotificationCategory.MEDICATION_CONFLICT), (
            "RECORDED GAP, not desired behaviour — see the docstring")


class TestGlucoseIsJudgedByThisPatientsOwnLab:
    """REGRESSION GUARDS. `api/vitals.py` evaluated nothing whatsoever."""

    async def _with_glucose_range(self, db, email):
        user = await _patient(db, email=email, conditions=("Diabetes",))
        # The real band on the reference record, carried on 9 of its 171
        # glucose results.
        for n in range(2):
            db.add(LabResult(
                user_id=user.id, test_name="Glucose",
                test_date=date.today() - timedelta(days=30 * (n + 1)),
                value=143.0, unit="mg/dL",
                reference_range_low=74.0, reference_range_high=106.0))
        await db.flush()
        return user

    @pytest.mark.asyncio
    async def test_a_low_reading_fires_whatever_the_timing(self, db):
        """Hypoglycaemia does not depend on whether they have eaten."""
        user = await self._with_glucose_range(db, "lowsugar@example.com")
        entry = VitalsLog(user_id=user.id, log_date=date.today(),
                          blood_glucose_mg_dl=50.0, glucose_timing="post-meal")
        db.add(entry)
        await db.flush()
        written = await active_response.evaluate_vitals(db, entry, user)
        await db.flush()
        assert written == 1
        notes = await _notes(db, user.id, NotificationCategory.LAB_ANOMALY)
        assert notes and "below" in notes[0].message
        assert "74" in notes[0].message, "must quote the patient's own range"

    @pytest.mark.asyncio
    async def test_a_high_FASTING_reading_fires(self, db):
        user = await self._with_glucose_range(db, "highfasting@example.com")
        entry = VitalsLog(user_id=user.id, log_date=date.today(),
                          blood_glucose_mg_dl=220.0, glucose_timing="fasting")
        db.add(entry)
        await db.flush()
        assert await active_response.evaluate_vitals(db, entry, user) == 1

    @pytest.mark.asyncio
    async def test_a_high_POST_MEAL_reading_does_not_fire(self, db):
        """A serum range is a FASTING range.

        Applying its ceiling to a deliberate post-meal fingerstick flags
        ordinary postprandial physiology. A post-prandial threshold needs an
        authority this system does not hold, and inventing one is what §0
        forbids — so nothing is said rather than something unfounded.
        """
        user = await self._with_glucose_range(db, "highpost@example.com")
        entry = VitalsLog(user_id=user.id, log_date=date.today(),
                          blood_glucose_mg_dl=220.0, glucose_timing="post-meal")
        db.add(entry)
        await db.flush()
        assert await active_response.evaluate_vitals(db, entry, user) == 0

    @pytest.mark.asyncio
    async def test_no_reported_range_means_silence_not_a_guess(self, db):
        user = await _patient(db, email="norange@example.com", conditions=("Diabetes",))
        entry = VitalsLog(user_id=user.id, log_date=date.today(),
                          blood_glucose_mg_dl=400.0, glucose_timing="fasting")
        db.add(entry)
        await db.flush()
        assert await active_response.evaluate_vitals(db, entry, user) == 0
        assert not await _notes(db, user.id, NotificationCategory.LAB_ANOMALY)


class TestItDoesNotShoutTwice:
    @pytest.mark.asyncio
    async def test_the_same_finding_twice_writes_one_notification(self, db):
        """Cross the sugar limit at lunch and every later meal re-crosses it.

        `notify_record_accessed` already learned this: without a window the
        patient gets five alerts for one visit and learns to ignore all five.
        """
        user = await _patient(db, email="dedupe@example.com")
        log = NutritionLog(user_id=user.id, log_date=date.today(),
                           meal_type="lunch", food_name="Beans",
                           potassium_mg=2500.0, nutrient_status="done")
        db.add(log)
        await db.flush()

        first = await active_response.evaluate_nutrition_log(db, log, user)
        await db.flush()
        second = await active_response.evaluate_nutrition_log(db, log, user)
        await db.flush()

        assert first >= 1
        assert second == 0, "the same nutrient on the same day is one finding"
        notes = await _notes(db, user.id, NotificationCategory.NUTRITION_ALERT)
        assert len([n for n in notes if "otassium" in n.title]) == 1

    @pytest.mark.asyncio
    async def test_a_disabled_category_suppresses_it(self, db):
        """`create_notification` returns None when the user switched it off.

        That is a real answer and not a failure — but it is silent, so the
        count must not pretend something was written.
        """
        user = await _patient(db, email="off@example.com")
        db.add(NotificationPreference(
            user_id=user.id, category=NotificationCategory.NUTRITION_ALERT,
            enabled=False))
        log = NutritionLog(user_id=user.id, log_date=date.today(),
                           meal_type="lunch", food_name="Beans",
                           potassium_mg=2500.0, nutrient_status="done")
        db.add(log)
        await db.flush()
        assert await active_response.evaluate_nutrition_log(db, log, user) == 0
        assert not await _notes(db, user.id, NotificationCategory.NUTRITION_ALERT)


class TestNothingIsEverJudgedRetroactively:
    """The operator's scope, enforced structurally rather than by a flag.

    *"do not notify retroactively. Notify from when this update lands onward."*
    There is no cutoff constant and no switch, because there is no code path
    that can reach a row the caller did not just write.
    """

    def _module(self):
        path = pathlib.Path(active_response.__file__)
        return ast.parse(path.read_text()), path.read_text()

    def test_the_module_queries_no_clinical_table(self):
        """A history sweep would have to start with a select. There is one, and
        it reads `Notification` for deduplication."""
        tree, _ = self._module()
        selected = []
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "select" and node.args):
                arg = node.args[0]
                if isinstance(arg, ast.Attribute):
                    selected.append(
                        f"{getattr(arg.value, 'id', '?')}.{arg.attr}")
                elif isinstance(arg, ast.Name):
                    selected.append(arg.id)
        assert selected == ["Notification.extra_data"], (
            f"only the dedupe read is allowed here; found {selected}. A query "
            "against a clinical table is how a retroactive sweep gets added.")

    def test_every_entry_point_requires_the_row_it_judges(self):
        """A function that takes only a user id could scan history. These
        cannot: each one is handed the row the request just wrote."""
        import inspect

        for name in ("evaluate_nutrition_log", "evaluate_medication_dose",
                     "evaluate_vitals"):
            fn = getattr(active_response, name)
            params = list(inspect.signature(fn).parameters)
            assert params[:1] == ["db"], f"{name}{tuple(params)}"
            assert len(params) >= 3, (
                f"{name} must take the row and the user, not just an id: {params}")

    @pytest.mark.asyncio
    async def test_an_old_meal_is_not_judged_when_a_new_one_is_written(self, db):
        """Writing today's meal must not produce findings about last year's.

        The day's aggregate is scoped to the written row's own date, so a 2018
        meal cannot be reached by logging a 2026 one.
        """
        user = await _patient(db, email="noretro@example.com")
        db.add(NutritionLog(user_id=user.id, log_date=date(2018, 5, 6),
                            meal_type="lunch", food_name="Old beans",
                            potassium_mg=9000.0, nutrient_status="done"))
        today = NutritionLog(user_id=user.id, log_date=date.today(),
                             meal_type="lunch", food_name="Rice",
                             potassium_mg=100.0, nutrient_status="done")
        db.add(today)
        await db.flush()

        await active_response.evaluate_nutrition_log(db, today, user)
        await db.flush()
        notes = await _notes(db, user.id, NotificationCategory.NUTRITION_ALERT)
        assert not notes, (
            f"a 9000 mg meal from 2018 must stay silent; got {[n.title for n in notes]}")


class TestTheWriteFailureIsNeverTheClinicalFailure:
    @pytest.mark.asyncio
    async def test_a_broken_evaluation_does_not_raise_into_the_save(self, db, monkeypatch):
        """§3ah: the row is the record. Losing an alert beats losing the meal."""
        user = await _patient(db, email="boom@example.com")

        async def _explode(*_a, **_k):
            raise RuntimeError("knowledge tier down")

        monkeypatch.setattr(active_response, "_personal_nutrient_limits", _explode)
        monkeypatch.setattr(active_response, "_guidance_for", _explode)

        log = NutritionLog(user_id=user.id, log_date=date.today(),
                           meal_type="lunch", food_name="Beans",
                           potassium_mg=2500.0, nutrient_status="done")
        db.add(log)
        await db.flush()
        assert await active_response.evaluate_nutrition_log(db, log, user) == 0


class TestEndToEndThroughTheRealEndpoint:
    """REGRESSION GUARDS, and the only honest ones in this file.

    Every test above calls the evaluator directly. With the OLD call sites
    restored those still pass, because the evaluator is new code that nothing
    reverted — so they are coverage, not evidence. §3av states it plainly: run
    the scan, and a test that cannot fail against the broken implementation is
    not a guard (§3al paid for that once already, where a PII test passed
    against broken code because the payload sat in a field the old path handled).

    The hardcoded `_LIMITS` dict lived in the ENDPOINT. So the endpoint is the
    only place a red run means anything, and these are the ones that go red
    with the pre-fix call sites in place.
    """

    @pytest.mark.asyncio
    async def test_logging_a_meal_notifies_at_THIS_patients_potassium_limit(
            self, client, db):
        """2500 mg: under the old hardcoded 4700, over this patient's own 2200."""
        from app.core.security import get_current_user
        from app.main import app

        user = await _patient(db, email="e2e-k@example.com")
        await db.commit()

        app.dependency_overrides[get_current_user] = lambda: user
        try:
            resp = await client.post("/api/v1/nutrition/", json={
                "log_date": date.today().isoformat(),
                "meal_type": "lunch",
                "food_name": "Beans and plantain",
                # `calories` present means `needs_enrichment` is False, so the
                # SYNCHRONOUS path runs — the one the old dict guarded.
                "calories": 400.0,
                "potassium_mg": 2500.0,
            })
            assert resp.status_code == 201, resp.text
        finally:
            app.dependency_overrides.pop(get_current_user, None)

        notes = await _notes(db, user.id, NotificationCategory.NUTRITION_ALERT)
        assert [n for n in notes if "otassium" in n.title], (
            "the old gate fired at 4700 and this patient's cap is 2200, so "
            f"2500 mg had to stay silent before this fix; got {[n.title for n in notes]}")

    @pytest.mark.asyncio
    async def test_logging_a_meal_notifies_a_diabetic_at_their_own_sugar_cap(
            self, client, db):
        """The operator's first example, end to end. Cap ~21 g, old gate 50 g."""
        from app.core.security import get_current_user
        from app.main import app

        user = await _patient(db, email="e2e-sugar@example.com")
        await db.commit()

        app.dependency_overrides[get_current_user] = lambda: user
        try:
            resp = await client.post("/api/v1/nutrition/", json={
                "log_date": date.today().isoformat(),
                "meal_type": "snack",
                "food_name": "Malt drink",
                "calories": 210.0,
                "sugar_g": 30.0,
            })
            assert resp.status_code == 201, resp.text
        finally:
            app.dependency_overrides.pop(get_current_user, None)

        notes = await _notes(db, user.id, NotificationCategory.NUTRITION_ALERT)
        assert [n for n in notes if "ugar" in n.title], (
            f"30 g is under the old 50 g gate; got {[n.title for n in notes]}")

    @pytest.mark.asyncio
    async def test_logging_a_DOSE_notifies_on_a_declared_drug_allergy(
            self, client, db):
        """The half of the instruction that had no implementation at all.

        `validate_dose` is stubbed to UNREACHABLE by the autouse fixture in
        conftest, which is the fail-open path (§3aj) — so the dose is accepted
        and the allergy check is what this asserts.
        """
        from app.core.security import get_current_user
        from app.main import app

        user = await _patient(db, email="e2e-dose@example.com",
                              allergies=REAL_ALLERGIES, conditions=())
        await db.commit()

        app.dependency_overrides[get_current_user] = lambda: user
        try:
            resp = await client.post("/api/v1/medications/dose-logs", json={
                "medication_name": "Heparine",
                "log_date": date.today().isoformat(),
                "dose_amount": 5000.0,
                "dose_unit": "unit",
            })
            assert resp.status_code == 201, resp.text
        finally:
            app.dependency_overrides.pop(get_current_user, None)

        notes = await _notes(db, user.id, NotificationCategory.MEDICATION_CONFLICT)
        assert notes, "nothing consulted users.allergies on this path before"
        assert "Heparine" in notes[0].message

    @pytest.mark.asyncio
    async def test_logging_a_GLUCOSE_reading_notifies_against_the_patients_own_range(
            self, client, db):
        """`api/vitals.py` evaluated nothing whatsoever before this."""
        from app.core.security import get_current_user
        from app.main import app

        user = await _patient(db, email="e2e-glucose@example.com",
                              conditions=("Diabetes",))
        for n in range(2):
            db.add(LabResult(
                user_id=user.id, test_name="Glucose",
                test_date=date.today() - timedelta(days=30 * (n + 1)),
                value=143.0, unit="mg/dL",
                reference_range_low=74.0, reference_range_high=106.0))
        await db.commit()

        app.dependency_overrides[get_current_user] = lambda: user
        try:
            resp = await client.post("/api/v1/vitals/", json={
                "log_date": date.today().isoformat(),
                "blood_glucose_mg_dl": 50.0,
                "glucose_timing": "fasting",
            })
            assert resp.status_code == 201, resp.text
        finally:
            app.dependency_overrides.pop(get_current_user, None)

        notes = await _notes(db, user.id, NotificationCategory.LAB_ANOMALY)
        assert notes, "a hypoglycaemic reading must be answered"
        assert "74" in notes[0].message, "must quote the patient's OWN range"
