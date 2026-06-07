"""Peritoneal Dialysis models — APD/CAPD exchanges and sessions."""

import enum
from datetime import datetime, timezone, date
from sqlalchemy import String, Float, DateTime, Date, ForeignKey, Text, Boolean, Integer, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class PDModality(str, enum.Enum):
    CAPD = "capd"
    APD = "apd"
    CCPD = "ccpd"


class EffluentClarity(str, enum.Enum):
    CLEAR = "clear"
    SLIGHTLY_CLOUDY = "slightly_cloudy"
    CLOUDY = "cloudy"
    BLOODY = "bloody"


class PDSession(Base):
    __tablename__ = "pd_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    condition_id: Mapped[int | None] = mapped_column(ForeignKey("chronic_conditions.id"))
    session_date: Mapped[date] = mapped_column(Date, nullable=False)
    modality: Mapped[str] = mapped_column(String(10), nullable=False, default="capd")

    # Pre & post vitals
    pre_weight_kg: Mapped[float | None] = mapped_column(Float)
    post_weight_kg: Mapped[float | None] = mapped_column(Float)
    target_uf_ml: Mapped[float | None] = mapped_column(Float)
    total_uf_ml: Mapped[float | None] = mapped_column(Float)
    pre_bp_systolic: Mapped[int | None] = mapped_column(Integer)
    pre_bp_diastolic: Mapped[int | None] = mapped_column(Integer)
    post_bp_systolic: Mapped[int | None] = mapped_column(Integer)
    post_bp_diastolic: Mapped[int | None] = mapped_column(Integer)
    pre_temp_f: Mapped[float | None] = mapped_column(Float)
    post_temp_f: Mapped[float | None] = mapped_column(Float)

    # APD machine settings
    machine_type: Mapped[str | None] = mapped_column(String(100))
    total_volume_ml: Mapped[float | None] = mapped_column(Float)
    fill_volume_ml: Mapped[float | None] = mapped_column(Float)
    number_of_cycles: Mapped[int | None] = mapped_column(Integer)
    therapy_time_hours: Mapped[float | None] = mapped_column(Float)
    last_fill_volume_ml: Mapped[float | None] = mapped_column(Float)

    # General
    exit_site_status: Mapped[str | None] = mapped_column(String(50))
    complications: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    user = relationship("User", backref="pd_sessions")
    exchanges = relationship("PDExchange", back_populates="session", cascade="all, delete-orphan", order_by="PDExchange.exchange_number")


class PDExchange(Base):
    __tablename__ = "pd_exchanges"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("pd_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    exchange_number: Mapped[int] = mapped_column(Integer, nullable=False)

    start_time: Mapped[str | None] = mapped_column(String(10))
    drain_start: Mapped[str | None] = mapped_column(String(10))
    drain_end: Mapped[str | None] = mapped_column(String(10))
    fill_end: Mapped[str | None] = mapped_column(String(10))

    solution_type: Mapped[str | None] = mapped_column(String(100))  # e.g. "1.5% Dextrose", "2.5%", "4.25%", "Icodextrin"
    inflow_volume_ml: Mapped[float | None] = mapped_column(Float)
    outflow_volume_ml: Mapped[float | None] = mapped_column(Float)
    uf_ml: Mapped[float | None] = mapped_column(Float)
    dwell_time_minutes: Mapped[int | None] = mapped_column(Integer)
    effluent_clarity: Mapped[str | None] = mapped_column(String(20), default="clear")
    effluent_color: Mapped[str | None] = mapped_column(String(50))
    notes: Mapped[str | None] = mapped_column(Text)

    session = relationship("PDSession", back_populates="exchanges")
