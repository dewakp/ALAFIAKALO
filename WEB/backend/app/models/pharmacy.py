"""Pharmacy models – Prescription → Dispensing → Adherence lifecycle."""

import enum
from datetime import datetime, timezone, date

from sqlalchemy import (
    String, Integer, DateTime, Date, ForeignKey,
    Text, Boolean, Enum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


# ── Enums ────────────────────────────────────────────────────────────

class PrescriptionStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    ON_HOLD = "on_hold"


class DispenseStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY_FOR_PICKUP = "ready_for_pickup"
    DISPENSED = "dispensed"
    RETURNED = "returned"
    CANCELLED = "cancelled"


class AdherenceStatus(str, enum.Enum):
    TAKEN = "taken"
    MISSED = "missed"
    SKIPPED = "skipped"
    LATE = "late"


class RefillStatus(str, enum.Enum):
    REQUESTED = "requested"
    APPROVED = "approved"
    DENIED = "denied"
    FILLED = "filled"


# ── Prescription ─────────────────────────────────────────────────────

class Prescription(Base):
    """A physician creates a prescription for a patient."""
    __tablename__ = "prescriptions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    prescriber_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)

    # Medication details
    medication_name: Mapped[str] = mapped_column(String(255), nullable=False)
    rxnorm_code: Mapped[str | None] = mapped_column(String(20))
    dosage: Mapped[str | None] = mapped_column(String(100))
    dosage_unit: Mapped[str | None] = mapped_column(String(50))
    strength: Mapped[str | None] = mapped_column(String(100))
    form: Mapped[str | None] = mapped_column(String(50))  # tablet, capsule, liquid, injection
    route: Mapped[str | None] = mapped_column(String(50))  # oral, topical, IV, IM, SC
    frequency: Mapped[str | None] = mapped_column(String(100))  # BID, TID, Q8H, etc.
    duration_days: Mapped[int | None] = mapped_column(Integer)
    quantity: Mapped[int | None] = mapped_column(Integer)
    refills_authorized: Mapped[int] = mapped_column(Integer, default=0)
    refills_remaining: Mapped[int] = mapped_column(Integer, default=0)

    # Clinical
    diagnosis: Mapped[str | None] = mapped_column(Text)
    instructions: Mapped[str | None] = mapped_column(Text)  # sig / patient instructions
    pharmacy_notes: Mapped[str | None] = mapped_column(Text)
    substitution_allowed: Mapped[bool] = mapped_column(Boolean, default=True)
    daw_code: Mapped[str | None] = mapped_column(String(10))  # Dispense As Written

    # Dates
    prescribed_date: Mapped[date] = mapped_column(Date, default=date.today)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)

    # Status
    status: Mapped[str] = mapped_column(
        Enum(PrescriptionStatus), default=PrescriptionStatus.ACTIVE
    )
    is_controlled_substance: Mapped[bool] = mapped_column(Boolean, default=False)
    dea_schedule: Mapped[str | None] = mapped_column(String(10))

    # Linked medication record
    medication_id: Mapped[int | None] = mapped_column(ForeignKey("medications.id"))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    patient = relationship("User", foreign_keys=[patient_id])
    prescriber = relationship("User", foreign_keys=[prescriber_id])
    medication = relationship("Medication", foreign_keys=[medication_id])
    dispenses = relationship("Dispense", back_populates="prescription", cascade="all, delete-orphan")
    refill_requests = relationship("RefillRequest", back_populates="prescription", cascade="all, delete-orphan")


# ── Dispense ─────────────────────────────────────────────────────────

class Dispense(Base):
    """A pharmacist dispenses medication against a prescription."""
    __tablename__ = "dispenses"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    prescription_id: Mapped[int] = mapped_column(ForeignKey("prescriptions.id"), nullable=False, index=True)
    pharmacist_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)

    quantity_dispensed: Mapped[int | None] = mapped_column(Integer)
    days_supply: Mapped[int | None] = mapped_column(Integer)
    ndc_code: Mapped[str | None] = mapped_column(String(20))  # National Drug Code
    lot_number: Mapped[str | None] = mapped_column(String(50))
    expiration_date: Mapped[date | None] = mapped_column(Date)
    manufacturer: Mapped[str | None] = mapped_column(String(255))
    is_generic: Mapped[bool] = mapped_column(Boolean, default=False)

    # Pharmacist review
    drug_utilization_review: Mapped[str | None] = mapped_column(Text)  # DUR notes
    clinical_notes: Mapped[str | None] = mapped_column(Text)
    counseling_provided: Mapped[bool] = mapped_column(Boolean, default=False)
    counseling_notes: Mapped[str | None] = mapped_column(Text)

    # Interaction checks
    interactions_checked: Mapped[bool] = mapped_column(Boolean, default=False)
    interactions_found: Mapped[str | None] = mapped_column(Text)  # JSON list
    allergy_checked: Mapped[bool] = mapped_column(Boolean, default=False)
    allergy_alerts: Mapped[str | None] = mapped_column(Text)

    status: Mapped[str] = mapped_column(
        Enum(DispenseStatus), default=DispenseStatus.PENDING
    )
    dispensed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    picked_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    prescription = relationship("Prescription", back_populates="dispenses")
    pharmacist = relationship("User", foreign_keys=[pharmacist_id])


# ── Adherence Log ────────────────────────────────────────────────────

class AdherenceLog(Base):
    """Patient records each medication take / miss."""
    __tablename__ = "adherence_logs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    prescription_id: Mapped[int] = mapped_column(ForeignKey("prescriptions.id"), nullable=False, index=True)

    scheduled_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actual_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(
        Enum(AdherenceStatus), default=AdherenceStatus.TAKEN
    )
    dose_taken: Mapped[str | None] = mapped_column(String(100))  # e.g. "500mg"
    notes: Mapped[str | None] = mapped_column(Text)
    side_effects_reported: Mapped[str | None] = mapped_column(Text)

    # Impact correlation fields (populated by AI/background)
    mood_before: Mapped[int | None] = mapped_column(Integer)  # 1-10
    mood_after: Mapped[int | None] = mapped_column(Integer)   # 1-10
    pain_before: Mapped[int | None] = mapped_column(Integer)  # 1-10
    pain_after: Mapped[int | None] = mapped_column(Integer)   # 1-10
    symptom_change: Mapped[str | None] = mapped_column(Text)  # JSON

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    patient = relationship("User", foreign_keys=[patient_id])
    prescription = relationship("Prescription")


# ── Medication Schedule ──────────────────────────────────────────────

class MedicationSchedule(Base):
    """Recurring schedule entries for a prescription."""
    __tablename__ = "medication_schedules"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    prescription_id: Mapped[int] = mapped_column(ForeignKey("prescriptions.id"), nullable=False, index=True)

    time_of_day: Mapped[str] = mapped_column(String(10), nullable=False)  # HH:MM
    days_of_week: Mapped[str | None] = mapped_column(String(50))  # "mon,tue,wed" or null=daily
    dose_label: Mapped[str | None] = mapped_column(String(100))  # "Morning dose", "Evening dose"
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    reminder_minutes_before: Mapped[int] = mapped_column(Integer, default=15)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    patient = relationship("User", foreign_keys=[patient_id])
    prescription = relationship("Prescription")


# ── Refill Request ───────────────────────────────────────────────────

class RefillRequest(Base):
    """Patient or pharmacist initiated refill request."""
    __tablename__ = "refill_requests"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    prescription_id: Mapped[int] = mapped_column(ForeignKey("prescriptions.id"), nullable=False, index=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    requested_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    status: Mapped[str] = mapped_column(
        Enum(RefillStatus), default=RefillStatus.REQUESTED
    )
    quantity_requested: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)
    denial_reason: Mapped[str | None] = mapped_column(Text)

    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    prescription = relationship("Prescription", back_populates="refill_requests")
    patient = relationship("User", foreign_keys=[patient_id])
    requested_by = relationship("User", foreign_keys=[requested_by_id])
    approved_by = relationship("User", foreign_keys=[approved_by_id])
