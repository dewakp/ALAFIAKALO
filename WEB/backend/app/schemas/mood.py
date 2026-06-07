"""Mood / Mental Health schemas."""

from datetime import date, datetime
from pydantic import BaseModel, Field


class MoodEntryCreate(BaseModel):
    entry_date: date
    mood_score: int = Field(..., ge=1, le=10)
    energy_level: int | None = Field(None, ge=1, le=10)
    stress_level: int | None = Field(None, ge=1, le=10)
    anxiety_level: int | None = Field(None, ge=1, le=10)
    sleep_quality: int | None = Field(None, ge=1, le=10)
    sleep_hours: float | None = None
    emotions: str | None = None
    triggers: str | None = None
    coping_strategies: str | None = None
    gratitude: str | None = None
    journal_entry: str | None = None
    notes: str | None = None


class MoodEntryUpdate(BaseModel):
    mood_score: int | None = Field(None, ge=1, le=10)
    energy_level: int | None = Field(None, ge=1, le=10)
    stress_level: int | None = Field(None, ge=1, le=10)
    anxiety_level: int | None = Field(None, ge=1, le=10)
    sleep_quality: int | None = Field(None, ge=1, le=10)
    sleep_hours: float | None = None
    emotions: str | None = None
    triggers: str | None = None
    coping_strategies: str | None = None
    gratitude: str | None = None
    journal_entry: str | None = None
    notes: str | None = None


class MoodEntryResponse(BaseModel):
    id: int
    user_id: int
    entry_date: date
    mood_score: int
    energy_level: int | None = None
    stress_level: int | None = None
    anxiety_level: int | None = None
    sleep_quality: int | None = None
    sleep_hours: float | None = None
    emotions: str | None = None
    triggers: str | None = None
    coping_strategies: str | None = None
    gratitude: str | None = None
    journal_entry: str | None = None
    notes: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
