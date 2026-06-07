"""Health conditions and diagnoses tracking."""

from datetime import datetime, timezone, date

from sqlalchemy import String, DateTime, Date, ForeignKey, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class HealthCondition(Base):
    """Track chronic conditions, diagnoses, and medical history."""
    __tablename__ = "health_conditions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    
    # Condition details
    condition_name: Mapped[str] = mapped_column(String(255), nullable=False)
    icd10_code: Mapped[str | None] = mapped_column(String(20))  # ICD-10 diagnosis code
    snomed_code: Mapped[str | None] = mapped_column(String(50))  # SNOMED CT code
    
    # Classification
    category: Mapped[str | None] = mapped_column(String(100))  # cardiovascular, respiratory, etc
    severity: Mapped[str | None] = mapped_column(String(50))  # mild, moderate, severe, critical
    status: Mapped[str] = mapped_column(String(50), default="active")  # active, resolved, managed, monitoring
    
    # Timeline
    diagnosis_date: Mapped[date | None] = mapped_column(Date)
    onset_date: Mapped[date | None] = mapped_column(Date)
    resolution_date: Mapped[date | None] = mapped_column(Date)
    
    # Medical details
    diagnosed_by: Mapped[str | None] = mapped_column(String(255))  # doctor name
    healthcare_facility: Mapped[str | None] = mapped_column(String(255))
    
    # Treatment
    current_treatment: Mapped[str | None] = mapped_column(Text)
    treatment_response: Mapped[str | None] = mapped_column(Text)
    
    # Impact
    affects_daily_life: Mapped[bool | None] = mapped_column(Boolean)
    requires_accommodation: Mapped[bool | None] = mapped_column(Boolean)
    hereditary: Mapped[bool | None] = mapped_column(Boolean)
    
    # Related information
    related_conditions: Mapped[str | None] = mapped_column(Text)  # JSON array of related condition IDs
    complications: Mapped[str | None] = mapped_column(Text)
    
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    user = relationship("User", back_populates="health_conditions")


class SymptomLog(Base):
    """Track symptoms and illness episodes."""
    __tablename__ = "symptom_logs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    log_date: Mapped[date] = mapped_column(Date, nullable=False)
    
    # Symptom details
    symptom_name: Mapped[str] = mapped_column(String(255), nullable=False)
    body_part: Mapped[str | None] = mapped_column(String(100))  # head, chest, abdomen, etc
    location_specific: Mapped[str | None] = mapped_column(String(255))  # left temple, lower right abdomen
    
    # Intensity
    severity: Mapped[int | None] = mapped_column()  # 1-10 scale
    duration_hours: Mapped[float | None] = mapped_column()
    
    # Characteristics
    symptom_type: Mapped[str | None] = mapped_column(String(100))  # pain, nausea, fatigue, etc
    quality: Mapped[str | None] = mapped_column(String(100))  # sharp, dull, throbbing, burning
    onset: Mapped[str | None] = mapped_column(String(50))  # sudden, gradual
    pattern: Mapped[str | None] = mapped_column(String(50))  # constant, intermittent, worsening
    
    # Associated factors
    triggers: Mapped[str | None] = mapped_column(Text)  # what makes it worse
    relievers: Mapped[str | None] = mapped_column(Text)  # what makes it better
    aggravating_factors: Mapped[str | None] = mapped_column(Text)
    
    # Context
    affects_function: Mapped[bool | None] = mapped_column(Boolean)
    interferes_sleep: Mapped[bool | None] = mapped_column(Boolean)
    interferes_work: Mapped[bool | None] = mapped_column(Boolean)
    interferes_activities: Mapped[bool | None] = mapped_column(Boolean)
    
    # Treatment attempted
    self_treatment: Mapped[str | None] = mapped_column(Text)
    medications_taken: Mapped[str | None] = mapped_column(Text)
    treatment_effective: Mapped[bool | None] = mapped_column(Boolean)
    
    # Medical attention
    sought_medical_care: Mapped[bool | None] = mapped_column(Boolean)
    emergency_visit: Mapped[bool | None] = mapped_column(Boolean)
    
    # Associated symptoms
    other_symptoms: Mapped[str | None] = mapped_column(Text)  # fever, chills, nausea
    
    # Related to condition
    related_condition_id: Mapped[int | None] = mapped_column(ForeignKey("health_conditions.id"))
    
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    user = relationship("User", back_populates="symptom_logs")


class IllnessLog(Base):
    """Track acute illnesses and recovery."""
    __tablename__ = "illness_logs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    
    # Illness details
    illness_name: Mapped[str] = mapped_column(String(255), nullable=False)
    illness_type: Mapped[str | None] = mapped_column(String(100))  # cold, flu, infection, injury
    
    # Timeline
    onset_date: Mapped[date] = mapped_column(Date, nullable=False)
    diagnosis_date: Mapped[date | None] = mapped_column(Date)
    recovery_date: Mapped[date | None] = mapped_column(Date)
    
    # Severity
    severity: Mapped[str | None] = mapped_column(String(50))  # mild, moderate, severe
    contagious: Mapped[bool | None] = mapped_column(Boolean)
    
    # Symptoms
    primary_symptoms: Mapped[str | None] = mapped_column(Text)
    secondary_symptoms: Mapped[str | None] = mapped_column(Text)
    
    # Medical care
    diagnosed_by: Mapped[str | None] = mapped_column(String(255))
    hospitalized: Mapped[bool | None] = mapped_column(Boolean)
    days_hospitalized: Mapped[int | None] = mapped_column()
    
    # Treatment
    treatment_plan: Mapped[str | None] = mapped_column(Text)
    medications_prescribed: Mapped[str | None] = mapped_column(Text)
    
    # Complications
    complications: Mapped[str | None] = mapped_column(Text)
    
    # Transmission
    suspected_source: Mapped[str | None] = mapped_column(Text)
    exposure_date: Mapped[date | None] = mapped_column(Date)
    
    # Impact
    days_missed_work: Mapped[int | None] = mapped_column()
    days_bedridden: Mapped[int | None] = mapped_column()
    
    # Status
    status: Mapped[str] = mapped_column(String(50), default="active")  # active, recovering, resolved
    
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    user = relationship("User", back_populates="illness_logs")
