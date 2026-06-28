"""Schemas for ground-truth overlays: genetic markers + environmental/social logs."""

from datetime import date, datetime
from pydantic import BaseModel, Field


# ── Genetic markers ──
class GeneticMarkerCreate(BaseModel):
    gene: str = Field(..., min_length=1, max_length=100)
    variant: str | None = None
    genotype: str | None = None
    risk_allele: str | None = None
    associated_condition: str | None = None
    risk_level: str | None = None
    source: str | None = None
    interpretation: str | None = None
    notes: str | None = None


class GeneticMarkerResponse(BaseModel):
    id: int
    user_id: int
    gene: str
    variant: str | None = None
    genotype: str | None = None
    risk_allele: str | None = None
    associated_condition: str | None = None
    risk_level: str | None = None
    source: str | None = None
    interpretation: str | None = None
    notes: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Environmental / social factors ──
class EnvSocialLogCreate(BaseModel):
    log_date: date
    location: str | None = None
    air_quality_index: int | None = None
    ambient_temp_c: float | None = None
    humidity_pct: float | None = None
    noise_level: str | None = None
    pollen_level: str | None = None
    household_size: int | None = None
    occupation: str | None = None
    work_stress_level: int | None = Field(None, ge=1, le=10)
    financial_stress_level: int | None = Field(None, ge=1, le=10)
    social_support_level: int | None = Field(None, ge=1, le=10)
    major_life_event: str | None = None
    notes: str | None = None


class EnvSocialLogResponse(BaseModel):
    id: int
    user_id: int
    log_date: date
    location: str | None = None
    air_quality_index: int | None = None
    ambient_temp_c: float | None = None
    humidity_pct: float | None = None
    noise_level: str | None = None
    pollen_level: str | None = None
    household_size: int | None = None
    occupation: str | None = None
    work_stress_level: int | None = None
    financial_stress_level: int | None = None
    social_support_level: int | None = None
    major_life_event: str | None = None
    notes: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
