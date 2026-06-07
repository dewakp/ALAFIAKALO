"""Comprehensive vitals and biometrics tracking."""

from datetime import datetime, timezone, date, time

from sqlalchemy import String, Float, Integer, DateTime, Date, Time, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class VitalsLog(Base):
    """Comprehensive vital signs tracking."""
    __tablename__ = "vitals_logs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    log_date: Mapped[date] = mapped_column(Date, nullable=False)
    log_time: Mapped[time | None] = mapped_column(Time)
    
    # Blood Pressure
    blood_pressure_systolic: Mapped[int | None] = mapped_column(Integer)
    blood_pressure_diastolic: Mapped[int | None] = mapped_column(Integer)
    blood_pressure_position: Mapped[str | None] = mapped_column(String(50))  # sitting, standing, lying
    
    # Heart Rate
    heart_rate_bpm: Mapped[int | None] = mapped_column(Integer)
    heart_rhythm: Mapped[str | None] = mapped_column(String(50))  # regular, irregular
    
    # Temperature
    body_temperature_c: Mapped[float | None] = mapped_column(Float)
    temperature_location: Mapped[str | None] = mapped_column(String(50))  # oral, ear, forehead, rectal
    
    # Respiratory
    respiratory_rate: Mapped[int | None] = mapped_column(Integer)  # breaths per minute
    blood_oxygen_pct: Mapped[float | None] = mapped_column(Float)  # SpO2
    
    # Weight and Body Composition
    weight_kg: Mapped[float | None] = mapped_column(Float)
    height_cm: Mapped[float | None] = mapped_column(Float)
    bmi: Mapped[float | None] = mapped_column(Float)
    body_fat_pct: Mapped[float | None] = mapped_column(Float)
    muscle_mass_kg: Mapped[float | None] = mapped_column(Float)
    bone_mass_kg: Mapped[float | None] = mapped_column(Float)
    water_pct: Mapped[float | None] = mapped_column(Float)
    visceral_fat: Mapped[int | None] = mapped_column(Integer)
    
    # Measurements
    waist_circumference_cm: Mapped[float | None] = mapped_column(Float)
    hip_circumference_cm: Mapped[float | None] = mapped_column(Float)
    neck_circumference_cm: Mapped[float | None] = mapped_column(Float)
    chest_circumference_cm: Mapped[float | None] = mapped_column(Float)
    
    # Blood Glucose
    blood_glucose_mg_dl: Mapped[float | None] = mapped_column(Float)
    glucose_timing: Mapped[str | None] = mapped_column(String(50))  # fasting, post-meal, random
    
    # Other Vitals
    peak_flow: Mapped[float | None] = mapped_column(Float)  # L/min for asthma/COPD
    pain_level: Mapped[int | None] = mapped_column(Integer)  # 0-10 scale
    
    # Context
    measurement_device: Mapped[str | None] = mapped_column(String(100))
    measurement_location: Mapped[str | None] = mapped_column(String(100))  # home, clinic, hospital
    measured_by: Mapped[str | None] = mapped_column(String(100))  # self, nurse, doctor
    
    # Conditions during measurement
    fasting: Mapped[bool | None] = mapped_column()
    after_exercise: Mapped[bool | None] = mapped_column()
    after_medication: Mapped[bool | None] = mapped_column()
    stressed: Mapped[bool | None] = mapped_column()
    
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    user = relationship("User", back_populates="vitals_logs")
