"""Clinician & Social Worker Dashboard endpoints — role-gated patient views."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.data_sharing import DataGrant
from app.models.vitals import VitalsLog
from app.models.mood import MoodEntry
from app.models.labs import LabResult
from app.models.medications import Medication
from app.models.user_roles import UserRoleAssignment
from app.models.conditions import HealthCondition
from app.schemas.wellness import ClinicianDashboardResponse, PatientSummary

router = APIRouter()


def _lab_dict(lab: LabResult) -> dict:
    """One lab result as the clients render it.

    `is_abnormal` is included because it is the whole point of scanning a list
    of results — without it the dashboard shows numbers a clinician has to
    range-check by eye, and the patient cards cannot flag anything.
    """
    return {
        "name": lab.test_name,
        "value": lab.value_string or (str(lab.value) if lab.value is not None else None),
        "unit": lab.unit,
        "date": str(lab.test_date),
        "is_abnormal": bool(lab.is_abnormal),
    }

CLINICIAN_ROLES = {
    "physician", "surgeon", "nurse_practitioner", "physician_assistant",
    "registered_nurse", "clinical_nurse_specialist", "other_clinician",
}
SW_ROLES = {"social_worker", "clinical_social_worker", "licensed_counselor"}


async def _get_user_role(user_id: int, db: AsyncSession) -> str | None:
    """Get user's primary active role."""
    result = await db.execute(
        select(UserRoleAssignment.role)
        .where(UserRoleAssignment.user_id == user_id, UserRoleAssignment.is_active == True, UserRoleAssignment.is_primary == True)
    )
    row = result.first()
    return row[0] if row else None


async def _get_patients_for_clinician(clinician_id: int, db: AsyncSession) -> list[PatientSummary]:
    """Get all patients who have granted data access to this clinician."""
    # Find users who have granted data access to this clinician
    result = await db.execute(
        select(DataGrant)
        .where(DataGrant.grantee_user_id == clinician_id, DataGrant.is_active == True)
    )
    grants = result.scalars().all()

    # Group grants by owner
    patient_grants: dict[int, list[str]] = {}
    for g in grants:
        patient_grants.setdefault(g.owner_id, []).append(g.data_type)

    patients = []
    for patient_id, permissions in patient_grants.items():
        # Get patient info
        result = await db.execute(select(User).where(User.id == patient_id))
        patient = result.scalar_one_or_none()
        if not patient:
            continue

        summary = PatientSummary(
            user_id=patient.id,
            full_name=patient.full_name,
            email=patient.email,
            permissions=permissions,
        )

        # Get latest vitals if permitted
        if "vitals" in permissions or "all" in permissions:
            result = await db.execute(
                select(VitalsLog).where(VitalsLog.user_id == patient_id).order_by(desc(VitalsLog.created_at)).limit(1)
            )
            vitals = result.scalar_one_or_none()
            if vitals:
                summary.latest_vitals = {
                    "date": str(vitals.log_date),
                    "bp": f"{vitals.blood_pressure_systolic}/{vitals.blood_pressure_diastolic}" if vitals.blood_pressure_systolic else None,
                    "hr": vitals.heart_rate_bpm,
                    "weight_kg": vitals.weight_kg,
                }

        # Get latest mood if permitted
        if "mood" in permissions or "all" in permissions:
            result = await db.execute(
                select(MoodEntry).where(MoodEntry.user_id == patient_id).order_by(desc(MoodEntry.created_at)).limit(1)
            )
            mood = result.scalar_one_or_none()
            if mood:
                summary.latest_mood = {
                    "date": str(mood.entry_date),
                    "score": mood.mood_score,
                }

        # Get latest labs if permitted
        if "labs" in permissions or "all" in permissions:
            result = await db.execute(
                select(LabResult).where(LabResult.user_id == patient_id).order_by(desc(LabResult.test_date)).limit(5)
            )
            labs = result.scalars().all()
            summary.latest_labs = [_lab_dict(l) for l in labs]

        # Get active medications if permitted
        if "medications" in permissions or "all" in permissions:
            result = await db.execute(
                select(Medication).where(Medication.user_id == patient_id, Medication.is_active == True)
            )
            meds = result.scalars().all()
            summary.medications = [m.name for m in meds]

        # Get the active problem list if permitted. `conditions` is a sharable
        # data type and was in the response schema, but nothing ever filled it —
        # so a patient who shared their conditions showed the clinician nothing.
        if "conditions" in permissions or "all" in permissions:
            result = await db.execute(
                select(HealthCondition).where(
                    HealthCondition.user_id == patient_id,
                    HealthCondition.status == "active",
                )
            )
            summary.conditions = [c.condition_name for c in result.scalars().all()]

        patients.append(summary)

    return patients


@router.get("/", response_model=ClinicianDashboardResponse)
async def get_clinician_dashboard(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get clinician or social worker dashboard with shared patient data."""
    role = await _get_user_role(current_user.id, db)

    # Allow access even without formal role assignment (for demo)
    display_role = role or "clinician"
    if role and role not in CLINICIAN_ROLES and role not in SW_ROLES:
        # Still allow if they have grants
        pass

    patients = await _get_patients_for_clinician(current_user.id, db)

    return ClinicianDashboardResponse(
        role=display_role,
        patient_count=len(patients),
        patients=patients,
    )


@router.get("/patient/{patient_id}", response_model=PatientSummary)
async def get_patient_detail(
    patient_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get detailed patient summary (requires active data grant)."""
    result = await db.execute(
        select(DataGrant)
        .where(
            DataGrant.grantee_user_id == current_user.id,
            DataGrant.owner_id == patient_id,
            DataGrant.is_active == True,
        )
    )
    grants = result.scalars().all()
    if not grants:
        raise HTTPException(status_code=403, detail="No active data grant from this patient")

    permissions = [g.data_type for g in grants]
    result = await db.execute(select(User).where(User.id == patient_id))
    patient = result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    summary = PatientSummary(
        user_id=patient.id, full_name=patient.full_name, email=patient.email,
        permissions=permissions,
    )
    # Populate all permitted data (same logic as above)
    if "vitals" in permissions or "all" in permissions:
        result = await db.execute(
            select(VitalsLog).where(VitalsLog.user_id == patient_id).order_by(desc(VitalsLog.created_at)).limit(1)
        )
        vitals = result.scalar_one_or_none()
        if vitals:
            summary.latest_vitals = {
                "date": str(vitals.log_date),
                "bp": f"{vitals.blood_pressure_systolic}/{vitals.blood_pressure_diastolic}" if vitals.blood_pressure_systolic else None,
                "hr": vitals.heart_rate_bpm, "weight_kg": vitals.weight_kg,
            }
    if "labs" in permissions or "all" in permissions:
        result = await db.execute(
            select(LabResult).where(LabResult.user_id == patient_id).order_by(desc(LabResult.test_date)).limit(10)
        )
        summary.latest_labs = [_lab_dict(l) for l in result.scalars().all()]
    if "medications" in permissions or "all" in permissions:
        result = await db.execute(
            select(Medication).where(Medication.user_id == patient_id, Medication.is_active == True)
        )
        summary.medications = [m.name for m in result.scalars().all()]
    if "conditions" in permissions or "all" in permissions:
        result = await db.execute(
            select(HealthCondition).where(
                HealthCondition.user_id == patient_id,
                HealthCondition.status == "active",
            )
        )
        summary.conditions = [c.condition_name for c in result.scalars().all()]
    if "mood" in permissions or "all" in permissions:
        result = await db.execute(
            select(MoodEntry).where(MoodEntry.user_id == patient_id).order_by(desc(MoodEntry.created_at)).limit(1)
        )
        mood = result.scalar_one_or_none()
        if mood:
            summary.latest_mood = {"date": str(mood.entry_date), "score": mood.mood_score}

    return summary
