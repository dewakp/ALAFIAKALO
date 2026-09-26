"""The SAK number is the product; the K+ cell is a person transcribing it.

`dialysate_products` resolves bath potassium from the cartridge code rather than
the typed cell, because the two disagree in a way that is plainly transcription
error rather than a change of prescription. Measured on this record:

    SAK 401   K=1 on 995 sessions · K=2 on 13 · blank on 4
    SAK 404   K=1 on   5 sessions · K=2 on 56
    SAK 405   K=1 on   1 session  · K=2 on  2

A product does not change its own potassium 13 times in 1,012 uses.

These tests pin the three behaviours that matter clinically:

  * the product wins a disagreement, and the disagreement is REPORTED — a silent
    correction would hide the 18 bad cells instead of surfacing them;
  * a blank cell is FILLED from the product, which is where the mapping earns
    the most (5 sessions record a SAK and no K at all);
  * anything we cannot evidence — SAK 405 at three sessions, the mistyped `1`,
    a code we have never seen — falls back to what the flowsheet typed and
    invents nothing.
"""

from __future__ import annotations

import pytest

from app.services.dialysate_products import bath_for_sak, reconcile_bath_potassium


def test_the_product_fills_a_blank_cell():
    """Five sessions record a SAK and no K. This is the case it earns most on."""
    value, note = reconcile_bath_potassium(401, None)
    assert value == 1.0
    assert note and "left it blank" in note
    assert "SAK 401" in note


def test_the_product_wins_a_disagreement_and_says_so():
    """13 sessions type K=2 against a SAK 401 cartridge."""
    value, note = reconcile_bath_potassium(401, 2.0)
    assert value == 1.0, "the cartridge that was run decides the bath"
    assert note, "a corrected clinical value must never be silent"
    assert "2" in note and "1" in note
    assert "Check the K+ cell" in note


def test_agreement_produces_no_note():
    """995 sessions agree. Saying so every time is noise, not information."""
    assert reconcile_bath_potassium(401, 1.0) == (1.0, None)
    assert reconcile_bath_potassium(404, 2.0) == (2.0, None)


def test_the_other_direction_is_corrected_too():
    """5 sessions type K=1 against a SAK 404 cartridge."""
    value, note = reconcile_bath_potassium(404, 1.0)
    assert value == 2.0
    assert note and "SAK 404" in note


@pytest.mark.parametrize("sak, reason", [
    (405, "three sessions split 1:2 is not evidence of anything"),
    (1, "not a product code — one session records this, mistyped"),
    (999, "a code this repo has never seen"),
])
def test_an_unevidenced_code_changes_nothing(sak, reason):
    """Unrecognised is not the same as absent: keep what was recorded."""
    assert bath_for_sak(sak) is None, reason
    assert reconcile_bath_potassium(sak, 1.0) == (1.0, None)
    # ...and it must not invent a value where none was typed either.
    assert reconcile_bath_potassium(sak, None) == (None, None)


def test_no_sak_recorded_keeps_the_typed_cell():
    """~900 sessions predate SAK recording entirely."""
    assert reconcile_bath_potassium(None, 1.0) == (1.0, None)
    assert reconcile_bath_potassium(None, None) == (None, None)


def test_calcium_magnesium_and_glucose_are_deliberately_absent():
    """The bath contains them; this repo cannot say in what concentration.

    The labels are not on disk and no citation exists for these SAK codes, so
    `dialysis_balance` keeps applying its declared assumption. Filling these in
    from recollection would turn an honest assumption into a false measurement —
    and a glucose gradient cannot be modelled at all until its bath
    concentration has a source.
    """
    product = bath_for_sak(401)
    assert product is not None
    for absent in ("calcium_meq", "magnesium_meq", "glucose_mg_dl"):
        assert not hasattr(product, absent), (
            f"{absent} must not be guessed at — see the module docstring"
        )
