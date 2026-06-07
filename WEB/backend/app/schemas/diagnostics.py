"""Pydantic schemas for the diagnostics engine."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ── Request Schemas ───────────────────────────────────────────────────

class SymptomInput(BaseModel):
    """A single reported symptom."""
    name: str = Field(..., description="Symptom name, e.g. 'headache', 'chest pain'")
    severity: Optional[int] = Field(None, ge=1, le=10, description="Severity 1-10")
    duration: Optional[str] = Field(None, description="Duration, e.g. '3 days', '2 weeks'")
    body_part: Optional[str] = Field(None, description="Body location, e.g. 'chest', 'abdomen'")
    quality: Optional[str] = Field(None, description="Description, e.g. 'sharp', 'dull', 'burning'")
    pattern: Optional[str] = Field(None, description="Pattern, e.g. 'constant', 'intermittent', 'worsening'")
    triggers: Optional[str] = Field(None, description="What makes it worse")
    relievers: Optional[str] = Field(None, description="What makes it better")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "headache",
                "severity": 6,
                "duration": "3 days",
                "body_part": "head",
                "quality": "throbbing",
                "pattern": "intermittent",
                "triggers": "bright lights, stress",
                "relievers": "rest, ibuprofen",
            }
        }


class DiagnosticAssessmentRequest(BaseModel):
    """Request body for a diagnostic assessment."""
    symptoms: List[SymptomInput] = Field(..., min_length=1, description="List of reported symptoms")
    additional_context: Optional[str] = Field(None, description="Free-text additional context from the patient")

    class Config:
        json_schema_extra = {
            "example": {
                "symptoms": [
                    {"name": "headache", "severity": 7, "duration": "5 days", "quality": "throbbing"},
                    {"name": "fatigue", "severity": 5, "duration": "1 week"},
                    {"name": "nausea", "severity": 3},
                ],
                "additional_context": "Symptoms started after a stressful week at work. No recent travel.",
            }
        }


class LabCorrelationRequest(BaseModel):
    """Request body for lab correlation analysis."""
    lab_result_ids: Optional[List[int]] = Field(
        None, description="Specific lab result IDs to analyze. If empty, uses most recent 20."
    )


class ICD10SearchRequest(BaseModel):
    """Query parameters for ICD-10 code search."""
    query: str = Field(..., min_length=2, description="Search term (symptom, condition, or code)")
    limit: int = Field(20, ge=1, le=100, description="Max results")


class ScreeningUpdateRequest(BaseModel):
    """Update the status of a screening recommendation."""
    status: str = Field(..., description="New status: recommended, scheduled, completed, declined, overdue")
    completed_date: Optional[datetime] = None
    notes: Optional[str] = None


class AssessmentReviewRequest(BaseModel):
    """Provider review of an AI diagnostic assessment."""
    reviewer_notes: str = Field(..., description="Provider's clinical notes on the assessment")
    confirmed_differentials: Optional[List[int]] = Field(
        None, description="IDs of differential diagnoses the provider confirms"
    )
    rejected_differentials: Optional[List[int]] = Field(
        None, description="IDs of differential diagnoses the provider rejects"
    )


# ── Response Schemas ──────────────────────────────────────────────────

class UrgencyOut(BaseModel):
    level: str
    label: str
    description: str
    color: str
    trigger: Optional[str] = None


class RecommendedTestOut(BaseModel):
    test: str
    rationale: Optional[str] = None
    urgency: Optional[str] = None  # routine, urgent, stat


class DifferentialDiagnosisOut(BaseModel):
    id: Optional[int] = None
    icd10_code: str
    condition: str
    body_system: Optional[str] = None
    confidence: float = Field(..., ge=0.0, le=1.0)
    rank: Optional[int] = None
    reasoning: Optional[str] = None
    matched_symptoms: Optional[List[str]] = None
    risk_factor_match: Optional[List[str]] = None
    source: str = "ai_enhanced"
    provider_confirmed: Optional[bool] = None


class DiagnosticAssessmentOut(BaseModel):
    assessment_id: Optional[str] = None
    id: Optional[int] = None
    patient_id: int
    assessed_at: str
    urgency: UrgencyOut
    reported_symptoms: List[Dict[str, Any]]
    differential_diagnoses: List[DifferentialDiagnosisOut]
    primary_impression: Optional[str] = None
    supporting_evidence: Optional[List[str]] = None
    contradicting_factors: Optional[List[str]] = None
    recommended_actions: Optional[List[str]] = None
    recommended_tests: Optional[List[RecommendedTestOut]] = None
    red_flags: Optional[List[str]] = None
    risk_factors_identified: Optional[List[str]] = None
    follow_up_timeline: Optional[str] = None
    patient_education: Optional[List[str]] = None
    status: Optional[str] = "completed"
    disclaimer: str

    class Config:
        from_attributes = True


class AssessmentSummaryOut(BaseModel):
    """Compact assessment for list views."""
    id: int
    assessment_code: str
    status: str
    urgency_level: str
    primary_impression: Optional[str] = None
    symptom_count: int = 0
    differential_count: int = 0
    created_at: datetime

    class Config:
        from_attributes = True


# ── Screening Schemas ─────────────────────────────────────────────────

class ScreeningRecommendationOut(BaseModel):
    id: Optional[int] = None
    screening: str
    icd10_code: Optional[str] = None
    rationale: Optional[str] = None
    frequency: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = "recommended"
    risk_level: Optional[str] = None

    class Config:
        from_attributes = True


class LifestyleModificationOut(BaseModel):
    area: str
    current: Optional[str] = None
    recommended: str
    impact: Optional[str] = None


class ProactiveScreeningOut(BaseModel):
    screening_id: Optional[str] = None
    patient_id: int
    screened_at: str
    risk_profile: Dict[str, Any] = {}
    recommended_screenings: List[ScreeningRecommendationOut] = []
    emerging_patterns: List[str] = []
    preventive_actions: List[str] = []
    lifestyle_modifications: List[LifestyleModificationOut] = []
    disclaimer: str


# ── Lab Correlation Schemas ───────────────────────────────────────────

class LabCorrelationOut(BaseModel):
    lab_test: str
    finding: Optional[str] = None
    clinical_significance: Optional[str] = None
    related_icd10: Optional[str] = None


class PossibleConditionOut(BaseModel):
    icd10_code: str
    condition: str
    supporting_labs: Optional[List[str]] = None
    confidence: Optional[float] = None


class LabCorrelationReportOut(BaseModel):
    correlation_id: Optional[str] = None
    patient_id: int
    analyzed_at: str
    labs_analyzed: int
    abnormal_count: int
    abnormal_labs: List[Dict[str, Any]] = []
    diagnostic_correlations: List[LabCorrelationOut] = []
    possible_conditions: List[PossibleConditionOut] = []
    recommended_follow_up_tests: List[RecommendedTestOut] = []
    clinical_significance: Optional[str] = None
    disclaimer: str


# ── ICD-10 Schemas ────────────────────────────────────────────────────

class ICD10CodeOut(BaseModel):
    code: str
    title: str
    chapter: str
    chapter_title: Optional[str] = None
    category: Optional[str] = None
    body_system: Optional[str] = None
    common_symptoms: List[str] = []
    risk_factors: List[str] = []
    is_billable: bool = True


class ICD10SearchResult(BaseModel):
    query: str
    results: List[ICD10CodeOut]
    total: int
