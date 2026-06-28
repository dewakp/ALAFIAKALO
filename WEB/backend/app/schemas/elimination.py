"""Elimination tracking schemas (bowel movements, urination, vomiting)."""

from datetime import date, datetime, time
from pydantic import BaseModel, Field


# ── Bowel Movements ───────────────────────────────────────────────────────────

class BowelMovementCreate(BaseModel):
    log_date: date
    log_time: time | None = None
    bristol_scale: int | None = Field(None, ge=1, le=7)
    color: str | None = None
    consistency: str | None = None
    size: str | None = None
    blood_present: bool | None = None
    mucus_present: bool | None = None
    undigested_food: bool | None = None
    pain_level: int | None = Field(None, ge=0, le=10)
    straining: bool | None = None
    urgency: bool | None = None
    duration_minutes: int | None = None
    location: str | None = None
    associated_symptoms: str | None = None
    notes: str | None = None


class BowelMovementUpdate(BaseModel):
    log_date: date | None = None
    log_time: time | None = None
    bristol_scale: int | None = Field(None, ge=1, le=7)
    color: str | None = None
    consistency: str | None = None
    size: str | None = None
    blood_present: bool | None = None
    mucus_present: bool | None = None
    undigested_food: bool | None = None
    pain_level: int | None = Field(None, ge=0, le=10)
    straining: bool | None = None
    urgency: bool | None = None
    duration_minutes: int | None = None
    location: str | None = None
    associated_symptoms: str | None = None
    notes: str | None = None


class BowelMovementResponse(BaseModel):
    id: int
    user_id: int
    log_date: date
    log_time: time | None = None
    bristol_scale: int | None = None
    color: str | None = None
    consistency: str | None = None
    size: str | None = None
    blood_present: bool | None = None
    mucus_present: bool | None = None
    undigested_food: bool | None = None
    pain_level: int | None = None
    straining: bool | None = None
    urgency: bool | None = None
    duration_minutes: int | None = None
    location: str | None = None
    associated_symptoms: str | None = None
    notes: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Urination Logs ────────────────────────────────────────────────────────────

class UrinationLogCreate(BaseModel):
    log_date: date
    log_time: time | None = None
    color: str | None = None
    clarity: str | None = None
    odor: str | None = None
    volume_ml: int | None = None
    stream_strength: str | None = None
    pain_level: int | None = Field(None, ge=0, le=10)
    burning_sensation: bool | None = None
    urgency: bool | None = None
    frequency_increased: bool | None = None
    blood_present: bool | None = None
    location: str | None = None
    nighttime: bool | None = None
    notes: str | None = None


class UrinationLogUpdate(BaseModel):
    log_date: date | None = None
    log_time: time | None = None
    color: str | None = None
    clarity: str | None = None
    odor: str | None = None
    volume_ml: int | None = None
    stream_strength: str | None = None
    pain_level: int | None = Field(None, ge=0, le=10)
    burning_sensation: bool | None = None
    urgency: bool | None = None
    frequency_increased: bool | None = None
    blood_present: bool | None = None
    location: str | None = None
    nighttime: bool | None = None
    notes: str | None = None


class UrinationLogResponse(BaseModel):
    id: int
    user_id: int
    log_date: date
    log_time: time | None = None
    color: str | None = None
    clarity: str | None = None
    odor: str | None = None
    volume_ml: int | None = None
    stream_strength: str | None = None
    pain_level: int | None = None
    burning_sensation: bool | None = None
    urgency: bool | None = None
    frequency_increased: bool | None = None
    blood_present: bool | None = None
    location: str | None = None
    nighttime: bool | None = None
    notes: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Vomiting Logs ─────────────────────────────────────────────────────────────

class VomitingLogCreate(BaseModel):
    log_date: date
    log_time: time | None = None
    volume: str | None = None
    color: str | None = None
    consistency: str | None = None
    contains_food: bool | None = None
    contains_bile: bool | None = None
    contains_blood: bool | None = None
    nausea_before: bool | None = None
    nausea_after: bool | None = None
    projectile: bool | None = None
    trigger: str | None = None
    time_since_last_meal_hours: float | None = None
    relief_after: bool | None = None
    fever: bool | None = None
    diarrhea: bool | None = None
    headache: bool | None = None
    dizziness: bool | None = None
    notes: str | None = None


class VomitingLogUpdate(BaseModel):
    log_date: date | None = None
    log_time: time | None = None
    volume: str | None = None
    color: str | None = None
    consistency: str | None = None
    contains_food: bool | None = None
    contains_bile: bool | None = None
    contains_blood: bool | None = None
    nausea_before: bool | None = None
    nausea_after: bool | None = None
    projectile: bool | None = None
    trigger: str | None = None
    time_since_last_meal_hours: float | None = None
    relief_after: bool | None = None
    fever: bool | None = None
    diarrhea: bool | None = None
    headache: bool | None = None
    dizziness: bool | None = None
    notes: str | None = None


class VomitingLogResponse(BaseModel):
    id: int
    user_id: int
    log_date: date
    log_time: time | None = None
    volume: str | None = None
    color: str | None = None
    consistency: str | None = None
    contains_food: bool | None = None
    contains_bile: bool | None = None
    contains_blood: bool | None = None
    nausea_before: bool | None = None
    nausea_after: bool | None = None
    projectile: bool | None = None
    trigger: str | None = None
    time_since_last_meal_hours: float | None = None
    relief_after: bool | None = None
    fever: bool | None = None
    diarrhea: bool | None = None
    headache: bool | None = None
    dizziness: bool | None = None
    notes: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Unified Elimination Entry (poop / urine / vomit) ──────────────────────────
# Backs the unified Elimination Log UI: one form + one timeline across all three
# event types. Each entry carries its `event_type` for collection AND display.

from typing import Literal

EVENT_TYPES = ("poop", "urine", "vomit")


class EliminationEntryCreate(BaseModel):
    event_type: Literal["poop", "urine", "vomit"]
    log_date: date
    log_time: time | None = None
    pre_event_weight_kg: float | None = None
    post_event_weight_kg: float | None = None
    description: str | None = None
    image_uri: str | None = None


class EliminationEntry(BaseModel):
    id: int
    event_type: str
    log_date: date
    log_time: time | None = None
    pre_event_weight_kg: float | None = None
    post_event_weight_kg: float | None = None
    description: str | None = None
    image_uri: str | None = None
    created_at: datetime
