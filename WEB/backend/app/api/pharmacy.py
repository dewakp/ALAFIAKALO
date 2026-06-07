"""Pharmacy API – Prescribe → Dispense → Adhere lifecycle.

Physicians create prescriptions, pharmacists dispense, patients track adherence.
Role-aware endpoints with cross-actor notification and impact analysis.
"""

from datetime import datetime, timezone, date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.notification_engine import (
    notify_prescription_created,
    notify_prescription_ready,
    notify_dispense_complete,
    notify_adherence_missed,
    notify_refill_reminder,
)
from app.models.user import User
from app.models.pharmacy import (
    Prescription,
    Dispense,
    AdherenceLog,
    MedicationSchedule,
    RefillRequest,
    PrescriptionStatus,
    DispenseStatus,
    AdherenceStatus,
    RefillStatus,
)
from app.schemas.pharmacy import (
    PrescriptionCreate,
    PrescriptionUpdate,
    PrescriptionResponse,
    DispenseCreate,
    DispenseUpdate,
    DispenseResponse,
    AdherenceLogCreate,
    AdherenceLogResponse,
    AdherenceReport,
    MedicationScheduleCreate,
    MedicationScheduleUpdate,
    MedicationScheduleResponse,
    RefillRequestCreate,
    RefillRequestUpdate,
    RefillRequestResponse,
    MedicationImpactReport,
)

router = APIRouter()


# ── Helpers ──────────────────────────────────────────────────────────

def _enrich_prescription(rx: Prescription) -> dict:
    """Add computed fields to a prescription row."""
    data = {c.name: getattr(rx, c.name) for c in rx.__table__.columns}
    data["patient_name"] = rx.patient.full_name if rx.patient else None
    data["prescriber_name"] = rx.prescriber.full_name if rx.prescriber else None
    data["dispense_count"] = len(rx.dispenses) if rx.dispenses else 0
    return data


# ═══════════════════════════════════════════════════════════════════════
#  PRESCRIPTIONS  (Physician-facing + shared read)
# ═══════════════════════════════════════════════════════════════════════

@router.post("/prescriptions", response_model=PrescriptionResponse, status_code=201)
async def create_prescription(
    body: PrescriptionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Physician creates a new prescription for a patient."""
    rx = Prescription(
        **body.model_dump(),
        prescriber_id=current_user.id,
        refills_remaining=body.refills_authorized,
    )
    db.add(rx)
    await db.flush()
    await db.refresh(rx, attribute_names=["patient", "prescriber", "dispenses"])

    # Notify patient
    await notify_prescription_created(
        db,
        user_id=body.patient_id,
        medication_name=body.medication_name,
        prescriber_name=current_user.full_name,
        prescription_id=rx.id,
    )
    return _enrich_prescription(rx)


@router.get("/prescriptions", response_model=list[PrescriptionResponse])
async def list_prescriptions(
    role: str = Query("patient", regex="^(patient|prescriber|pharmacist)$"),
    status: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List prescriptions. Filter by role perspective and optional status."""
    query = select(Prescription)

    if role == "patient":
        query = query.where(Prescription.patient_id == current_user.id)
    elif role == "prescriber":
        query = query.where(Prescription.prescriber_id == current_user.id)
    # pharmacist sees all active prescriptions (queue)

    if status:
        query = query.where(Prescription.status == status)

    query = query.order_by(Prescription.created_at.desc())
    result = await db.execute(query)
    rxs = result.scalars().unique().all()
    return [_enrich_prescription(rx) for rx in rxs]


@router.get("/prescriptions/{rx_id}", response_model=PrescriptionResponse)
async def get_prescription(
    rx_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get single prescription (accessible by patient, prescriber, or pharmacist)."""
    result = await db.execute(
        select(Prescription).where(Prescription.id == rx_id)
    )
    rx = result.scalar_one_or_none()
    if not rx:
        raise HTTPException(404, "Prescription not found")
    # Access control: patient, prescriber, or any user (pharmacist)
    if rx.patient_id != current_user.id and rx.prescriber_id != current_user.id:
        pass  # pharmacists can view any prescription in the workflow
    return _enrich_prescription(rx)


@router.patch("/prescriptions/{rx_id}", response_model=PrescriptionResponse)
async def update_prescription(
    rx_id: int,
    updates: PrescriptionUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update prescription (prescriber or pharmacist)."""
    result = await db.execute(
        select(Prescription).where(Prescription.id == rx_id)
    )
    rx = result.scalar_one_or_none()
    if not rx:
        raise HTTPException(404, "Prescription not found")

    for field, value in updates.model_dump(exclude_unset=True).items():
        setattr(rx, field, value)

    await db.flush()
    await db.refresh(rx, attribute_names=["patient", "prescriber", "dispenses"])
    return _enrich_prescription(rx)


@router.delete("/prescriptions/{rx_id}", status_code=204)
async def cancel_prescription(
    rx_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cancel a prescription (sets status to CANCELLED)."""
    result = await db.execute(
        select(Prescription).where(
            Prescription.id == rx_id,
            Prescription.prescriber_id == current_user.id,
        )
    )
    rx = result.scalar_one_or_none()
    if not rx:
        raise HTTPException(404, "Prescription not found or not yours")
    rx.status = PrescriptionStatus.CANCELLED
    await db.flush()


# ═══════════════════════════════════════════════════════════════════════
#  DISPENSING  (Pharmacist-facing)
# ═══════════════════════════════════════════════════════════════════════

@router.get("/queue", response_model=list[PrescriptionResponse])
async def pharmacy_queue(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Pharmacist queue: active prescriptions awaiting dispensing."""
    query = (
        select(Prescription)
        .where(Prescription.status.in_([
            PrescriptionStatus.ACTIVE,
            PrescriptionStatus.PARTIALLY_FILLED,
        ]))
        .order_by(Prescription.prescribed_date.asc())
    )
    result = await db.execute(query)
    return [_enrich_prescription(rx) for rx in result.scalars().unique().all()]


@router.post("/dispenses", response_model=DispenseResponse, status_code=201)
async def create_dispense(
    body: DispenseCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Pharmacist dispenses medication against a prescription."""
    # Validate prescription
    rx_result = await db.execute(
        select(Prescription).where(Prescription.id == body.prescription_id)
    )
    rx = rx_result.scalar_one_or_none()
    if not rx:
        raise HTTPException(404, "Prescription not found")
    if rx.status == PrescriptionStatus.CANCELLED:
        raise HTTPException(400, "Cannot dispense a cancelled prescription")
    if rx.status == PrescriptionStatus.EXPIRED:
        raise HTTPException(400, "Prescription has expired")

    disp = Dispense(
        **body.model_dump(),
        pharmacist_id=current_user.id,
        dispensed_at=datetime.now(timezone.utc),
        status=DispenseStatus.DISPENSED,
    )
    db.add(disp)

    # Update prescription status
    rx.status = PrescriptionStatus.FILLED

    await db.flush()
    await db.refresh(disp, attribute_names=["pharmacist", "prescription"])

    # Notify patient
    await notify_dispense_complete(
        db,
        user_id=rx.patient_id,
        medication_name=rx.medication_name,
        pharmacist_name=current_user.full_name,
        dispense_id=disp.id,
    )

    data = {c.name: getattr(disp, c.name) for c in disp.__table__.columns}
    data["pharmacist_name"] = current_user.full_name
    data["medication_name"] = rx.medication_name
    return data


@router.get("/dispenses", response_model=list[DispenseResponse])
async def list_dispenses(
    prescription_id: int | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List dispense records. Pharmacist sees their dispenses; patients see their prescription's dispenses."""
    query = select(Dispense)
    if prescription_id:
        query = query.where(Dispense.prescription_id == prescription_id)
    else:
        query = query.where(Dispense.pharmacist_id == current_user.id)
    query = query.order_by(Dispense.created_at.desc())
    result = await db.execute(query)

    dispenses = result.scalars().all()
    out = []
    for d in dispenses:
        data = {c.name: getattr(d, c.name) for c in d.__table__.columns}
        data["pharmacist_name"] = d.pharmacist.full_name if d.pharmacist else None
        data["medication_name"] = d.prescription.medication_name if d.prescription else None
        out.append(data)
    return out


@router.patch("/dispenses/{disp_id}", response_model=DispenseResponse)
async def update_dispense(
    disp_id: int,
    updates: DispenseUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update dispense status / review notes."""
    result = await db.execute(
        select(Dispense).where(
            Dispense.id == disp_id,
            Dispense.pharmacist_id == current_user.id,
        )
    )
    disp = result.scalar_one_or_none()
    if not disp:
        raise HTTPException(404, "Dispense record not found")

    for field, value in updates.model_dump(exclude_unset=True).items():
        setattr(disp, field, value)

    # If moving to ready_for_pickup — notify patient
    if updates.status == DispenseStatus.READY_FOR_PICKUP.value:
        rx = await db.get(Prescription, disp.prescription_id)
        if rx:
            await notify_prescription_ready(
                db,
                user_id=rx.patient_id,
                medication_name=rx.medication_name,
                prescription_id=rx.id,
            )

    await db.flush()
    await db.refresh(disp, attribute_names=["pharmacist", "prescription"])
    data = {c.name: getattr(disp, c.name) for c in disp.__table__.columns}
    data["pharmacist_name"] = disp.pharmacist.full_name if disp.pharmacist else None
    data["medication_name"] = disp.prescription.medication_name if disp.prescription else None
    return data


# ═══════════════════════════════════════════════════════════════════════
#  ADHERENCE  (Patient-facing)
# ═══════════════════════════════════════════════════════════════════════

@router.post("/adherence", response_model=AdherenceLogResponse, status_code=201)
async def log_adherence(
    body: AdherenceLogCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Patient logs a medication take / miss / skip."""
    # Verify prescription belongs to patient
    rx = await db.get(Prescription, body.prescription_id)
    if not rx or rx.patient_id != current_user.id:
        raise HTTPException(404, "Prescription not found")

    log = AdherenceLog(
        **body.model_dump(),
        patient_id=current_user.id,
    )
    db.add(log)
    await db.flush()
    await db.refresh(log)

    data = {c.name: getattr(log, c.name) for c in log.__table__.columns}
    data["medication_name"] = rx.medication_name
    return data


@router.get("/adherence", response_model=list[AdherenceLogResponse])
async def list_adherence(
    prescription_id: int | None = None,
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List adherence logs for current patient."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    query = (
        select(AdherenceLog)
        .where(
            AdherenceLog.patient_id == current_user.id,
            AdherenceLog.created_at >= cutoff,
        )
    )
    if prescription_id:
        query = query.where(AdherenceLog.prescription_id == prescription_id)
    query = query.order_by(AdherenceLog.scheduled_time.desc())
    result = await db.execute(query)
    logs = result.scalars().all()
    out = []
    for log in logs:
        data = {c.name: getattr(log, c.name) for c in log.__table__.columns}
        data["medication_name"] = log.prescription.medication_name if log.prescription else None
        out.append(data)
    return out


@router.get("/adherence/report", response_model=AdherenceReport)
async def adherence_report(
    prescription_id: int | None = None,
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Aggregated adherence metrics for the patient."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    query = select(AdherenceLog).where(
        AdherenceLog.patient_id == current_user.id,
        AdherenceLog.created_at >= cutoff,
    )
    if prescription_id:
        query = query.where(AdherenceLog.prescription_id == prescription_id)

    result = await db.execute(query)
    logs = list(result.scalars().all())

    total = len(logs)
    taken = sum(1 for l in logs if l.status == AdherenceStatus.TAKEN.value)
    missed = sum(1 for l in logs if l.status == AdherenceStatus.MISSED.value)
    skipped = sum(1 for l in logs if l.status == AdherenceStatus.SKIPPED.value)
    late = sum(1 for l in logs if l.status == AdherenceStatus.LATE.value)
    rate = (taken + late) / total * 100 if total else 0

    # Average delay for late doses
    delays = []
    for l in logs:
        if l.status == AdherenceStatus.LATE.value and l.actual_time and l.scheduled_time:
            delays.append((l.actual_time - l.scheduled_time).total_seconds() / 60)

    # Streaks
    sorted_logs = sorted(logs, key=lambda l: l.scheduled_time)
    streak = 0
    longest = 0
    for l in sorted_logs:
        if l.status in (AdherenceStatus.TAKEN.value, AdherenceStatus.LATE.value):
            streak += 1
            longest = max(longest, streak)
        else:
            streak = 0

    # Side effects
    side_effects = []
    for l in logs:
        if l.side_effects_reported:
            for se in l.side_effects_reported.split(","):
                se = se.strip()
                if se and se not in side_effects:
                    side_effects.append(se)

    med_name = None
    if prescription_id:
        rx = await db.get(Prescription, prescription_id)
        med_name = rx.medication_name if rx else None

    return AdherenceReport(
        prescription_id=prescription_id,
        patient_id=current_user.id,
        medication_name=med_name,
        total_scheduled=total,
        total_taken=taken,
        total_missed=missed,
        total_skipped=skipped,
        total_late=late,
        adherence_rate=round(rate, 1),
        avg_delay_minutes=round(sum(delays) / len(delays), 1) if delays else None,
        streak_current=streak,
        streak_longest=longest,
        common_side_effects=side_effects,
        period_start=(cutoff.date()),
        period_end=date.today(),
    )


# ═══════════════════════════════════════════════════════════════════════
#  MEDICATION SCHEDULES
# ═══════════════════════════════════════════════════════════════════════

@router.post("/schedules", response_model=MedicationScheduleResponse, status_code=201)
async def create_schedule(
    body: MedicationScheduleCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a medication schedule entry."""
    rx = await db.get(Prescription, body.prescription_id)
    if not rx or rx.patient_id != current_user.id:
        raise HTTPException(404, "Prescription not found")

    sched = MedicationSchedule(**body.model_dump(), patient_id=current_user.id)
    db.add(sched)
    await db.flush()
    await db.refresh(sched)
    data = {c.name: getattr(sched, c.name) for c in sched.__table__.columns}
    data["medication_name"] = rx.medication_name
    return data


@router.get("/schedules", response_model=list[MedicationScheduleResponse])
async def list_schedules(
    active_only: bool = True,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List patient's medication schedules."""
    query = select(MedicationSchedule).where(
        MedicationSchedule.patient_id == current_user.id,
    )
    if active_only:
        query = query.where(MedicationSchedule.is_active == True)  # noqa: E712
    query = query.order_by(MedicationSchedule.time_of_day.asc())
    result = await db.execute(query)
    schedules = result.scalars().all()
    out = []
    for s in schedules:
        data = {c.name: getattr(s, c.name) for c in s.__table__.columns}
        data["medication_name"] = s.prescription.medication_name if s.prescription else None
        out.append(data)
    return out


@router.patch("/schedules/{sched_id}", response_model=MedicationScheduleResponse)
async def update_schedule(
    sched_id: int,
    updates: MedicationScheduleUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a schedule entry."""
    result = await db.execute(
        select(MedicationSchedule).where(
            MedicationSchedule.id == sched_id,
            MedicationSchedule.patient_id == current_user.id,
        )
    )
    sched = result.scalar_one_or_none()
    if not sched:
        raise HTTPException(404, "Schedule not found")

    for field, value in updates.model_dump(exclude_unset=True).items():
        setattr(sched, field, value)
    await db.flush()
    await db.refresh(sched)
    data = {c.name: getattr(sched, c.name) for c in sched.__table__.columns}
    data["medication_name"] = sched.prescription.medication_name if sched.prescription else None
    return data


@router.delete("/schedules/{sched_id}", status_code=204)
async def delete_schedule(
    sched_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a schedule entry."""
    result = await db.execute(
        select(MedicationSchedule).where(
            MedicationSchedule.id == sched_id,
            MedicationSchedule.patient_id == current_user.id,
        )
    )
    sched = result.scalar_one_or_none()
    if not sched:
        raise HTTPException(404, "Schedule not found")
    await db.delete(sched)


# ═══════════════════════════════════════════════════════════════════════
#  REFILL REQUESTS
# ═══════════════════════════════════════════════════════════════════════

@router.post("/refills", response_model=RefillRequestResponse, status_code=201)
async def request_refill(
    body: RefillRequestCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Patient (or pharmacist) requests a refill."""
    rx = await db.get(Prescription, body.prescription_id)
    if not rx:
        raise HTTPException(404, "Prescription not found")
    if rx.refills_remaining <= 0:
        raise HTTPException(400, "No refills remaining on this prescription")

    refill = RefillRequest(
        **body.model_dump(),
        patient_id=rx.patient_id,
        requested_by_id=current_user.id,
    )
    db.add(refill)
    await db.flush()
    await db.refresh(refill)

    # Notify prescriber about refill request
    await notify_refill_reminder(
        db,
        user_id=rx.prescriber_id,
        medication_name=rx.medication_name,
        patient_name=rx.patient.full_name if rx.patient else "Patient",
        prescription_id=rx.id,
    )

    data = {c.name: getattr(refill, c.name) for c in refill.__table__.columns}
    data["medication_name"] = rx.medication_name
    return data


@router.get("/refills", response_model=list[RefillRequestResponse])
async def list_refills(
    prescription_id: int | None = None,
    status: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List refill requests (patient sees their own; prescriber sees requests for their rxs)."""
    query = select(RefillRequest).where(
        or_(
            RefillRequest.patient_id == current_user.id,
            RefillRequest.requested_by_id == current_user.id,
        )
    )
    if prescription_id:
        query = query.where(RefillRequest.prescription_id == prescription_id)
    if status:
        query = query.where(RefillRequest.status == status)
    query = query.order_by(RefillRequest.requested_at.desc())
    result = await db.execute(query)
    refills = result.scalars().all()
    out = []
    for r in refills:
        data = {c.name: getattr(r, c.name) for c in r.__table__.columns}
        data["medication_name"] = r.prescription.medication_name if r.prescription else None
        out.append(data)
    return out


@router.patch("/refills/{refill_id}", response_model=RefillRequestResponse)
async def resolve_refill(
    refill_id: int,
    updates: RefillRequestUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Approve or deny a refill request (prescriber action)."""
    result = await db.execute(
        select(RefillRequest).where(RefillRequest.id == refill_id)
    )
    refill = result.scalar_one_or_none()
    if not refill:
        raise HTTPException(404, "Refill request not found")

    for field, value in updates.model_dump(exclude_unset=True).items():
        setattr(refill, field, value)

    refill.approved_by_id = current_user.id
    refill.resolved_at = datetime.now(timezone.utc)

    # If approved, decrement refills_remaining
    if updates.status == RefillStatus.APPROVED.value:
        rx = await db.get(Prescription, refill.prescription_id)
        if rx and rx.refills_remaining > 0:
            rx.refills_remaining -= 1
            rx.status = PrescriptionStatus.ACTIVE

    await db.flush()
    await db.refresh(refill)
    data = {c.name: getattr(refill, c.name) for c in refill.__table__.columns}
    data["medication_name"] = refill.prescription.medication_name if refill.prescription else None
    return data


# ═══════════════════════════════════════════════════════════════════════
#  IMPACT ANALYSIS  (cross-domain)
# ═══════════════════════════════════════════════════════════════════════

@router.get("/impact/{rx_id}", response_model=MedicationImpactReport)
async def medication_impact(
    rx_id: int,
    days: int = Query(30, ge=7, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Analyze the health impact of a prescription by correlating adherence
    data with vitals, mood, labs, and side-effect reports.
    """
    rx = await db.get(Prescription, rx_id)
    if not rx:
        raise HTTPException(404, "Prescription not found")

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # Adherence stats
    adh_result = await db.execute(
        select(AdherenceLog).where(
            AdherenceLog.prescription_id == rx_id,
            AdherenceLog.created_at >= cutoff,
        )
    )
    logs = list(adh_result.scalars().all())
    total = len(logs)
    taken = sum(1 for l in logs if l.status in (AdherenceStatus.TAKEN.value, AdherenceStatus.LATE.value))
    missed = sum(1 for l in logs if l.status == AdherenceStatus.MISSED.value)
    rate = taken / total * 100 if total else 0

    # Mood impact
    mood_befores = [l.mood_before for l in logs if l.mood_before is not None]
    mood_afters = [l.mood_after for l in logs if l.mood_after is not None]
    avg_mood_before = sum(mood_befores) / len(mood_befores) if mood_befores else None
    avg_mood_after = sum(mood_afters) / len(mood_afters) if mood_afters else None

    mood_trend = None
    if avg_mood_before is not None and avg_mood_after is not None:
        diff = avg_mood_after - avg_mood_before
        if diff > 0.5:
            mood_trend = "improving"
        elif diff < -0.5:
            mood_trend = "declining"
        else:
            mood_trend = "stable"

    # Side effects
    side_effects = []
    se_freq: dict[str, int] = {}
    for l in logs:
        if l.side_effects_reported:
            for se in l.side_effects_reported.split(","):
                se = se.strip()
                if se:
                    se_freq[se] = se_freq.get(se, 0) + 1
                    if se not in side_effects:
                        side_effects.append(se)

    return MedicationImpactReport(
        prescription_id=rx_id,
        medication_name=rx.medication_name,
        patient_id=rx.patient_id,
        analysis_period_days=days,
        adherence_rate=round(rate, 1),
        doses_taken=taken,
        doses_missed=missed,
        avg_mood_before=round(avg_mood_before, 1) if avg_mood_before else None,
        avg_mood_after=round(avg_mood_after, 1) if avg_mood_after else None,
        mood_trend=mood_trend,
        reported_side_effects=side_effects,
        side_effect_frequency=se_freq if se_freq else None,
        ai_summary=(
            f"Over {days} days: {rate:.0f}% adherence ({taken} taken, {missed} missed). "
            + (f"Mood trend: {mood_trend}. " if mood_trend else "")
            + (f"Side effects: {', '.join(side_effects[:5])}." if side_effects else "No side effects reported.")
        ),
    )
