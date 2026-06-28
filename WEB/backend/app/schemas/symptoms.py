"""Symptom log schemas (Basis collection domain: symptoms)."""

from datetime import date, datetime
from pydantic import BaseModel, Field


class SymptomLogCreate(BaseModel):
    log_date: date
    symptom_name: str = Field(..., min_length=1, max_length=255)
    body_part: str | None = None
    location_specific: str | None = None
    severity: int | None = Field(None, ge=1, le=10)
    duration_hours: float | None = None
    symptom_type: str | None = None
    quality: str | None = None
    onset: str | None = None
    pattern: str | None = None
    triggers: str | None = None
    relievers: str | None = None
    affects_function: bool | None = None
    interferes_sleep: bool | None = None
    interferes_work: bool | None = None
    self_treatment: str | None = None
    medications_taken: str | None = None
    sought_medical_care: bool | None = None
    other_symptoms: str | None = None
    notes: str | None = None


class SymptomLogUpdate(BaseModel):
    symptom_name: str | None = Field(None, min_length=1, max_length=255)
    body_part: str | None = None
    location_specific: str | None = None
    severity: int | None = Field(None, ge=1, le=10)
    duration_hours: float | None = None
    symptom_type: str | None = None
    quality: str | None = None
    onset: str | None = None
    pattern: str | None = None
    triggers: str | None = None
    relievers: str | None = None
    affects_function: bool | None = None
    interferes_sleep: bool | None = None
    interferes_work: bool | None = None
    self_treatment: str | None = None
    medications_taken: str | None = None
    sought_medical_care: bool | None = None
    other_symptoms: str | None = None
    notes: str | None = None


class SymptomLogResponse(BaseModel):
    id: int
    user_id: int
    log_date: date
    symptom_name: str
    body_part: str | None = None
    location_specific: str | None = None
    severity: int | None = None
    duration_hours: float | None = None
    symptom_type: str | None = None
    quality: str | None = None
    onset: str | None = None
    pattern: str | None = None
    triggers: str | None = None
    relievers: str | None = None
    affects_function: bool | None = None
    interferes_sleep: bool | None = None
    interferes_work: bool | None = None
    self_treatment: str | None = None
    medications_taken: str | None = None
    sought_medical_care: bool | None = None
    other_symptoms: str | None = None
    notes: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
