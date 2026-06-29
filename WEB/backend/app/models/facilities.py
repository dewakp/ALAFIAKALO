"""Facility directory — places (NOT clinicians).

Physicians are humans; facilities are places they practice from. This is a
separate table from `physicians` on purpose: a hospital/clinic/pharmacy is never
a licensed individual and is never a patient's clinician. Sources like OpenStreetMap
populate facilities; clinicians (CMS NPPES) stay in `physicians`.

`physician_facilities` is the many-to-many "practices at" link between the two.
"""
from datetime import datetime, timezone
from enum import Enum as PyEnum

from sqlalchemy import (
    String, Boolean, DateTime, Float, Integer, ForeignKey, Index, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class FacilityType(str, PyEnum):
    hospital = "hospital"
    clinic = "clinic"
    pharmacy = "pharmacy"
    dental = "dental"
    doctors_office = "doctors_office"
    lab = "lab"
    imaging = "imaging"
    facility = "facility"          # generic / unknown


class Facility(Base):
    """A healthcare place (hospital, clinic, pharmacy, …)."""
    __tablename__ = "facilities"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    name: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    facility_type: Mapped[str] = mapped_column(
        String(60), default=FacilityType.facility.value, index=True)

    # Contact
    phone: Mapped[str | None] = mapped_column(String(30))
    website: Mapped[str | None] = mapped_column(String(500))

    # Location
    address_line1: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(100), index=True)
    state_province: Mapped[str | None] = mapped_column(String(100))
    postal_code: Mapped[str | None] = mapped_column(String(20))
    country: Mapped[str | None] = mapped_column(String(100), index=True)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    location_precision: Mapped[str | None] = mapped_column(String(20))  # exact | approximate

    # Provenance
    source: Mapped[str | None] = mapped_column(String(40), index=True)   # osm, …
    source_uid: Mapped[str | None] = mapped_column(String(64))

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc))

    practitioners = relationship("PhysicianFacility", back_populates="facility",
                                 cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("source", "source_uid", name="uq_facility_source_uid"),
        Index("ix_facilities_geo", "latitude", "longitude"),
    )


class PhysicianFacility(Base):
    """A clinician practices at a facility (many-to-many)."""
    __tablename__ = "physician_facilities"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    physician_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("physicians.id", ondelete="CASCADE"), nullable=False, index=True)
    facility_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("facilities.id", ondelete="CASCADE"), nullable=False, index=True)
    relationship_type: Mapped[str] = mapped_column(String(40), default="practices_at")
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    facility = relationship("Facility", back_populates="practitioners")

    __table_args__ = (
        UniqueConstraint("physician_id", "facility_id", name="uq_physician_facility"),
    )
