from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from sqlalchemy.orm import selectinload
from typing import List

import alafia_crypto as _rc  # Rust crypto backend
from datetime import datetime

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.notification_engine import notify_therapy_session_completed, notify_treatment_anomaly
from app.models.user import User
from app.models.chronic_conditions import ChronicCondition, TherapySession, ConditionMetric, IntradialyticReading, ClinicalNote, FlowsheetStatus
from app.schemas.chronic_conditions import (
    ChronicConditionCreate,
    ChronicConditionUpdate,
    ChronicConditionResponse,
    TherapySessionCreate,
    TherapySessionUpdate,
    TherapySessionResponse,
    ConditionMetricCreate,
    ConditionMetricUpdate,
    ConditionMetricResponse,
    IntradialyticReadingCreate,
    IntradialyticReadingUpdate,
    IntradialyticReadingResponse,
    ClinicalNoteCreate,
    ClinicalNoteResponse,
    FlowsheetSignRequest,
    FlowsheetActionResponse,
)

router = APIRouter()


# ============= CHRONIC CONDITIONS =============

@router.get("/conditions", response_model=List[ChronicConditionResponse])
async def get_chronic_conditions(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    is_active: bool = Query(None),
    category: str = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all chronic conditions for the current user."""
    query = select(ChronicCondition).where(ChronicCondition.user_id == current_user.id)
    
    if is_active is not None:
        query = query.where(ChronicCondition.is_active == is_active)
    if category:
        query = query.where(ChronicCondition.category == category)
    
    query = query.offset(skip).limit(limit).order_by(ChronicCondition.diagnosis_date.desc())
    result = await db.execute(query)
    conditions = result.scalars().all()
    return conditions


@router.get("/conditions/{condition_id}", response_model=ChronicConditionResponse)
async def get_chronic_condition(
    condition_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific chronic condition by ID."""
    query = select(ChronicCondition).where(
        and_(
            ChronicCondition.id == condition_id,
            ChronicCondition.user_id == current_user.id
        )
    )
    result = await db.execute(query)
    condition = result.scalar_one_or_none()
    
    if not condition:
        raise HTTPException(status_code=404, detail="Chronic condition not found")
    
    return condition


@router.post("/conditions", response_model=ChronicConditionResponse, status_code=201)
async def create_chronic_condition(
    condition: ChronicConditionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new chronic condition."""
    db_condition = ChronicCondition(
        **condition.model_dump(),
        user_id=current_user.id
    )
    db.add(db_condition)
    await db.commit()
    await db.refresh(db_condition)
    return db_condition


@router.put("/conditions/{condition_id}", response_model=ChronicConditionResponse)
async def update_chronic_condition(
    condition_id: int,
    condition_update: ChronicConditionUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a chronic condition."""
    query = select(ChronicCondition).where(
        and_(
            ChronicCondition.id == condition_id,
            ChronicCondition.user_id == current_user.id
        )
    )
    result = await db.execute(query)
    db_condition = result.scalar_one_or_none()
    
    if not db_condition:
        raise HTTPException(status_code=404, detail="Chronic condition not found")
    
    update_data = condition_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_condition, field, value)
    
    await db.commit()
    await db.refresh(db_condition)
    return db_condition


@router.delete("/conditions/{condition_id}", status_code=204)
async def delete_chronic_condition(
    condition_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a chronic condition."""
    query = select(ChronicCondition).where(
        and_(
            ChronicCondition.id == condition_id,
            ChronicCondition.user_id == current_user.id
        )
    )
    result = await db.execute(query)
    db_condition = result.scalar_one_or_none()
    
    if not db_condition:
        raise HTTPException(status_code=404, detail="Chronic condition not found")
    
    await db.delete(db_condition)
    await db.commit()


# ============= THERAPY SESSIONS =============

@router.get("/therapy-sessions", response_model=List[TherapySessionResponse])
async def get_therapy_sessions(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    condition_id: int = Query(None),
    therapy_type: str = Query(None),
    status: str = Query(None),
    start_date: datetime = Query(None),
    end_date: datetime = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all therapy sessions for the current user."""
    query = (
        select(TherapySession)
        .options(selectinload(TherapySession.intradialytic_readings))
        .where(TherapySession.user_id == current_user.id)
    )
    
    if condition_id:
        query = query.where(TherapySession.condition_id == condition_id)
    if therapy_type:
        query = query.where(TherapySession.therapy_type == therapy_type)
    if status:
        query = query.where(TherapySession.status == status)
    if start_date:
        query = query.where(TherapySession.scheduled_date >= start_date)
    if end_date:
        query = query.where(TherapySession.scheduled_date <= end_date)
    
    query = query.offset(skip).limit(limit).order_by(TherapySession.scheduled_date.desc())
    result = await db.execute(query)
    sessions = result.scalars().unique().all()
    return sessions


@router.get("/therapy-sessions/{session_id}", response_model=TherapySessionResponse)
async def get_therapy_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific therapy session by ID with intradialytic readings."""
    query = (
        select(TherapySession)
        .options(selectinload(TherapySession.intradialytic_readings))
        .where(
            and_(
                TherapySession.id == session_id,
                TherapySession.user_id == current_user.id
            )
        )
    )
    result = await db.execute(query)
    session = result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(status_code=404, detail="Therapy session not found")
    
    return session


@router.post("/therapy-sessions", response_model=TherapySessionResponse, status_code=201)
async def create_therapy_session(
    session: TherapySessionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new therapy session."""
    # Verify condition belongs to user if condition_id is provided
    if session.condition_id:
        condition_query = select(ChronicCondition).where(
            and_(
                ChronicCondition.id == session.condition_id,
                ChronicCondition.user_id == current_user.id
            )
        )
        condition_result = await db.execute(condition_query)
        condition = condition_result.scalar_one_or_none()
        if not condition:
            raise HTTPException(status_code=404, detail="Chronic condition not found")
    
    db_session = TherapySession(
        **session.model_dump(),
        user_id=current_user.id
    )
    db.add(db_session)
    await db.commit()

    # Re-query with relationships eagerly loaded to avoid async lazy-load errors
    result = await db.execute(
        select(TherapySession)
        .options(selectinload(TherapySession.intradialytic_readings))
        .where(TherapySession.id == db_session.id)
    )
    db_session = result.scalar_one()

    # Notification: therapy completed
    if db_session.status == "completed":
        therapy_type = db_session.therapy_type.value if hasattr(db_session.therapy_type, 'value') else str(db_session.therapy_type)
        await notify_therapy_session_completed(
            db, user_id=current_user.id, therapy_type=therapy_type,
            session_date=str(db_session.scheduled_date), session_id=db_session.id,
        )
    # Notification: treatment anomaly (excessive fluid removal)
    if db_session.fluid_removed_ml and db_session.fluid_removed_ml > 4000:
        therapy_type = db_session.therapy_type.value if hasattr(db_session.therapy_type, 'value') else str(db_session.therapy_type)
        await notify_treatment_anomaly(
            db, user_id=current_user.id, session_id=db_session.id,
            therapy_type=therapy_type,
            description=f"Excessive fluid removal ({db_session.fluid_removed_ml} mL) detected. Please review.",
        )

    return db_session


@router.put("/therapy-sessions/{session_id}", response_model=TherapySessionResponse)
async def update_therapy_session(
    session_id: int,
    session_update: TherapySessionUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a therapy session."""
    query = select(TherapySession).where(
        and_(
            TherapySession.id == session_id,
            TherapySession.user_id == current_user.id
        )
    )
    result = await db.execute(query)
    db_session = result.scalar_one_or_none()
    
    if not db_session:
        raise HTTPException(status_code=404, detail="Therapy session not found")
    
    update_data = session_update.model_dump(exclude_unset=True)
    old_status = db_session.status
    for field, value in update_data.items():
        setattr(db_session, field, value)
    
    await db.commit()

    # Re-query with relationships eagerly loaded
    result = await db.execute(
        select(TherapySession)
        .options(selectinload(TherapySession.intradialytic_readings))
        .where(TherapySession.id == db_session.id)
    )
    db_session = result.scalar_one()

    # Notification: status changed to completed
    new_status = db_session.status.value if hasattr(db_session.status, 'value') else str(db_session.status)
    if old_status != "completed" and new_status == "completed":
        therapy_type = db_session.therapy_type.value if hasattr(db_session.therapy_type, 'value') else str(db_session.therapy_type)
        await notify_therapy_session_completed(
            db, user_id=current_user.id, therapy_type=therapy_type,
            session_date=str(db_session.scheduled_date), session_id=db_session.id,
        )

    return db_session


@router.delete("/therapy-sessions/{session_id}", status_code=204)
async def delete_therapy_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a therapy session."""
    query = select(TherapySession).where(
        and_(
            TherapySession.id == session_id,
            TherapySession.user_id == current_user.id
        )
    )
    result = await db.execute(query)
    db_session = result.scalar_one_or_none()
    
    if not db_session:
        raise HTTPException(status_code=404, detail="Therapy session not found")
    
    await db.delete(db_session)
    await db.commit()


# ============= CONDITION METRICS =============

@router.get("/condition-metrics", response_model=List[ConditionMetricResponse])
async def get_condition_metrics(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    condition_id: int = Query(None),
    metric_name: str = Query(None),
    start_date: datetime = Query(None),
    end_date: datetime = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all condition metrics for the current user."""
    query = select(ConditionMetric).where(ConditionMetric.user_id == current_user.id)
    
    if condition_id:
        query = query.where(ConditionMetric.condition_id == condition_id)
    if metric_name:
        query = query.where(ConditionMetric.metric_name == metric_name)
    if start_date:
        query = query.where(ConditionMetric.measured_date >= start_date)
    if end_date:
        query = query.where(ConditionMetric.measured_date <= end_date)
    
    query = query.offset(skip).limit(limit).order_by(ConditionMetric.measured_date.desc())
    result = await db.execute(query)
    metrics = result.scalars().all()
    return metrics


@router.get("/condition-metrics/{metric_id}", response_model=ConditionMetricResponse)
async def get_condition_metric(
    metric_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific condition metric by ID."""
    query = select(ConditionMetric).where(
        and_(
            ConditionMetric.id == metric_id,
            ConditionMetric.user_id == current_user.id
        )
    )
    result = await db.execute(query)
    metric = result.scalar_one_or_none()
    
    if not metric:
        raise HTTPException(status_code=404, detail="Condition metric not found")
    
    return metric


@router.post("/condition-metrics", response_model=ConditionMetricResponse, status_code=201)
async def create_condition_metric(
    metric: ConditionMetricCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new condition metric."""
    # Verify condition belongs to user
    condition_query = select(ChronicCondition).where(
        and_(
            ChronicCondition.id == metric.condition_id,
            ChronicCondition.user_id == current_user.id
        )
    )
    condition_result = await db.execute(condition_query)
    condition = condition_result.scalar_one_or_none()
    if not condition:
        raise HTTPException(status_code=404, detail="Chronic condition not found")
    
    db_metric = ConditionMetric(
        **metric.model_dump(),
        user_id=current_user.id
    )
    db.add(db_metric)
    await db.commit()
    await db.refresh(db_metric)
    return db_metric


@router.put("/condition-metrics/{metric_id}", response_model=ConditionMetricResponse)
async def update_condition_metric(
    metric_id: int,
    metric_update: ConditionMetricUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a condition metric."""
    query = select(ConditionMetric).where(
        and_(
            ConditionMetric.id == metric_id,
            ConditionMetric.user_id == current_user.id
        )
    )
    result = await db.execute(query)
    db_metric = result.scalar_one_or_none()
    
    if not db_metric:
        raise HTTPException(status_code=404, detail="Condition metric not found")
    
    update_data = metric_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_metric, field, value)
    
    await db.commit()
    await db.refresh(db_metric)
    return db_metric


@router.delete("/condition-metrics/{metric_id}", status_code=204)
async def delete_condition_metric(
    metric_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a condition metric."""
    query = select(ConditionMetric).where(
        and_(
            ConditionMetric.id == metric_id,
            ConditionMetric.user_id == current_user.id
        )
    )
    result = await db.execute(query)
    db_metric = result.scalar_one_or_none()
    
    if not db_metric:
        raise HTTPException(status_code=404, detail="Condition metric not found")
    
    await db.delete(db_metric)
    await db.commit()


# ============= INTRADIALYTIC READINGS =============

@router.get("/therapy-sessions/{session_id}/readings", response_model=List[IntradialyticReadingResponse])
async def get_intradialytic_readings(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all intradialytic readings for a therapy session."""
    # Verify session belongs to user
    session_query = select(TherapySession).where(
        and_(TherapySession.id == session_id, TherapySession.user_id == current_user.id)
    )
    session_result = await db.execute(session_query)
    if not session_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Therapy session not found")

    query = (
        select(IntradialyticReading)
        .where(IntradialyticReading.session_id == session_id)
        .order_by(IntradialyticReading.reading_time)
    )
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/therapy-sessions/{session_id}/readings", response_model=IntradialyticReadingResponse, status_code=201)
async def create_intradialytic_reading(
    session_id: int,
    reading: IntradialyticReadingCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Add an intradialytic reading to a therapy session."""
    session_query = select(TherapySession).where(
        and_(TherapySession.id == session_id, TherapySession.user_id == current_user.id)
    )
    session_result = await db.execute(session_query)
    if not session_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Therapy session not found")

    db_reading = IntradialyticReading(
        **reading.model_dump(exclude={"session_id"}),
        session_id=session_id,
        user_id=current_user.id,
    )
    db.add(db_reading)
    await db.commit()
    await db.refresh(db_reading)
    return db_reading


@router.delete("/readings/{reading_id}", status_code=204)
async def delete_intradialytic_reading(
    reading_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete an intradialytic reading."""
    query = select(IntradialyticReading).where(
        and_(IntradialyticReading.id == reading_id, IntradialyticReading.user_id == current_user.id)
    )
    result = await db.execute(query)
    db_reading = result.scalar_one_or_none()
    if not db_reading:
        raise HTTPException(status_code=404, detail="Reading not found")
    await db.delete(db_reading)
    await db.commit()


# ============= HD SESSION SUMMARY / STATS =============

@router.get("/hd-summary")
async def get_hd_summary(
    days: int = Query(90, ge=7, le=3650),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get hemodialysis session summary statistics."""
    cutoff = datetime.utcnow() - __import__('datetime').timedelta(days=days)
    query = (
        select(TherapySession)
        .options(selectinload(TherapySession.intradialytic_readings))
        .where(
            and_(
                TherapySession.user_id == current_user.id,
                TherapySession.therapy_type.in_(["HEMODIALYSIS", "hemodialysis"]),
                TherapySession.scheduled_date >= cutoff,
            )
        )
        .order_by(TherapySession.scheduled_date.desc())
    )
    result = await db.execute(query)
    sessions = result.scalars().unique().all()

    total = len(sessions)
    if total == 0:
        return {"total_sessions": 0, "period_days": days}

    weights_pre = [s.pre_dialysis_weight_kg for s in sessions if s.pre_dialysis_weight_kg]
    weights_post = [s.post_dialysis_weight_kg for s in sessions if s.post_dialysis_weight_kg]
    fluids = [s.fluid_removed_ml for s in sessions if s.fluid_removed_ml]
    durations = [s.duration_minutes for s in sessions if s.duration_minutes]

    return {
        "total_sessions": total,
        "period_days": days,
        "avg_pre_weight_kg": round(sum(weights_pre) / len(weights_pre), 1) if weights_pre else None,
        "avg_post_weight_kg": round(sum(weights_post) / len(weights_post), 1) if weights_post else None,
        "avg_fluid_removed_ml": round(sum(fluids) / len(fluids), 0) if fluids else None,
        "avg_duration_min": round(sum(durations) / len(durations), 0) if durations else None,
        "sessions_with_readings": sum(1 for s in sessions if s.intradialytic_readings),
    }


# ============= FLOWSHEET LIFECYCLE =============

async def _get_session_for_flowsheet(session_id: int, user_id: int, db: AsyncSession) -> TherapySession:
    """Fetch a therapy session or 404."""
    query = select(TherapySession).where(
        and_(TherapySession.id == session_id, TherapySession.user_id == user_id)
    )
    result = await db.execute(query)
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Therapy session not found")
    return session


def _compute_payload_hash(session: TherapySession) -> str:
    """SHA-512 hash of the flowsheet's key fields (via Rust crypto)."""
    import json
    payload = json.dumps({
        "session_id": session.id,
        "user_id": session.user_id,
        "scheduled_date": str(session.scheduled_date),
        "pre_dialysis_weight_kg": session.pre_dialysis_weight_kg,
        "post_dialysis_weight_kg": session.post_dialysis_weight_kg,
        "fluid_removed_ml": session.fluid_removed_ml,
        "blood_flow_rate": session.blood_flow_rate,
        "total_uf_liters": session.total_uf_liters,
    }, sort_keys=True, default=str)
    return _rc.compute_data_hash(payload)


@router.post("/therapy-sessions/{session_id}/submit", response_model=FlowsheetActionResponse)
async def submit_flowsheet(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark a therapy session as submitted (draft → submitted)."""
    session = await _get_session_for_flowsheet(session_id, current_user.id, db)
    current = session.flowsheet_status
    if current is not None and current != FlowsheetStatus.DRAFT:
        raise HTTPException(400, f"Cannot submit: current status is '{current}'")
    session.flowsheet_status = FlowsheetStatus.SUBMITTED
    await db.commit()
    return FlowsheetActionResponse(id=session.id, flowsheet_status="submitted", message="Flowsheet submitted")


@router.post("/therapy-sessions/{session_id}/sign", response_model=FlowsheetActionResponse)
async def sign_flowsheet(
    session_id: int,
    body: FlowsheetSignRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Digitally sign a submitted flowsheet (submitted → signed).

    Accepts a base64-encoded PNG signature image and computes a
    SHA-512 payload hash anchored to the blockchain.
    """
    session = await _get_session_for_flowsheet(session_id, current_user.id, db)
    if session.flowsheet_status != FlowsheetStatus.SUBMITTED:
        raise HTTPException(400, f"Cannot sign: current status is '{session.flowsheet_status}'")
    session.flowsheet_status = FlowsheetStatus.SIGNED
    session.signature_image = body.signature_image
    session.signed_at = datetime.utcnow()
    session.signed_by = current_user.id
    session.payload_hash = _compute_payload_hash(session)

    # Anchor to blockchain (best-effort)
    try:
        from app.services.blockchain_ledger import BlockchainLedger
        from app.services.blockchain_engine import ChainType, EventAction
        ledger = BlockchainLedger(db)
        await ledger.record_therapy_event(
            action=EventAction.therapy_session_completed,
            data={"event": "FLOWSHEET_SIGNED", "payload_hash": session.payload_hash},
            actor_id=current_user.id,
            entity_id=session.id,
        )
    except Exception:
        pass  # chain failures must not block clinical workflow

    await db.commit()
    return FlowsheetActionResponse(id=session.id, flowsheet_status="signed", message="Flowsheet signed")


@router.post("/therapy-sessions/{session_id}/countersign", response_model=FlowsheetActionResponse)
async def countersign_flowsheet(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Nurse home-review countersign (signed → countersigned)."""
    session = await _get_session_for_flowsheet(session_id, current_user.id, db)
    if session.flowsheet_status != FlowsheetStatus.SIGNED:
        raise HTTPException(400, f"Cannot countersign: current status is '{session.flowsheet_status}'")
    session.flowsheet_status = FlowsheetStatus.COUNTERSIGNED
    session.countersigned_at = datetime.utcnow()
    session.countersigned_by = current_user.id
    await db.commit()
    return FlowsheetActionResponse(id=session.id, flowsheet_status="countersigned", message="Flowsheet countersigned")


@router.post("/therapy-sessions/{session_id}/review", response_model=FlowsheetActionResponse)
async def review_flowsheet(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Physician review (countersigned → reviewed → locked)."""
    session = await _get_session_for_flowsheet(session_id, current_user.id, db)
    if session.flowsheet_status not in (FlowsheetStatus.COUNTERSIGNED, FlowsheetStatus.SIGNED):
        raise HTTPException(400, f"Cannot review: current status is '{session.flowsheet_status}'")
    session.flowsheet_status = FlowsheetStatus.REVIEWED
    session.reviewed_at = datetime.utcnow()
    session.reviewed_by = current_user.id
    await db.commit()
    return FlowsheetActionResponse(id=session.id, flowsheet_status="reviewed", message="Flowsheet reviewed")


@router.post("/therapy-sessions/{session_id}/lock", response_model=FlowsheetActionResponse)
async def lock_flowsheet(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Lock a reviewed flowsheet — no further edits allowed."""
    session = await _get_session_for_flowsheet(session_id, current_user.id, db)
    if session.flowsheet_status != FlowsheetStatus.REVIEWED:
        raise HTTPException(400, f"Cannot lock: current status is '{session.flowsheet_status}'")
    session.flowsheet_status = FlowsheetStatus.LOCKED
    await db.commit()
    return FlowsheetActionResponse(id=session.id, flowsheet_status="locked", message="Flowsheet locked")


# ============= CLINICAL NOTES =============

@router.get("/therapy-sessions/{session_id}/notes", response_model=List[ClinicalNoteResponse])
async def get_clinical_notes(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all clinical notes for a therapy session."""
    await _get_session_for_flowsheet(session_id, current_user.id, db)
    query = (
        select(ClinicalNote)
        .where(ClinicalNote.session_id == session_id)
        .order_by(ClinicalNote.created_at)
    )
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/therapy-sessions/{session_id}/notes", response_model=ClinicalNoteResponse, status_code=201)
async def add_clinical_note(
    session_id: int,
    body: ClinicalNoteCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add an immutable clinical note to a therapy session.

    Notes cannot be edited or deleted after creation — they are
    append-only with a SHA-512 integrity hash.
    """
    session = await _get_session_for_flowsheet(session_id, current_user.id, db)
    if session.flowsheet_status == FlowsheetStatus.LOCKED:
        raise HTTPException(400, "Cannot add notes to a locked flowsheet")

    note_hash = _rc.sha512_hex(body.note_text)
    note = ClinicalNote(
        session_id=session_id,
        author_id=current_user.id,
        note_type=body.note_type,
        note_text=body.note_text,
        note_hash=note_hash,
    )
    db.add(note)

    # Anchor to blockchain
    try:
        from app.services.blockchain_ledger import BlockchainLedger
        from app.services.blockchain_engine import ChainType, EventAction
        ledger = BlockchainLedger(db)
        await ledger.record_therapy_event(
            action=EventAction.therapy_notes_added,
            data={"event": "NOTE_ADDED", "note_hash": note_hash, "session_id": session_id},
            actor_id=current_user.id,
            entity_id=session_id,
        )
    except Exception:
        pass

    await db.commit()
    await db.refresh(note)
    return note
