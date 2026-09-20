"""What a patient was exposed to on one day, from every source that records it.

The collection layer for `nutrient_effects_day`, kept separate for the same
reason `dialysis_context` is separate from `dialysis_balance`: the model stays
pure and testable without fixtures, and every query touching a clinical table
lives in one reviewable place.

It is its own module rather than part of `nutrient_effects_service` because
that would be a circular import — `nutrient_effects_day` already imports the
service for `Effect` and `gate_needed`.

THREE SOURCES, AND THE THIRD IS THE ONE NOBODY READS
----------------------------------------------------
§3aa names two medication tables and warns about a third. All three matter here:

  1. treatments      `therapy_sessions`, completed only
  2. doses taken     `medication_dose_logs` — what the patient filled in
  3. drugs given     `therapy_sessions.drugs_administered` — free text written
                     by the unit, holding Epogene x1,962 and Venofer x1,248 on
                     the reference record and ZERO of them in a dose log

Dropping the third is how a review of that record concluded "no ESA prescribed
or taken" while the patient had been on one for years.

Medications come through `clinical_sources.administration_events_on_day`, which
covers sources 2 and 3 together. This module previously queried
`medication_dose_logs` directly and parsed the flowsheet itself — the guard in
tests/test_clinical_sources.py failed it, correctly. Worse than the rule break,
the hand-rolled version did not deduplicate a drug recorded in both sources on
one day, so a self-administered dose on home haemodialysis would have been
counted twice.

> ⚠️ That reader deliberately does NOT filter on `nutrients_resolved`, and that
> is the whole point. `_aggregate_daily_nutrients` does filter on it, and
> `api/medications.py` sets it as `bool(nutrients)` — so a drug that
> contributes no nutrient ADDITIVELY is marked false and excluded forever. A
> phosphate binder does not contribute phosphorus; it SUBTRACTS the phosphorus
> the patient ate. That filter hides precisely the agents this layer exists
> for: on the dev copy of production, Sevelamer is logged 168 times and every
> one of those rows is invisible to nutrient tracking today.
>
> It is also worth knowing that `firebase_sync` inserts dose logs with
> `nutrients_resolved` hardcoded to `false` and never resolves them, so on this
> database 452 doses across four users resolve nothing at all — medication
> nutrient contribution has only ever worked for one patient.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chronic_conditions import TherapySession
from app.services.clinical_sources import administration_events_on_day
from app.services.dialysis_context import COMPLETED_STATUSES
from app.services.nutrient_effects_day import AgentExposure
from app.services.nutrient_effects_service import normalize_agent

logger = logging.getLogger(__name__)

_COMPLETED_LOWER = {s.lower() for s in COMPLETED_STATUSES}


def _label_for_treatment(therapy_type: str) -> str:
    return (therapy_type or "treatment").replace("_", " ").strip().title()


async def exposures_for_day(
    db: AsyncSession, user_id: int, day: date
) -> list[AgentExposure]:
    """Every agent this patient met on `day`.

    One exposure per occurrence, never aggregated here: each session carries its
    own dialysate volume, and the effects layer scales and clamps per exposure.
    Collapsing them would apply one session's ratio to a day that had two.
    """
    out: list[AgentExposure] = []

    # `scheduled_date` is DateTime WITHOUT timezone. Comparing it to an aware
    # value makes asyncpg raise and the endpoint 500s, which the page then
    # renders as its empty state on a patient who dialysed (§3aa).
    start = datetime.combine(day, time.min)
    end = datetime.combine(day, time.max)

    sessions = (await db.execute(
        select(TherapySession).where(
            TherapySession.user_id == user_id,
            TherapySession.scheduled_date >= start,
            TherapySession.scheduled_date <= end,
        )
    )).scalars().all()

    for row in sessions:
        status = str(getattr(row.status, "value", row.status) or "")
        if status.lower() not in _COMPLETED_LOWER:
            # Booked, in progress or cancelled. A treatment that did not happen
            # must not credit the patient with anything.
            continue

        therapy_type = str(getattr(row.therapy_type, "value", row.therapy_type) or "")
        if therapy_type:
            # Keyed on the therapy TYPE, not on "dialysis" generally: PD fluid
            # is glucose-based and HD's is not, so one key for both would apply
            # the wrong agent's effects. `sessions_for_day` drops this field
            # entirely, which is why this module reads the rows itself.
            # A volume that was never recorded is OMITTED, not written as 0.0.
            # `scaled_magnitude` reads a missing key as "no basis to scale on"
            # and returns the unscaled prior, which is the honest answer.
            # Writing 0.0 happens to behave the same today only because 0.0 is
            # falsy — and the moment that check became `is not None`, every
            # unrecorded session would silently clamp to 0.5x and under-report
            # the loss. A missing measurement must never be encoded as a number
            # that looks measured (§3am).
            context: dict[str, float] = {}
            if row.dialysate_volume_liters is not None:
                context["dialysate_volume_l"] = float(row.dialysate_volume_liters)
            # Protein scales on THROUGHPUT, so the recorded blood volume has to
            # reach the store or `scaled_magnitude` finds no basis and returns
            # the flat 9 g prior — the constant this whole basis exists to
            # replace, reinstated on the one path that feeds the day's totals.
            # Only the MEASURED total goes in: `therapy_sessions.blood_flow_rate`
            # is the PRESCRIBED rate, a flat 350 on every row (§3ac), so
            # deriving Qb x duration here would manufacture a figure that looks
            # measured and is identical for every patient.
            if row.total_blood_volume_processed is not None:
                context["blood_volume_processed_l"] = float(
                    row.total_blood_volume_processed)

            out.append(AgentExposure(
                kind="treatment",
                key=normalize_agent(therapy_type, "treatment"),
                label=_label_for_treatment(therapy_type),
                occurrences=1,
                context=context,
            ))

    # Medications — BOTH sources, through the canonical reader (§3aa). This
    # module used to query `medication_dose_logs` directly and parse the
    # flowsheet itself, which the guard in tests/test_clinical_sources.py
    # correctly failed: reading one of a split domain's tables and calling it
    # the answer is how a decade of ESA and IV iron stayed invisible.
    #
    # `administration_events_on_day` rather than `administrations_on_day`: that
    # one merges a drug recorded twice in a day into one row for display, and
    # merging would understate three 500 mg tablets as 500 mg.
    for event in await administration_events_on_day(db, user_id, day):
        out.append(AgentExposure(
            kind="medication",
            # Keyed and labelled on the CANONICAL name, so Venofer, venofer and
            # Iron sucrose are one agent rather than three sets of facts.
            key=normalize_agent(event.name, "medication"),
            label=event.name,
            occurrences=1,
            # `event.dose` is verbatim text — "800.0 mg", or a flowsheet's
            # "20,000 SQ". It is NOT put in context as a number: the previous
            # version wrote `float(dose_amount or 0.0)`, which turned an
            # unrecorded dose into a measured zero. A per_dose_unit effect
            # needs that string parsed and refused when it cannot be, which is
            # deliberately not done here yet.
            context={},
        ))

    return out


def agent_pairs(exposures: list[AgentExposure]) -> list[tuple[str, str]]:
    """The distinct (kind, label) pairs, for asking the store what it knows.

    Labels rather than keys: `stored_effects` normalises on the way in, and
    handing it a pre-normalised key would fold a canonical drug name twice.
    """
    seen: dict[tuple[str, str], None] = {}
    for e in exposures:
        seen.setdefault((e.kind, e.label), None)
    return list(seen.keys())
