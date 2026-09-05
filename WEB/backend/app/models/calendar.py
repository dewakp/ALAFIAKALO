"""Calendar event model.

Unified calendar for scheduling, tracking, and planning:
- Appointments (doctor visits, check-ups)
- Meals (planned meals, nutrition schedules)
- Medications (dosing reminders, refill dates)
- Activities (exercises, workouts, sports)
- Wellness (meditation, breathing, therapy sessions)
- Custom events
"""

from datetime import datetime, timezone, date, time

from sqlalchemy import (
    String, Integer, DateTime, Date, Time, ForeignKey, Text, Boolean,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class CalendarEvent(Base):
    __tablename__ = "calendar_events"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)

    # ── Core fields ──────────────────────────────────────────────
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    # Category: appointment, meal, medication, exercise, meditation,
    #           therapy, lab, wellness, custom
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # ── Timing ───────────────────────────────────────────────────
    event_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    start_time: Mapped[time | None] = mapped_column(Time)
    end_time: Mapped[time | None] = mapped_column(Time)
    all_day: Mapped[bool] = mapped_column(Boolean, default=False)

    # ── Recurrence ───────────────────────────────────────────────
    # none, daily, weekly, biweekly, monthly, yearly, custom
    recurrence: Mapped[str | None] = mapped_column(String(20))
    recurrence_end_date: Mapped[date | None] = mapped_column(Date)
    # For custom recurrence: e.g. "mon,wed,fri" or "1,15" (days of month)
    recurrence_days: Mapped[str | None] = mapped_column(String(100))

    # ── Status & tracking ────────────────────────────────────────
    # scheduled, completed, missed, cancelled, skipped
    status: Mapped[str] = mapped_column(String(20), default="scheduled")

    # ── Location (optional) ──────────────────────────────────────
    location: Mapped[str | None] = mapped_column(String(500))

    # ── Reminders ────────────────────────────────────────────────
    # Minutes before event: e.g. 15, 30, 60, 1440 (1 day)
    reminder_minutes: Mapped[int | None] = mapped_column(Integer)

    # ── Category-specific metadata (JSON-like text) ──────────────
    # Appointments: doctor name, specialty, clinic
    # Meals: meal type (breakfast/lunch/dinner/snack), planned foods
    # Medications: medication name, dosage, related medication_id
    # Exercise: exercise type, duration_minutes, intensity
    # Meditation: technique, duration_minutes
    # Therapy: therapist name, therapy type
    metadata_json: Mapped[str | None] = mapped_column(Text)

    # ── Linked records (optional FK-like references) ─────────────
    # Links to existing records in other tables
    linked_medication_id: Mapped[int | None] = mapped_column(Integer)
    linked_condition_id: Mapped[int | None] = mapped_column(Integer)
    linked_fitness_id: Mapped[int | None] = mapped_column(Integer)

    # ── Color/priority ───────────────────────────────────────────
    color: Mapped[str | None] = mapped_column(String(20))  #  hex color e.g. #4CAF50
    priority: Mapped[str | None] = mapped_column(String(10))  # low, medium, high

    # ── Notes & completion ───────────────────────────────────────
    notes: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # ── Timestamps ───────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    user = relationship("User", back_populates="calendar_events")
