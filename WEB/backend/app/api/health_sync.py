"""Health data sync API – one-way ingest from mobile health platforms.

Supports Apple HealthKit and Android Health Connect.  Every record is
fingerprinted by (user_id, platform, data_type, external_id) so duplicates
are rejected at the DB-constraint level.
"""

import json
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.health_sync import HealthSyncConnection, SyncedRecord
from app.models.fitness import FitnessLog
from app.models.mood import MoodEntry
from app.models.lifestyle import LifestyleEntry
from app.models.nutrition import NutritionLog
from app.schemas.health_sync import (
    SyncConnectionCreate, SyncConnectionResponse, SyncConnectionUpdate,
    SyncBatchRequest, SyncBatchResponse, SyncRecordResult,
    SyncStatusResponse,
)

router = APIRouter()


# ── Helpers ───────────────────────────────────────────────────────────

def _safe_int(v) -> int | None:
    if v is None:
        return None
    try:
        return int(round(float(v)))
    except (ValueError, TypeError):
        return None


def _safe_float(v) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _parse_date(v) -> "date | None":
    from datetime import date as _date
    if v is None:
        return None
    if isinstance(v, _date):
        return v
    if isinstance(v, datetime):
        return v.date()
    try:
        return _date.fromisoformat(str(v)[:10])
    except (ValueError, TypeError):
        return None


# ── Record Mappers ────────────────────────────────────────────────────

async def _map_workout(d: dict, user_id: int, db: AsyncSession) -> tuple[str, int]:
    """Map a workout / exercise record to fitness_logs."""
    log = FitnessLog(
        user_id=user_id,
        log_date=_parse_date(d.get("start_date") or d.get("date")) or datetime.now(timezone.utc).date(),
        activity_type=d.get("activity_type", d.get("workout_type", "other")),
        duration_minutes=_safe_int(d.get("duration_minutes")),
        distance_km=_safe_float(d.get("distance_km")),
        calories_burned=_safe_float(d.get("calories_burned", d.get("active_energy_burned"))),
        heart_rate_avg=_safe_int(d.get("heart_rate_avg")),
        heart_rate_max=_safe_int(d.get("heart_rate_max")),
        steps=_safe_int(d.get("steps")),
        intensity=d.get("intensity"),
        notes=d.get("notes", "Synced from health platform"),
    )
    db.add(log)
    await db.flush()
    return "fitness_logs", log.id


async def _map_steps(d: dict, user_id: int, db: AsyncSession) -> tuple[str, int]:
    """Map a daily step-count aggregate to fitness_logs."""
    log = FitnessLog(
        user_id=user_id,
        log_date=_parse_date(d.get("date") or d.get("start_date")) or datetime.now(timezone.utc).date(),
        activity_type="walking",
        steps=_safe_int(d.get("count", d.get("steps"))),
        distance_km=_safe_float(d.get("distance_km")),
        calories_burned=_safe_float(d.get("calories_burned")),
        notes="Step count synced from health platform",
    )
    db.add(log)
    await db.flush()
    return "fitness_logs", log.id


async def _map_heart_rate(d: dict, user_id: int, db: AsyncSession) -> tuple[str, int]:
    """Map a heart-rate sample to lifestyle_entries (resting HR)."""
    entry = LifestyleEntry(
        user_id=user_id,
        entry_date=_parse_date(d.get("date") or d.get("start_date")) or datetime.now(timezone.utc).date(),
        resting_heart_rate=_safe_int(d.get("bpm", d.get("value"))),
        notes="Heart rate synced from health platform",
    )
    db.add(entry)
    await db.flush()
    return "lifestyle_entries", entry.id


async def _map_sleep(d: dict, user_id: int, db: AsyncSession) -> tuple[str, int]:
    """Map a sleep analysis record to mood_entries (sleep fields)."""
    entry = MoodEntry(
        user_id=user_id,
        entry_date=_parse_date(d.get("date") or d.get("end_date") or d.get("start_date")) or datetime.now(timezone.utc).date(),
        mood_score=_safe_int(d.get("mood_score")) or 5,
        sleep_quality=_safe_int(d.get("sleep_quality")),
        sleep_hours=_safe_float(d.get("total_hours", d.get("duration_hours"))),
        notes="Sleep data synced from health platform",
    )
    db.add(entry)
    await db.flush()
    return "mood_entries", entry.id


async def _map_weight(d: dict, user_id: int, db: AsyncSession) -> tuple[str, int]:
    """Map a body-mass measurement to lifestyle_entries."""
    entry = LifestyleEntry(
        user_id=user_id,
        entry_date=_parse_date(d.get("date") or d.get("start_date")) or datetime.now(timezone.utc).date(),
        weight_kg=_safe_float(d.get("value_kg", d.get("value"))),
        bmi=_safe_float(d.get("bmi")),
        height_cm=_safe_float(d.get("height_cm")),
        notes="Weight synced from health platform",
    )
    db.add(entry)
    await db.flush()
    return "lifestyle_entries", entry.id


async def _map_blood_pressure(d: dict, user_id: int, db: AsyncSession) -> tuple[str, int]:
    """Map BP reading to lifestyle_entries."""
    entry = LifestyleEntry(
        user_id=user_id,
        entry_date=_parse_date(d.get("date") or d.get("start_date")) or datetime.now(timezone.utc).date(),
        blood_pressure_systolic=_safe_int(d.get("systolic")),
        blood_pressure_diastolic=_safe_int(d.get("diastolic")),
        notes="Blood pressure synced from health platform",
    )
    db.add(entry)
    await db.flush()
    return "lifestyle_entries", entry.id


async def _map_blood_oxygen(d: dict, user_id: int, db: AsyncSession) -> tuple[str, int]:
    """Map SpO2 reading to lifestyle_entries."""
    entry = LifestyleEntry(
        user_id=user_id,
        entry_date=_parse_date(d.get("date") or d.get("start_date")) or datetime.now(timezone.utc).date(),
        blood_oxygen_pct=_safe_float(d.get("percentage", d.get("value"))),
        notes="Blood oxygen synced from health platform",
    )
    db.add(entry)
    await db.flush()
    return "lifestyle_entries", entry.id


async def _map_body_temperature(d: dict, user_id: int, db: AsyncSession) -> tuple[str, int]:
    """Map temperature reading to lifestyle_entries."""
    entry = LifestyleEntry(
        user_id=user_id,
        entry_date=_parse_date(d.get("date") or d.get("start_date")) or datetime.now(timezone.utc).date(),
        body_temperature_c=_safe_float(d.get("value_celsius", d.get("value"))),
        notes="Body temperature synced from health platform",
    )
    db.add(entry)
    await db.flush()
    return "lifestyle_entries", entry.id


async def _map_nutrition(d: dict, user_id: int, db: AsyncSession) -> tuple[str, int]:
    """Map a nutrition record to nutrition_logs."""
    log = NutritionLog(
        user_id=user_id,
        log_date=_parse_date(d.get("date") or d.get("start_date")) or datetime.now(timezone.utc).date(),
        meal_type=d.get("meal_type", "snack"),
        food_name=d.get("food_name", "Health platform import"),
        calories=_safe_float(d.get("calories", d.get("energy_kcal"))),
        protein_g=_safe_float(d.get("protein_g")),
        carbs_g=_safe_float(d.get("carbs_g")),
        fat_g=_safe_float(d.get("fat_g")),
        fiber_g=_safe_float(d.get("fiber_g")),
        sugar_g=_safe_float(d.get("sugar_g")),
        sodium_mg=_safe_float(d.get("sodium_mg")),
        notes="Nutrition synced from health platform",
    )
    db.add(log)
    await db.flush()
    return "nutrition_logs", log.id


async def _map_mindfulness(d: dict, user_id: int, db: AsyncSession) -> tuple[str, int]:
    """Map a mindfulness / meditation session to mood_entries."""
    entry = MoodEntry(
        user_id=user_id,
        entry_date=_parse_date(d.get("date") or d.get("start_date")) or datetime.now(timezone.utc).date(),
        mood_score=_safe_int(d.get("mood_score")) or 6,
        energy_level=_safe_int(d.get("energy_level")),
        coping_strategies=d.get("session_type", "mindfulness"),
        notes=f"Mindfulness session ({d.get('duration_minutes', '?')} min) synced from health platform",
    )
    db.add(entry)
    await db.flush()
    return "mood_entries", entry.id


_MAPPERS = {
    "workout": _map_workout,
    "steps": _map_steps,
    "heart_rate": _map_heart_rate,
    "sleep": _map_sleep,
    "weight": _map_weight,
    "blood_pressure": _map_blood_pressure,
    "blood_oxygen": _map_blood_oxygen,
    "body_temperature": _map_body_temperature,
    "nutrition": _map_nutrition,
    "mindfulness": _map_mindfulness,
}


# ── Connection CRUD ───────────────────────────────────────────────────

@router.post("/connections", response_model=SyncConnectionResponse, status_code=201)
async def create_connection(
    body: SyncConnectionCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    existing = await db.execute(
        select(HealthSyncConnection).where(
            HealthSyncConnection.user_id == user.id,
            HealthSyncConnection.platform == body.platform,
        )
    )
    conn = existing.scalar_one_or_none()
    if conn:
        conn.is_active = True
        if body.enabled_data_types:
            conn.enabled_data_types = json.dumps(body.enabled_data_types)
        conn.updated_at = datetime.now(timezone.utc)
    else:
        conn = HealthSyncConnection(
            user_id=user.id,
            platform=body.platform,
            is_active=True,
            enabled_data_types=json.dumps(body.enabled_data_types) if body.enabled_data_types else None,
        )
        db.add(conn)
    await db.flush()

    resp = SyncConnectionResponse.model_validate(conn)
    if conn.enabled_data_types:
        resp.enabled_data_types = json.loads(conn.enabled_data_types)
    return resp


@router.get("/connections", response_model=list[SyncConnectionResponse])
async def list_connections(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(HealthSyncConnection).where(HealthSyncConnection.user_id == user.id)
    )
    conns = result.scalars().all()
    out = []
    for c in conns:
        r = SyncConnectionResponse.model_validate(c)
        if c.enabled_data_types:
            r.enabled_data_types = json.loads(c.enabled_data_types)
        out.append(r)
    return out


@router.patch("/connections/{platform}", response_model=SyncConnectionResponse)
async def update_connection(
    platform: str,
    body: SyncConnectionUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(HealthSyncConnection).where(
            HealthSyncConnection.user_id == user.id,
            HealthSyncConnection.platform == platform,
        )
    )
    conn = result.scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")

    if body.is_active is not None:
        conn.is_active = body.is_active
    if body.enabled_data_types is not None:
        conn.enabled_data_types = json.dumps(body.enabled_data_types)
    conn.updated_at = datetime.now(timezone.utc)
    await db.flush()

    resp = SyncConnectionResponse.model_validate(conn)
    if conn.enabled_data_types:
        resp.enabled_data_types = json.loads(conn.enabled_data_types)
    return resp


@router.delete("/connections/{platform}", status_code=204)
async def delete_connection(
    platform: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(HealthSyncConnection).where(
            HealthSyncConnection.user_id == user.id,
            HealthSyncConnection.platform == platform,
        )
    )
    conn = result.scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    await db.delete(conn)


# ── Batch Sync (Main Endpoint) ────────────────────────────────────────

@router.post("/ingest", response_model=SyncBatchResponse)
async def sync_ingest(
    body: SyncBatchRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Ingest a batch of health records from an external platform.
    
    Each record is deduplicated by (user_id, platform, data_type, external_id).
    Duplicates are silently skipped – never causing errors or data corruption.
    """
    # Verify connection exists and is active
    result = await db.execute(
        select(HealthSyncConnection).where(
            HealthSyncConnection.user_id == user.id,
            HealthSyncConnection.platform == body.platform,
        )
    )
    conn = result.scalar_one_or_none()
    if not conn or not conn.is_active:
        raise HTTPException(
            status_code=400,
            detail=f"No active {body.platform} connection. Create one first via POST /sync/connections"
        )

    # Pre-check: which external_ids already exist?  (batch dedup query)
    existing_ids_query = select(SyncedRecord.external_id).where(
        SyncedRecord.user_id == user.id,
        SyncedRecord.platform == body.platform,
        SyncedRecord.external_id.in_([r.external_id for r in body.records]),
    )
    existing_result = await db.execute(existing_ids_query)
    existing_ids = {row[0] for row in existing_result}

    results: list[SyncRecordResult] = []
    created_count = 0
    dup_count = 0
    error_count = 0

    for rec in body.records:
        # ── Dedup gate ──
        if rec.external_id in existing_ids:
            results.append(SyncRecordResult(
                external_id=rec.external_id, status="duplicate"
            ))
            dup_count += 1
            continue

        # ── Route to mapper ──
        mapper = _MAPPERS.get(rec.data_type)
        if not mapper:
            results.append(SyncRecordResult(
                external_id=rec.external_id, status="error",
                error=f"Unknown data_type: {rec.data_type}",
            ))
            error_count += 1
            continue

        try:
            table, record_id = await mapper(rec.data, user.id, db)

            # Record in dedup ledger
            synced = SyncedRecord(
                user_id=user.id,
                platform=body.platform,
                data_type=rec.data_type,
                external_id=rec.external_id,
                target_table=table,
                target_record_id=record_id,
                source_timestamp=rec.source_timestamp,
            )
            db.add(synced)
            await db.flush()

            existing_ids.add(rec.external_id)  # prevent intra-batch dupes
            results.append(SyncRecordResult(
                external_id=rec.external_id, status="created",
                target_table=table, target_record_id=record_id,
            ))
            created_count += 1
        except Exception as e:
            results.append(SyncRecordResult(
                external_id=rec.external_id, status="error",
                error=str(e),
            ))
            error_count += 1

    # Update connection metadata
    conn.last_sync_at = datetime.now(timezone.utc)
    conn.last_sync_status = "success" if error_count == 0 else ("partial" if created_count > 0 else "failed")
    conn.last_sync_records = created_count
    conn.last_sync_duplicates = dup_count
    conn.updated_at = datetime.now(timezone.utc)

    return SyncBatchResponse(
        total=len(body.records),
        created=created_count,
        duplicates=dup_count,
        errors=error_count,
        results=results,
    )


# ── Sync Status ───────────────────────────────────────────────────────

@router.get("/status/{platform}", response_model=SyncStatusResponse)
async def sync_status(
    platform: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(HealthSyncConnection).where(
            HealthSyncConnection.user_id == user.id,
            HealthSyncConnection.platform == platform,
        )
    )
    conn = result.scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")

    # Count totals by type
    count_q = await db.execute(
        select(SyncedRecord.data_type, func.count(SyncedRecord.id)).where(
            SyncedRecord.user_id == user.id,
            SyncedRecord.platform == platform,
        ).group_by(SyncedRecord.data_type)
    )
    by_type = {row[0]: row[1] for row in count_q}
    total = sum(by_type.values())

    return SyncStatusResponse(
        platform=platform,
        is_active=conn.is_active,
        last_sync_at=conn.last_sync_at,
        last_sync_status=conn.last_sync_status,
        last_sync_records=conn.last_sync_records,
        last_sync_duplicates=conn.last_sync_duplicates,
        total_synced_records=total,
        records_by_type=by_type,
    )
