"""Diagnostic assessment models.

Stores AI-powered diagnostic assessments, differential diagnoses,
screening recommendations, and diagnostic audit trails — all ICD-10 coded.
"""

from datetime import datetime, timezone
from enum import Enum as PyEnum

from sqlalchemy import (
    String,
    DateTime,
    ForeignKey,
    Text,
    Boolean,
    Float,
    Integer,
    JSON,
    Enum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


# ── Enums ─────────────────────────────────────────────────────────────

class AssessmentStatus(str, PyEnum):
    pending = "pending"
    completed = "completed"
    reviewed = "reviewed"          # Reviewed by a provider
    superseded = "superseded"      # Replaced by newer assessment


class UrgencyLevel(str, PyEnum):
    emergency = "emergency"
    urgent = "urgent"
    soon = "soon"
    routine = "routine"
    monitoring = "monitoring"


class ScreeningStatus(str, PyEnum):
    recommended = "recommended"
    scheduled = "scheduled"
    completed = "completed"
    declined = "declined"
    overdue = "overdue"


class DiagnosticSource(str, PyEnum):
    rule_based = "rule_based"
    ai_enhanced = "ai_enhanced"
    provider_confirmed = "provider_confirmed"


# ── Assessment (the top-level diagnostic session) ────────────────────

class DiagnosticAssessment(Base):
    """A single diagnostic assessment session."""
    __tablename__ = "diagnostic_assessments"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)

    # Identifiers
    assessment_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)

    # Status & urgency
    status: Mapped[str] = mapped_column(
        Enum(AssessmentStatus), default=AssessmentStatus.completed, nullable=False
    )
    urgency_level: Mapped[str] = mapped_column(
        Enum(UrgencyLevel), default=UrgencyLevel.routine, nullable=False
    )
    urgency_trigger: Mapped[str | None] = mapped_column(String(255))

    # Inputs
    reported_symptoms: Mapped[dict | None] = mapped_column(JSON)  # list of symptom dicts
    additional_context: Mapped[str | None] = mapped_column(Text)

    # Primary output
    primary_impression: Mapped[str | None] = mapped_column(Text)
    supporting_evidence: Mapped[list | None] = mapped_column(JSON)
    contradicting_factors: Mapped[list | None] = mapped_column(JSON)

    # Recommendations
    recommended_actions: Mapped[list | None] = mapped_column(JSON)
    recommended_tests: Mapped[list | None] = mapped_column(JSON)
    red_flags: Mapped[list | None] = mapped_column(JSON)
    risk_factors_identified: Mapped[list | None] = mapped_column(JSON)
    follow_up_timeline: Mapped[str | None] = mapped_column(String(255))
    patient_education: Mapped[list | None] = mapped_column(JSON)

    # Provider review (if a provider reviews the AI assessment)
    reviewed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    reviewer_notes: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    differentials: Mapped[list["DifferentialDiagnosis"]] = relationship(
        back_populates="assessment", cascade="all, delete-orphan", lazy="selectin"
    )


class DifferentialDiagnosis(Base):
    """Individual differential diagnosis within an assessment."""
    __tablename__ = "differential_diagnoses"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    assessment_id: Mapped[int] = mapped_column(
        ForeignKey("diagnostic_assessments.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Diagnosis info
    icd10_code: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    condition_name: Mapped[str] = mapped_column(String(500), nullable=False)
    body_system: Mapped[str | None] = mapped_column(String(100))

    # Scoring
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    rank: Mapped[int] = mapped_column(Integer, default=0)

    # Evidence
    matched_symptoms: Mapped[list | None] = mapped_column(JSON)
    risk_factor_match: Mapped[list | None] = mapped_column(JSON)
    reasoning: Mapped[str | None] = mapped_column(Text)

    # Source tracking
    source: Mapped[str] = mapped_column(
        Enum(DiagnosticSource), default=DiagnosticSource.ai_enhanced, nullable=False
    )

    # Provider can confirm/reject AI differentials
    provider_confirmed: Mapped[bool | None] = mapped_column(Boolean)
    provider_notes: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    assessment: Mapped["DiagnosticAssessment"] = relationship(back_populates="differentials")


# ── Screening Recommendations ────────────────────────────────────────

class ScreeningRecommendation(Base):
    """Proactive screening recommendations generated for a user."""
    __tablename__ = "screening_recommendations"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)

    # Screening info
    screening_name: Mapped[str] = mapped_column(String(500), nullable=False)
    icd10_code: Mapped[str | None] = mapped_column(String(20))
    rationale: Mapped[str | None] = mapped_column(Text)
    frequency: Mapped[str | None] = mapped_column(String(255))
    priority: Mapped[str | None] = mapped_column(String(50))  # high, medium, low

    # Status
    status: Mapped[str] = mapped_column(
        Enum(ScreeningStatus), default=ScreeningStatus.recommended, nullable=False
    )

    # Risk context
    risk_level: Mapped[str | None] = mapped_column(String(50))  # low, moderate, high, critical
    risk_rationale: Mapped[str | None] = mapped_column(Text)
    associated_risks: Mapped[list | None] = mapped_column(JSON)

    # Scheduling
    recommended_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


# ── Lab Correlation Report ───────────────────────────────────────────

class LabCorrelationReport(Base):
    """Stores AI-generated lab result correlation analyses."""
    __tablename__ = "lab_correlation_reports"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)

    correlation_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)

    labs_analyzed: Mapped[int] = mapped_column(Integer, default=0)
    abnormal_count: Mapped[int] = mapped_column(Integer, default=0)
    abnormal_labs: Mapped[list | None] = mapped_column(JSON)

    diagnostic_correlations: Mapped[list | None] = mapped_column(JSON)
    possible_conditions: Mapped[list | None] = mapped_column(JSON)
    recommended_follow_up_tests: Mapped[list | None] = mapped_column(JSON)
    clinical_significance: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
