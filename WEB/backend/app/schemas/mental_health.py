"""Mental Health schemas."""

from datetime import date, datetime
from pydantic import BaseModel, Field


# --- Assessments ---

class AssessmentCreate(BaseModel):
    assessment_date: date
    assessment_type: str = Field(..., pattern="^(phq9|gad7|who5|custom)$")

    phq_interest: int | None = Field(None, ge=0, le=3)
    phq_feeling_down: int | None = Field(None, ge=0, le=3)
    phq_sleep: int | None = Field(None, ge=0, le=3)
    phq_energy: int | None = Field(None, ge=0, le=3)
    phq_appetite: int | None = Field(None, ge=0, le=3)
    phq_self_esteem: int | None = Field(None, ge=0, le=3)
    phq_concentration: int | None = Field(None, ge=0, le=3)
    phq_psychomotor: int | None = Field(None, ge=0, le=3)
    phq_suicidal_ideation: int | None = Field(None, ge=0, le=3)

    gad_nervous: int | None = Field(None, ge=0, le=3)
    gad_uncontrollable_worry: int | None = Field(None, ge=0, le=3)
    gad_excessive_worry: int | None = Field(None, ge=0, le=3)
    gad_trouble_relaxing: int | None = Field(None, ge=0, le=3)
    gad_restless: int | None = Field(None, ge=0, le=3)
    gad_irritable: int | None = Field(None, ge=0, le=3)
    gad_afraid: int | None = Field(None, ge=0, le=3)

    who5_cheerful: int | None = Field(None, ge=0, le=5)
    who5_calm: int | None = Field(None, ge=0, le=5)
    who5_active: int | None = Field(None, ge=0, le=5)
    who5_rested: int | None = Field(None, ge=0, le=5)
    who5_interesting: int | None = Field(None, ge=0, le=5)

    notes: str | None = None


class AssessmentResponse(BaseModel):
    id: int
    user_id: int
    assessment_date: date
    assessment_type: str
    phq_interest: int | None = None
    phq_feeling_down: int | None = None
    phq_sleep: int | None = None
    phq_energy: int | None = None
    phq_appetite: int | None = None
    phq_self_esteem: int | None = None
    phq_concentration: int | None = None
    phq_psychomotor: int | None = None
    phq_suicidal_ideation: int | None = None
    gad_nervous: int | None = None
    gad_uncontrollable_worry: int | None = None
    gad_excessive_worry: int | None = None
    gad_trouble_relaxing: int | None = None
    gad_restless: int | None = None
    gad_irritable: int | None = None
    gad_afraid: int | None = None
    who5_cheerful: int | None = None
    who5_calm: int | None = None
    who5_active: int | None = None
    who5_rested: int | None = None
    who5_interesting: int | None = None
    total_score: int | None = None
    severity: str | None = None
    notes: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Breathing Sessions ---

class BreathingSessionCreate(BaseModel):
    session_date: date
    exercise_type: str = Field(..., pattern="^(box_breathing|4_7_8|deep_breathing|body_scan|grounding_5_4_3_2_1)$")
    duration_seconds: int = Field(..., gt=0)
    mood_before: int | None = Field(None, ge=1, le=10)
    mood_after: int | None = Field(None, ge=1, le=10)
    notes: str | None = None


class BreathingSessionResponse(BaseModel):
    id: int
    user_id: int
    session_date: date
    exercise_type: str
    duration_seconds: int
    mood_before: int | None = None
    mood_after: int | None = None
    notes: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Gratitude ---

class GratitudeCreate(BaseModel):
    entry_date: date
    item_1: str = Field(..., min_length=1)
    item_2: str | None = None
    item_3: str | None = None
    reflection: str | None = None


class GratitudeResponse(BaseModel):
    id: int
    user_id: int
    entry_date: date
    item_1: str
    item_2: str | None = None
    item_3: str | None = None
    reflection: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Dashboard / Stats ---

class MentalHealthStats(BaseModel):
    avg_mood_7d: float | None = None
    avg_mood_30d: float | None = None
    avg_stress_7d: float | None = None
    avg_anxiety_7d: float | None = None
    avg_sleep_quality_7d: float | None = None
    avg_sleep_hours_7d: float | None = None
    mood_trend: str | None = None  # improving, stable, declining
    total_entries_30d: int = 0
    streak_days: int = 0
    total_breathing_minutes_30d: float = 0
    latest_phq9_score: int | None = None
    latest_phq9_severity: str | None = None
    latest_gad7_score: int | None = None
    latest_gad7_severity: str | None = None
    latest_who5_score: int | None = None
    wellness_score: int | None = None  # 0-100 composite


class BreathingExerciseInfo(BaseModel):
    id: str
    name: str
    description: str
    inhale_seconds: int
    hold_seconds: int
    exhale_seconds: int
    hold_after_exhale_seconds: int
    recommended_cycles: int
    benefits: list[str]
