"""Mental Health assessment and wellness models."""

from datetime import datetime, timezone, date

from sqlalchemy import String, Integer, DateTime, Date, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class MentalHealthAssessment(Base):
    """PHQ-9 / GAD-7 style standardized assessment."""
    __tablename__ = "mental_health_assessments"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    assessment_date: Mapped[date] = mapped_column(Date, nullable=False)
    assessment_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    # Types: phq9, gad7, pss10, who5, custom

    # PHQ-9 items (depression) — each 0-3
    phq_interest: Mapped[int | None] = mapped_column(Integer)
    phq_feeling_down: Mapped[int | None] = mapped_column(Integer)
    phq_sleep: Mapped[int | None] = mapped_column(Integer)
    phq_energy: Mapped[int | None] = mapped_column(Integer)
    phq_appetite: Mapped[int | None] = mapped_column(Integer)
    phq_self_esteem: Mapped[int | None] = mapped_column(Integer)
    phq_concentration: Mapped[int | None] = mapped_column(Integer)
    phq_psychomotor: Mapped[int | None] = mapped_column(Integer)
    phq_suicidal_ideation: Mapped[int | None] = mapped_column(Integer)

    # GAD-7 items (anxiety) — each 0-3
    gad_nervous: Mapped[int | None] = mapped_column(Integer)
    gad_uncontrollable_worry: Mapped[int | None] = mapped_column(Integer)
    gad_excessive_worry: Mapped[int | None] = mapped_column(Integer)
    gad_trouble_relaxing: Mapped[int | None] = mapped_column(Integer)
    gad_restless: Mapped[int | None] = mapped_column(Integer)
    gad_irritable: Mapped[int | None] = mapped_column(Integer)
    gad_afraid: Mapped[int | None] = mapped_column(Integer)

    # WHO-5 Well-Being Index items — each 0-5
    who5_cheerful: Mapped[int | None] = mapped_column(Integer)
    who5_calm: Mapped[int | None] = mapped_column(Integer)
    who5_active: Mapped[int | None] = mapped_column(Integer)
    who5_rested: Mapped[int | None] = mapped_column(Integer)
    who5_interesting: Mapped[int | None] = mapped_column(Integer)

    # Computed scores
    total_score: Mapped[int | None] = mapped_column(Integer)
    severity: Mapped[str | None] = mapped_column(String(50))
    # Severities: minimal, mild, moderate, moderately_severe, severe

    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    user = relationship("User", back_populates="mental_health_assessments")


class BreathingSession(Base):
    """Tracked guided breathing / meditation session."""
    __tablename__ = "breathing_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    session_date: Mapped[date] = mapped_column(Date, nullable=False)
    exercise_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # Types: box_breathing, 4_7_8, deep_breathing, body_scan, grounding_5_4_3_2_1
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    mood_before: Mapped[int | None] = mapped_column(Integer)  # 1-10
    mood_after: Mapped[int | None] = mapped_column(Integer)   # 1-10
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    user = relationship("User", back_populates="breathing_sessions")


class GratitudeEntry(Base):
    """Daily gratitude journal entries."""
    __tablename__ = "gratitude_entries"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    item_1: Mapped[str] = mapped_column(Text, nullable=False)
    item_2: Mapped[str | None] = mapped_column(Text)
    item_3: Mapped[str | None] = mapped_column(Text)
    reflection: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    user = relationship("User", back_populates="gratitude_entries")
