# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""Α reads the therapy switch — TASKS 20a, and the switch's stated purpose.

The switch shipped on 2026-10-14 as a table nothing consulted: `compute_alpha`
resolved its indications from condition TEXT and never looked at what the
patient said they were receiving. That is §3ar's dead control on the axis the
operator asked for — *"items zeroed out (no impact) when not present (like a
switch)"* — so the zeros had nowhere to go.

Two claims are pinned here, and the second is the one that is easy to get
backwards:

1. A declared therapy GRANTS an indication axis. It is a statement, where
   condition text is a spelling — "ESKD" matches none of the renal hints.
2. **A stated zero never REMOVES one.** A patient with ESRD who says they are
   not on dialysis is pre-dialysis CKD: still renal, because the condition says
   so. Subtracting would withhold a guideline from the patient who needs it.
"""

import pytest

from app.services.hebcs_engine import (
    compute_alpha, indication_provenance, indications_for, pathways_for,
)


class _Condition:
    """The shape `clinical_sources.conditions()` returns."""
    def __init__(self, name, icd11_title=None):
        self.name = name
        self.icd11_title = icd11_title


def _switch(code, receiving, **kw):
    return {code: {"code": code, "receiving": receiving, **kw}}


# ── 1. a therapy is evidence the condition's SPELLING may not carry ─────────

def test_a_condition_spelled_ESKD_grants_no_axis_on_its_own():
    """The §3an keyword shape, measured rather than asserted. This is the
    weakness a declared therapy exists to cover — and the exact failure that
    killed the first version of the surfacing (`_CONDITION_HINTS`)."""
    assert indications_for([_Condition("ESKD")]) == set()


def test_a_DECLARED_DIALYSIS_grants_the_renal_axis():
    """QB94.1 is "Care involving extracorporeal dialysis" — WHO's words, which
    already contain what the renal hints look for. No code->axis table was
    added; a second hand-typed clinical mapping is what §3an forbids."""
    axes = indications_for([_Condition("ESKD")], _switch("QB94.1", True))
    assert "renal" in axes


def test_a_dependence_code_also_grants_it():
    """QB42 is "Dependence on renal dialysis". A patient can be dependent on
    dialysis without a condition row anybody coded."""
    assert "renal" in indications_for(None, _switch("QB42", True))


def test_a_therapy_with_no_tagged_axis_grants_NOTHING():
    """Radiotherapy matches no hint, so it grants no axis — correct while no
    guideline target is tagged for it. Granting an axis with nothing to score
    would report a managed patient as unmanaged."""
    assert indications_for(None, _switch("QB96", True)) == set()


# ── 2. a stated zero is evidence, and it never subtracts ────────────────────

def test_a_STATED_ZERO_does_not_remove_an_axis(  ):
    """⚠️ The direction that matters. A renal patient who is NOT on dialysis is
    pre-dialysis CKD — still renal. Reading the zero as "not renal" would
    withhold every KDIGO target from exactly the patient being worked up for
    them."""
    conditions = [_Condition("End-Stage Renal Disease")]
    assert "renal" in indications_for(conditions, _switch("QB94.1", False))


def test_a_stated_zero_alone_grants_no_axis_either():
    """It says nothing about the disease, in either direction."""
    assert indications_for(None, _switch("QB94.1", False)) == set()


def test_an_UNANSWERED_therapy_says_nothing():
    """No row at all. §3at's third state: absence of evidence, not evidence of
    absence — and the reason the switch replaced a set."""
    assert indications_for([_Condition("ESKD")], {}) == set()


# ── 3. the axis must be auditable ──────────────────────────────────────────

def test_the_axis_says_WHY_it_applies():
    """An axis decides which guideline Α applies. A bare set of names cannot be
    checked by the person it is about."""
    why = indication_provenance([_Condition("Chronic kidney disease")],
                                _switch("QB94.2", True))
    assert "renal" in why
    joined = " ".join(why["renal"])
    assert "condition: Chronic kidney disease" in joined
    assert "QB94.2" in joined and "peritoneal" in joined.lower()


def test_provenance_names_only_the_therapy_when_the_condition_is_silent():
    why = indication_provenance([_Condition("ESKD")], _switch("QB94.1", True))
    assert len(why["renal"]) == 1 and "QB94.1" in why["renal"][0]


# ── 4. Ω and Α must agree on the axis ───────────────────────────────────────

def test_BOTH_scores_read_the_same_evidence():
    """`indications_for` is deliberately one function serving both. Handing the
    switch to Α and not to Ω would reinstate the drift it exists to prevent —
    KDIGO applied while the same patient's PTH is called unexpected."""
    declared = _switch("QB94.1", True)

    without = {b.name for p in pathways_for([_Condition("ESKD")])
               for b in p.biomarkers}
    with_therapy = {b.name for p in pathways_for([_Condition("ESKD")],
                                                 therapies=declared)
                    for b in p.biomarkers}

    # Measured in the container, not asserted loosely — the first version of
    # this test read `gained & renal_markers or gained`, which passes on ANY
    # gain and so measured nothing (§3av: a scan is evidence only once it is
    # shown to see what it claims to).
    assert sorted(with_therapy - without) == [
        "CaxP Product", "Ferritin", "Iron Saturation (TSAT)", "PTH (Intact)"]
    assert not (without - with_therapy), (
        "a declaration may only ADD expected markers, never remove one")


# ── 5. the regimen is reported, never scored ───────────────────────────────

def test_the_REGIMEN_travels_even_when_alpha_is_None():
    """A patient on apheresis has no Α — no guideline target is tagged for it —
    and returning an empty object would read as "no treatment on record" for
    someone under active treatment (§3aa)."""
    out = compute_alpha({}, conditions=None,
                        therapies=_switch("QB99", True, regimen="plasma exchange"))
    assert out["alpha"] is None
    assert [t["code"] for t in out["therapies_receiving"]] == ["QB99"]
    assert out["regimens"] == {"plasma exchange": ["QB99"]}


def test_a_stated_zero_is_REPORTED_beside_alpha():
    """The whole point of a measured zero: Α can say a renal patient is not on
    a therapy without anybody guessing whether the question was asked."""
    out = compute_alpha({}, conditions=[_Condition("ESRD")],
                        therapies={**_switch("QB94.1", True),
                                   **_switch("QB94.2", False)})
    assert [t["code"] for t in out["therapies_receiving"]] == ["QB94.1"]
    assert [t["code"] for t in out["therapies_stated_zero"]] == ["QB94.2"]


def test_a_stated_zero_NEVER_enters_the_arithmetic():
    """Whether a patient SHOULD be on something they declined is a clinical
    judgement (§3an). Α must be identical with the zero present and absent."""
    values = {"Hemoglobin": 11.3, "PTH": 300, "Ferritin": 500}
    conditions = [_Condition("End-Stage Renal Disease")]
    bare = compute_alpha(values, conditions=conditions,
                         therapies=_switch("QB94.1", True))
    with_zero = compute_alpha(values, conditions=conditions,
                              therapies={**_switch("QB94.1", True),
                                         **_switch("QB94.2", False),
                                         **_switch("QB98", False)})
    assert bare["alpha"] == with_zero["alpha"], (
        "a therapy the patient declined must not move the management score")
    assert len(with_zero["therapies_stated_zero"]) == 2


def test_a_zeroed_member_is_not_part_of_a_regimen():
    """A compound is what the patient is actually given."""
    out = compute_alpha({}, therapies={
        **_switch("QB94.1", True, regimen="anaemia management"),
        **_switch("QB98", False, regimen="anaemia management")})
    assert out["regimens"] == {"anaemia management": ["QB94.1"]}


def test_the_titles_come_from_WHO_and_are_not_written_here():
    """§3ad, applied to this payload: every title must be the catalog's."""
    from app.services.icd11_catalog import get_icd11_by_code
    out = compute_alpha({}, therapies=_switch("QB94.2", True))
    row = out["therapies_receiving"][0]
    assert row["title"] == get_icd11_by_code("QB94.2").title


@pytest.mark.parametrize("code", ["ZZ99.9", "", "NOTACODE"])
def test_a_code_outside_the_catalog_carries_NO_invented_title(code):
    """A title typed from memory beside a code is a second source of truth."""
    out = compute_alpha({}, therapies=_switch(code, True))
    assert out["therapies_receiving"][0]["title"] is None
