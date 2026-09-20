"""Fold a day's AGENT exposures into the nutrient picture, alongside the totals.

The general sibling of `dialysis_day_adjustment`, and deliberately modelled on
it. That module handles gradient transfer for the four solutes with a serum
draw and a bath concentration; this one handles everything else a patient is
exposed to — a treatment, a dose taken, a drug the unit administered, a
supplement, a herb — which is the far larger set and had no representation at
all.

WHAT IT DOES NOT DO
-------------------
It does not move `current`. `apply_to_totals` is explicit that "the limit is
untouched, `current` stays the dietary intake, so the guideline comparison is
unchanged; the balance is reported alongside", and an effects layer that
quietly rewrote the total would break that contract in the one place a
clinician reads a number against a guideline. Effects attach under their own
key and are reported beside the intake, never in place of it.

It also never touches `dialysis_balance`. Two layers writing one field is how a
fix lands on one path and misses the other.

GATING
------
`gate_needed()` decides from the goal's own `kind` whether crediting an effect
would move the patient toward "you are fine" — a limit lowered or a target
raised. Those need a measurement behind them. Where one is absent the effect is
still REPORTED, with the reason it was not credited: §3aa's rule that an
unexplained absence reads as "nothing happened", which here would be false.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.services.nutrient_effects_service import (
    ADDS, BINDS_DIETARY, BLOCKS_ABSORPTION, INCREASES_REQUIREMENT, REMOVES,
    Effect, gate_needed,
)

logger = logging.getLogger(__name__)

#: Unit conversions we will perform. Anything outside this is REFUSED rather
#: than guessed: §3am's rule that an unreadable unit raises instead of assuming
#: metric, because guessing is how a number lands in the wrong column.
_TO_BASE = {
    ("g", "g"): 1.0, ("mg", "mg"): 1.0, ("mcg", "mcg"): 1.0, ("iu", "iu"): 1.0,
    ("g", "mg"): 1000.0, ("mg", "g"): 0.001,
    ("mg", "mcg"): 1000.0, ("mcg", "mg"): 0.001,
}

#: Goal key suffix → the unit that goal is expressed in.
_GOAL_UNIT_BY_SUFFIX = {"_g": "g", "_mg": "mg", "_mcg": "mcg", "_iu": "iu"}


@dataclass(frozen=True)
class AgentExposure:
    """One agent the patient met today, and how much of it.

    `occurrences` is sessions for a treatment, doses for a medication.
    `context` carries whatever the effect's `scales_with` may reference — a
    session's `dialysate_volume_l`, for instance.
    """

    kind: str
    key: str
    label: str
    occurrences: int = 1
    context: dict[str, float] = field(default_factory=dict)


@dataclass
class AppliedEffect:
    """One effect's contribution to one nutrient, and whether it counted."""

    nutrient_key: str
    agent_label: str
    direction: str
    delta: float               # signed, in the GOAL's unit; 0.0 when withheld
    modelled: float            # what the effect computed, before gating
    applied: bool
    mechanism: str | None = None
    reason: str | None = None
    withheld: str | None = None


@dataclass
class EffectsDay:
    """The day's agent exposures, for display beside the numbers."""

    agents: list[str] = field(default_factory=list)
    applied: list[AppliedEffect] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def had_effects(self) -> bool:
        return bool(self.applied)


def _goal_unit(goal: dict) -> str | None:
    unit = str(goal.get("unit") or "").strip().lower()
    if unit:
        return unit
    key = str(goal.get("key") or "")
    for suffix, u in _GOAL_UNIT_BY_SUFFIX.items():
        if key.endswith(suffix):
            return u
    return None


def _convert(value: float, from_unit: str | None, to_unit: str | None) -> float | None:
    """Convert, or return None when we cannot do it honestly."""
    if from_unit is None or to_unit is None:
        return None
    factor = _TO_BASE.get((from_unit.lower(), to_unit.lower()))
    return None if factor is None else value * factor


def apply_effects_to_totals(
    goals: list[dict],
    exposures: list[AgentExposure],
    effects: list[Effect],
    *,
    measurement_fresh: bool = False,
) -> tuple[list[dict], EffectsDay]:
    """Attach each agent's effects to the goals they touch. Goals are copied.

    `measurement_fresh` is the caller's statement that a recent, relevant
    measurement exists. It gates only the effects that would reassure — see
    `gate_needed`. It is a single flag rather than per-nutrient serum because
    the nutrients this layer covers (glucose, thiamine, folate, zinc) have no
    serum draw in this system at all; pretending otherwise would be inventing a
    measurement that was never taken.
    """
    day = EffectsDay()
    adjusted = [dict(goal) for goal in goals]
    by_key = {goal["key"]: goal for goal in adjusted}

    # Grouped into a LIST per agent, not a dict of one. A dict comprehension
    # keyed on (kind, key) keeps only the last value, so two haemodialysis
    # sessions in one day — entirely ordinary — would silently collapse to one
    # and the first session's exposure would vanish. Each exposure also carries
    # its OWN context, and the protein clamp (0.5-2.0x) is applied per session,
    # so summing per exposure is not the same as scaling an average.
    exposures_by_agent: dict[tuple[str, str], list[AgentExposure]] = {}
    for exposure in exposures:
        exposures_by_agent.setdefault((exposure.kind, exposure.key), []).append(exposure)
    if exposures:
        day.agents = sorted({e.label for e in exposures})

    for effect in effects:
        matching = exposures_by_agent.get((effect.agent_kind, effect.agent_key))
        if not matching:
            continue    # a known effect for an agent the patient did not meet today

        goal = by_key.get(effect.nutrient_key)
        if goal is None:
            # The nutrient is real (it is a catalog key — the store refuses
            # anything else) but this patient has no goal for it, so there is
            # nothing to report it against. Say so once rather than drop it
            # silently: that silence is exactly how magnesium's computed
            # transfer disappeared for every dialysis patient.
            day.notes.append(
                f"{effect.agent_label} affects {effect.nutrient_key}, which is "
                "not one of your tracked targets, so it is not shown against one."
            )
            continue

        # Sum across EVERY exposure to this agent, each scaled by its own
        # context. Two sessions of different dialysate volume lose different
        # amounts of amino acid, and each is clamped on its own ratio.
        magnitude = 0.0
        size_unknown = False
        for exposure in matching:
            per_occurrence = effect.scaled_magnitude(exposure.context)
            if per_occurrence is None:
                size_unknown = True
                break
            magnitude += per_occurrence * max(1, exposure.occurrences)

        if size_unknown:
            day.applied.append(AppliedEffect(
                nutrient_key=effect.nutrient_key, agent_label=effect.agent_label,
                direction=effect.direction, delta=0.0, modelled=0.0, applied=False,
                mechanism=effect.mechanism,
                withheld=("The size of this effect is not established, so it is "
                          "noted but not counted."),
            ))
            continue

        converted = _convert(magnitude, effect.magnitude_unit, _goal_unit(goal))
        if converted is None:
            day.notes.append(
                f"{effect.agent_label}'s effect on {effect.nutrient_key} is recorded "
                f"in {effect.magnitude_unit or 'an unstated unit'}, which does not "
                f"convert to {_goal_unit(goal) or 'this goal'} — not counted."
            )
            continue

        # ADDS raises the day's figure; everything else lowers what the patient
        # effectively retains or absorbs. INCREASES_REQUIREMENT moves the goal,
        # not the total, so it is reported with a zero delta.
        if effect.direction == ADDS:
            delta = converted
        elif effect.direction == INCREASES_REQUIREMENT:
            delta = 0.0
        else:
            delta = -converted

        gated = gate_needed(effect.direction, str(goal.get("kind") or "target"))
        withheld = None
        if gated and not measurement_fresh:
            withheld = (
                "Not counted: this would lower what you appear to need, and "
                "there is no recent measurement to confirm it."
            )

        day.applied.append(AppliedEffect(
            nutrient_key=effect.nutrient_key, agent_label=effect.agent_label,
            direction=effect.direction,
            delta=0.0 if withheld else delta,
            modelled=delta,
            applied=withheld is None and delta != 0.0,
            mechanism=effect.mechanism,
            withheld=withheld,
        ))

    # Attach per goal, beside `dialysis_balance` and never over it.
    for applied in day.applied:
        goal = by_key.get(applied.nutrient_key)
        if goal is None:
            continue
        goal.setdefault("nutrient_effects", []).append({
            "agent": applied.agent_label,
            "direction": applied.direction,
            "delta": round(applied.delta, 2),
            "modelled": round(applied.modelled, 2),
            "applied": applied.applied,
            "mechanism": applied.mechanism,
            "withheld": applied.withheld,
        })

    return adjusted, day
