"""Solute transfer across a session, and the gates on letting it move a limit.

The physiology tests pin the model against published per-session bands. The
safety tests pin the thing that actually matters: a modelled removal is not
permission to eat more potassium unless several independent things are true.
"""

from datetime import date, timedelta

import pytest

from app.services.dialysis_balance import (
    CALCIUM, MAGNESIUM, PHOSPHORUS, POTASSIUM, PROTEIN,
    DEFAULT_COEFFICIENTS, SerumLevels, SessionParams, SessionNotModellable,
    estimate_session_removal, validate_session, with_calibration,
)
from app.services.dialysis_day_adjustment import (
    SERUM_BLOCK_ABOVE, UNCALIBRATED_FRACTION, apply_to_totals,
)

MG_PER_MEQ_K = 39.10


def a_session(**overrides) -> SessionParams:
    """A typical treatment for this patient: 30 L, 1 mEq bath, ~3 h."""
    params = dict(
        dialysate_volume_l=30.0, duration_minutes=184.0, blood_flow_ml_min=350.0,
        ultrafiltration_ml=608.0, bath_potassium_meq=1.0, completed=True,
    )
    params.update(overrides)
    return SessionParams(**params)


def a_serum(**overrides) -> SerumLevels:
    params = dict(
        potassium_mmol_l=5.0, phosphorus_mg_dl=5.0,
        magnesium_mg_dl=2.0, calcium_mg_dl=9.0, measured_on=date(2026, 8, 1),
    )
    params.update(overrides)
    return SerumLevels(**params)


# ── Physiology ───────────────────────────────────────────────────────────────

class TestAgainstPublishedBands:
    def test_potassium_removal_is_in_the_published_range(self):
        """A conventional session removes roughly 70–100 mEq of potassium."""
        removed = estimate_session_removal(a_session(), a_serum())[POTASSIUM]
        mEq = removed.mass_mg / MG_PER_MEQ_K
        assert 60 <= mEq <= 110, f"{mEq:.0f} mEq is outside the plausible band"

    def test_phosphorus_removal_is_in_the_published_range(self):
        """~500–1000 mg over a session."""
        removed = estimate_session_removal(a_session(), a_serum())[PHOSPHORUS]
        assert 400 <= removed.mass_mg <= 1100

    def test_amino_acid_loss_is_in_the_published_range(self):
        """6–12 g — the mechanism behind the raised protein target on dialysis."""
        grams = estimate_session_removal(a_session(), a_serum())[PROTEIN].mass_mg / 1000
        assert 5 <= grams <= 13

    def test_calcium_against_a_rich_bath_is_a_GAIN(self):
        """The classic effect: a 3.0 mEq/L bath loads calcium rather than removing it.

        Only ionised calcium is dialysable, so total serum calcium of 9 mg/dL is
        ~1.1 mmol/L diffusible — below a 1.5 mmol/L bath.
        """
        estimate = estimate_session_removal(a_session(), a_serum())[CALCIUM]
        assert estimate.mass_mg < 0
        assert estimate.is_gain
        assert 100 <= abs(estimate.mass_mg) <= 500

    def test_a_higher_bath_removes_less_potassium(self):
        low = estimate_session_removal(a_session(bath_potassium_meq=1.0), a_serum())[POTASSIUM]
        high = estimate_session_removal(a_session(bath_potassium_meq=3.0), a_serum())[POTASSIUM]
        assert high.mass_mg < low.mass_mg

    def test_a_higher_serum_removes_more_potassium(self):
        normal = estimate_session_removal(a_session(), a_serum(potassium_mmol_l=4.0))[POTASSIUM]
        high = estimate_session_removal(a_session(), a_serum(potassium_mmol_l=6.5))[POTASSIUM]
        assert high.mass_mg > normal.mass_mg

    def test_phosphorus_removal_plateaus_with_time(self):
        """Rebound-limited: doubling the session does not double removal."""
        short = estimate_session_removal(a_session(duration_minutes=120), a_serum())[PHOSPHORUS]
        long = estimate_session_removal(a_session(duration_minutes=240), a_serum())[PHOSPHORUS]
        assert long.mass_mg > short.mass_mg
        assert long.mass_mg < short.mass_mg * 1.8


class TestTreatmentParameters:
    """All four prescription parameters must actually reach the arithmetic.

    Dialysate quantity, duration, blood volume processed and bath composition
    each change what a session clears. An earlier version accepted blood flow
    and then never referenced it, so two sessions differing only in access
    quality produced identical answers.
    """

    def test_dialysate_quantity_changes_removal(self):
        small = estimate_session_removal(a_session(dialysate_volume_l=15.0), a_serum())[POTASSIUM]
        large = estimate_session_removal(a_session(dialysate_volume_l=60.0), a_serum())[POTASSIUM]
        assert large.mass_mg > small.mass_mg

    def test_duration_changes_potassium_not_only_phosphorus(self):
        """The same volume pushed through faster equilibrates less completely.

        Duration used to affect phosphorus alone; for everything else it was
        accepted and ignored.
        """
        slow = estimate_session_removal(a_session(duration_minutes=240), a_serum())[POTASSIUM]
        fast = estimate_session_removal(a_session(duration_minutes=60), a_serum())[POTASSIUM]
        assert fast.mass_mg < slow.mass_mg

    def test_blood_volume_processed_is_derived_from_flow_and_time(self):
        session = a_session(blood_flow_ml_min=350.0, duration_minutes=184.0)
        assert session.blood_volume_processed_l == pytest.approx(64.4, rel=1e-3)

    def test_a_poor_access_clears_less(self):
        """Same dialysate, same duration — only the blood flow differs."""
        good = estimate_session_removal(a_session(blood_flow_ml_min=350.0), a_serum())[POTASSIUM]
        poor = estimate_session_removal(a_session(blood_flow_ml_min=120.0), a_serum())[POTASSIUM]
        assert poor.mass_mg < good.mass_mg

    def test_removal_cannot_exceed_what_the_blood_delivered(self):
        """A hard ceiling: solute can only leave in blood that went through."""
        session = a_session(blood_flow_ml_min=50.0, duration_minutes=60.0,
                            dialysate_volume_l=60.0)
        serum = a_serum()
        estimate = estimate_session_removal(session, serum)[POTASSIUM]

        blood_l = session.blood_volume_processed_l
        diffusible = serum.potassium_mmol_l * 39.10 * DEFAULT_COEFFICIENTS[POTASSIUM].diffusible_fraction
        assert estimate.diffusive_mg <= blood_l * diffusible * 0.9 + 1e-6

    def test_an_unrecorded_blood_flow_is_not_penalised(self):
        """Missing data must not silently understate a session."""
        known = estimate_session_removal(a_session(blood_flow_ml_min=350.0), a_serum())[POTASSIUM]
        unknown = estimate_session_removal(a_session(blood_flow_ml_min=None), a_serum())[POTASSIUM]
        assert unknown.mass_mg >= known.mass_mg

    def test_bath_composition_changes_the_direction_of_transfer(self):
        """Dialysate mix: a bath below serum removes, above serum adds."""
        removes = estimate_session_removal(
            a_session(bath_magnesium_meq=0.5), a_serum(magnesium_mg_dl=2.4)
        )[MAGNESIUM]
        adds = estimate_session_removal(
            a_session(bath_magnesium_meq=3.0), a_serum(magnesium_mg_dl=1.4)
        )[MAGNESIUM]
        assert removes.mass_mg > 0
        assert adds.mass_mg < 0

    def test_a_recorded_bath_beats_the_assumed_one(self):
        assumed = estimate_session_removal(a_session(), a_serum())[CALCIUM]
        recorded = estimate_session_removal(a_session(bath_calcium_meq=2.5), a_serum())[CALCIUM]
        assert assumed.assumptions and not recorded.assumptions
        assert recorded.mass_mg != assumed.mass_mg


class TestSessionRecordIntegrity:
    def test_delivered_volume_beats_the_prescription(self):
        """A session cut short must not be credited with the full order."""
        full = estimate_session_removal(a_session(), a_serum())[POTASSIUM]
        short = estimate_session_removal(
            a_session(dialysate_delivered_l=15.0), a_serum()
        )[POTASSIUM]
        assert short.mass_mg < full.mass_mg * 0.7

    def test_the_lactate_value_in_the_potassium_column_is_rejected(self):
        """11 real sessions record a 45 mEq/L 'potassium' bath — that is lactate.

        Modelling it would predict a huge potassium *gain* and could tighten a
        limit on false evidence, so the session is refused instead.
        """
        problems = validate_session(a_session(bath_potassium_meq=45.0))
        assert problems and "outside the plausible range" in problems[0]

        with pytest.raises(SessionNotModellable):
            estimate_session_removal(a_session(bath_potassium_meq=45.0), a_serum())

    def test_a_missing_volume_is_refused_not_guessed(self):
        with pytest.raises(SessionNotModellable):
            estimate_session_removal(a_session(dialysate_volume_l=None), a_serum())

    def test_an_absent_serum_value_yields_no_estimate_for_that_analyte(self):
        removals = estimate_session_removal(a_session(), a_serum(potassium_mmol_l=None))
        assert POTASSIUM not in removals
        assert PHOSPHORUS in removals

    def test_assumed_bath_composition_is_declared(self):
        estimate = estimate_session_removal(a_session(), a_serum())[CALCIUM]
        assert estimate.assumptions, "an assumed bath must be stated, not silent"


# ── Totals, not limits ───────────────────────────────────────────────────────

def a_goal(key="potassium_mg", goal=3000.0, kind="limit", current=2000.0):
    return {"key": key, "name": key, "unit": "mg", "goal": goal, "current": current,
            "kind": kind, "priority": 2, "rationale": ""}


CALIBRATED = {
    POTASSIUM: with_calibration(POTASSIUM, saturation=0.85, holdout_mae=0.34),
    PHOSPHORUS: with_calibration(PHOSPHORUS, saturation=0.55, holdout_mae=0.38),
}
TODAY = date(2026, 8, 17)


class TestLimitsNeverMove:
    """A treatment changes the day's balance, not the dietary guideline.

    KDOQI's 2,000-3,000 mg/day of potassium is already the figure for a patient
    on dialysis. Raising it on a treatment day would count that clearance twice.
    """

    def test_a_session_does_not_change_the_potassium_limit(self):
        goals, day = apply_to_totals(
            [a_goal()], [a_session()], a_serum(measured_on=TODAY), CALIBRATED, TODAY
        )
        assert day.had_dialysis
        assert goals[0]["goal"] == 3000.0

    def test_a_session_does_not_change_any_limit(self):
        goals, _ = apply_to_totals(
            [a_goal(), a_goal("calcium_mg", 1000.0), a_goal("phosphorus_mg", 900.0)],
            [a_session()], a_serum(measured_on=TODAY), CALIBRATED, TODAY,
        )
        assert [g["goal"] for g in goals] == [3000.0, 1000.0, 900.0]

    def test_the_intake_figure_is_left_alone_for_the_guideline_check(self):
        """`current` stays dietary intake so intake-vs-limit stays comparable."""
        goals, _ = apply_to_totals(
            [a_goal(current=2000.0)], [a_session()], a_serum(measured_on=TODAY),
            CALIBRATED, TODAY,
        )
        assert goals[0]["current"] == 2000.0


class TestRemovalLowersTheDaysBalance:
    def test_potassium_eaten_and_then_dialysed_off_nets_lower(self):
        goals, _ = apply_to_totals(
            [a_goal(current=2000.0)], [a_session()], a_serum(measured_on=TODAY),
            CALIBRATED, TODAY,
        )
        balance = goals[0]["dialysis_balance"]
        assert balance["direction"] == "removed"
        assert balance["delta"] < 0
        assert balance["net"] < balance["intake"]

    def test_a_high_potassium_withholds_the_removal_credit(self):
        """A total shown near zero on the day of a high potassium would mislead."""
        serum = a_serum(potassium_mmol_l=SERUM_BLOCK_ABOVE[POTASSIUM] + 0.1, measured_on=TODAY)
        goals, _ = apply_to_totals([a_goal()], [a_session()], serum, CALIBRATED, TODAY)

        balance = goals[0]["dialysis_balance"]
        assert balance["delta"] == 0
        assert balance["net"] == balance["intake"]
        assert "not deducted while it is high" in balance["withheld"]

    def test_no_recent_bloods_withholds_the_removal_credit(self):
        stale = a_serum(measured_on=TODAY - timedelta(days=400))
        goals, _ = apply_to_totals([a_goal()], [a_session()], stale, CALIBRATED, TODAY)
        assert goals[0]["dialysis_balance"]["delta"] == 0
        assert "No recent blood test" in goals[0]["dialysis_balance"]["withheld"]

    def test_ageing_bloods_shrink_the_removal_credit(self):
        """Bloods are drawn monthly, so the taper runs across the back half."""
        fresh = apply_to_totals([a_goal()], [a_session()], a_serum(measured_on=TODAY),
                                CALIBRATED, TODAY)[0][0]
        ageing = apply_to_totals([a_goal()], [a_session()],
                                 a_serum(measured_on=TODAY - timedelta(days=22)),
                                 CALIBRATED, TODAY)[0][0]
        assert 0 > ageing["dialysis_balance"]["delta"] > fresh["dialysis_balance"]["delta"]

    def test_a_month_old_result_counts_for_nothing(self):
        """A serum potassium can move a full mmol/L between treatments, so a
        month-old value is not evidence about today."""
        goals, _ = apply_to_totals(
            [a_goal()], [a_session()],
            a_serum(measured_on=TODAY - timedelta(days=31)), CALIBRATED, TODAY,
        )
        assert goals[0]["dialysis_balance"]["delta"] == 0
        assert goals[0]["dialysis_balance"]["withheld"]

    def test_a_fortnight_old_result_still_counts_in_full(self):
        recent = apply_to_totals([a_goal()], [a_session()],
                                 a_serum(measured_on=TODAY - timedelta(days=13)),
                                 CALIBRATED, TODAY)[0][0]
        today = apply_to_totals([a_goal()], [a_session()], a_serum(measured_on=TODAY),
                                CALIBRATED, TODAY)[0][0]
        assert recent["dialysis_balance"]["delta"] == today["dialysis_balance"]["delta"]

    def test_an_uncalibrated_analyte_is_discounted(self):
        goals, _ = apply_to_totals(
            [a_goal("magnesium_mg", 420.0)], [a_session()],
            a_serum(measured_on=TODAY), CALIBRATED, TODAY,
        )
        balance = goals[0]["dialysis_balance"]
        assert balance["calibrated"] is False
        assert any("not been confirmed" in r for r in balance["reasons"])

    def test_a_scheduled_session_changes_nothing(self):
        goals, day = apply_to_totals(
            [a_goal()], [a_session(completed=False)], a_serum(measured_on=TODAY),
            CALIBRATED, TODAY,
        )
        assert day.session_count == 0
        assert "dialysis_balance" not in goals[0]
        assert "not recorded as completed" in " ".join(day.notes)


class TestGainRaisesTheDaysTotal:
    """The case this whole feature most needs to get right.

    A patient takes on calcium from the bath without eating any of it. If that
    never reaches the day's total, their calcium load is understated on every
    treatment day.
    """

    def test_bath_calcium_is_added_to_the_days_total(self):
        goals, _ = apply_to_totals(
            [a_goal("calcium_mg", 1000.0, current=400.0)], [a_session()],
            a_serum(measured_on=TODAY), CALIBRATED, TODAY,
        )
        balance = goals[0]["dialysis_balance"]
        assert balance["direction"] == "gained"
        assert balance["delta"] > 0
        assert balance["net"] > balance["intake"]

    def test_a_gain_is_counted_even_with_no_recent_bloods(self):
        """Gains are never gated — a guard that only ever relaxes is not a guard."""
        goals, _ = apply_to_totals(
            [a_goal("calcium_mg", 1000.0, current=400.0)], [a_session()],
            a_serum(measured_on=None), CALIBRATED, TODAY,
        )
        assert goals[0]["dialysis_balance"]["delta"] > 0

    def test_a_gain_is_counted_even_when_serum_is_high(self):
        serum = a_serum(calcium_mg_dl=SERUM_BLOCK_ABOVE[CALCIUM] + 0.5, measured_on=TODAY)
        goals, _ = apply_to_totals(
            [a_goal("calcium_mg", 1000.0, current=400.0)], [a_session()],
            serum, CALIBRATED, TODAY,
        )
        assert goals[0]["dialysis_balance"]["delta"] > 0


class TestProtein:
    def test_amino_acid_loss_lowers_retained_protein(self):
        """Protein is a target, not a limit: less is retained than was eaten."""
        goals, _ = apply_to_totals(
            [a_goal("protein_g", 82.5, kind="target", current=70.0)], [a_session()],
            a_serum(measured_on=TODAY), CALIBRATED, TODAY,
        )
        balance = goals[0]["dialysis_balance"]
        assert balance["net"] < balance["intake"]
        assert 4 <= balance["intake"] - balance["net"] <= 13   # grams, not milligrams


class TestNoDialysis:
    def test_a_rest_day_touches_nothing(self):
        goals, day = apply_to_totals([a_goal()], [], a_serum(measured_on=TODAY),
                                     CALIBRATED, TODAY)
        assert not day.had_dialysis
        assert "dialysis_balance" not in goals[0]
        assert goals[0]["goal"] == 3000.0


class TestItSaysWhyWhenItCannotCompute:
    """Silence is the failure mode this feature actually shipped with.

    A real session on 2026-08-19 had no recorded dialysate volume and labs a
    year old, so the model correctly produced nothing — and the page showed
    nothing, which read as "dialysis had no effect on my nutrition". An
    unexplained blank is indistinguishable from a confident zero.
    """

    def test_a_session_without_a_dialysate_volume_explains_itself(self):
        goals, day = apply_to_totals(
            [a_goal()], [a_session(dialysate_volume_l=None)],
            a_serum(measured_on=TODAY), CALIBRATED, TODAY,
        )
        assert day.had_dialysis, "the treatment still happened"
        assert day.notes, "a session that cannot be modelled must say so"
        note = " ".join(day.notes)
        assert "could not be included" in note
        assert "dialysate volume" in note.lower()
        assert "flowsheet" in note, "tell the patient how to fix it"

    def test_analytes_with_no_recent_bloods_are_named(self):
        """Otherwise potassium simply vanishes from the day with no reason."""
        goals, day = apply_to_totals(
            [a_goal(), a_goal("protein_g", 82.5, kind="target", current=70.0)],
            [a_session()],
            SerumLevels(measured_on=TODAY),   # no serum values at all
            CALIBRATED, TODAY,
        )
        note = " ".join(day.notes)
        assert "No recent blood test" in note
        assert "potassium" in note
        # Protein is not serum-gated, so it still resolves.
        protein = next(g for g in goals if g["key"] == "protein_g")
        assert protein["dialysis_balance"]["direction"] == "removed"

    def test_a_fully_specified_session_needs_no_excuse(self):
        _, day = apply_to_totals(
            [a_goal()], [a_session()], a_serum(measured_on=TODAY), CALIBRATED, TODAY
        )
        assert not day.notes, f"nothing to explain, but got: {day.notes}"
