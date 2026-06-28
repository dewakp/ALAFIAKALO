"""Sleep log schemas (Basis collection domain: sleep)."""

from datetime import date, datetime, time
from pydantic import BaseModel, Field


class SleepLogCreate(BaseModel):
    sleep_date: date
    bedtime: time | None = None
    wake_time: time | None = None
    total_hours: float | None = Field(None, ge=0, le=24)
    quality_score: int | None = Field(None, ge=1, le=10)
    times_awakened: int | None = Field(None, ge=0)
    time_to_fall_asleep_min: int | None = Field(None, ge=0)
    alcohol_consumed: bool | None = None
    screen_time_before_min: int | None = Field(None, ge=0)
    sleep_aids: str | None = None
    had_nightmares: bool | None = None
    sleep_disorders: str | None = None
    morning_alertness: int | None = Field(None, ge=1, le=10)
    notes: str | None = None


class SleepLogUpdate(BaseModel):
    bedtime: time | None = None
    wake_time: time | None = None
    total_hours: float | None = Field(None, ge=0, le=24)
    quality_score: int | None = Field(None, ge=1, le=10)
    times_awakened: int | None = Field(None, ge=0)
    time_to_fall_asleep_min: int | None = Field(None, ge=0)
    alcohol_consumed: bool | None = None
    screen_time_before_min: int | None = Field(None, ge=0)
    sleep_aids: str | None = None
    had_nightmares: bool | None = None
    sleep_disorders: str | None = None
    morning_alertness: int | None = Field(None, ge=1, le=10)
    notes: str | None = None


class SleepLogResponse(BaseModel):
    id: int
    user_id: int
    sleep_date: date
    bedtime: time | None = None
    wake_time: time | None = None
    total_hours: float | None = None
    quality_score: int | None = None
    times_awakened: int | None = None
    time_to_fall_asleep_min: int | None = None
    alcohol_consumed: bool | None = None
    screen_time_before_min: int | None = None
    sleep_aids: str | None = None
    had_nightmares: bool | None = None
    sleep_disorders: str | None = None
    morning_alertness: int | None = None
    notes: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
