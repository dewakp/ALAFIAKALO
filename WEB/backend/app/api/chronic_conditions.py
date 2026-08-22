from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from sqlalchemy import select, and_, func
from sqlalchemy.orm import selectinload
from typing import List

import alafia_crypto as _rc  # Rust crypto backend
from datetime import date, datetime, timezone

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.notification_engine import notify_therapy_session_completed, notify_treatment_anomaly
from app.models.user import User
from app.models.chronic_conditions import ChronicCondition, TherapySession, ConditionMetric, IntradialyticReading, ClinicalNote, FlowsheetStatus
from app.services import flowsheet_defaults as fs_defaults
from app.services.flowsheet_drugs import COMMON_DIALYSIS_DRUGS
from app.services.icd11_catalog import (
    ICD11_CODE_RE,
    catalog_version as icd11_catalog_version,
    get_icd11_by_code,
    list_chapters as icd11_chapters,
    search_icd11,
)
from app.schemas.chronic_conditions import (
    FlowsheetDefaultsResponse,
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
    ICD11CodeOut,
    ICD11SearchResult,
    ICD11Chapter,
)


def _naive_utc(value: datetime | None) -> datetime | None:
    """Drop the timezone from a client-supplied datetime, converting to UTC.

    `therapy_sessions.scheduled_date` and `condition_metrics.measured_date` are
    `DateTime` WITHOUT timezone. Clients send an ISO-8601 instant — the web
    Hemodialysis page sends `new Date().toISOString()`, which ends in `Z` — and
    FastAPI parses that into a tz-AWARE datetime. Comparing aware to naive makes
    asyncpg raise DataError, the endpoint 500s, and the page's catch block
    renders the failure as "No hemodialysis sessions found for this period."

    That is how a patient with 730 dialysis sessions saw zero. Normalising here
    keeps the fix on the boundary, where the ambiguity actually enters.
    """
    if value is None or value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


#: therapy_sessions columns declared `DateTime` WITHOUT timezone. A client that
#: sends an instant ("...Z", or any offset) gives FastAPI a tz-AWARE datetime,
#: and asyncpg refuses to bind one to a naive column — DataError, 500, and on
#: this surface the page renders that as an empty state.
_NAIVE_SESSION_DATETIMES = (
    "scheduled_date", "actual_start_time", "actual_end_time",
    "next_session_scheduled",
)


def _naive_session_payload(data: dict) -> dict:
    """Normalise every naive-column datetime in a session payload.

    `_naive_utc` was already applied to the query FILTERS and not to the body,
    so reading a date range worked and writing one 500'd. The test suite could
    not see it: it ran on SQLite, which has no aware/naive distinction at all.
    """
    for key in _NAIVE_SESSION_DATETIMES:
        if key in data:
            data[key] = _naive_utc(data[key])
    return data


logger = logging.getLogger(__name__)

def _apply_icd11(data: dict) -> dict:
    """Normalise and verify an ICD-11 code, and set its title from the catalog.

    Two things a client must not decide. First, whether the code is real: a
    stem code is only four alphanumerics, so a typo is very often still
    code-SHAPED, and an unverified one lands on a clinical record looking
    exactly like a verified one. Second, what the code is called — the title is
    WHO's, so it is filled in server-side and any client-supplied
    `icd11_title` is discarded rather than trusted.

    Mutates and returns *data* so both create and update share the rule. An
    explicit null clears the pair.
    """
    if "icd11_code" not in data:
        # PATCH-style update that never mentioned the field.
        data.pop("icd11_title", None)
        return data

    raw = (data.get("icd11_code") or "").strip().upper()
    if not raw:
        data["icd11_code"] = None
        data["icd11_title"] = None
        return data

    if not ICD11_CODE_RE.match(raw):
        raise HTTPException(
            status_code=422,
            detail=f"'{raw}' is not a valid ICD-11 code format (e.g. GB61.5).",
        )

    entry = get_icd11_by_code(raw)
    if entry is None:
        raise HTTPException(
            status_code=422,
            detail=f"ICD-11 code '{raw}' does not exist in the WHO catalog.",
        )

    data["icd11_code"] = entry.code
    data["icd11_title"] = entry.title
    return data


router = APIRouter()


# ============= CHRONIC CONDITIONS =============

# ============= ICD-11 CATALOG =============
#
# Reference data, not patient data: the whole WHO MMS linearization ships with
# the image (app/data/icd11_mms.tsv.gz), so this never makes an outbound call.
# Authenticated like the rest of the namespace, but deliberately NOT rate
# limited — a type-ahead fires a request per keystroke, and there is nothing to
# enumerate in a public classification.


@router.get("/icd11/search", response_model=ICD11SearchResult)
async def search_icd11_codes(
    q: str = Query(..., min_length=1, max_length=100, description="Code or free text"),
    chapter: str | None = Query(None, max_length=2),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
):
    """Search ICD-11 by code or description.

    Handles what patients actually type: lay terms ("ESRD", "G6PD", "heart
    attack"), US spellings of WHO's British titles ("hemodialysis"), and any
    word order.
    """
    matches = search_icd11(q, chapter=chapter, limit=limit)
    return ICD11SearchResult(
        query=q,
        results=[ICD11CodeOut(**vars(m)) for m in matches],
        total=len(matches),
        catalog_version=icd11_catalog_version(),
    )


@router.get("/icd11/chapters", response_model=List[ICD11Chapter])
async def list_icd11_chapters(
    current_user: User = Depends(get_current_user),
):
    """The 28 ICD-11 chapters, for browsing rather than searching."""
    return [ICD11Chapter(**c) for c in icd11_chapters()]


@router.get("/icd11/{code}", response_model=ICD11CodeOut)
async def get_icd11_code(
    code: str,
    current_user: User = Depends(get_current_user),
):
    """Resolve a single ICD-11 code to its official WHO title."""
    entry = get_icd11_by_code(code)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Unknown ICD-11 code: {code}")
    return ICD11CodeOut(**vars(entry))


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
        **_apply_icd11(condition.model_dump()),
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
    
    update_data = _apply_icd11(condition_update.model_dump(exclude_unset=True))
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
        .options(selectinload(TherapySession.intradialytic_readings),
                 selectinload(TherapySession.clinical_notes))
        .where(TherapySession.user_id == current_user.id)
    )
    
    if condition_id:
        query = query.where(TherapySession.condition_id == condition_id)
    if therapy_type:
        query = query.where(TherapySession.therapy_type == therapy_type)
    if status:
        query = query.where(TherapySession.status == status)
    if start_date:
        query = query.where(TherapySession.scheduled_date >= _naive_utc(start_date))
    if end_date:
        query = query.where(TherapySession.scheduled_date <= _naive_utc(end_date))
    
    query = query.offset(skip).limit(limit).order_by(TherapySession.scheduled_date.desc())
    result = await db.execute(query)
    sessions = result.scalars().unique().all()
    return sessions


@router.get("/flowsheet-drugs")
async def list_flowsheet_drugs(
    current_user: User = Depends(get_current_user),
):
    """Drugs commonly given DURING dialysis, for structured flowsheet capture.

    The field behind this held free text for 1,964 sessions — a decade of ESA
    and IV iron that no other screen could see, and that the HD flowsheet form
    could not even record (it had no drugs field at all; the data arrived by
    import). Offering the list is what makes structured entry possible without
    changing how the column is stored.
    """
    return {"drugs": COMMON_DIALYSIS_DRUGS}


@router.get("/therapy-sessions/defaults", response_model=FlowsheetDefaultsResponse)
async def get_flowsheet_defaults(
    for_date: date | None = Query(None, alias="date"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """What a new treatment form can pre-fill for this patient.

    Declared before `/therapy-sessions/{session_id}` so "defaults" is not parsed
    as an id.

    Everything returned is a *default*: the client shows it, shows the basis for
    it, and lets the patient change it. Nothing here is submitted on their
    behalf.
    """
    defaults = await fs_defaults.defaults_for(
        db, current_user.id, for_date or date.today()
    )
    return FlowsheetDefaultsResponse(
        target_weight_kg=defaults.target_weight_kg,
        target_weight_basis=defaults.target_weight_basis,
        target_weight_sample_size=defaults.target_weight_sample_size,
        access_type=defaults.access_type,
        access_kind=defaults.access_kind,
        disabled_fields=defaults.disabled_fields,
        carried_forward=defaults.carried_forward,
        carried_from_date=defaults.carried_from_date,
        notes=defaults.notes,
    )


@router.get("/therapy-sessions/{session_id}", response_model=TherapySessionResponse)
async def get_therapy_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific therapy session by ID with intradialytic readings."""
    query = (
        select(TherapySession)
        .options(selectinload(TherapySession.intradialytic_readings),
                 selectinload(TherapySession.clinical_notes))
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
    
    # Two treatments on one day are legitimate and are told apart by their
    # start and finish times. So a same-day session is a DUPLICATE only when it
    # starts and finishes at the same moment; otherwise it is a second
    # treatment, and of 150 same-day rows here 133 are populated and carry
    # readings. A blanket one-per-day rule would have rejected all of them.
    #
    # Separately, a save that creates the session and then fails on its readings
    # leaves an empty row behind and the user retries — 2026-08-15, id 2739
    # (23:20, every clinical field NULL, no readings) beside id 2740 (00:49, the
    # real data). That shell is recycled because it holds nothing to lose.
    #
    # NOTE the times are frequently absent in imported history: only 16 of those
    # 150 same-day rows carry a start time at all, because the flowsheet import
    # dropped them. The match below therefore requires a non-NULL start — two
    # NULL starts are unknown, not equal.
    payload = _naive_session_payload(session.model_dump())

    existing_shell = None
    existing_same_slot = None
    if session.scheduled_date is not None:
        same_day = (await db.execute(
            select(TherapySession).where(
                and_(
                    TherapySession.user_id == current_user.id,
                    TherapySession.therapy_type == session.therapy_type,
                    func.date(TherapySession.scheduled_date)
                        == _naive_utc(session.scheduled_date).date(),
                )
            )
        )).scalars().all()
        incoming_start = _naive_utc(session.actual_start_time)
        incoming_end = _naive_utc(session.actual_end_time)
        for candidate in same_day:
            # Same day AND same start/finish is the same treatment, resubmitted.
            if (incoming_start is not None
                    and candidate.actual_start_time == incoming_start
                    and candidate.actual_end_time == incoming_end):
                existing_same_slot = candidate
                break
            if not _is_empty_session(candidate) or candidate.flowsheet_status:
                continue
            # A shell with readings attached is not safe to recycle: the new
            # save's timepoints would merge into the old row's.
            has_readings = (await db.execute(
                select(func.count(IntradialyticReading.id))
                .where(IntradialyticReading.session_id == candidate.id)
            )).scalar() or 0
            if has_readings == 0:
                existing_shell = candidate
                break

    reuse = existing_same_slot or existing_shell
    if reuse is not None:
        logger.info(
            "Reusing therapy session %s for user %s (%s) instead of creating a "
            "duplicate for %s",
            reuse.id, current_user.id,
            "same start/finish" if existing_same_slot else "empty shell",
            session.scheduled_date,
        )
        for key, value in payload.items():
            setattr(reuse, key, value)
        db_session = reuse
    else:
        db_session = TherapySession(
            **payload,
            user_id=current_user.id
        )
        db.add(db_session)
    await db.commit()

    # Re-query with relationships eagerly loaded to avoid async lazy-load errors
    result = await db.execute(
        select(TherapySession)
        .options(selectinload(TherapySession.intradialytic_readings),
                 selectinload(TherapySession.clinical_notes))
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
    
    update_data = _naive_session_payload(session_update.model_dump(exclude_unset=True))
    old_status = db_session.status
    for field, value in update_data.items():
        setattr(db_session, field, value)
    
    await db.commit()

    # Re-query with relationships eagerly loaded
    result = await db.execute(
        select(TherapySession)
        .options(selectinload(TherapySession.intradialytic_readings),
                 selectinload(TherapySession.clinical_notes))
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
        query = query.where(ConditionMetric.measured_date >= _naive_utc(start_date))
    if end_date:
        query = query.where(ConditionMetric.measured_date <= _naive_utc(end_date))
    
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
    """Add an intradialytic reading to a therapy session.

    **`reading_time` is NOT a key.** An earlier version of this function treated
    it as one and upserted on (session_id, reading_time). That would have
    silently merged 1816 rows across 1267 sessions, because the flowsheet import
    never captured the clock time: 3664 readings — 22.6% of the table — carry
    `00:00:00`, and 1263 of the 1271 same-time collisions are at exactly that
    value. Session 757 holds two midnight rows reading 144/95 p102 and 140/88
    p111. Those are two observations with one lost timestamp, not one observation
    written twice, and collapsing them destroys a vital sign.

    Genuine duplication is a row that matches another in EVERY clinical column —
    2 rows in the whole database. That is the only signal safe to act on.
    """
    session_query = select(TherapySession).where(
        and_(TherapySession.id == session_id, TherapySession.user_id == current_user.id)
    )
    session_result = await db.execute(session_query)
    if not session_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Therapy session not found")

    fields = reading.model_dump(exclude={"session_id"})

    # An exact re-send — every clinical column equal — is a double submit or a
    # retry, and returning the existing row makes both harmless. Anything that
    # differs by even one value is a different observation and is inserted.
    siblings = (await db.execute(
        select(IntradialyticReading).where(IntradialyticReading.session_id == session_id)
    )).scalars().all()
    for existing in siblings:
        if all(getattr(existing, key, None) == value
               for key, value in fields.items() if key in _READING_CONTENT_FIELDS):
            return existing

    db_reading = IntradialyticReading(
        **fields,
        session_id=session_id,
        user_id=current_user.id,
    )
    db.add(db_reading)
    await db.commit()
    await db.refresh(db_reading)
    return db_reading


@router.put("/readings/{reading_id}", response_model=IntradialyticReadingResponse)
async def update_intradialytic_reading(
    reading_id: int,
    reading: IntradialyticReadingUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Edit a reading in place.

    Without this there was no way to change one: the editor loaded the grid,
    the user corrected a value, and saving POSTed it back as a NEW row — so
    every edit grew the flowsheet. The rows could not be deduplicated afterwards
    either, because `reading_time` is 00:00:00 on 22.6% of the table and cannot
    identify anything.
    """
    existing = (await db.execute(
        select(IntradialyticReading).where(
            and_(IntradialyticReading.id == reading_id,
                 IntradialyticReading.user_id == current_user.id)
        )
    )).scalar_one_or_none()
    if not existing:
        raise HTTPException(status_code=404, detail="Reading not found")

    for field, value in reading.model_dump(exclude_unset=True, exclude={"session_id"}).items():
        setattr(existing, field, value)
    await db.commit()
    await db.refresh(existing)
    return existing


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
        .options(selectinload(TherapySession.intradialytic_readings),
                 selectinload(TherapySession.clinical_notes))
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

    # `if s.value` drops 0 as well as NULL, and 0 mL removed is a real
    # measurement, not a missing one. On the reference record exactly one
    # session in the 90-day window has fluid_removed_ml = 0, and excluding it
    # reported 876 mL where the true mean is 850 — a 3% overstatement of
    # ultrafiltration, on the number a nephrologist dries a patient to. It also
    # made this screen disagree with the clinician's view of the same window.
    weights_pre = [s.pre_dialysis_weight_kg for s in sessions if s.pre_dialysis_weight_kg is not None]
    weights_post = [s.post_dialysis_weight_kg for s in sessions if s.post_dialysis_weight_kg is not None]
    fluids = [s.fluid_removed_ml for s in sessions if s.fluid_removed_ml is not None]
    durations = [s.duration_minutes for s in sessions if s.duration_minutes is not None]

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


#: Clinical columns of an intradialytic reading. Two rows are the same reading
#: only when ALL of these match — never on `reading_time` alone, which the
#: flowsheet import left as 00:00:00 on 22.6% of the table.
_READING_CONTENT_FIELDS = (
    "reading_time", "reading_number", "systolic_bp", "diastolic_bp", "pulse",
    "mean_arterial_pressure", "dialysate_rate", "dialysate_volume_remaining",
    "uf_rate", "uf_volume_removed", "blood_flow_rate", "arterial_pressure",
    "venous_pressure", "effluent_pressure", "access_state", "saline_amount",
    "remarks",
)

#: The fields that make a therapy session a record of a treatment. A row with
#: none of them is a shell left by a save that died before it finished.
_SESSION_CONTENT_FIELDS = (
    "pre_dialysis_weight_kg", "post_dialysis_weight_kg", "fluid_removed_ml",
    "duration_minutes", "actual_start_time", "actual_end_time",
    "pre_systolic_bp", "post_systolic_bp", "pre_heart_rate", "post_heart_rate",
    "blood_flow_rate", "total_uf_liters", "patient_notes", "complications",
)


def _is_empty_session(session: TherapySession) -> bool:
    """True when a session carries no clinical content at all."""
    return all(getattr(session, f, None) in (None, "") for f in _SESSION_CONTENT_FIELDS)


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
