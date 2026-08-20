"""Gather what the transfer model needs for one patient on one day.

`dialysis_balance` and `dialysis_day_adjustment` are deliberately pure. This is
the layer that goes to the database for them: the day's completed sessions, the
most recent serum values, and any coefficients fitted to this patient.

Kept separate so the model stays testable without fixtures, and so every query
that touches a clinical table lives in one reviewable place.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chronic_conditions import IntradialyticReading, TherapySession
from app.models.dialysis_coefficients import DialysisSoluteCoefficient
from app.models.labs import LabResult
from app.services.dialysis_balance import (
    CALCIUM, MAGNESIUM, PHOSPHORUS, POTASSIUM,
    Coefficients, DEFAULT_COEFFICIENTS, SerumLevels, SessionParams,
)

logger = logging.getLogger(__name__)

#: Statuses that mean the treatment actually happened. Anything else — booked,
#: in progress, cancelled — must not credit the patient with clearance.
COMPLETED_STATUSES = {"completed", "COMPLETED", "finished", "complete"}

#: Blood-flow readings outside this band are recording errors. The raw column
#: spans 0–4660 mL/min; 4660 is not physically possible through a dialyser.
BLOOD_FLOW_PLAUSIBLE = (50.0, 600.0)

#: How far back to look for a serum value.
#:
#: Dialysis bloods are drawn monthly, so 30 days means "the most recent routine
#: draw" and nothing staler. A serum potassium is a snapshot of a fast-moving
#: quantity — it can move a full mmol/L between treatments — so an older value
#: is not evidence about today, and this gate governs whether the model may
#: deduct treatment removal from a nutrient total.
SERUM_LOOKBACK_DAYS = 30

#: Lab names, as they arrive from the document importer and the EHR feed.
_SERUM_TESTS = {
    POTASSIUM: ("Potassium", "K+"),
    PHOSPHORUS: ("Phosphorus", "Phosphorous"),
    MAGNESIUM: ("Magnesium", "Magnessium"),
    CALCIUM: ("Calcium",),
}


async def sessions_for_day(db: AsyncSession, user_id: int, day: date) -> list[SessionParams]:
    """Completed treatments on `day`, with delivered blood flow where recorded.

    `therapy_sessions.blood_flow_rate` holds the *prescribed* rate, which is a
    flat 350 on every row in this dataset and therefore carries no information.
    The delivered rate is the mean of the session's own intradialytic readings,
    which genuinely varies (roughly 150–480 mL/min), so that is preferred and
    the prescription is only a fallback.
    """
    # `scheduled_date` is DateTime WITHOUT timezone — comparing it to an aware
    # value makes asyncpg raise, the endpoint 500s, and the page renders its
    # empty state on a patient who dialysed. Bound it with naive datetimes.
    start = datetime.combine(day, time.min)
    end = datetime.combine(day, time.max)

    rows = (await db.execute(
        select(TherapySession).where(
            TherapySession.user_id == user_id,
            TherapySession.scheduled_date >= start,
            TherapySession.scheduled_date <= end,
        )
    )).scalars().all()
    if not rows:
        return []

    measured = dict((await db.execute(
        select(
            IntradialyticReading.session_id,
            func.avg(IntradialyticReading.blood_flow_rate),
        )
        .where(
            IntradialyticReading.session_id.in_([r.id for r in rows]),
            IntradialyticReading.blood_flow_rate.between(*BLOOD_FLOW_PLAUSIBLE),
        )
        .group_by(IntradialyticReading.session_id)
    )).all())

    sessions: list[SessionParams] = []
    for row in rows:
        status = str(getattr(row.status, "value", row.status) or "")
        sessions.append(SessionParams(
            dialysate_volume_l=row.dialysate_volume_liters,
            duration_minutes=row.duration_minutes,
            blood_flow_ml_min=measured.get(row.id) or row.blood_flow_rate,
            ultrafiltration_ml=row.fluid_removed_ml,
            bath_potassium_meq=row.dialysate_potassium_meq,
            completed=status.lower() in {s.lower() for s in COMPLETED_STATUSES},
        ))
    return sessions


async def latest_serum(db: AsyncSession, user_id: int, on_or_before: date) -> SerumLevels:
    """Most recent value for each modelled analyte, with the date of the newest.

    `lab_results` is not one of the split-table models in canon §3aa, so reading
    it directly here is correct.
    """
    cutoff = date.fromordinal(max(on_or_before.toordinal() - SERUM_LOOKBACK_DAYS, 1))
    names = [name for aliases in _SERUM_TESTS.values() for name in aliases]

    rows = (await db.execute(
        select(LabResult.test_name, LabResult.value, LabResult.test_date)
        .where(
            LabResult.user_id == user_id,
            LabResult.test_name.in_(names),
            LabResult.value.isnot(None),
            LabResult.test_date <= on_or_before,
            LabResult.test_date >= cutoff,
        )
        .order_by(LabResult.test_date.desc())
    )).all()

    newest: dict[str, tuple[float, date]] = {}
    for test_name, value, test_date in rows:
        for analyte, aliases in _SERUM_TESTS.items():
            if test_name in aliases and analyte not in newest:
                newest[analyte] = (float(value), test_date)

    serum = SerumLevels(
        potassium_mmol_l=newest.get(POTASSIUM, (None, None))[0],
        phosphorus_mg_dl=newest.get(PHOSPHORUS, (None, None))[0],
        magnesium_mg_dl=newest.get(MAGNESIUM, (None, None))[0],
        calcium_mg_dl=newest.get(CALCIUM, (None, None))[0],
    )
    dates = [d for _, d in newest.values() if d]
    # The staleness gate should judge on the freshest confirmation available.
    serum.measured_on = max(dates) if dates else None
    return serum


async def coefficients_for(db: AsyncSession, user_id: int) -> dict[str, Coefficients]:
    """This patient's fitted coefficients, falling back to the priors.

    Only a coefficient that beat a naive baseline on held-out bloods is marked
    calibrated. An unvalidated fit is worse than no fit, because it would let
    the model lower a nutrient total on evidence that never predicted anything.
    """
    rows = (await db.execute(
        select(DialysisSoluteCoefficient).where(
            DialysisSoluteCoefficient.user_id == user_id
        )
    )).scalars().all()

    resolved = dict(DEFAULT_COEFFICIENTS)
    for row in rows:
        base = DEFAULT_COEFFICIENTS.get(row.analyte)
        if base is None:
            continue
        if not row.trustworthy:
            logger.debug(
                "Coefficient for %s not adopted (beats_baseline=%s n_holdout=%s)",
                row.analyte, row.beats_baseline, row.n_holdout,
            )
            continue
        from dataclasses import replace

        resolved[row.analyte] = replace(
            base, calibrated=True, holdout_mae=row.holdout_mae
        )
    return resolved
