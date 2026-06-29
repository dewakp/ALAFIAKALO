"""Physician Directory schemas (Pydantic v2)."""

from datetime import datetime
from pydantic import BaseModel, Field


# ── Physician ──────────────────────────────────────────────────────

class PhysicianCreate(BaseModel):
    full_name: str
    specialty: str
    specialty_category: str | None = None
    credentials: str | None = None
    npi_number: str | None = None
    license_number: str | None = None

    phone: str | None = None
    email: str | None = None
    website: str | None = None

    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    state_province: str | None = None
    postal_code: str | None = None
    country: str | None = None
    latitude: float | None = None
    longitude: float | None = None

    facility_name: str | None = None
    accepting_new_patients: bool | None = None
    telehealth_available: bool | None = None
    languages_spoken: str | None = None
    operating_hours: str | None = None
    insurance_accepted: str | None = None


class PhysicianUpdate(BaseModel):
    full_name: str | None = None
    specialty: str | None = None
    specialty_category: str | None = None
    credentials: str | None = None
    npi_number: str | None = None
    license_number: str | None = None

    phone: str | None = None
    email: str | None = None
    website: str | None = None

    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    state_province: str | None = None
    postal_code: str | None = None
    country: str | None = None
    latitude: float | None = None
    longitude: float | None = None

    facility_name: str | None = None
    accepting_new_patients: bool | None = None
    telehealth_available: bool | None = None
    languages_spoken: str | None = None
    operating_hours: str | None = None
    insurance_accepted: str | None = None


class PhysicianResponse(BaseModel):
    id: int
    full_name: str
    specialty: str
    specialty_category: str | None = None
    credentials: str | None = None
    npi_number: str | None = None
    license_number: str | None = None

    phone: str | None = None
    email: str | None = None
    website: str | None = None

    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    state_province: str | None = None
    postal_code: str | None = None
    country: str | None = None
    latitude: float | None = None
    longitude: float | None = None

    facility_name: str | None = None
    accepting_new_patients: bool | None = None
    telehealth_available: bool | None = None
    languages_spoken: str | None = None
    operating_hours: str | None = None
    insurance_accepted: str | None = None

    average_rating: float | None = 0.0
    review_count: int = 0
    source: str = "user_contributed"
    is_verified: bool = False
    status: str = "unverified"

    # Clinician type + license verification (gates patient association)
    clinician_role: str = "physician"
    license_state: str | None = None
    primary_source: str | None = None
    verification_status: str = "quarantined"
    credential_verified: bool = False

    created_at: datetime

    model_config = {"from_attributes": True}


# ── Saved Physician ───────────────────────────────────────────────

class SavePhysicianRequest(BaseModel):
    physician_id: int
    nickname: str | None = None
    notes: str | None = None
    is_primary_care: bool = False
    relationship_type: str | None = None


class SavedPhysicianUpdate(BaseModel):
    nickname: str | None = None
    notes: str | None = None
    is_primary_care: bool | None = None
    relationship_type: str | None = None


class SavedPhysicianResponse(BaseModel):
    id: int
    user_id: int
    physician_id: int
    nickname: str | None = None
    notes: str | None = None
    is_primary_care: bool = False
    relationship_type: str | None = None
    created_at: datetime
    physician: PhysicianResponse | None = None

    model_config = {"from_attributes": True}


# ── Reviews ────────────────────────────────────────────────────────

class ReviewCreate(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    title: str | None = None
    review_text: str | None = None
    is_anonymous: bool = False


class ReviewUpdate(BaseModel):
    rating: int | None = Field(None, ge=1, le=5)
    title: str | None = None
    review_text: str | None = None
    is_anonymous: bool | None = None


class ReviewResponse(BaseModel):
    id: int
    user_id: int
    physician_id: int
    rating: int
    title: str | None = None
    review_text: str | None = None
    is_anonymous: bool = False
    created_at: datetime
    reviewer_name: str | None = None

    model_config = {"from_attributes": True}


# ── Search / Geo ───────────────────────────────────────────────────

class PhysicianSearchParams(BaseModel):
    """Query parameters for searching physicians."""
    q: str | None = None                      # free-text name search
    specialty: str | None = None
    specialty_category: str | None = None
    city: str | None = None
    state_province: str | None = None
    country: str | None = None
    latitude: float | None = None             # center for radius search
    longitude: float | None = None
    radius_km: float = 50.0                   # default 50 km radius
    accepting_new_patients: bool | None = None
    telehealth_available: bool | None = None
    min_rating: float | None = None
    verified_only: bool = False
    limit: int = Field(50, ge=1, le=200)
    offset: int = Field(0, ge=0)


class GeoSearchResult(BaseModel):
    """A nearby physician search result with distance."""
    physician: PhysicianResponse
    distance_km: float | None = None


class NearbySearchResponse(BaseModel):
    results: list[GeoSearchResult]
    total: int
    center_lat: float | None = None
    center_lon: float | None = None
    radius_km: float


class GeocodingResult(BaseModel):
    """Result from the free geocoding service."""
    display_name: str
    latitude: float
    longitude: float
    address_type: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    postal_code: str | None = None


# ── Specialty Taxonomy ─────────────────────────────────────────────

class SpecialtyCategoryResponse(BaseModel):
    categories: dict[str, list[str]]
