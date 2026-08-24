"""Medication schemas."""

from datetime import date, datetime, time
from typing import Any
from pydantic import BaseModel, field_validator


def _blank_dates_are_null(cls, value):
    """Treat an empty string as "no date".

    HTML date inputs submit `""` when cleared, and `date | None` rejects that
    with "Input should be a valid date or datetime, input is too short" — which
    is what a user saw on every attempt to save a prescription with no end date.
    The blank is the browser's representation of null, not a malformed date, and
    all three clients can send it, so it is normalised here rather than in one UI.
    """
    if isinstance(value, str) and not value.strip():
        return None
    return value


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

    _blank_dates = field_validator(*['start_date', 'end_date'], mode="before")(_blank_dates_are_null)


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

    _blank_dates = field_validator(*['start_date', 'end_date'], mode="before")(_blank_dates_are_null)


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
    source: str | None = None    # None = entered manually; else importing portal/org
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Medication Dose Log schemas ───────────────────────────────────────────────


class MedicationDoseLogCreate(BaseModel):
    # Set true to record a dose the plausibility guard flagged (see
    # services/med_dose_validation). Deliberately explicit: the guard fires only
    # on provable contradictions — a unit the drug is not measured in, a dose
    # above a sourced ceiling, or a name that contains a different drug — so
    # overriding one is a decision, not a default.
    acknowledge_unusual: bool = False
    medication_name: str
    log_date: date
    log_time: time | None = None
    dose_amount: float
    dose_unit: str
    medication_id: int | None = None     # FK to medications table (optional)
    pre_systolic_bp: int | None = None
    pre_diastolic_bp: int | None = None
    pre_heart_rate: int | None = None
    post_systolic_bp: int | None = None
    post_diastolic_bp: int | None = None
    post_heart_rate: int | None = None
    pre_temperature_c: float | None = None
    post_temperature_c: float | None = None
    notes: str | None = None


class MedicationDoseLogResponse(BaseModel):
    id: int
    user_id: int
    medication_id: int | None = None
    med_profile_id: int | None = None
    medication_name: str
    log_date: date
    log_time: time | None = None
    dose_amount: float
    dose_unit: str
    pre_systolic_bp: int | None = None
    pre_diastolic_bp: int | None = None
    pre_heart_rate: int | None = None
    post_systolic_bp: int | None = None
    post_diastolic_bp: int | None = None
    post_heart_rate: int | None = None
    pre_temperature_c: float | None = None
    post_temperature_c: float | None = None
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


class IntakeIntentRequest(BaseModel):
    """Free text such as "I take Calcitriol" or "took 2 tablets of calcium carbonate"."""
    text: str
