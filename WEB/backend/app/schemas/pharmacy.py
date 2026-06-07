"""Pharmacy schemas – Prescription / Dispensing / Adherence / Schedule / Refill."""

from datetime import date, datetime
from pydantic import BaseModel


# ── Prescription ─────────────────────────────────────────────────────

class PrescriptionCreate(BaseModel):
    patient_id: int
    medication_name: str
    rxnorm_code: str | None = None
    dosage: str | None = None
    dosage_unit: str | None = None
    strength: str | None = None
    form: str | None = None
    route: str | None = None
    frequency: str | None = None
    duration_days: int | None = None
    quantity: int | None = None
    refills_authorized: int = 0
    diagnosis: str | None = None
    instructions: str | None = None
    pharmacy_notes: str | None = None
    substitution_allowed: bool = True
    daw_code: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    expiry_date: date | None = None
    is_controlled_substance: bool = False
    dea_schedule: str | None = None
    medication_id: int | None = None


class PrescriptionUpdate(BaseModel):
    status: str | None = None
    dosage: str | None = None
    dosage_unit: str | None = None
    strength: str | None = None
    frequency: str | None = None
    duration_days: int | None = None
    quantity: int | None = None
    refills_authorized: int | None = None
    instructions: str | None = None
    pharmacy_notes: str | None = None
    substitution_allowed: bool | None = None
    end_date: date | None = None
    expiry_date: date | None = None


class PrescriptionResponse(BaseModel):
    id: int
    patient_id: int
    prescriber_id: int
    medication_name: str
    rxnorm_code: str | None = None
    dosage: str | None = None
    dosage_unit: str | None = None
    strength: str | None = None
    form: str | None = None
    route: str | None = None
    frequency: str | None = None
    duration_days: int | None = None
    quantity: int | None = None
    refills_authorized: int
    refills_remaining: int
    diagnosis: str | None = None
    instructions: str | None = None
    pharmacy_notes: str | None = None
    substitution_allowed: bool
    daw_code: str | None = None
    prescribed_date: date
    expiry_date: date | None = None
    start_date: date | None = None
    end_date: date | None = None
    status: str
    is_controlled_substance: bool
    dea_schedule: str | None = None
    medication_id: int | None = None
    created_at: datetime
    updated_at: datetime

    # Enrichment fields
    patient_name: str | None = None
    prescriber_name: str | None = None
    dispense_count: int | None = None

    model_config = {"from_attributes": True}


# ── Dispense ─────────────────────────────────────────────────────────

class DispenseCreate(BaseModel):
    prescription_id: int
    quantity_dispensed: int | None = None
    days_supply: int | None = None
    ndc_code: str | None = None
    lot_number: str | None = None
    expiration_date: date | None = None
    manufacturer: str | None = None
    is_generic: bool = False
    drug_utilization_review: str | None = None
    clinical_notes: str | None = None
    counseling_provided: bool = False
    counseling_notes: str | None = None
    interactions_checked: bool = False
    interactions_found: str | None = None
    allergy_checked: bool = False
    allergy_alerts: str | None = None


class DispenseUpdate(BaseModel):
    status: str | None = None
    clinical_notes: str | None = None
    counseling_provided: bool | None = None
    counseling_notes: str | None = None
    interactions_checked: bool | None = None
    interactions_found: str | None = None
    allergy_checked: bool | None = None
    allergy_alerts: str | None = None


class DispenseResponse(BaseModel):
    id: int
    prescription_id: int
    pharmacist_id: int
    quantity_dispensed: int | None = None
    days_supply: int | None = None
    ndc_code: str | None = None
    lot_number: str | None = None
    expiration_date: date | None = None
    manufacturer: str | None = None
    is_generic: bool
    drug_utilization_review: str | None = None
    clinical_notes: str | None = None
    counseling_provided: bool
    counseling_notes: str | None = None
    interactions_checked: bool
    interactions_found: str | None = None
    allergy_checked: bool
    allergy_alerts: str | None = None
    status: str
    dispensed_at: datetime | None = None
    picked_up_at: datetime | None = None
    created_at: datetime

    # Enrichment fields
    pharmacist_name: str | None = None
    medication_name: str | None = None

    model_config = {"from_attributes": True}


# ── Adherence ────────────────────────────────────────────────────────

class AdherenceLogCreate(BaseModel):
    prescription_id: int
    scheduled_time: datetime
    actual_time: datetime | None = None
    status: str = "taken"
    dose_taken: str | None = None
    notes: str | None = None
    side_effects_reported: str | None = None
    mood_before: int | None = None
    mood_after: int | None = None
    pain_before: int | None = None
    pain_after: int | None = None
    symptom_change: str | None = None


class AdherenceLogResponse(BaseModel):
    id: int
    patient_id: int
    prescription_id: int
    scheduled_time: datetime
    actual_time: datetime | None = None
    status: str
    dose_taken: str | None = None
    notes: str | None = None
    side_effects_reported: str | None = None
    mood_before: int | None = None
    mood_after: int | None = None
    pain_before: int | None = None
    pain_after: int | None = None
    symptom_change: str | None = None
    created_at: datetime

    medication_name: str | None = None

    model_config = {"from_attributes": True}


class AdherenceReport(BaseModel):
    """Aggregated adherence metrics for a prescription or patient."""
    prescription_id: int | None = None
    patient_id: int
    medication_name: str | None = None
    total_scheduled: int = 0
    total_taken: int = 0
    total_missed: int = 0
    total_skipped: int = 0
    total_late: int = 0
    adherence_rate: float = 0.0
    avg_delay_minutes: float | None = None
    streak_current: int = 0
    streak_longest: int = 0
    common_side_effects: list[str] = []
    period_start: date | None = None
    period_end: date | None = None


# ── Schedule ─────────────────────────────────────────────────────────

class MedicationScheduleCreate(BaseModel):
    prescription_id: int
    time_of_day: str
    days_of_week: str | None = None
    dose_label: str | None = None
    is_active: bool = True
    reminder_minutes_before: int = 15


class MedicationScheduleUpdate(BaseModel):
    time_of_day: str | None = None
    days_of_week: str | None = None
    dose_label: str | None = None
    is_active: bool | None = None
    reminder_minutes_before: int | None = None


class MedicationScheduleResponse(BaseModel):
    id: int
    patient_id: int
    prescription_id: int
    time_of_day: str
    days_of_week: str | None = None
    dose_label: str | None = None
    is_active: bool
    reminder_minutes_before: int
    created_at: datetime

    medication_name: str | None = None

    model_config = {"from_attributes": True}


# ── Refill ───────────────────────────────────────────────────────────

class RefillRequestCreate(BaseModel):
    prescription_id: int
    quantity_requested: int | None = None
    notes: str | None = None


class RefillRequestUpdate(BaseModel):
    status: str | None = None
    denial_reason: str | None = None


class RefillRequestResponse(BaseModel):
    id: int
    prescription_id: int
    patient_id: int
    requested_by_id: int
    approved_by_id: int | None = None
    status: str
    quantity_requested: int | None = None
    notes: str | None = None
    denial_reason: str | None = None
    requested_at: datetime
    resolved_at: datetime | None = None

    medication_name: str | None = None

    model_config = {"from_attributes": True}


# ── Impact Analysis ──────────────────────────────────────────────────

class MedicationImpactReport(BaseModel):
    """Health impact analysis for a prescription."""
    prescription_id: int
    medication_name: str
    patient_id: int
    analysis_period_days: int
    # Adherence
    adherence_rate: float
    doses_taken: int
    doses_missed: int
    # Vitals changes
    vitals_before: dict | None = None
    vitals_after: dict | None = None
    vitals_trend: str | None = None
    # Mood impact
    avg_mood_before: float | None = None
    avg_mood_after: float | None = None
    mood_trend: str | None = None
    # Side effects
    reported_side_effects: list[str] = []
    side_effect_frequency: dict | None = None
    # Lab correlations
    lab_changes: list[dict] = []
    # Overall assessment
    effectiveness_score: float | None = None  # 0-10
    tolerability_score: float | None = None   # 0-10
    ai_summary: str | None = None
