"""Medications CRUD endpoints + medication dose log (nutrient-contributing doses)."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
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
)
from app.services.med_nutrient_service import lookup_med_nutrients, seed_med_profiles

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
    raise HTTPException(
        status_code=403,
        detail="Medication entries cannot be deleted. You can modify this entry instead.",
    )


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
