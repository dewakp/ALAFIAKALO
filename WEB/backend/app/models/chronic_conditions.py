from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Date, Time, ForeignKey, Text, Enum as SQLEnum
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from app.core.database import Base


class ConditionCategory(str, enum.Enum):
    """Categories of chronic conditions"""
    CANCER = "cancer"
    RENAL = "renal"
    DIABETES = "diabetes"
    BLOOD_DISORDER = "blood_disorder"
    CARDIOVASCULAR = "cardiovascular"
    RESPIRATORY = "respiratory"
    AUTOIMMUNE = "autoimmune"
    NEUROLOGICAL = "neurological"
    ENDOCRINE = "endocrine"
    OTHER = "other"


class ConditionSeverity(str, enum.Enum):
    """Severity levels for chronic conditions"""
    MILD = "mild"
    MODERATE = "moderate"
    SEVERE = "severe"
    CRITICAL = "critical"
    REMISSION = "remission"


class TherapyType(str, enum.Enum):
    """Types of therapy sessions"""
    DIALYSIS = "dialysis"
    HEMODIALYSIS = "hemodialysis"
    PERITONEAL_DIALYSIS = "peritoneal_dialysis"
    CHEMOTHERAPY = "chemotherapy"
    RADIATION_THERAPY = "radiation_therapy"
    IMMUNOTHERAPY = "immunotherapy"
    TARGETED_THERAPY = "targeted_therapy"
    HORMONE_THERAPY = "hormone_therapy"
    INFUSION_THERAPY = "infusion_therapy"
    PHYSICAL_THERAPY = "physical_therapy"
    OCCUPATIONAL_THERAPY = "occupational_therapy"
    BLOOD_TRANSFUSION = "blood_transfusion"
    PHOTOTHERAPY = "phototherapy"
    OTHER = "other"


class TherapyStatus(str, enum.Enum):
    """Status of therapy sessions"""
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    MISSED = "missed"
    RESCHEDULED = "rescheduled"


class FlowsheetStatus(str, enum.Enum):
    """Flowsheet submission lifecycle (mirrors FLOWSHEET portal).

    Progression: draft → submitted → signed → countersigned → reviewed → locked
    """
    DRAFT = "draft"
    SUBMITTED = "submitted"
    SIGNED = "signed"
    COUNTERSIGNED = "countersigned"
    REVIEWED = "reviewed"
    LOCKED = "locked"


class ChronicCondition(Base):
    """
    Model for tracking chronic health conditions and diseases.
    Supports cancers, renal diseases, diabetes, G6PD deficiency, etc.
    """
    __tablename__ = "chronic_conditions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Condition Details
    condition_name = Column(String(200), nullable=False)  # e.g., "Type 2 Diabetes", "Chronic Kidney Disease Stage 3"
    category = Column(SQLEnum(ConditionCategory), nullable=False, index=True)
    icd10_code = Column(String(20), nullable=True)  # ICD-10 diagnosis code
    severity = Column(SQLEnum(ConditionSeverity), nullable=False)
    
    # Diagnosis Information
    diagnosis_date = Column(DateTime, nullable=True)
    diagnosed_by = Column(String(200), nullable=True)  # Doctor's name
    diagnosing_facility = Column(String(300), nullable=True)
    
    # Status
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    remission_date = Column(DateTime, nullable=True)
    
    # Stage/Classification (for cancers and other staged conditions)
    stage = Column(String(50), nullable=True)  # e.g., "Stage IIIA", "ESRD", "Uncontrolled"
    grade = Column(String(50), nullable=True)  # e.g., "Grade 2", "Well-differentiated"
    
    # Treatment Plan
    current_treatment_plan = Column(Text, nullable=True)
    primary_physician = Column(String(200), nullable=True)
    specialist_physician = Column(String(200), nullable=True)
    
    # Monitoring
    monitoring_frequency = Column(String(100), nullable=True)  # e.g., "Monthly", "Every 3 months"
    next_appointment = Column(DateTime, nullable=True)
    
    # Notes and History
    notes = Column(Text, nullable=True)
    symptoms = Column(Text, nullable=True)  # JSON or comma-separated
    complications = Column(Text, nullable=True)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    user = relationship("User", back_populates="chronic_conditions")
    therapy_sessions = relationship("TherapySession", back_populates="condition", cascade="all, delete-orphan")
    condition_metrics = relationship("ConditionMetric", back_populates="condition", cascade="all, delete-orphan")


class TherapySession(Base):
    """
    Model for tracking therapy sessions (dialysis, chemo, radiation, etc.)
    """
    __tablename__ = "therapy_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    condition_id = Column(Integer, ForeignKey("chronic_conditions.id", ondelete="CASCADE"), nullable=True, index=True)
    
    # Session Type and Details
    therapy_type = Column(SQLEnum(TherapyType), nullable=False, index=True)
    therapy_name = Column(String(200), nullable=True)  # Specific name, e.g., "Cisplatin + Etoposide Protocol"
    session_number = Column(Integer, nullable=True)  # e.g., "Session 3 of 12"
    total_sessions_planned = Column(Integer, nullable=True)
    
    # Scheduling
    scheduled_date = Column(DateTime, nullable=False, index=True)
    actual_start_time = Column(DateTime, nullable=True)
    actual_end_time = Column(DateTime, nullable=True)
    duration_minutes = Column(Integer, nullable=True)
    status = Column(SQLEnum(TherapyStatus), nullable=False, default=TherapyStatus.SCHEDULED, index=True)
    
    # Location and Provider
    facility_name = Column(String(300), nullable=True)
    facility_address = Column(String(500), nullable=True)
    attending_physician = Column(String(200), nullable=True)
    attending_nurse = Column(String(200), nullable=True)
    
    # Treatment Details (flexible for different therapy types)
    # For Dialysis
    dialysis_access_type = Column(String(100), nullable=True)  # "AV Fistula", "Central Catheter", "Peritoneal Catheter"
    pre_dialysis_weight_kg = Column(Float, nullable=True)
    post_dialysis_weight_kg = Column(Float, nullable=True)
    fluid_removed_ml = Column(Float, nullable=True)
    blood_flow_rate = Column(Float, nullable=True)  # ml/min
    dialysate_flow_rate = Column(Float, nullable=True)  # ml/min
    
    # Enhanced Dialysis Fields (from DaVita Home HHD Flowsheet)
    dry_weight_kg = Column(Float, nullable=True)  # Target dry weight
    previous_post_weight_kg = Column(Float, nullable=True)  # Previous session post weight
    fluid_to_remove_kg = Column(Float, nullable=True)  # Target fluid removal
    flow_fraction = Column(Float, nullable=True)  # Flow fraction percentage
    filtration_fraction = Column(String(50), nullable=True)  # e.g., "48% 40%"
    day_of_week = Column(String(20), nullable=True)
    rn_reviewer = Column(String(200), nullable=True)
    
    # Dialysate Prescription
    dialysate_volume_liters = Column(Float, nullable=True)  # Total volume ordered (e.g., 30 L)
    dialysate_lactate_meq = Column(Float, nullable=True)  # Lactate concentration (e.g., 45 mEq)
    dialysate_potassium_meq = Column(Float, nullable=True)  # K+ concentration (e.g., 1.0 mEq)
    sak_number = Column(Integer, nullable=True)  # SAK filter number
    needle_gauge = Column(String(20), nullable=True)  # e.g., "17g", "16g"
    needle_length = Column(Float, nullable=True)  # in inches
    buttonhole_technique = Column(Boolean, nullable=True)  # Buttonhole needling technique
    
    # Standing BP (Pre & Post)
    pre_standing_systolic_bp = Column(Integer, nullable=True)
    pre_standing_diastolic_bp = Column(Integer, nullable=True)
    pre_standing_heart_rate = Column(Integer, nullable=True)
    post_standing_systolic_bp = Column(Integer, nullable=True)
    post_standing_diastolic_bp = Column(Integer, nullable=True)
    post_standing_heart_rate = Column(Integer, nullable=True)
    
    # Equipment Tracking
    cartridge_lot = Column(String(50), nullable=True)
    sak_lot = Column(String(50), nullable=True)
    cycler_number = Column(String(50), nullable=True)
    warmer_serial = Column(String(50), nullable=True)
    control_panel_serial = Column(String(50), nullable=True)
    
    # Pre-Treatment Symptom Checklist
    pre_shortness_of_breath = Column(Boolean, nullable=True)
    pre_swelling = Column(Boolean, nullable=True)
    pre_change_in_mobility = Column(Boolean, nullable=True)
    pre_digestion_problems = Column(Boolean, nullable=True)
    pre_hosp_er_since_last = Column(Boolean, nullable=True)  # Hospitalization/ER since last tx
    
    # Access Assessment (Pre & Post)
    access_thrill_bruit = Column(Boolean, nullable=True)  # Fistula/Graft thrill & bruit
    access_redness_drainage = Column(Boolean, nullable=True)  # Access redness/drainage/swelling
    
    # Post-Treatment Totals
    total_dialysate_liters = Column(Float, nullable=True)  # Total dialysate used
    total_uf_liters = Column(Float, nullable=True)  # Total ultrafiltration volume
    total_blood_volume_processed = Column(Float, nullable=True)  # Total BVP
    dialyzer_appearance = Column(String(100), nullable=True)  # e.g., "Streaked", "Clear", "Clotted"
    post_bleeding_stop_time = Column(String(50), nullable=True)  # e.g., "4 mins"
    post_bruising = Column(Boolean, nullable=True)
    post_infiltration = Column(Boolean, nullable=True)
    post_shortness_of_breath = Column(Boolean, nullable=True)
    post_swelling = Column(Boolean, nullable=True)
    post_digestion_problems = Column(Boolean, nullable=True)
    post_access_thrill_bruit = Column(Boolean, nullable=True)
    
    # Machine Maintenance
    purification_pak_change = Column(Boolean, nullable=True)
    air_filter_cleaned = Column(Boolean, nullable=True)
    waste_line_bleach_disinfection = Column(Boolean, nullable=True)
    sak_use_number = Column(Integer, nullable=True)  # SAK usage count
    total_chloramine_level = Column(Float, nullable=True)
    alarm_test_completed = Column(Boolean, nullable=True)
    
    # Lab Tubes Drawn This Session
    lab_tubes_drawn = Column(Text, nullable=True)  # e.g., "SST, Green, Lavender, Dark Blue"
    
    # For Chemotherapy/Infusions
    drugs_administered = Column(Text, nullable=True)  # JSON or comma-separated list
    dosage = Column(String(200), nullable=True)
    route_of_administration = Column(String(100), nullable=True)  # IV, Oral, Subcutaneous, etc.
    
    # For Radiation Therapy
    radiation_dose_gy = Column(Float, nullable=True)  # Gray units
    treatment_area = Column(String(200), nullable=True)
    
    # Vitals During Session
    pre_systolic_bp = Column(Integer, nullable=True)
    pre_diastolic_bp = Column(Integer, nullable=True)
    post_systolic_bp = Column(Integer, nullable=True)
    post_diastolic_bp = Column(Integer, nullable=True)
    pre_heart_rate = Column(Integer, nullable=True)
    post_heart_rate = Column(Integer, nullable=True)
    pre_temperature = Column(Float, nullable=True)
    post_temperature = Column(Float, nullable=True)
    oxygen_saturation = Column(Integer, nullable=True)
    
    # Side Effects and Complications
    side_effects = Column(Text, nullable=True)  # Nausea, fatigue, pain, etc.
    adverse_reactions = Column(Text, nullable=True)
    complications = Column(Text, nullable=True)
    
    # Assessment and Notes
    patient_tolerance = Column(String(50), nullable=True)  # Good, Fair, Poor
    # NOTE: there is no `clinical_notes` COLUMN. Notes are rows in the
    # `clinical_notes` table (relationship below) — this class previously
    # declared both, and the relationship silently shadowed the column, so
    # passing a string for it raised "Incompatible collection type: None is not
    # list-like" and 500'd every session create. The column was never migrated;
    # the free-text field that does exist on this table is `patient_notes`.
    patient_notes = Column(Text, nullable=True)
    
    # Next Session
    next_session_scheduled = Column(DateTime, nullable=True)

    # ── Flowsheet Submission Lifecycle (aligned with FLOWSHEET portal) ──
    flowsheet_status = Column(
        SQLEnum(FlowsheetStatus), nullable=True, default=None, index=True,
        comment="draft→submitted→signed→countersigned→reviewed→locked",
    )
    signature_image = Column(Text, nullable=True)  # base64-encoded PNG digital signature
    signed_at = Column(DateTime, nullable=True)
    signed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    countersigned_at = Column(DateTime, nullable=True)
    countersigned_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    payload_hash = Column(String(128), nullable=True)  # SHA-512 hash of signed fields

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    user = relationship("User", back_populates="therapy_sessions", foreign_keys=[user_id])
    condition = relationship("ChronicCondition", back_populates="therapy_sessions")
    intradialytic_readings = relationship("IntradialyticReading", back_populates="session", cascade="all, delete-orphan", order_by="IntradialyticReading.reading_time")
    clinical_notes = relationship("ClinicalNote", back_populates="session", cascade="all, delete-orphan", order_by="ClinicalNote.created_at")


class IntradialyticReading(Base):
    """
    Time-series monitoring data recorded during hemodialysis sessions.
    Captures vitals and machine parameters every 15-30 minutes.
    Based on DaVita Home HHD Flowsheet format.
    """
    __tablename__ = "intradialytic_readings"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("therapy_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Timestamp
    reading_time = Column(Time, nullable=False)  # Time of reading during session
    reading_number = Column(Integer, nullable=True)  # Sequential reading number
    
    # Blood Pressure & Heart Rate
    systolic_bp = Column(Integer, nullable=True)
    diastolic_bp = Column(Integer, nullable=True)
    pulse = Column(Integer, nullable=True)
    mean_arterial_pressure = Column(Float, nullable=True)  # MAP = (SYS + 2*DIA) / 3
    
    # Dialysate Parameters
    dialysate_rate = Column(Float, nullable=True)  # mL/min or L/hr
    dialysate_volume_remaining = Column(Float, nullable=True)  # Liters remaining
    
    # Ultrafiltration (Fluid Removal)
    uf_rate = Column(Float, nullable=True)  # L/hr or mL/hr
    uf_volume_removed = Column(Float, nullable=True)  # Cumulative liters removed
    
    # Blood Circuit Pressures
    blood_flow_rate = Column(Float, nullable=True)  # mL/min
    arterial_pressure = Column(Float, nullable=True)  # mmHg
    venous_pressure = Column(Float, nullable=True)  # mmHg
    effluent_pressure = Column(Float, nullable=True)  # mmHg
    
    # Access & Interventions
    access_state = Column(String(50), nullable=True)  # "ok", "needs attention"
    saline_amount = Column(String(50), nullable=True)  # e.g., "100 mL", "100 ml"
    
    # Remarks
    remarks = Column(Text, nullable=True)  # Free-text notes for this reading
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    session = relationship("TherapySession", back_populates="intradialytic_readings")
    user = relationship("User")


class ConditionMetric(Base):
    """
    Model for tracking condition-specific metrics over time.
    Examples: HbA1c for diabetes, GFR for renal disease, tumor markers for cancer, etc.
    """
    __tablename__ = "condition_metrics"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    condition_id = Column(Integer, ForeignKey("chronic_conditions.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Metric Details
    metric_name = Column(String(200), nullable=False, index=True)  # e.g., "HbA1c", "eGFR", "PSA", "CA-125"
    metric_category = Column(String(100), nullable=True)  # Blood test, Imaging, Vital sign, etc.
    
    # Value
    value = Column(Float, nullable=False)
    unit = Column(String(50), nullable=False)  # %, mg/dL, mL/min/1.73m², ng/mL, etc.
    
    # Reference and Status
    reference_range_min = Column(Float, nullable=True)
    reference_range_max = Column(Float, nullable=True)
    reference_range_text = Column(String(200), nullable=True)  # e.g., "<5.7% (Normal)", "60-89 (Mild decrease)"
    status = Column(String(50), nullable=True)  # Normal, Low, High, Critical, Improved, Worsened
    
    # Context
    measured_date = Column(DateTime, nullable=False, index=True)
    measured_by = Column(String(200), nullable=True)  # Lab name or physician
    test_method = Column(String(200), nullable=True)
    
    # Clinical Significance
    clinical_interpretation = Column(Text, nullable=True)
    action_required = Column(String(500), nullable=True)
    
    # Notes
    notes = Column(Text, nullable=True)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    user = relationship("User", back_populates="condition_metrics")
    condition = relationship("ChronicCondition", back_populates="condition_metrics")


class ClinicalNote(Base):
    """Immutable clinical note attached to a therapy session.

    Notes are append-only (no update / delete allowed at the application
    level).  Each note carries a SHA-512 hash of its content for tamper
    detection, mirroring the FLOWSHEET portal design.
    """
    __tablename__ = "clinical_notes"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("therapy_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    author_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    author_role = Column(String(50), nullable=True)  # patient, care_partner, nurse, physician

    note_type = Column(String(50), nullable=False, default="general")  # general, clinical, assessment, plan
    note_text = Column(Text, nullable=False)
    note_hash = Column(String(128), nullable=False)  # SHA-512 of note_text for integrity

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    session = relationship("TherapySession", back_populates="clinical_notes")
    author = relationship("User")


# Common condition-specific metrics reference:
# 
# DIABETES:
# - HbA1c (Glycated Hemoglobin) - %
# - Fasting Blood Glucose - mg/dL
# - Postprandial Glucose - mg/dL
# - Fructosamine - µmol/L
# - C-Peptide - ng/mL
# - Insulin Level - µU/mL
# 
# RENAL DISEASE:
# - eGFR (Estimated Glomerular Filtration Rate) - mL/min/1.73m²
# - Serum Creatinine - mg/dL
# - Blood Urea Nitrogen (BUN) - mg/dL
# - Albumin/Creatinine Ratio - mg/g
# - Protein in Urine (24hr) - g/24hr
# - Potassium - mEq/L
# - Phosphorus - mg/dL
# - Calcium - mg/dL
# - Hemoglobin - g/dL (for anemia in CKD)
# - Parathyroid Hormone (PTH) - pg/mL
# 
# CANCER (varies by type):
# - PSA (Prostate-Specific Antigen) - ng/mL (Prostate cancer)
# - CA-125 (Cancer Antigen 125) - U/mL (Ovarian cancer)
# - CEA (Carcinoembryonic Antigen) - ng/mL (Colorectal cancer)
# - CA 19-9 - U/mL (Pancreatic cancer)
# - AFP (Alpha-Fetoprotein) - ng/mL (Liver cancer)
# - HCG (Human Chorionic Gonadotropin) - mIU/mL (Testicular cancer)
# - Tumor Size - cm (from imaging)
# - White Blood Cell Count - cells/µL (for leukemia)
# - Blast Percentage - % (for leukemia)
# 
# G6PD DEFICIENCY:
# - G6PD Enzyme Level - U/gHb
# - Bilirubin (Total) - mg/dL
# - Bilirubin (Indirect) - mg/dL
# - Reticulocyte Count - %
# - Hemoglobin - g/dL
# - Haptoglobin - mg/dL
# - LDH (Lactate Dehydrogenase) - U/L
