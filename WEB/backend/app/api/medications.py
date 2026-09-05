"""Medications CRUD endpoints + medication dose log (nutrient-contributing doses)."""

import json
import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.notification_engine import notify_medication_conflict
from app.models.user import User
from app.models.medications import Medication
from app.models.med_nutrient import MedNutrientProfile, MedicationDoseLog
from app.schemas.medications import (
    MedicationCreate,
    MedicationUpdate,
    MedicationResponse,
    MedicationDoseLogCreate,
    MedicationDoseLogResponse,
    MedNutrientLookupResponse,
    IntakeIntentRequest,
)
from app.services.med_dose_validation import validate_dose, blocking
from app.services.med_intake_intent import propose_intake
from app.services.med_nutrient_service import lookup_med_nutrients

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/", response_model=list[MedicationResponse])
async def list_medications(
    active_only: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(Medication).where(Medication.user_id == current_user.id)
    if active_only:
        query = query.where(Medication.is_active == True)
    query = query.order_by(Medication.created_at.desc())
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/", response_model=MedicationResponse, status_code=201)
async def create_medication(
    med_in: MedicationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    med = Medication(**med_in.model_dump(), user_id=current_user.id)
    db.add(med)
    await db.flush()
    await db.refresh(med)

    # Notification: check for duplicate / conflict with existing active meds
    existing = await db.execute(
        select(Medication).where(
            Medication.user_id == current_user.id,
            Medication.is_active == True,  # noqa: E712
            Medication.id != med.id,
        )
    )
    for other in existing.scalars().all():
        if other.name and med.name and other.name.lower() == med.name.lower():
            await notify_medication_conflict(
                db, user_id=current_user.id,
                drug_a=med.name, drug_b=other.name,
                conflict_detail="Duplicate medication detected. You may already be taking this drug.",
            )
            break

    return med


@router.get("/{med_id:int}", response_model=MedicationResponse)
async def get_medication(
    med_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Medication).where(Medication.id == med_id, Medication.user_id == current_user.id)
    )
    med = result.scalar_one_or_none()
    if not med:
        raise HTTPException(status_code=404, detail="Medication not found")
    return med


@router.patch("/{med_id:int}", response_model=MedicationResponse)
async def update_medication(
    med_id: int,
    updates: MedicationUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Medication).where(Medication.id == med_id, Medication.user_id == current_user.id)
    )
    med = result.scalar_one_or_none()
    if not med:
        raise HTTPException(status_code=404, detail="Medication not found")
    for field, value in updates.model_dump(exclude_unset=True).items():
        setattr(med, field, value)
    await db.flush()
    await db.refresh(med)
    return med


@router.delete("/{med_id:int}", status_code=204)
async def delete_medication(
    med_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Medication).where(Medication.id == med_id, Medication.user_id == current_user.id)
    )
    med = result.scalar_one_or_none()
    if not med:
        raise HTTPException(status_code=404, detail="Medication not found")

    # This used to refuse EVERY delete with a flat 403, so the button in the UI
    # could never succeed — and the client swallowed the rejection, so the row
    # simply sat there and the app looked broken.
    #
    # What the rule is actually for is the clinical record: a prescription with
    # doses recorded against it is part of the patient's history and must not
    # vanish. A prescription with NO dose logs is a catalog entry — the EHR
    # import creates these, and this account's only two are 2017 sandbox rows
    # with zero doses. Deleting one of those destroys nothing.
    dose_count = await db.scalar(
        select(func.count(MedicationDoseLog.id)).where(
            MedicationDoseLog.medication_id == med_id
        )
    ) or 0
    if dose_count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(f"{med.name} has {dose_count} recorded dose"
                    f"{'' if dose_count == 1 else 's'} logged against it, so it is part "
                    f"of your history and cannot be deleted. Mark it inactive instead."),
        )

    await db.delete(med)
    await db.flush()


# ── Med → Nutrient profile endpoints ─────────────────────────────────────────


@router.get("/nutrient-profiles", response_model=list[MedNutrientLookupResponse])
async def list_med_nutrient_profiles(
    q: str | None = Query(None, description="Optional search filter"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all known medication → nutrient profiles (global reference DB)."""
    query = select(MedNutrientProfile).where(MedNutrientProfile.is_active.is_(True))
    result = await db.execute(query)
    profiles = result.scalars().all()
    if q:
        ql = q.lower()
        profiles = [
            p for p in profiles
            if ql in (p.med_name_original or "").lower()
            or ql in (p.brand_names or "").lower()
            or ql in (p.active_ingredient or "").lower()
        ]
    return [
        MedNutrientLookupResponse(
            profile_id=p.id,
            med_name_resolved=p.med_name_original,
            dose_unit_canonical=p.dose_unit_canonical,
            nutrients_per_dose_unit=p.nutrients_per_dose_unit,
            brand_names=p.brand_names,
            active_ingredient=p.active_ingredient,
            source=p.source,
        )
        for p in profiles
    ]


@router.get("/nutrient-lookup", response_model=dict)
async def lookup_med_nutrient(
    medication_name: str = Query(...),
    dose_amount: float = Query(...),
    dose_unit: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Look up the nutrients contributed by a single medication dose.

    Example: /nutrient-lookup?medication_name=Calcitriol&dose_amount=0.5&dose_unit=mcg
    → {"vitamin_d_iu": 20.0}
    """
    return await lookup_med_nutrients(db, medication_name, dose_amount, dose_unit)


# ── Medication Dose Log endpoints ─────────────────────────────────────────────


@router.post("/intake-intent")
async def propose_medication_intake(
    body: IntakeIntentRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Read "I take Calcitriol" into a dose the user confirms. Writes NOTHING.

    Supplies a missing dose from this user's own logging history, with the
    provenance shown alongside it, and refuses to pre-fill anything the dose
    guard can prove is wrong. Confirmation is required by design: on this
    database, 6 of 9 user/medication pairs with repeat logs use more than one
    dose over time, so "the dose from history" is often not a single answer.
    """
    proposal = await propose_intake(db, current_user.id, body.text)
    return proposal.as_dict()


@router.post("/promote-logged")
async def promote_logged_medications(
    min_logs: int = 3,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Turn a regularly-logged medication into a prescription row.

    A patient who logs Calcium carbonate 489 times is taking Calcium carbonate;
    requiring them to also type it into Prescriptions is asking them to tell us
    something we already know. This reads their own dose logs and creates the
    missing `medications` rows.

    Deliberately explicit rather than automatic on every write: a prescription is
    a clinical statement, and one mistyped dose log should not silently become
    one. `min_logs` is the evidence threshold, and a one-off typo like the
    "Calcium Calcitriol" row on this database (logged ONCE against Calcium
    carbonate's 489) stays below it.

    Idempotent: an existing row for the same name — matched case-insensitively,
    because the same drug arrives as both "Calcium Carbonate" and "Calcium
    carbonate" — is left alone rather than duplicated.
    """
    name_key = func.lower(MedicationDoseLog.medication_name)
    candidates = (await db.execute(
        select(
            func.max(MedicationDoseLog.medication_name).label("display"),
            func.count(MedicationDoseLog.id).label("times"),
            func.max(MedicationDoseLog.log_date).label("last"),
        )
        .where(MedicationDoseLog.user_id == current_user.id)
        .group_by(name_key)
        .having(func.count(MedicationDoseLog.id) >= max(1, min_logs))
    )).all()

    existing = {
        (n or "").strip().lower()
        for (n,) in (await db.execute(
            select(Medication.name).where(Medication.user_id == current_user.id)
        )).all()
    }

    created = []
    for row in candidates:
        if (row.display or "").strip().lower() in existing:
            continue
        med = Medication(
            user_id=current_user.id,
            name=row.display,
            is_active=True,
            notes=(f"Added from your own logs — recorded {row.times} times, "
                   f"last {row.last.isoformat() if row.last else 'unknown'}."),
        )
        db.add(med)
        created.append({"name": row.display, "times_logged": int(row.times)})

    if created:
        await db.commit()
    return {"created": created, "min_logs": max(1, min_logs)}


@router.get("/frequent")
async def frequently_logged_medications(
    limit: int = 25,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """What this patient ACTUALLY takes, from their own dose logs.

    The intake picker was populated only from `/medications/` — the prescription
    table. On this database that is the wrong source for the question being
    asked: an account with **943 dose logs and 0 prescriptions** got an empty
    picker and no suggestion for "Calcium", a drug it had recorded hundreds of
    times. Canon 3aa, in the intake form: prescribed and taken are different
    facts, and reading one table and calling it the answer hides the other.

    Grouped case-insensitively, because the same drug arrives as both "Calcium
    Carbonate" and "Calcium carbonate" and two rows would misstate the regimen.
    The spelling returned is the one most recently used, so the suggestion looks
    like what the patient last typed.
    """
    name_key = func.lower(MedicationDoseLog.medication_name)
    rows = (await db.execute(
        select(
            name_key.label("key"),
            func.max(MedicationDoseLog.medication_name).label("display"),
            func.count(MedicationDoseLog.id).label("times"),
            func.max(MedicationDoseLog.log_date).label("last"),
        )
        .where(MedicationDoseLog.user_id == current_user.id)
        .group_by(name_key)
        # Recency first: what you took yesterday is a better suggestion than
        # something logged 200 times two years ago and stopped since.
        .order_by(func.max(MedicationDoseLog.log_date).desc(),
                  func.count(MedicationDoseLog.id).desc())
        .limit(max(1, min(limit, 100)))
    )).all()

    return [
        {
            "name": r.display,
            "times_logged": int(r.times),
            "last_taken": r.last.isoformat() if r.last else None,
        }
        for r in rows
    ]


@router.post("/dose-logs", response_model=MedicationDoseLogResponse, status_code=201)
async def log_medication_dose(
    dose_in: MedicationDoseLogCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Record a medication dose event and auto-resolve its nutrient contribution.

    The nutrient_contributed field is computed automatically and stored for
    inclusion in the daily nutrition summary.
    """
    # Refuse a dose that reference data says cannot be right. This is the guard
    # that "calcium calcitriol 1000 mg" walked past: calcitriol is dosed in
    # MICROGRAMS, so read literally that row is ~1000x a real dose sitting in a
    # clinical record — and it is exactly what a "usual dose from history"
    # feature would replay. max_dose_for()/unit_convert_factor() already existed
    # and nothing called them.
    # The guard runs EITHER WAY. When the dose is acknowledged we still need to
    # know what was overridden — a flag with no reason tells a clinician that
    # something was wrong but not what, which is barely better than silence.
    findings = blocking(await validate_dose(
        db, dose_in.medication_name, dose_in.dose_amount, dose_in.dose_unit,
    ))
    if findings and not dose_in.acknowledge_unusual:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "This dose looks wrong — please check it.",
                "findings": [f.as_dict() for f in findings],
                "override_with": "acknowledge_unusual",
            },
        )

    # Only a dose that was actually refused counts as an override. Setting the
    # flag on every acknowledged request would mark ordinary doses as overridden
    # whenever a client sent the flag defensively.
    was_overridden = bool(findings and dose_in.acknowledge_unusual)
    override_reason = (
        json.dumps([f.as_dict() for f in findings]) if was_overridden else None
    )
    if was_overridden:
        logger.warning(
            "dose recorded over a blocking finding",
            extra={
                "user_id": current_user.id,
                "medication_name": dose_in.medication_name,
                "dose": f"{dose_in.dose_amount} {dose_in.dose_unit}",
                "codes": [f.code for f in findings],
            },
        )

    # Resolve nutrients
    resolved = await lookup_med_nutrients(
        db,
        dose_in.medication_name,
        dose_in.dose_amount,
        dose_in.dose_unit,
    )
    nutrients = resolved.get("nutrients", {})
    profile_id = resolved.get("profile_id")

    dose_log = MedicationDoseLog(
        user_id=current_user.id,
        medication_id=dose_in.medication_id,
        med_profile_id=profile_id,
        medication_name=dose_in.medication_name,
        log_date=dose_in.log_date,
        log_time=dose_in.log_time,
        dose_amount=dose_in.dose_amount,
        dose_unit=dose_in.dose_unit,
        pre_systolic_bp=dose_in.pre_systolic_bp,
        pre_diastolic_bp=dose_in.pre_diastolic_bp,
        pre_heart_rate=dose_in.pre_heart_rate,
        post_systolic_bp=dose_in.post_systolic_bp,
        post_diastolic_bp=dose_in.post_diastolic_bp,
        post_heart_rate=dose_in.post_heart_rate,
        pre_temperature_c=dose_in.pre_temperature_c,
        post_temperature_c=dose_in.post_temperature_c,
        override_acknowledged=was_overridden,
        override_reason=override_reason,
        nutrients_contributed=nutrients if nutrients else None,
        nutrients_resolved=bool(nutrients),
        notes=dose_in.notes,
    )
    db.add(dose_log)
    try:
        await db.flush()
    except IntegrityError:
        # Same medication, amount, date AND time already logged — a true duplicate.
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This exact dose is already logged for that date and time.",
        )
    await db.refresh(dose_log)
    return dose_log


@router.get("/dose-logs", response_model=list[MedicationDoseLogResponse])
async def list_medication_dose_logs(
    log_date: date | None = Query(None),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List medication dose log entries, optionally filtered by date range."""
    query = select(MedicationDoseLog).where(
        MedicationDoseLog.user_id == current_user.id
    )
    if log_date:
        query = query.where(MedicationDoseLog.log_date == log_date)
    if start_date:
        query = query.where(MedicationDoseLog.log_date >= start_date)
    if end_date:
        query = query.where(MedicationDoseLog.log_date <= end_date)
    query = query.order_by(MedicationDoseLog.log_date.desc(), MedicationDoseLog.created_at.desc())
    result = await db.execute(query)
    return result.scalars().all()


@router.delete("/dose-logs/{log_id}", status_code=204)
async def delete_medication_dose_log(
    log_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a medication dose log entry (e.g. logged by mistake)."""
    result = await db.execute(
        select(MedicationDoseLog).where(
            MedicationDoseLog.id == log_id,
            MedicationDoseLog.user_id == current_user.id,
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Dose log not found")
    await db.delete(entry)
    await db.flush()
