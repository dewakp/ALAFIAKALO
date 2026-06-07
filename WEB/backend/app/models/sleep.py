"""Sleep tracking models."""

from datetime import datetime, timezone, date, time

from sqlalchemy import String, Float, Integer, DateTime, Date, Time, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class SleepLog(Base):
    """Comprehensive sleep tracking."""
    __tablename__ = "sleep_logs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    sleep_date: Mapped[date] = mapped_column(Date, nullable=False)
    
    # Sleep timing
    bedtime: Mapped[time | None] = mapped_column(Time)
    wake_time: Mapped[time | None] = mapped_column(Time)
    total_hours: Mapped[float | None] = mapped_column(Float)
    
    # Sleep quality metrics
    quality_score: Mapped[int | None] = mapped_column(Integer)  # 1-10 scale
    deep_sleep_hours: Mapped[float | None] = mapped_column(Float)
    light_sleep_hours: Mapped[float | None] = mapped_column(Float)
    rem_sleep_hours: Mapped[float | None] = mapped_column(Float)
    awake_hours: Mapped[float | None] = mapped_column(Float)
    
    # Disruptions
    times_awakened: Mapped[int | None] = mapped_column(Integer)
    time_to_fall_asleep_min: Mapped[int | None] = mapped_column(Integer)
    
    # Environment
    sleep_environment: Mapped[str | None] = mapped_column(String(100))  # bedroom, hotel, etc
    room_temperature_c: Mapped[float | None] = mapped_column(Float)
    noise_level: Mapped[str | None] = mapped_column(String(20))  # quiet, moderate, loud
    
    # Pre-sleep factors
    caffeine_cutoff_hours: Mapped[float | None] = mapped_column(Float)  # hours before bed
    alcohol_consumed: Mapped[bool | None] = mapped_column()
    exercise_hours_before: Mapped[float | None] = mapped_column(Float)
    screen_time_before_min: Mapped[int | None] = mapped_column(Integer)
    
    # Sleep aids
    sleep_aids: Mapped[str | None] = mapped_column(Text)  # melatonin, medication, etc
    
    # Dreams and symptoms
    had_dreams: Mapped[bool | None] = mapped_column()
    had_nightmares: Mapped[bool | None] = mapped_column()
    sleep_disorders: Mapped[str | None] = mapped_column(Text)  # snoring, apnea, insomnia
    
    # Morning feeling
    morning_alertness: Mapped[int | None] = mapped_column(Integer)  # 1-10
    morning_mood: Mapped[int | None] = mapped_column(Integer)  # 1-10
    
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    user = relationship("User", back_populates="sleep_logs")
