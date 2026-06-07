"""Lifestyle tracking models."""

from datetime import datetime, timezone, date

from sqlalchemy import String, Float, Integer, DateTime, Date, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class LifestyleEntry(Base):
    __tablename__ = "lifestyle_entries"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    weight_kg: Mapped[float | None] = mapped_column(Float)
    height_cm: Mapped[float | None] = mapped_column(Float)
    bmi: Mapped[float | None] = mapped_column(Float)
    blood_pressure_systolic: Mapped[int | None] = mapped_column(Integer)
    blood_pressure_diastolic: Mapped[int | None] = mapped_column(Integer)
    resting_heart_rate: Mapped[int | None] = mapped_column(Integer)
    body_temperature_c: Mapped[float | None] = mapped_column(Float)
    blood_oxygen_pct: Mapped[float | None] = mapped_column(Float)
    smoking_status: Mapped[str | None] = mapped_column(String(50))
    alcohol_drinks: Mapped[int | None] = mapped_column(Integer)
    caffeine_mg: Mapped[float | None] = mapped_column(Float)
    screen_time_minutes: Mapped[int | None] = mapped_column(Integer)
    outdoor_time_minutes: Mapped[int | None] = mapped_column(Integer)
    social_interactions: Mapped[int | None] = mapped_column(Integer)  # count
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    user = relationship("User", back_populates="lifestyle_entries")
