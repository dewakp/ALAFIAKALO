"""Apply a dialysis session's solute transfer to the day's nutrient totals.

**Limits do not move because a treatment happened.** A dietary limit is a
guideline about what to eat, and KDOQI's 2,000–3,000 mg/day of potassium is
already the figure for a patient on dialysis — the clearance is baked into it.
Raising it on treatment days would count the same clearance twice.

What a session changes is the day's *balance*. Potassium eaten that morning may
leave the body the same afternoon. Calcium the patient never ate crosses in from
the dialysate and is retained. So the totals are adjusted, and the limits are
left alone:

    intake_mg      what the food log says was eaten
    dialysis_mg    signed: negative = removed by treatment, positive = gained
    net_mg         intake + dialysis — the body's actual balance for the day

The intake-versus-limit comparison is preserved untouched, because that is the
guideline check. `net_mg` is reported alongside it as the physiological reality,
never in place of it — a potassium total driven to zero by dialysis must not
read as licence to eat more.

Gains are the case that most needs this. Against a 3.0 mEq/L bath a patient
takes on a few hundred milligrams of calcium per session without eating any of
it; if that never reaches the day's total, their calcium load is understated
every single treatment day.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from app.services.dialysis_balance import (
    CALCIUM, MAGNESIUM, PHOSPHORUS, POTASSIUM, PROTEIN,
    Coefficients, DEFAULT_COEFFICIENTS, SerumLevels, SessionParams,
    SessionNotModellable, estimate_session_removal,
)

#: Nutrient-goal keys, as `nutrient_goals_service` emits them.
GOAL_KEY = {
    POTASSIUM: "potassium_mg",
    PHOSPHORUS: "phosphorus_mg",
    MAGNESIUM: "magnesium_mg",
    CALCIUM: "calcium_mg",
    PROTEIN: "protein_g",
}

#: Above these the patient is already in trouble for that analyte. Removal
#: credit is withheld — a total shown as near-zero on the day of a high
#: potassium would be actively misleading. Gains are still applied.
SERUM_BLOCK_ABOVE = {
    POTASSIUM: 5.5,      # mmol/L
    PHOSPHORUS: 5.5,     # mg/dL
    MAGNESIUM: 2.6,      # mg/dL
    CALCIUM: 10.5,       # mg/dL
}

#: Serum older than this stops counting as confirmation; between the two the
#: removal credit tapers to zero. Gains are never tapered.
FRESH_DAYS = 45
STALE_DAYS = 120

#: An uncalibrated analyte's removal is discounted — the transfer is real, but
#: its size is a literature figure rather than this patient's measured one.
UNCALIBRATED_FRACTION = 0.4


@dataclass
class NutrientBalance:
    """One nutrient's day, split into what was eaten and what treatment did."""

    key: str
    analyte: str
    intake: float               # in the goal's own unit (mg, or g for protein)
    dialysis_delta: float       # signed, same unit
    net: float                  # intake + dialysis_delta
    modelled_mg: float          # raw model output before gating
    direction: str              # "removed" | "gained" | "none"
    calibrated: bool
    reasons: list[str] = field(default_factory=list)
    withheld: str | None = None

    @property
    def changed(self) -> bool:
        return abs(self.dialysis_delta) > 0.005


@dataclass
class DialysisDay:
    """The day's treatment, for display beside the numbers."""

    session_count: int = 0
    modelled: dict[str, float] = field(default_factory=dict)
    balances: list[NutrientBalance] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def had_dialysis(self) -> bool:
        return self.session_count > 0


def _staleness_factor(measured_on: date | None, today: date) -> float:
    if measured_on is None:
        return 0.0
    age = (today - measured_on).days
    if age < 0:
        return 0.0
    if age <= FRESH_DAYS:
        return 1.0
    if age >= STALE_DAYS:
        return 0.0
    return 1.0 - (age - FRESH_DAYS) / (STALE_DAYS - FRESH_DAYS)


def _serum_for(analyte: str, serum: SerumLevels) -> float | None:
    return {
        POTASSIUM: serum.potassium_mmol_l,
        PHOSPHORUS: serum.phosphorus_mg_dl,
        MAGNESIUM: serum.magnesium_mg_dl,
        CALCIUM: serum.calcium_mg_dl,
    }.get(analyte)


def _gate_removal(
    analyte: str,
    removal_mg: float,
    serum: SerumLevels,
    today: date,
    calibrated: bool,
) -> tuple[float, list[str], str | None]:
    """How much of a modelled removal may be credited against the day's total.

    Only removals are gated. Crediting a removal lowers a total and therefore
    looks like room to eat more, so it has to be justified; a gain raises the
    total and needs no permission.
    """
    reasons: list[str] = []

    if not calibrated:
        removal_mg *= UNCALIBRATED_FRACTION
        reasons.append(
            "Only part of the modelled removal is counted: this nutrient's "
            "transfer has not been confirmed against your own blood tests."
        )

    level = _serum_for(analyte, serum)
    threshold = SERUM_BLOCK_ABOVE.get(analyte)
    if level is not None and threshold is not None and level >= threshold:
        return 0.0, reasons, (
            f"Your most recent {analyte} was {level:g}, at or above {threshold:g}. "
            "Treatment removal is not deducted while it is high."
        )

    factor = _staleness_factor(serum.measured_on, today)
    if factor <= 0:
        return 0.0, reasons, (
            "No recent blood test to confirm this, so treatment removal is not deducted."
        )
    if factor < 1.0:
        reasons.append("Reduced because your most recent blood test is getting old.")

    return removal_mg * factor, reasons, None


def apply_to_totals(
    goals: list[dict],
    sessions: list[SessionParams],
    serum: SerumLevels,
    coefficients: dict[str, Coefficients] | None = None,
    today: date | None = None,
) -> tuple[list[dict], DialysisDay]:
    """Fold treatment into the day's totals, leaving every limit untouched.

    `goals` is what `nutrient_goals_service.compute_goals` produced, already
    carrying each nutrient's `current` intake. Goals are copied, not mutated.
    """
    today = today or date.today()
    day = DialysisDay()
    adjusted = [dict(goal) for goal in goals]
    by_key = {goal["key"]: goal for goal in adjusted}

    completed = [s for s in sessions if s.completed]
    skipped = len(sessions) - len(completed)
    if skipped:
        day.notes.append(
            f"{skipped} session(s) today are not recorded as completed and were not counted."
        )
    day.session_count = len(completed)
    if not completed:
        return adjusted, day

    coeffs = {**DEFAULT_COEFFICIENTS, **(coefficients or {})}

    totals: dict[str, float] = {}
    for session in completed:
        try:
            removals = estimate_session_removal(session, serum, coeffs)
        except SessionNotModellable as exc:
            day.notes.append(f"A session could not be modelled: {exc}")
            continue
        for analyte, estimate in removals.items():
            totals[analyte] = totals.get(analyte, 0.0) + estimate.mass_mg

    day.modelled = dict(totals)

    for analyte, mass_mg in totals.items():
        key = GOAL_KEY.get(analyte)
        goal = by_key.get(key)
        if goal is None:
            continue

        intake = float(goal.get("current") or 0.0)
        scale = 0.001 if key == "protein_g" else 1.0   # protein is in grams
        calibrated = coeffs[analyte].calibrated

        if mass_mg < 0:
            # Gained from the dialysate: the patient retained this without
            # eating it, so it belongs in the day's total. Never gated.
            delta = -mass_mg * scale
            balance = NutrientBalance(
                key=key, analyte=analyte, intake=intake, dialysis_delta=delta,
                net=intake + delta, modelled_mg=mass_mg, direction="gained",
                calibrated=calibrated,
                reasons=[
                    "Today's dialysate is richer in this than your blood, so treatment "
                    "added to your daily total without you eating it."
                ],
            )
        elif analyte == PROTEIN:
            # Amino acids leave in the effluent: the patient keeps less of what
            # they ate, so the day's effective protein intake is lower.
            credited, reasons, withheld = mass_mg * scale, [], None
            balance = NutrientBalance(
                key=key, analyte=analyte, intake=intake, dialysis_delta=-credited,
                net=intake - credited, modelled_mg=mass_mg, direction="removed",
                calibrated=calibrated,
                reasons=["Dialysis removes amino acids, so less of today's protein is retained."],
            )
        else:
            credited, reasons, withheld = _gate_removal(
                analyte, mass_mg, serum, today, calibrated
            )
            delta = -credited * scale
            balance = NutrientBalance(
                key=key, analyte=analyte, intake=intake, dialysis_delta=delta,
                net=intake + delta, modelled_mg=mass_mg,
                direction="removed" if credited > 0 else "none",
                calibrated=calibrated, reasons=reasons, withheld=withheld,
            )

        # The limit is untouched. `current` stays the dietary intake, so the
        # guideline comparison is unchanged; the balance is reported alongside.
        goal["dialysis_balance"] = {
            "intake": round(balance.intake, 2),
            "delta": round(balance.dialysis_delta, 2),
            "net": round(balance.net, 2),
            "modelled_mg": round(balance.modelled_mg, 1),
            "direction": balance.direction,
            "calibrated": calibrated,
            "reasons": balance.reasons,
            "withheld": balance.withheld,
        }
        day.balances.append(balance)

    return adjusted, day
