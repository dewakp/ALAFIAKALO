"""Mood / Mental Health tracking models."""

from datetime import datetime, timezone, date

from sqlalchemy import Integer, DateTime, Date, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class MoodEntry(Base):
    __tablename__ = "mood_entries"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    mood_score: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-10 scale
    energy_level: Mapped[int | None] = mapped_column(Integer)  # 1-10
    stress_level: Mapped[int | None] = mapped_column(Integer)  # 1-10
    anxiety_level: Mapped[int | None] = mapped_column(Integer)  # 1-10
    sleep_quality: Mapped[int | None] = mapped_column(Integer)  # 1-10
    sleep_hours: Mapped[float | None] = mapped_column()
    emotions: Mapped[str | None] = mapped_column(Text)  # JSON array of emotion tags
    triggers: Mapped[str | None] = mapped_column(Text)  # what triggered the mood
    coping_strategies: Mapped[str | None] = mapped_column(Text)
    gratitude: Mapped[str | None] = mapped_column(Text)
    journal_entry: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    user = relationship("User", back_populates="mood_entries")
