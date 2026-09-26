"""Glucose is a bath constituent, so it crosses the membrane BOTH ways.

Potassium and phosphorus are essentially always removed; calcium against a
3.0 mEq/L bath is essentially always gained. Glucose is the one analyte whose
direction depends on the day: the NxStage lactate cartridge is **100 mg/dL**, so
a fasting serum below that GAINS sugar the patient never ate, and a diabetic's
serum above it LOSES sugar to the dialysate.

That figure is why this could not be modelled earlier. The bath concentration is
not recorded per session and no citation for it existed in the repository, so a
gradient would have had to be invented. It now comes off the printed cartridge
label (photographed 2026-09-26), which also confirms the calcium 3.0 and
magnesium 1.0 that `dialysis_balance` had been ASSUMING and declaring as such.

These tests pin the three things that would be clinically wrong if they slipped:

  * the direction follows the gradient, with no special-casing;
  * the credit lands on `carbs_g` and never on `sugar_g` — blood glucose
    crossing a dialyser is carbohydrate leaving the body, while `sugar_g` is a
    LIMIT on ADDED sugars, and crediting a removal there would tell a diabetic
    on dialysis they had room for more sugar;
  * a cartridge whose label has not been read reports None rather than
    inheriting the numbers of one that has.
"""

from __future__ import annotations

from datetime import date

from app.services.dialysate_products import bath_for_sak
from app.services.dialysis_balance import (
    GLUCOSE,
    DEFAULT_BATH_GLUCOSE_MG_DL,
    SerumLevels,
    SessionParams,
    estimate_session_removal,
)
from app.services.dialysis_day_adjustment import (
    GOAL_KEY, SERUM_BLOCK_ABOVE, apply_to_totals,
)


def _session(**kw) -> SessionParams:
    """An ordinary home session: 30 L bath, 4 h, Qb 350, 1 L off."""
    params = dict(
        dialysate_volume_l=30.0, duration_minutes=240.0,
        blood_flow_ml_min=350.0, ultrafiltration_ml=1000.0,
        bath_potassium_meq=1.0, completed=True,
    )
    params.update(kw)
    return SessionParams(**params)


# ── The label ────────────────────────────────────────────────────────────────

def test_the_cartridge_label_supplies_the_bath():
    """SAK 401, read off the printed label rather than assumed."""
    product = bath_for_sak(401)
    assert product is not None
    assert product.potassium_meq == 1.0
    assert product.glucose_mg_dl == 100.0
    # These two were assumptions in dialysis_balance; the label confirms them.
    assert product.calcium_meq == 3.0
    assert product.magnesium_meq == 1.0
    assert product.lactate_meq == 45.0
    assert product.source and "label" in product.source.lower()


def test_an_unread_label_reports_nothing_rather_than_inheriting():
    """404 differs in potassium; its other constituents have no source."""
    product = bath_for_sak(404)
    assert product is not None
    assert product.potassium_meq == 2.0
    for unknown in ("glucose_mg_dl", "calcium_meq", "magnesium_meq", "lactate_meq"):
        assert getattr(product, unknown) is None, (
            f"{unknown} must not be copied from the 401 label — different product"
        )


# ── The gradient ─────────────────────────────────────────────────────────────

def test_a_high_serum_loses_glucose_to_the_bath():
    """This patient's glucose averages 146 mg/dL against a 100 mg/dL bath."""
    result = estimate_session_removal(
        _session(bath_glucose_mg_dl=100.0),
        SerumLevels(glucose_mg_dl=250.0),
    )
    assert GLUCOSE in result
    assert result[GLUCOSE].mass_mg > 0, "above the bath, glucose is REMOVED"
    assert not result[GLUCOSE].is_gain


def test_a_serum_below_the_bath_GAINS_sugar_nobody_ate():
    """Dialysate glucose absorption is real and belongs in the day's total."""
    result = estimate_session_removal(
        _session(bath_glucose_mg_dl=100.0),
        SerumLevels(glucose_mg_dl=70.0),
    )
    assert result[GLUCOSE].mass_mg < 0, "below the bath, glucose is GAINED"
    assert result[GLUCOSE].is_gain


def test_no_serum_glucose_means_no_estimate_at_all():
    """An absent measurement is absent — never a zero, never the bath value."""
    result = estimate_session_removal(_session(), SerumLevels(potassium_mmol_l=4.0))
    assert GLUCOSE not in result


def test_the_bath_falls_back_to_the_standard_concentrate():
    """A session with no SAK still models against the documented 100 mg/dL."""
    assert DEFAULT_BATH_GLUCOSE_MG_DL == 100.0
    with_bath = estimate_session_removal(
        _session(bath_glucose_mg_dl=100.0), SerumLevels(glucose_mg_dl=200.0))
    without = estimate_session_removal(
        _session(), SerumLevels(glucose_mg_dl=200.0))
    assert without[GLUCOSE].mass_mg == with_bath[GLUCOSE].mass_mg


# ── Where the credit lands ───────────────────────────────────────────────────

def test_glucose_adjusts_carbohydrate_and_never_the_added_sugar_limit():
    """The distinction is clinical, not cosmetic.

    `sugar_g` limits ADDED sugars to 5% of calories for a diabetic. Crediting a
    dialysis glucose removal against it would read as permission to eat more
    sugar because blood glucose fell during treatment.
    """
    assert GOAL_KEY[GLUCOSE] == "carbs_g"
    assert "sugar_g" not in GOAL_KEY.values()


def test_a_high_glucose_withholds_the_removal_credit():
    """Crediting removal against a TARGET tells the patient to eat more.

    Every other threshold here guards a limit ("you have room for more"); this
    one guards a target, so the conservative direction is the same but the
    reasoning is inverted. Gains are never gated.
    """
    assert SERUM_BLOCK_ABOVE[GLUCOSE] == 180.0
    assert SERUM_BLOCK_ABOVE[GLUCOSE] > DEFAULT_BATH_GLUCOSE_MG_DL, (
        "a threshold at or below the bath would gate every ordinary session"
    )


# ── Units: the 1000x guard ───────────────────────────────────────────────────

def test_a_gram_goal_is_reported_in_GRAMS_not_milligrams():
    """The model works in mg; `carbs_g` is grams.

    That scaling used to test `key == "protein_g"`, because protein was the only
    gram-denominated goal. Glucose maps to `carbs_g`, so the old test would have
    reported a carbohydrate change a THOUSAND times too large — and no other
    test in the suite would have noticed, since nothing else lands on a `_g`
    key. A day's dialysis glucose is single-digit to low-double-digit grams.

    `measured_on` must be set: without it the staleness gate withholds the
    credit entirely and this would pass for the wrong reason.
    """
    today = date(2026, 9, 26)
    goals = [{
        "key": "carbs_g", "name": "Carbohydrate", "unit": "g",
        "goal": 250.0, "kind": "target", "current": 200.0,
        "priority": 60, "rationale": "",
    }]
    # 150 mg/dL: above the 100 mg/dL bath so glucose is removed, and below the
    # 180 mg/dL gate so the credit is actually applied.
    serum = SerumLevels(glucose_mg_dl=150.0, measured_on=today)

    _adjusted, day = apply_to_totals(
        goals, [_session(bath_glucose_mg_dl=100.0)], serum, today=today,
    )

    carbs = [b for b in day.balances if b.key == "carbs_g"]
    assert carbs, "glucose must reach the carbohydrate goal"
    delta = abs(carbs[0].dialysis_delta)
    assert 0 < delta < 100, (
        f"a day's glucose transfer is grams, got {delta:g} — a value in the "
        "thousands means the mg->g scale did not fire for this key"
    )
