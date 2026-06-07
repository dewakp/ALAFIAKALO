"""Physician Directory models.

Provides the data layer for physician directory management:
- Physician: global directory of healthcare providers (crowd-sourced + admin-curated)
- SavedPhysician: per-user bookmarks with personal notes
- PhysicianReview: user reviews and ratings

Geo-search powered by free OpenStreetMap / Nominatim (backend),
with platform-native map rendering (Leaflet web, MapKit iOS, OSMDroid Android).
"""

from datetime import datetime, timezone
from enum import Enum as PyEnum

from sqlalchemy import (
    String, Boolean, DateTime, Text, Float, Integer,
    ForeignKey, Index, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


# ── Enums ──────────────────────────────────────────────────────────

class PhysicianSource(str, PyEnum):
    """How the physician record was created."""
    user_contributed = "user_contributed"
    admin_curated = "admin_curated"
    imported = "imported"            # bulk/migration import (e.g. from Alafia)
    osm = "osm"                      # discovered via OpenStreetMap / Overpass


class PhysicianStatus(str, PyEnum):
    active = "active"
    inactive = "inactive"
    unverified = "unverified"


# ── Specialty Taxonomy ─────────────────────────────────────────────

SPECIALTY_CATEGORIES: dict[str, list[str]] = {
    "Primary Care": [
        "Family Medicine", "Internal Medicine", "General Practice",
        "Pediatrics", "Geriatrics",
    ],
    "Surgical": [
        "General Surgery", "Orthopedic Surgery", "Cardiothoracic Surgery",
        "Neurosurgery", "Plastic Surgery", "Urology", "Vascular Surgery",
        "Ophthalmology",
    ],
    "Medical Specialties": [
        "Cardiology", "Dermatology", "Endocrinology",
        "Gastroenterology", "Hematology", "Infectious Disease",
        "Nephrology", "Neurology", "Oncology", "Pulmonology",
        "Rheumatology", "Allergy & Immunology",
    ],
    "Mental Health": [
        "Psychiatry", "Psychology", "Clinical Social Work",
        "Addiction Medicine",
    ],
    "Women's Health": [
        "Obstetrics & Gynecology", "Reproductive Endocrinology",
        "Maternal-Fetal Medicine",
    ],
    "Rehabilitation": [
        "Physical Medicine & Rehabilitation", "Physical Therapy",
        "Occupational Therapy", "Speech-Language Pathology",
    ],
    "Diagnostic": [
        "Radiology", "Pathology", "Nuclear Medicine",
        "Clinical Laboratory",
    ],
    "Dental": [
        "General Dentistry", "Orthodontics", "Periodontics",
        "Oral Surgery", "Endodontics",
    ],
    "Other": [
        "Emergency Medicine", "Anesthesiology", "Pain Management",
        "Sports Medicine", "Nutrition & Dietetics", "Pharmacy",
        "Podiatry", "Optometry", "Audiology", "Chiropractic",
        "Traditional Medicine", "Naturopathy", "Acupuncture",
    ],
}

ALL_SPECIALTIES: list[str] = sorted(
    s for group in SPECIALTY_CATEGORIES.values() for s in group
)


# ── Physician (global directory) ───────────────────────────────────

class Physician(Base):
    __tablename__ = "physicians"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Identity
    full_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    specialty: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    specialty_category: Mapped[str | None] = mapped_column(String(100))
    credentials: Mapped[str | None] = mapped_column(String(100))          # MD, DO, DDS, NP …
    npi_number: Mapped[str | None] = mapped_column(String(20), unique=True)  # US NPI
    license_number: Mapped[str | None] = mapped_column(String(50))

    # Contact
    phone: Mapped[str | None] = mapped_column(String(30))
    email: Mapped[str | None] = mapped_column(String(255))
    website: Mapped[str | None] = mapped_column(Text)

    # Location
    address_line1: Mapped[str | None] = mapped_column(String(255))
    address_line2: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(100), index=True)
    state_province: Mapped[str | None] = mapped_column(String(100))
    postal_code: Mapped[str | None] = mapped_column(String(20))
    country: Mapped[str | None] = mapped_column(String(100), index=True)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)

    # Practice Details
    facility_name: Mapped[str | None] = mapped_column(String(255))
    accepting_new_patients: Mapped[bool | None] = mapped_column(Boolean)
    telehealth_available: Mapped[bool | None] = mapped_column(Boolean)
    languages_spoken: Mapped[str | None] = mapped_column(Text)            # JSON array or CSV
    operating_hours: Mapped[str | None] = mapped_column(Text)             # JSON
    insurance_accepted: Mapped[str | None] = mapped_column(Text)          # JSON array

    # Aggregated ratings (computed)
    average_rating: Mapped[float | None] = mapped_column(Float, default=0.0)
    review_count: Mapped[int] = mapped_column(Integer, default=0)

    # Provenance
    source: Mapped[str] = mapped_column(
        String(30), default=PhysicianSource.user_contributed.value
    )
    source_id: Mapped[str | None] = mapped_column(String(255))           # external ID (OSM node, etc.)
    contributed_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL")
    )
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(
        String(20), default=PhysicianStatus.unverified.value
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    saved_by_users = relationship("SavedPhysician", back_populates="physician", cascade="all, delete-orphan")
    reviews = relationship("PhysicianReview", back_populates="physician", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_physicians_geo", "latitude", "longitude"),
        Index("ix_physicians_specialty_city", "specialty", "city"),
    )


# ── SavedPhysician (per-user bookmark) ─────────────────────────────

class SavedPhysician(Base):
    __tablename__ = "saved_physicians"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    physician_id: Mapped[int] = mapped_column(Integer, ForeignKey("physicians.id", ondelete="CASCADE"), nullable=False)

    # Personal annotations
    nickname: Mapped[str | None] = mapped_column(String(100))
    notes: Mapped[str | None] = mapped_column(Text)
    is_primary_care: Mapped[bool] = mapped_column(Boolean, default=False)
    relationship_type: Mapped[str | None] = mapped_column(String(50))     # PCP, specialist, dentist, …

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    user = relationship("User", backref="saved_physicians")
    physician = relationship("Physician", back_populates="saved_by_users")

    __table_args__ = (
        UniqueConstraint("user_id", "physician_id", name="uq_user_physician"),
    )


# ── PhysicianReview ────────────────────────────────────────────────

class PhysicianReview(Base):
    __tablename__ = "physician_reviews"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    physician_id: Mapped[int] = mapped_column(Integer, ForeignKey("physicians.id", ondelete="CASCADE"), nullable=False)

    rating: Mapped[int] = mapped_column(Integer, nullable=False)          # 1-5
    title: Mapped[str | None] = mapped_column(String(255))
    review_text: Mapped[str | None] = mapped_column(Text)
    is_anonymous: Mapped[bool] = mapped_column(Boolean, default=False)

    # Moderation
    is_approved: Mapped[bool] = mapped_column(Boolean, default=True)
    reported: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    user = relationship("User", backref="physician_reviews")
    physician = relationship("Physician", back_populates="reviews")

    __table_args__ = (
        UniqueConstraint("user_id", "physician_id", name="uq_user_physician_review"),
        Index("ix_physician_reviews_physician", "physician_id"),
    )
