"""Schemas for health data sync from external platforms."""

from datetime import datetime, date
from pydantic import BaseModel, Field
from typing import Optional


# ── Connection Management ─────────────────────────────────────────────

class SyncConnectionCreate(BaseModel):
    platform: str = Field(..., pattern="^(healthkit|health_connect)$")
    enabled_data_types: list[str] | None = None


class SyncConnectionResponse(BaseModel):
    id: int
    platform: str
    is_active: bool
    enabled_data_types: list[str] | None = None
    last_sync_at: datetime | None = None
    last_sync_status: str | None = None
    last_sync_records: int | None = None
    last_sync_duplicates: int | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SyncConnectionUpdate(BaseModel):
    is_active: bool | None = None
    enabled_data_types: list[str] | None = None


# ── Batch Sync Payload ────────────────────────────────────────────────

class SyncRecord(BaseModel):
    """A single record coming from the external health platform."""
    external_id: str = Field(..., description="Unique ID from the source platform (UUID)")
    data_type: str = Field(..., description="steps | heart_rate | workout | sleep | weight | blood_pressure | blood_oxygen | body_temperature | nutrition | mindfulness | menstrual_cycle")
    source_timestamp: datetime
    data: dict = Field(..., description="Payload varies by data_type")


class SyncBatchRequest(BaseModel):
    """Batch of records to sync in a single request."""
    platform: str = Field(..., pattern="^(healthkit|health_connect)$")
    records: list[SyncRecord] = Field(..., min_length=1, max_length=500)


class SyncRecordResult(BaseModel):
    external_id: str
    status: str  # created | duplicate | error
    target_table: str | None = None
    target_record_id: int | None = None
    error: str | None = None


class SyncBatchResponse(BaseModel):
    total: int
    created: int
    duplicates: int
    errors: int
    results: list[SyncRecordResult]


# ── Sync Status ───────────────────────────────────────────────────────

class SyncStatusResponse(BaseModel):
    platform: str
    is_active: bool
    last_sync_at: datetime | None = None
    last_sync_status: str | None = None
    last_sync_records: int | None = None
    last_sync_duplicates: int | None = None
    total_synced_records: int
    records_by_type: dict[str, int]
