"""Vitals schemas — standalone vital-signs data collection (Basis ground truth)."""

from datetime import date, datetime, time
from pydantic import BaseModel, Field


class VitalsLogCreate(BaseModel):
    log_date: date
    log_time: time | None = None
    weight_kg: float | None = Field(None, ge=0, le=500)
    height_cm: float | None = Field(None, ge=0, le=300)
    bmi: float | None = None
    blood_pressure_systolic: int | None = Field(None, ge=0, le=300)
    blood_pressure_diastolic: int | None = Field(None, ge=0, le=200)
    blood_pressure_position: str | None = None
    heart_rate_bpm: int | None = Field(None, ge=0, le=400)
    heart_rhythm: str | None = None
    body_temperature_c: float | None = Field(None, ge=20, le=45)
    respiratory_rate: int | None = Field(None, ge=0, le=80)
    blood_oxygen_pct: float | None = Field(None, ge=0, le=100)
    blood_glucose_mg_dl: float | None = Field(None, ge=0, le=1000)
    glucose_timing: str | None = None
    pain_level: int | None = Field(None, ge=0, le=10)
    notes: str | None = None


class VitalsLogUpdate(BaseModel):
    log_time: time | None = None
    weight_kg: float | None = Field(None, ge=0, le=500)
    height_cm: float | None = Field(None, ge=0, le=300)
    bmi: float | None = None
    blood_pressure_systolic: int | None = Field(None, ge=0, le=300)
    blood_pressure_diastolic: int | None = Field(None, ge=0, le=200)
    blood_pressure_position: str | None = None
    heart_rate_bpm: int | None = Field(None, ge=0, le=400)
    heart_rhythm: str | None = None
    body_temperature_c: float | None = Field(None, ge=20, le=45)
    respiratory_rate: int | None = Field(None, ge=0, le=80)
    blood_oxygen_pct: float | None = Field(None, ge=0, le=100)
    blood_glucose_mg_dl: float | None = Field(None, ge=0, le=1000)
    glucose_timing: str | None = None
    pain_level: int | None = Field(None, ge=0, le=10)
    notes: str | None = None


class VitalsLogResponse(BaseModel):
    id: int
    user_id: int
    log_date: date
    log_time: time | None = None
    weight_kg: float | None = None
    height_cm: float | None = None
    bmi: float | None = None
    blood_pressure_systolic: int | None = None
    blood_pressure_diastolic: int | None = None
    blood_pressure_position: str | None = None
    heart_rate_bpm: int | None = None
    heart_rhythm: str | None = None
    body_temperature_c: float | None = None
    respiratory_rate: int | None = None
    blood_oxygen_pct: float | None = None
    blood_glucose_mg_dl: float | None = None
    glucose_timing: str | None = None
    pain_level: int | None = None
    notes: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
