from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, time


# Chronic Condition Schemas

class ChronicConditionBase(BaseModel):
    condition_name: str = Field(..., max_length=200)
    category: str
    icd10_code: Optional[str] = Field(None, max_length=20)
    severity: str
    diagnosis_date: Optional[datetime] = None
    diagnosed_by: Optional[str] = Field(None, max_length=200)
    diagnosing_facility: Optional[str] = Field(None, max_length=300)
    is_active: bool = True
    remission_date: Optional[datetime] = None
    stage: Optional[str] = Field(None, max_length=50)
    grade: Optional[str] = Field(None, max_length=50)
    current_treatment_plan: Optional[str] = None
    primary_physician: Optional[str] = Field(None, max_length=200)
    specialist_physician: Optional[str] = Field(None, max_length=200)
    monitoring_frequency: Optional[str] = Field(None, max_length=100)
    next_appointment: Optional[datetime] = None
    notes: Optional[str] = None
    symptoms: Optional[str] = None
    complications: Optional[str] = None


class ChronicConditionCreate(ChronicConditionBase):
    pass


class ChronicConditionUpdate(BaseModel):
    condition_name: Optional[str] = Field(None, max_length=200)
    category: Optional[str] = None
    icd10_code: Optional[str] = Field(None, max_length=20)
    severity: Optional[str] = None
    diagnosis_date: Optional[datetime] = None
    diagnosed_by: Optional[str] = Field(None, max_length=200)
    diagnosing_facility: Optional[str] = Field(None, max_length=300)
    is_active: Optional[bool] = None
    remission_date: Optional[datetime] = None
    stage: Optional[str] = Field(None, max_length=50)
    grade: Optional[str] = Field(None, max_length=50)
    current_treatment_plan: Optional[str] = None
    primary_physician: Optional[str] = Field(None, max_length=200)
    specialist_physician: Optional[str] = Field(None, max_length=200)
    monitoring_frequency: Optional[str] = Field(None, max_length=100)
    next_appointment: Optional[datetime] = None
    notes: Optional[str] = None
    symptoms: Optional[str] = None
    complications: Optional[str] = None


class ChronicConditionResponse(ChronicConditionBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Therapy Session Schemas

class TherapySessionBase(BaseModel):
    condition_id: Optional[int] = None
    therapy_type: str
    therapy_name: Optional[str] = Field(None, max_length=200)
    session_number: Optional[int] = None
    total_sessions_planned: Optional[int] = None
    scheduled_date: datetime
    actual_start_time: Optional[datetime] = None
    actual_end_time: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    status: str = "scheduled"
    facility_name: Optional[str] = Field(None, max_length=300)
    facility_address: Optional[str] = Field(None, max_length=500)
    attending_physician: Optional[str] = Field(None, max_length=200)
    attending_nurse: Optional[str] = Field(None, max_length=200)
    
    # Dialysis-specific
    dialysis_access_type: Optional[str] = Field(None, max_length=100)
    pre_dialysis_weight_kg: Optional[float] = None
    post_dialysis_weight_kg: Optional[float] = None
    fluid_removed_ml: Optional[float] = None
    blood_flow_rate: Optional[float] = None
    dialysate_flow_rate: Optional[float] = None
    
    # Enhanced Dialysis Fields
    dry_weight_kg: Optional[float] = None
    previous_post_weight_kg: Optional[float] = None
    fluid_to_remove_kg: Optional[float] = None
    flow_fraction: Optional[float] = None
    filtration_fraction: Optional[str] = Field(None, max_length=50)
    day_of_week: Optional[str] = Field(None, max_length=20)
    rn_reviewer: Optional[str] = Field(None, max_length=200)
    
    # Dialysate Prescription
    dialysate_volume_liters: Optional[float] = None
    dialysate_lactate_meq: Optional[float] = None
    dialysate_potassium_meq: Optional[float] = None
    sak_number: Optional[int] = None
    needle_gauge: Optional[str] = Field(None, max_length=20)
    needle_length: Optional[float] = None
    buttonhole_technique: Optional[bool] = None
    
    # Standing BP (Pre & Post)
    pre_standing_systolic_bp: Optional[int] = None
    pre_standing_diastolic_bp: Optional[int] = None
    pre_standing_heart_rate: Optional[int] = None
    post_standing_systolic_bp: Optional[int] = None
    post_standing_diastolic_bp: Optional[int] = None
    post_standing_heart_rate: Optional[int] = None
    
    # Equipment Tracking
    cartridge_lot: Optional[str] = Field(None, max_length=50)
    sak_lot: Optional[str] = Field(None, max_length=50)
    cycler_number: Optional[str] = Field(None, max_length=50)
    warmer_serial: Optional[str] = Field(None, max_length=50)
    control_panel_serial: Optional[str] = Field(None, max_length=50)
    
    # Pre-Treatment Symptom Checklist
    pre_shortness_of_breath: Optional[bool] = None
    pre_swelling: Optional[bool] = None
    pre_change_in_mobility: Optional[bool] = None
    pre_digestion_problems: Optional[bool] = None
    pre_hosp_er_since_last: Optional[bool] = None
    
    # Access Assessment
    access_thrill_bruit: Optional[bool] = None
    access_redness_drainage: Optional[bool] = None
    
    # Post-Treatment Totals
    total_dialysate_liters: Optional[float] = None
    total_uf_liters: Optional[float] = None
    total_blood_volume_processed: Optional[float] = None
    dialyzer_appearance: Optional[str] = Field(None, max_length=100)
    post_bleeding_stop_time: Optional[str] = Field(None, max_length=50)
    post_bruising: Optional[bool] = None
    post_infiltration: Optional[bool] = None
    post_shortness_of_breath: Optional[bool] = None
    post_swelling: Optional[bool] = None
    post_digestion_problems: Optional[bool] = None
    post_access_thrill_bruit: Optional[bool] = None
    
    # Machine Maintenance
    purification_pak_change: Optional[bool] = None
    air_filter_cleaned: Optional[bool] = None
    waste_line_bleach_disinfection: Optional[bool] = None
    sak_use_number: Optional[int] = None
    total_chloramine_level: Optional[float] = None
    alarm_test_completed: Optional[bool] = None
    
    # Lab Tubes
    lab_tubes_drawn: Optional[str] = None
    
    # Chemo/Infusion-specific
    drugs_administered: Optional[str] = None
    dosage: Optional[str] = Field(None, max_length=200)
    route_of_administration: Optional[str] = Field(None, max_length=100)
    
    # Radiation-specific
    radiation_dose_gy: Optional[float] = None
    treatment_area: Optional[str] = Field(None, max_length=200)
    
    # Vitals
    pre_systolic_bp: Optional[int] = None
    pre_diastolic_bp: Optional[int] = None
    post_systolic_bp: Optional[int] = None
    post_diastolic_bp: Optional[int] = None
    pre_heart_rate: Optional[int] = None
    post_heart_rate: Optional[int] = None
    pre_temperature: Optional[float] = None
    post_temperature: Optional[float] = None
    oxygen_saturation: Optional[int] = None
    
    # Outcomes
    side_effects: Optional[str] = None
    adverse_reactions: Optional[str] = None
    complications: Optional[str] = None
    patient_tolerance: Optional[str] = Field(None, max_length=50)
    # `clinical_notes` is NOT a field on the session — notes are their own rows
    # (POST /therapy-sessions/{id}/clinical-notes). Accepting it here fed a
    # string into a relationship and 500'd the create.
    patient_notes: Optional[str] = None
    next_session_scheduled: Optional[datetime] = None


class TherapySessionCreate(TherapySessionBase):
    pass


class TherapySessionUpdate(BaseModel):
    condition_id: Optional[int] = None
    therapy_type: Optional[str] = None
    therapy_name: Optional[str] = Field(None, max_length=200)
    session_number: Optional[int] = None
    total_sessions_planned: Optional[int] = None
    scheduled_date: Optional[datetime] = None
    actual_start_time: Optional[datetime] = None
    actual_end_time: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    status: Optional[str] = None
    facility_name: Optional[str] = Field(None, max_length=300)
    facility_address: Optional[str] = Field(None, max_length=500)
    attending_physician: Optional[str] = Field(None, max_length=200)
    attending_nurse: Optional[str] = Field(None, max_length=200)
    dialysis_access_type: Optional[str] = Field(None, max_length=100)
    pre_dialysis_weight_kg: Optional[float] = None
    post_dialysis_weight_kg: Optional[float] = None
    fluid_removed_ml: Optional[float] = None
    blood_flow_rate: Optional[float] = None
    dialysate_flow_rate: Optional[float] = None
    dry_weight_kg: Optional[float] = None
    previous_post_weight_kg: Optional[float] = None
    fluid_to_remove_kg: Optional[float] = None
    flow_fraction: Optional[float] = None
    filtration_fraction: Optional[str] = Field(None, max_length=50)
    day_of_week: Optional[str] = Field(None, max_length=20)
    rn_reviewer: Optional[str] = Field(None, max_length=200)
    dialysate_volume_liters: Optional[float] = None
    dialysate_lactate_meq: Optional[float] = None
    dialysate_potassium_meq: Optional[float] = None
    sak_number: Optional[int] = None
    needle_gauge: Optional[str] = Field(None, max_length=20)
    needle_length: Optional[float] = None
    buttonhole_technique: Optional[bool] = None
    pre_standing_systolic_bp: Optional[int] = None
    pre_standing_diastolic_bp: Optional[int] = None
    pre_standing_heart_rate: Optional[int] = None
    post_standing_systolic_bp: Optional[int] = None
    post_standing_diastolic_bp: Optional[int] = None
    post_standing_heart_rate: Optional[int] = None
    cartridge_lot: Optional[str] = Field(None, max_length=50)
    sak_lot: Optional[str] = Field(None, max_length=50)
    cycler_number: Optional[str] = Field(None, max_length=50)
    warmer_serial: Optional[str] = Field(None, max_length=50)
    control_panel_serial: Optional[str] = Field(None, max_length=50)
    pre_shortness_of_breath: Optional[bool] = None
    pre_swelling: Optional[bool] = None
    pre_change_in_mobility: Optional[bool] = None
    pre_digestion_problems: Optional[bool] = None
    pre_hosp_er_since_last: Optional[bool] = None
    access_thrill_bruit: Optional[bool] = None
    access_redness_drainage: Optional[bool] = None
    total_dialysate_liters: Optional[float] = None
    total_uf_liters: Optional[float] = None
    total_blood_volume_processed: Optional[float] = None
    dialyzer_appearance: Optional[str] = Field(None, max_length=100)
    post_bleeding_stop_time: Optional[str] = Field(None, max_length=50)
    post_bruising: Optional[bool] = None
    post_infiltration: Optional[bool] = None
    post_shortness_of_breath: Optional[bool] = None
    post_swelling: Optional[bool] = None
    post_digestion_problems: Optional[bool] = None
    post_access_thrill_bruit: Optional[bool] = None
    purification_pak_change: Optional[bool] = None
    air_filter_cleaned: Optional[bool] = None
    waste_line_bleach_disinfection: Optional[bool] = None
    sak_use_number: Optional[int] = None
    total_chloramine_level: Optional[float] = None
    alarm_test_completed: Optional[bool] = None
    lab_tubes_drawn: Optional[str] = None
    drugs_administered: Optional[str] = None
    dosage: Optional[str] = Field(None, max_length=200)
    route_of_administration: Optional[str] = Field(None, max_length=100)
    radiation_dose_gy: Optional[float] = None
    treatment_area: Optional[str] = Field(None, max_length=200)
    pre_systolic_bp: Optional[int] = None
    pre_diastolic_bp: Optional[int] = None
    post_systolic_bp: Optional[int] = None
    post_diastolic_bp: Optional[int] = None
    pre_heart_rate: Optional[int] = None
    post_heart_rate: Optional[int] = None
    pre_temperature: Optional[float] = None
    post_temperature: Optional[float] = None
    oxygen_saturation: Optional[int] = None
    side_effects: Optional[str] = None
    adverse_reactions: Optional[str] = None
    complications: Optional[str] = None
    patient_tolerance: Optional[str] = Field(None, max_length=50)
    # `clinical_notes` is NOT a field on the session — notes are their own rows
    # (POST /therapy-sessions/{id}/clinical-notes). Accepting it here fed a
    # string into a relationship and 500'd the create.
    patient_notes: Optional[str] = None
    next_session_scheduled: Optional[datetime] = None


class TherapySessionResponse(TherapySessionBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime
    intradialytic_readings: Optional[List["IntradialyticReadingResponse"]] = []
    clinical_notes: Optional[List["ClinicalNoteResponse"]] = []

    # Flowsheet lifecycle
    flowsheet_status: Optional[str] = None
    signature_image: Optional[str] = None
    signed_at: Optional[datetime] = None
    signed_by: Optional[int] = None
    countersigned_at: Optional[datetime] = None
    countersigned_by: Optional[int] = None
    reviewed_at: Optional[datetime] = None
    reviewed_by: Optional[int] = None
    payload_hash: Optional[str] = None

    class Config:
        from_attributes = True


# Intradialytic Reading Schemas

class IntradialyticReadingBase(BaseModel):
    reading_time: Optional[time] = None
    reading_number: Optional[int] = None
    systolic_bp: Optional[int] = None
    diastolic_bp: Optional[int] = None
    pulse: Optional[int] = None
    mean_arterial_pressure: Optional[float] = None
    dialysate_rate: Optional[float] = None
    dialysate_volume_remaining: Optional[float] = None
    uf_rate: Optional[float] = None
    uf_volume_removed: Optional[float] = None
    blood_flow_rate: Optional[float] = None
    arterial_pressure: Optional[float] = None
    venous_pressure: Optional[float] = None
    effluent_pressure: Optional[float] = None
    access_state: Optional[str] = Field(None, max_length=50)
    saline_amount: Optional[str] = Field(None, max_length=50)
    remarks: Optional[str] = None


class IntradialyticReadingCreate(IntradialyticReadingBase):
    session_id: int


class IntradialyticReadingUpdate(BaseModel):
    reading_time: Optional[time] = None
    reading_number: Optional[int] = None
    systolic_bp: Optional[int] = None
    diastolic_bp: Optional[int] = None
    pulse: Optional[int] = None
    mean_arterial_pressure: Optional[float] = None
    dialysate_rate: Optional[float] = None
    dialysate_volume_remaining: Optional[float] = None
    uf_rate: Optional[float] = None
    uf_volume_removed: Optional[float] = None
    blood_flow_rate: Optional[float] = None
    arterial_pressure: Optional[float] = None
    venous_pressure: Optional[float] = None
    effluent_pressure: Optional[float] = None
    access_state: Optional[str] = Field(None, max_length=50)
    saline_amount: Optional[str] = Field(None, max_length=50)
    remarks: Optional[str] = None


class IntradialyticReadingResponse(IntradialyticReadingBase):
    id: int
    session_id: int
    user_id: int
    created_at: datetime

    class Config:
        from_attributes = True


# Condition Metric Schemas

class ConditionMetricBase(BaseModel):
    condition_id: int
    metric_name: str = Field(..., max_length=200)
    metric_category: Optional[str] = Field(None, max_length=100)
    value: float
    unit: str = Field(..., max_length=50)
    reference_range_min: Optional[float] = None
    reference_range_max: Optional[float] = None
    reference_range_text: Optional[str] = Field(None, max_length=200)
    status: Optional[str] = Field(None, max_length=50)
    measured_date: datetime
    measured_by: Optional[str] = Field(None, max_length=200)
    test_method: Optional[str] = Field(None, max_length=200)
    clinical_interpretation: Optional[str] = None
    action_required: Optional[str] = Field(None, max_length=500)
    notes: Optional[str] = None


class ConditionMetricCreate(ConditionMetricBase):
    pass


class ConditionMetricUpdate(BaseModel):
    condition_id: Optional[int] = None
    metric_name: Optional[str] = Field(None, max_length=200)
    metric_category: Optional[str] = Field(None, max_length=100)
    value: Optional[float] = None
    unit: Optional[str] = Field(None, max_length=50)
    reference_range_min: Optional[float] = None
    reference_range_max: Optional[float] = None
    reference_range_text: Optional[str] = Field(None, max_length=200)
    status: Optional[str] = Field(None, max_length=50)
    measured_date: Optional[datetime] = None
    measured_by: Optional[str] = Field(None, max_length=200)
    test_method: Optional[str] = Field(None, max_length=200)
    clinical_interpretation: Optional[str] = None
    action_required: Optional[str] = Field(None, max_length=500)
    notes: Optional[str] = None


class ConditionMetricResponse(ConditionMetricBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============= CLINICAL NOTES =============

class ClinicalNoteCreate(BaseModel):
    note_type: str = Field("general", max_length=50)
    note_text: str = Field(..., min_length=1)


class ClinicalNoteResponse(BaseModel):
    id: int
    session_id: int
    author_id: int
    author_role: Optional[str] = None
    note_type: str
    note_text: str
    note_hash: str
    created_at: datetime

    class Config:
        from_attributes = True


# ============= FLOWSHEET WORKFLOW ACTIONS =============

class FlowsheetSignRequest(BaseModel):
    signature_image: str = Field(..., description="Base64-encoded PNG of digital signature")


class FlowsheetActionResponse(BaseModel):
    id: int
    flowsheet_status: str
    message: str
