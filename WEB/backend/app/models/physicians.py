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
    String, Boolean, DateTime, Text, Float, Integer, JSON,
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


class EntityType(str, PyEnum):
    """A directory record is either a licensed clinician (an individual) or a facility/place.

    Facilities (hospitals, pharmacies, clinics — e.g. from OSM) are NOT clinicians:
    they are never license-verified as individuals and never a patient's clinician.
    """
    clinician = "clinician"
    facility = "facility"


class ClinicianRole(str, PyEnum):
    """The kind of clinician — the directory holds all of them, not just physicians."""
    physician = "physician"
    nurse = "nurse"
    nurse_practitioner = "nurse_practitioner"
    physician_assistant = "physician_assistant"
    dietitian = "dietitian"
    pharmacist = "pharmacist"
    therapist = "therapist"            # PT / OT / SLP / RT
    mental_health = "mental_health"    # psychologist / counselor / social worker
    dentist = "dentist"
    optometrist = "optometrist"
    podiatrist = "podiatrist"
    chiropractor = "chiropractor"
    midwife = "midwife"
    other = "other"


class VerificationStatus(str, PyEnum):
    """License-verification state machine — gates patient association.

    quarantined       — no license on record; held, never shown to patients.
    license_on_record — license present from a non-trusted source; awaits admin.
    verified          — patient-associable (auto for CMS+license, else admin).
    rejected          — admin rejected; never associable.
    """
    quarantined = "quarantined"
    license_on_record = "license_on_record"
    verified = "verified"
    rejected = "rejected"


# Sources we trust enough to auto-verify a clinician that carries a license number.
TRUSTED_LICENSE_SOURCES = {"cms_nppes"}


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
    location_precision: Mapped[str | None] = mapped_column(String(20))  # exact | approximate

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

    # Entity kind: a licensed clinician (individual) vs a facility/place.
    entity_type: Mapped[str] = mapped_column(
        String(20), default=EntityType.clinician.value, index=True
    )

    # Clinician type + license verification workflow ------------------------
    clinician_role: Mapped[str | None] = mapped_column(
        String(40), default=ClinicianRole.physician.value, index=True
    )
    license_state: Mapped[str | None] = mapped_column(String(50))
    primary_source: Mapped[str | None] = mapped_column(String(40), index=True)

    # The gate: only `credential_verified` clinicians may be linked to a patient.
    verification_status: Mapped[str] = mapped_column(
        String(30), default=VerificationStatus.quarantined.value, index=True
    )
    credential_verified: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    verified_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL")
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verification_notes: Mapped[str | None] = mapped_column(Text)
    held_reason: Mapped[str | None] = mapped_column(String(80))

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


# ── ClinicianSourceRecord (provenance — one row per source that knows them) ──

class ClinicianSourceRecord(Base):
    """Where a directory record's data came from. Enables dedup + multi-source merge."""
    __tablename__ = "clinician_source_records"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    physician_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("physicians.id", ondelete="CASCADE"), index=True
    )
    source: Mapped[str] = mapped_column(String(40), nullable=False)        # cms_nppes, osm, …
    source_uid: Mapped[str] = mapped_column(String(64), nullable=False)    # NPI / external id
    content_hash: Mapped[str | None] = mapped_column(String(64))           # change detection
    raw_payload: Mapped[dict | None] = mapped_column(JSON)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        UniqueConstraint("source", "source_uid", name="uq_clinician_source_uid"),
        Index("ix_clinician_source_records_uid", "source", "source_uid"),
    )


# ── ClinicianIngestCandidate (quarantine + dedup queue) ─────────────────────

class ClinicianIngestCandidate(Base):
    """A normalized record discovered by the worker, before it joins the directory.

    Records without a license are parked here as `held_no_license` and never
    promoted to `physicians` until a license is confirmed.
    """
    __tablename__ = "clinician_ingest_candidates"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    source: Mapped[str] = mapped_column(String(40), nullable=False)
    source_uid: Mapped[str] = mapped_column(String(64), nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(64))

    # Normalized fields
    npi_number: Mapped[str | None] = mapped_column(String(20), index=True)
    full_name: Mapped[str | None] = mapped_column(String(255))
    clinician_role: Mapped[str | None] = mapped_column(String(40))
    specialty: Mapped[str | None] = mapped_column(String(150))
    credentials: Mapped[str | None] = mapped_column(String(100))
    license_number: Mapped[str | None] = mapped_column(String(50))
    license_state: Mapped[str | None] = mapped_column(String(50))
    city: Mapped[str | None] = mapped_column(String(100))
    state_province: Mapped[str | None] = mapped_column(String(100))
    postal_code: Mapped[str | None] = mapped_column(String(20))
    country: Mapped[str | None] = mapped_column(String(100))
    phone: Mapped[str | None] = mapped_column(String(30))

    # Outcome
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    # pending | held_no_license | inserted | merged_duplicate | rejected
    reason: Mapped[str | None] = mapped_column(String(255))
    matched_physician_id: Mapped[int | None] = mapped_column(Integer, index=True)
    raw_payload: Mapped[dict | None] = mapped_column(JSON)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_clinician_candidates_source_uid", "source", "source_uid"),
        Index("ix_clinician_candidates_status", "status"),
    )


# ── ClinicianVerificationLog (audit trail of the state machine) ─────────────

class ClinicianVerificationLog(Base):
    """Append-only audit of every verification-status transition."""
    __tablename__ = "clinician_verification_log"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    physician_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("physicians.id", ondelete="SET NULL"), index=True
    )
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    # ingested | auto_verified | held | admin_verified | admin_rejected | merged
    from_status: Mapped[str | None] = mapped_column(String(30))
    to_status: Mapped[str | None] = mapped_column(String(30))
    actor_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL")
    )
    source: Mapped[str | None] = mapped_column(String(40))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
