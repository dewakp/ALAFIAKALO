"""Lifestyle schemas."""

from datetime import date, datetime
from pydantic import BaseModel


class LifestyleEntryCreate(BaseModel):
    entry_date: date
    weight_kg: float | None = None
    height_cm: float | None = None
    bmi: float | None = None
    blood_pressure_systolic: int | None = None
    blood_pressure_diastolic: int | None = None
    resting_heart_rate: int | None = None
    body_temperature_c: float | None = None
    blood_oxygen_pct: float | None = None
    smoking_status: str | None = None
    alcohol_drinks: int | None = None
    caffeine_mg: float | None = None
    screen_time_minutes: int | None = None
    outdoor_time_minutes: int | None = None
    social_interactions: int | None = None
    notes: str | None = None


class LifestyleEntryUpdate(BaseModel):
    weight_kg: float | None = None
    height_cm: float | None = None
    bmi: float | None = None
    blood_pressure_systolic: int | None = None
    blood_pressure_diastolic: int | None = None
    resting_heart_rate: int | None = None
    body_temperature_c: float | None = None
    blood_oxygen_pct: float | None = None
    smoking_status: str | None = None
    alcohol_drinks: int | None = None
    caffeine_mg: float | None = None
    screen_time_minutes: int | None = None
    outdoor_time_minutes: int | None = None
    social_interactions: int | None = None
    notes: str | None = None


class LifestyleEntryResponse(BaseModel):
    id: int
    user_id: int
    entry_date: date
    weight_kg: float | None = None
    height_cm: float | None = None
    bmi: float | None = None
    blood_pressure_systolic: int | None = None
    blood_pressure_diastolic: int | None = None
    resting_heart_rate: int | None = None
    body_temperature_c: float | None = None
    blood_oxygen_pct: float | None = None
    smoking_status: str | None = None
    alcohol_drinks: int | None = None
    caffeine_mg: float | None = None
    screen_time_minutes: int | None = None
    outdoor_time_minutes: int | None = None
    social_interactions: int | None = None
    notes: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
