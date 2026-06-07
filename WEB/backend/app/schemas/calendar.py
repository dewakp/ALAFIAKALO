"""Calendar event schemas."""

from datetime import date, time, datetime
from pydantic import BaseModel


VALID_CATEGORIES = {
    "appointment", "meal", "medication", "exercise",
    "meditation", "therapy", "lab", "wellness", "custom",
}

VALID_STATUSES = {"scheduled", "completed", "missed", "cancelled", "skipped"}
VALID_RECURRENCES = {"none", "daily", "weekly", "biweekly", "monthly", "yearly", "custom"}
VALID_PRIORITIES = {"low", "medium", "high"}


class CalendarEventCreate(BaseModel):
    title: str
    description: str | None = None
    category: str  # appointment, meal, medication, exercise, meditation, therapy, lab, wellness, custom

    event_date: date
    start_time: time | None = None
    end_time: time | None = None
    all_day: bool = False

    recurrence: str | None = None
    recurrence_end_date: date | None = None
    recurrence_days: str | None = None

    status: str = "scheduled"
    location: str | None = None
    reminder_minutes: int | None = None

    metadata_json: str | None = None

    linked_medication_id: int | None = None
    linked_condition_id: int | None = None
    linked_fitness_id: int | None = None

    color: str | None = None
    priority: str | None = None
    notes: str | None = None


class CalendarEventUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    category: str | None = None

    event_date: date | None = None
    start_time: time | None = None
    end_time: time | None = None
    all_day: bool | None = None

    recurrence: str | None = None
    recurrence_end_date: date | None = None
    recurrence_days: str | None = None

    status: str | None = None
    location: str | None = None
    reminder_minutes: int | None = None

    metadata_json: str | None = None

    linked_medication_id: int | None = None
    linked_condition_id: int | None = None
    linked_fitness_id: int | None = None

    color: str | None = None
    priority: str | None = None
    notes: str | None = None
    completed_at: datetime | None = None


class CalendarEventResponse(BaseModel):
    id: int
    user_id: int
    title: str
    description: str | None = None
    category: str

    event_date: date
    start_time: time | None = None
    end_time: time | None = None
    all_day: bool

    recurrence: str | None = None
    recurrence_end_date: date | None = None
    recurrence_days: str | None = None

    status: str
    location: str | None = None
    reminder_minutes: int | None = None

    metadata_json: str | None = None

    linked_medication_id: int | None = None
    linked_condition_id: int | None = None
    linked_fitness_id: int | None = None

    color: str | None = None
    priority: str | None = None
    notes: str | None = None
    completed_at: datetime | None = None

    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
