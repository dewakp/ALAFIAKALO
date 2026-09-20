"""The effects pass reports alongside the totals — it never rewrites them.

`apply_to_totals` states the contract this must honour: "the limit is untouched,
`current` stays the dietary intake, so the guideline comparison is unchanged;
the balance is reported alongside". A general effects layer that quietly moved
`current` would break that in the one place a clinician reads a number against
a guideline.
"""

from __future__ import annotations

import pytest

from app.services.nutrient_effects_day import (
    AgentExposure, apply_effects_to_totals,
)
from app.services.nutrient_effects_service import (
    ADDS, INCREASES_REQUIREMENT, REMOVES, Effect,
)


def _goal(key: str, unit: str, kind: str, current: float, goal: float = 100.0) -> dict:
    return {"key": key, "name": key, "unit": unit, "goal": goal,
            "kind": kind, "priority": 10, "rationale": "", "current": current}


def _protein_effect(magnitude: float = 9.0) -> Effect:
    return Effect(
        agent_kind="treatment", agent_key="hemodialysis", agent_label="Hemodialysis",
        nutrient_key="protein_g", direction=REMOVES, magnitude=magnitude,
        magnitude_unit="g", basis="per_session",
        mechanism="Free amino acids leave in the effluent.",
    )


def _session(occurrences: int = 1, volume_l: float = 30.0) -> AgentExposure:
    return AgentExposure(
        kind="treatment", key="hemodialysis", label="Hemodialysis",
        occurrences=occurrences, context={"dialysate_volume_l": volume_l},
    )


# ── The contract ──────────────────────────────────────────────────────

def test_current_is_never_mutated():
    """The guideline comparison must survive the effects layer untouched."""
    goals = [_goal("protein_g", "g", "target", current=70.0)]
    adjusted, _ = apply_effects_to_totals(goals, [_session()], [_protein_effect()])
    assert adjusted[0]["current"] == 70.0
    assert goals[0]["current"] == 70.0, "the caller's own list was mutated"


def test_the_dialysis_balance_field_is_never_touched():
    """Two layers writing one field is how a fix lands on one path only."""
    goals = [{**_goal("protein_g", "g", "target", 70.0),
              "dialysis_balance": {"intake": 70.0, "delta": -9.0}}]
    adjusted, _ = apply_effects_to_totals(goals, [_session()], [_protein_effect()])
    assert adjusted[0]["dialysis_balance"] == {"intake": 70.0, "delta": -9.0}


def test_an_effect_attaches_under_its_own_key():
    goals = [_goal("protein_g", "g", "target", 70.0)]
    adjusted, day = apply_effects_to_totals(goals, [_session()], [_protein_effect()])
    attached = adjusted[0]["nutrient_effects"]
    assert len(attached) == 1
    assert attached[0]["agent"] == "Hemodialysis"
    assert attached[0]["delta"] == pytest.approx(-9.0)
    assert attached[0]["applied"] is True
    assert day.had_effects


def test_occurrences_multiply_the_effect():
    """Two treatments in a day lose twice the amino acids."""
    goals = [_goal("protein_g", "g", "target", 70.0)]
    adjusted, _ = apply_effects_to_totals(
        goals, [_session(occurrences=2)], [_protein_effect()])
    assert adjusted[0]["nutrient_effects"][0]["delta"] == pytest.approx(-18.0)


def test_two_sessions_in_a_day_both_count():
    """A dict keyed on (kind, key) keeps only the LAST exposure.

    Two haemodialysis sessions in one day is ordinary, and each carries its own
    dialysate volume — so collapsing them silently drops the first and scales
    the wrong ratio. 15 L clamps to 0.5x (4.5 g) and 60 L to the 2.0x ceiling
    (18 g); summed that is 22.5 g, which is neither session alone nor twice
    either of them.
    """
    goals = [_goal("protein_g", "g", "target", 70.0)]
    two = [
        AgentExposure(kind="treatment", key="hemodialysis", label="Hemodialysis",
                      context={"dialysate_volume_l": 15.0}),
        AgentExposure(kind="treatment", key="hemodialysis", label="Hemodialysis",
                      context={"dialysate_volume_l": 60.0}),
    ]
    scaling = Effect(
        agent_kind="treatment", agent_key="hemodialysis", agent_label="Hemodialysis",
        nutrient_key="protein_g", direction=REMOVES, magnitude=9.0,
        magnitude_unit="g", basis="per_session",
        scales_with="dialysate_volume_l", scale_reference=30.0,
        scale_min=0.5, scale_max=2.0,
    )
    adjusted, _ = apply_effects_to_totals(goals, two, [scaling])
    assert adjusted[0]["nutrient_effects"][0]["delta"] == pytest.approx(-22.5)


def test_an_agent_not_met_today_contributes_nothing():
    """A stored fact is not an exposure. Knowing what sevelamer does is not the
    same as the patient having taken it."""
    goals = [_goal("protein_g", "g", "target", 70.0)]
    adjusted, day = apply_effects_to_totals(goals, [], [_protein_effect()])
    assert "nutrient_effects" not in adjusted[0]
    assert not day.had_effects


# ── Gating reports; it does not go silent ─────────────────────────────

def test_a_withheld_effect_is_still_reported():
    """Silence would read as "nothing happened", which is false (§3aa).

    Lowering a LIMIT creates dietary headroom, so it needs a measurement. With
    none, the effect is shown WITH the reason it was not counted.
    """
    goals = [_goal("phosphorus_mg", "mg", "limit", current=900.0)]
    binder = Effect(
        agent_kind="medication", agent_key="a binder", agent_label="A Binder",
        nutrient_key="phosphorus_mg", direction=REMOVES, magnitude=200.0,
        magnitude_unit="mg", basis="per_dose_unit",
    )
    exposure = AgentExposure(kind="medication", key="a binder", label="A Binder")
    adjusted, _ = apply_effects_to_totals(
        goals, [exposure], [binder], measurement_fresh=False)

    entry = adjusted[0]["nutrient_effects"][0]
    assert entry["applied"] is False
    assert entry["delta"] == 0.0
    assert entry["withheld"], "a withheld effect must say why"
    assert entry["modelled"] == pytest.approx(-200.0), "what it would have been is kept"


def test_the_same_effect_counts_once_a_measurement_confirms_it():
    goals = [_goal("phosphorus_mg", "mg", "limit", current=900.0)]
    binder = Effect(
        agent_kind="medication", agent_key="a binder", agent_label="A Binder",
        nutrient_key="phosphorus_mg", direction=REMOVES, magnitude=200.0,
        magnitude_unit="mg", basis="per_dose_unit",
    )
    exposure = AgentExposure(kind="medication", key="a binder", label="A Binder")
    adjusted, _ = apply_effects_to_totals(
        goals, [exposure], [binder], measurement_fresh=True)
    assert adjusted[0]["nutrient_effects"][0]["applied"] is True


def test_an_addition_is_never_gated():
    """Raising a LIMIT tightens the budget, so it needs no permission —
    the asymmetry `_gate_removal` already states."""
    goals = [_goal("sugar_g", "g", "limit", current=40.0)]
    dextrose = Effect(
        agent_kind="treatment", agent_key="peritoneal dialysis",
        agent_label="Peritoneal Dialysis", nutrient_key="sugar_g",
        direction=ADDS, magnitude=60.0, magnitude_unit="g",
        basis="per_litre_dialysate",
    )
    exposure = AgentExposure(kind="treatment", key="peritoneal dialysis",
                             label="Peritoneal Dialysis")
    adjusted, _ = apply_effects_to_totals(
        goals, [exposure], [dextrose], measurement_fresh=False)
    entry = adjusted[0]["nutrient_effects"][0]
    assert entry["applied"] is True
    assert entry["delta"] == pytest.approx(60.0)


# ── Refusals, never guesses ───────────────────────────────────────────

def test_an_unconvertible_unit_is_refused_not_guessed():
    """"4000 units" of an ESA does not convert to mg. §3am: an unreadable unit
    raises rather than assuming, because guessing lands a number in the wrong
    column."""
    goals = [_goal("iron_mg", "mg", "target", current=8.0)]
    esa = Effect(
        agent_kind="medication", agent_key="epoetin alfa", agent_label="Epoetin alfa",
        nutrient_key="iron_mg", direction=REMOVES, magnitude=4000.0,
        magnitude_unit="units", basis="per_dose_unit",
    )
    exposure = AgentExposure(kind="medication", key="epoetin alfa",
                             label="Epoetin alfa")
    adjusted, day = apply_effects_to_totals(goals, [exposure], [esa])
    assert "nutrient_effects" not in adjusted[0]
    assert any("does not convert" in n for n in day.notes)


def test_an_unknown_magnitude_is_noted_but_not_counted():
    """Recording THAT an effect exists is useful; inventing its size is not."""
    goals = [_goal("vitamin_b1_thiamine_mg", "mg", "target", current=1.0)]
    effect = Effect(
        agent_kind="treatment", agent_key="hemodialysis", agent_label="Hemodialysis",
        nutrient_key="vitamin_b1_thiamine_mg", direction=REMOVES,
        magnitude=None, magnitude_unit=None, basis="per_session",
    )
    adjusted, _ = apply_effects_to_totals(goals, [_session()], [effect])
    entry = adjusted[0]["nutrient_effects"][0]
    assert entry["applied"] is False
    assert entry["withheld"]


def test_a_nutrient_with_no_goal_is_named_not_dropped():
    """The magnesium lesson, generalised.

    Magnesium's transfer was computed on every dialysis day and discarded
    because no goal carried that key — and nothing said so. An effect with no
    goal to report against must produce a note, never silence.
    """
    goals = [_goal("protein_g", "g", "target", 70.0)]
    zinc = Effect(
        agent_kind="treatment", agent_key="hemodialysis", agent_label="Hemodialysis",
        nutrient_key="zinc_mg", direction=REMOVES, magnitude=2.0,
        magnitude_unit="mg", basis="per_session",
    )
    _, day = apply_effects_to_totals(goals, [_session()], [zinc])
    assert any("zinc_mg" in n for n in day.notes), day.notes


def test_increases_requirement_reports_without_moving_the_total():
    """An ESA raises what the patient NEEDS; it adds no iron to the day."""
    goals = [_goal("iron_mg", "mg", "target", current=8.0)]
    esa = Effect(
        agent_kind="medication", agent_key="epoetin alfa", agent_label="Epoetin alfa",
        nutrient_key="iron_mg", direction=INCREASES_REQUIREMENT,
        magnitude=1.0, magnitude_unit="mg", basis="per_dose_unit",
        mechanism="Drives erythropoiesis, which consumes iron.",
    )
    exposure = AgentExposure(kind="medication", key="epoetin alfa",
                             label="Epoetin alfa")
    adjusted, _ = apply_effects_to_totals(goals, [exposure], [esa])
    entry = adjusted[0]["nutrient_effects"][0]
    assert entry["delta"] == 0.0
    assert entry["direction"] == INCREASES_REQUIREMENT
    assert adjusted[0]["current"] == 8.0
