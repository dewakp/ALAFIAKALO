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
    ADDS, BINDS_DIETARY, BLOCKS_ABSORPTION, INCREASES_REQUIREMENT, PER_DOSE_UNIT,
    REMOVES, Effect, gate_needed,
)

logger = logging.getLogger(__name__)

#: Unit conversions we will perform. Anything outside this is REFUSED rather
#: than guessed: §3am's rule that an unreadable unit raises instead of assuming
#: metric, because guessing is how a number lands in the wrong column.
_TO_BASE = {
    ("g", "g"): 1.0, ("mg", "mg"): 1.0, ("mcg", "mcg"): 1.0, ("iu", "iu"): 1.0,
    ("g", "mg"): 1000.0, ("mg", "g"): 0.001,
    ("mg", "mcg"): 1000.0, ("mcg", "mg"): 0.001,
    ("g", "mcg"): 1_000_000.0, ("mcg", "g"): 0.000_001,
}

#: The SAME unit under two spellings, not a conversion. `NUTRIENT_CATALOG`
#: declares micrograms as "µg" while every key ends `_mcg`, and
#: `_GOAL_UNIT_BY_SUFFIX` therefore yields "mcg" — so an effect whose unit
#: arrived as "µg" (the resolver stored exactly that for Doxercalciferol) could
#: never convert, and was refused with a message telling the patient the units
#: do not match when in fact they are identical.
_UNIT_ALIASES = {"µg": "mcg", "ug": "mcg", "mcgs": "mcg", "mgs": "mg",
                 "gram": "g", "grams": "g", "iu.": "iu"}


def _canonical_unit(unit: str | None) -> str | None:
    if not unit:
        return None
    cleaned = unit.strip().lower()
    return _UNIT_ALIASES.get(cleaned, cleaned)

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
    #: The amount actually given, parsed, with the unit it was written in. None
    #: means the record says the drug was given and does NOT say how much — a
    #: real and common state on a flowsheet ("Venofer" with no parenthesis, 41
    #: sessions). It must read as "amount not recorded" and never as a default:
    #: a per-dose effect multiplied by an assumed 100 mg is a fabricated
    #: clinical figure, which is worse than an absent one (§3aj).
    dose_amount: float | None = None
    dose_unit: str | None = None
    #: Exactly as the record wrote it, so a refusal can quote the text it could
    #: not read rather than saying only that it failed.
    dose_text: str | None = None
    #: Set when the amount parsed cleanly but cannot be a single administration
    #: of this drug — the flowsheet writes doxercalciferol as "4mg" on 20
    #: sessions where every other row reads "2 mcg", and 4 mg converts to 4,000
    #: mcg without complaint. Carries the reason, so the day can say WHY a
    #: recorded dose was not counted instead of reporting it as missing.
    dose_refused: str | None = None


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
    """Convert, or return None when we cannot do it honestly.

    Spellings are folded FIRST: "µg" and "mcg" are one unit, and refusing to
    convert between them would report a unit mismatch that does not exist.
    """
    source = _canonical_unit(from_unit)
    target = _canonical_unit(to_unit)
    if source is None or target is None:
        return None
    factor = _TO_BASE.get((source, target))
    return None if factor is None else value * factor


def _dose_in(effect_dose_unit: str | None, exposure: AgentExposure) -> float | None:
    """How many of the effect's dose units this exposure actually delivered.

    None means "cannot be worked out", and it has three distinct causes that all
    demand the same answer: the record states no amount (a flowsheet reading
    just "Venofer"), the amount is written in a unit that does not convert to
    the effect's ("2.5 ml" against a figure stated per mg), or the effect never
    said what its magnitude is per.

    Every one of those must refuse. The alternative — assuming the usual dose,
    or treating an unreadable one as the effect's own unit — fabricates a
    clinical quantity out of a gap in the record, which is the §3aj failure the
    dose guard exists to prevent.
    """
    if exposure.dose_refused:
        # It parsed, and it cannot be right. Multiplying by it anyway is the
        # whole hazard: 4 mg of a drug sold in 2.5 mcg units becomes a
        # thousand-fold nutrient contribution that looks measured.
        return None
    if exposure.dose_amount is None or not exposure.dose_unit:
        return None
    if not effect_dose_unit:
        return None
    # Both sides fold through `_canonical_unit` inside `_convert`, so a dose
    # written "4mcg" still matches an effect stored per "µg".
    converted = _convert(exposure.dose_amount, exposure.dose_unit, effect_dose_unit)
    if converted is None:
        return None
    return converted * max(1, exposure.occurrences)


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
        counted = 0
        unreadable: list[str] = []
        refused: list[str] = []
        for exposure in matching:
            per_occurrence = effect.scaled_magnitude(exposure.context)
            if per_occurrence is None:
                size_unknown = True
                break
            if effect.basis == PER_DOSE_UNIT and effect.dose_unit:
                # `dose_unit` is what separates the two readings of "per dose".
                # WITH one, the magnitude is per unit of drug — 1 mg of iron per
                # mg of iron sucrose — so it means nothing until multiplied by
                # how much was actually given, and Venofer is written with no
                # amount on 41 sessions. Crediting those with a borrowed 100 mg
                # would invent iron the record never claimed.
                delivered = _dose_in(effect.dose_unit, exposure)
                if delivered is None:
                    if exposure.dose_refused:
                        refused.append(exposure.dose_refused)
                    else:
                        unreadable.append(exposure.dose_text or "no amount recorded")
                    continue
                magnitude += per_occurrence * delivered
            else:
                # WITHOUT one, the magnitude is per ADMINISTRATION — "200 mg of
                # phosphorus bound per dose taken" — which needs no amount at
                # all. Demanding one here broke three passing tests, and they
                # were right: a binder's effect is per tablet swallowed.
                magnitude += per_occurrence * max(1, exposure.occurrences)
            counted += 1

        if (effect.basis == PER_DOSE_UNIT and effect.dose_unit
                and counted == 0 and not size_unknown):
            # Given, and we cannot say how much. That is a finding in itself and
            # the one thing this must never render as zero (§3aa).
            quoted = next((u for u in unreadable if u != "no amount recorded"), None)
            if refused:
                # A dose that parsed and failed the check is a DIFFERENT finding
                # from one nobody wrote down, and saying "no amount recorded"
                # here would hide a probable units error in the chart.
                withheld = f"{effect.agent_label}: {refused[0]}"
            elif quoted:
                withheld = (
                    f"{effect.agent_label} was given, but the amount recorded "
                    f"({quoted}) cannot be read as a dose, so its contribution "
                    "cannot be worked out."
                )
            else:
                withheld = (
                    f"{effect.agent_label} was given, but no amount is recorded, "
                    "so its contribution cannot be worked out."
                )
            day.applied.append(AppliedEffect(
                nutrient_key=effect.nutrient_key, agent_label=effect.agent_label,
                direction=effect.direction, delta=0.0, modelled=0.0, applied=False,
                mechanism=effect.mechanism, withheld=withheld,
            ))
            continue

        # A refusal alongside readable doses must still be said out loud. The
        # first version of this only reported `unreadable`, so a dose rejected
        # by the guard would vanish while the others counted — the silent drop
        # this whole layer exists to prevent (§3aa).
        if refused and counted:
            day.notes.append(
                f"{effect.agent_label}: {len(refused)} administration(s) today "
                f"record an amount that failed the dose check and were not "
                f"counted. {refused[0]}"
            )
        if unreadable and counted:
            day.notes.append(
                f"{effect.agent_label}: {len(unreadable)} of "
                f"{len(unreadable) + counted} administrations today have no "
                "readable amount, so only the recorded ones are counted."
            )

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
                "Not counted: this would change what you appear to need, and "
                "there is no recent measurement to confirm it."
            )
        elif not effect.calibrated and effect.provenance == "llm":
            # A model-supplied MAGNITUDE is reported, never counted.
            #
            # Measured on the real store: the resolver returned 1 mg of sodium
            # per mg of docusate. Sodium docusate is about 5% sodium by mass, so
            # that figure is roughly twentyfold high — and it arrived as
            # evidence "high" with confidence 0.6, so no confidence threshold
            # would have caught it. On a sodium limit a wrong number is worse
            # than no number.
            #
            # The effect itself still shows, with its mechanism: "this drug adds
            # sodium, amount not established" is true and useful. What is
            # refused is letting an unverified figure move a clinical total.
            # A literature prior or a fitted coefficient counts normally.
            withheld = (
                f"{effect.agent_label} affects this, but the amount comes from "
                "an automated source and has not been confirmed, so it is shown "
                "rather than counted."
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
