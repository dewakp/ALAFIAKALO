"""Elimination tracking models (bowel movements, urination, vomiting)."""

from datetime import datetime, timezone, date, time

from sqlalchemy import String, Integer, DateTime, Date, Time, ForeignKey, Text, Boolean, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class BowelMovement(Base):
    """Track bowel movements for digestive health monitoring."""
    __tablename__ = "bowel_movements"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    log_date: Mapped[date] = mapped_column(Date, nullable=False)
    log_time: Mapped[time | None] = mapped_column(Time)
    
    # Bristol Stool Scale (1-7)
    bristol_scale: Mapped[int | None] = mapped_column(Integer)  # 1=hard lumps, 7=liquid
    
    # Characteristics
    color: Mapped[str | None] = mapped_column(String(50))  # brown, black, red, green, yellow, pale
    consistency: Mapped[str | None] = mapped_column(String(50))  # hard, normal, soft, watery
    size: Mapped[str | None] = mapped_column(String(20))  # small, normal, large
    
    # Symptoms
    blood_present: Mapped[bool | None] = mapped_column(Boolean)
    mucus_present: Mapped[bool | None] = mapped_column(Boolean)
    undigested_food: Mapped[bool | None] = mapped_column(Boolean)
    pain_level: Mapped[int | None] = mapped_column(Integer)  # 0-10
    straining: Mapped[bool | None] = mapped_column(Boolean)
    urgency: Mapped[bool | None] = mapped_column(Boolean)
    
    # Duration
    duration_minutes: Mapped[int | None] = mapped_column(Integer)
    
    # Context
    location: Mapped[str | None] = mapped_column(String(50))  # home, work, public
    associated_symptoms: Mapped[str | None] = mapped_column(Text)  # cramping, bloating, gas
    
    notes: Mapped[str | None] = mapped_column(Text)

    # Firebase-synced fields
    event_type: Mapped[str | None] = mapped_column(String(50))  # poop, urine, vomit, etc.
    pre_event_weight_kg: Mapped[float | None] = mapped_column(Float)
    post_event_weight_kg: Mapped[float | None] = mapped_column(Float)
    image_uri: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    user = relationship("User", back_populates="bowel_movements")


class UrinationLog(Base):
    """Track urination patterns and characteristics."""
    __tablename__ = "urination_logs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    log_date: Mapped[date] = mapped_column(Date, nullable=False)
    log_time: Mapped[time | None] = mapped_column(Time)
    
    # Characteristics
    color: Mapped[str | None] = mapped_column(String(50))  # pale, yellow, amber, dark
    clarity: Mapped[str | None] = mapped_column(String(50))  # clear, cloudy, foamy
    odor: Mapped[str | None] = mapped_column(String(50))  # normal, strong, sweet, foul
    
    # Volume
    volume_ml: Mapped[int | None] = mapped_column(Integer)
    stream_strength: Mapped[str | None] = mapped_column(String(20))  # weak, normal, strong
    
    # Symptoms
    pain_level: Mapped[int | None] = mapped_column(Integer)  # 0-10
    burning_sensation: Mapped[bool | None] = mapped_column(Boolean)
    urgency: Mapped[bool | None] = mapped_column(Boolean)
    frequency_increased: Mapped[bool | None] = mapped_column(Boolean)
    blood_present: Mapped[bool | None] = mapped_column(Boolean)
    
    # Context
    location: Mapped[str | None] = mapped_column(String(50))
    nighttime: Mapped[bool | None] = mapped_column(Boolean)  # nocturia tracking
    
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    user = relationship("User", back_populates="urination_logs")


class VomitingLog(Base):
    """Track vomiting episodes."""
    __tablename__ = "vomiting_logs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    log_date: Mapped[date] = mapped_column(Date, nullable=False)
    log_time: Mapped[time | None] = mapped_column(Time)
    
    # Characteristics
    volume: Mapped[str | None] = mapped_column(String(20))  # small, moderate, large
    color: Mapped[str | None] = mapped_column(String(50))
    consistency: Mapped[str | None] = mapped_column(String(50))
    
    # Contents
    contains_food: Mapped[bool | None] = mapped_column(Boolean)
    contains_bile: Mapped[bool | None] = mapped_column(Boolean)
    contains_blood: Mapped[bool | None] = mapped_column(Boolean)
    
    # Symptoms
    nausea_before: Mapped[bool | None] = mapped_column(Boolean)
    nausea_after: Mapped[bool | None] = mapped_column(Boolean)
    projectile: Mapped[bool | None] = mapped_column(Boolean)
    
    # Context
    trigger: Mapped[str | None] = mapped_column(Text)  # food, medication, illness, motion
    time_since_last_meal_hours: Mapped[float | None] = mapped_column()
    relief_after: Mapped[bool | None] = mapped_column(Boolean)
    
    # Associated symptoms
    fever: Mapped[bool | None] = mapped_column(Boolean)
    diarrhea: Mapped[bool | None] = mapped_column(Boolean)
    headache: Mapped[bool | None] = mapped_column(Boolean)
    dizziness: Mapped[bool | None] = mapped_column(Boolean)
    
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    user = relationship("User", back_populates="vomiting_logs")
