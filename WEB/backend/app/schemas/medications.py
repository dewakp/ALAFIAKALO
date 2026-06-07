"""Medication schemas."""

from datetime import date, datetime
from typing import Any
from pydantic import BaseModel


class MedicationCreate(BaseModel):
    name: str
    rxnorm_code: str | None = None
    dosage: str | None = None
    dosage_unit: str | None = None
    frequency: str | None = None
    route: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    prescribing_doctor: str | None = None
    reason: str | None = None
    side_effects: str | None = None
    is_active: bool = True
    notes: str | None = None


class MedicationUpdate(BaseModel):
    name: str | None = None
    rxnorm_code: str | None = None
    dosage: str | None = None
    dosage_unit: str | None = None
    frequency: str | None = None
    route: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    prescribing_doctor: str | None = None
    reason: str | None = None
    side_effects: str | None = None
    is_active: bool | None = None
    notes: str | None = None


class MedicationResponse(BaseModel):
    id: int
    user_id: int
    name: str
    rxnorm_code: str | None = None
    dosage: str | None = None
    dosage_unit: str | None = None
    frequency: str | None = None
    route: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    prescribing_doctor: str | None = None
    reason: str | None = None
    side_effects: str | None = None
    is_active: bool
    notes: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Medication Dose Log schemas ───────────────────────────────────────────────


class MedicationDoseLogCreate(BaseModel):
    medication_name: str
    log_date: date
    dose_amount: float
    dose_unit: str
    medication_id: int | None = None     # FK to medications table (optional)
    notes: str | None = None


class MedicationDoseLogResponse(BaseModel):
    id: int
    user_id: int
    medication_id: int | None = None
    med_profile_id: int | None = None
    medication_name: str
    log_date: date
    dose_amount: float
    dose_unit: str
    nutrients_contributed: dict[str, Any] | None = None
    nutrients_resolved: bool
    notes: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Med → Nutrient profile lookup schema ─────────────────────────────────────


class MedNutrientLookupResponse(BaseModel):
    profile_id: int | None = None
    med_name_resolved: str
    dose_unit_canonical: str | None = None
    nutrients_per_dose_unit: dict[str, Any]
    brand_names: str | None = None
    active_ingredient: str | None = None
    source: str
