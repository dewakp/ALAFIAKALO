"""Fitness schemas."""

from datetime import date, datetime
from pydantic import BaseModel


class FitnessLogCreate(BaseModel):
    log_date: date
    activity_type: str
    duration_minutes: int | None = None
    distance_km: float | None = None
    calories_burned: float | None = None
    heart_rate_avg: int | None = None
    heart_rate_max: int | None = None
    steps: int | None = None
    sets: int | None = None
    reps: int | None = None
    weight_kg: float | None = None
    intensity: str | None = None
    notes: str | None = None


class FitnessLogUpdate(BaseModel):
    activity_type: str | None = None
    duration_minutes: int | None = None
    distance_km: float | None = None
    calories_burned: float | None = None
    heart_rate_avg: int | None = None
    heart_rate_max: int | None = None
    steps: int | None = None
    sets: int | None = None
    reps: int | None = None
    weight_kg: float | None = None
    intensity: str | None = None
    notes: str | None = None


class FitnessLogResponse(BaseModel):
    id: int
    user_id: int
    log_date: date
    activity_type: str
    duration_minutes: int | None = None
    distance_km: float | None = None
    calories_burned: float | None = None
    heart_rate_avg: int | None = None
    heart_rate_max: int | None = None
    steps: int | None = None
    sets: int | None = None
    reps: int | None = None
    weight_kg: float | None = None
    intensity: str | None = None
    notes: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
