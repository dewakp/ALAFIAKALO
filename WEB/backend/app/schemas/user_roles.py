"""Schemas for user roles and professional profiles."""

from pydantic import BaseModel
from typing import Optional
from datetime import datetime


# ── Role Assignment ───────────────────────────────────────────────────

class RoleAssignmentCreate(BaseModel):
    role: str
    is_primary: bool = False


class RoleAssignmentResponse(BaseModel):
    id: int
    user_id: int
    role: str
    is_primary: bool
    is_active: bool
    granted_at: datetime | None = None
    professional_profile: Optional["ProfessionalProfileResponse"] = None

    model_config = {"from_attributes": True}


# ── Professional Profile ─────────────────────────────────────────────

class ProfessionalProfileCreate(BaseModel):
    # Credentials
    license_number: str | None = None
    license_state: str | None = None
    license_country: str | None = None
    license_expiry: str | None = None
    npi_number: str | None = None
    dea_number: str | None = None
    board_certifications: list[str] | None = None

    # Education
    medical_school: str | None = None
    degree: str | None = None
    graduation_year: int | None = None
    residency_program: str | None = None
    fellowship_program: str | None = None

    # Practice
    specialty: str | None = None
    sub_specialty: str | None = None
    years_of_experience: int | None = None
    practice_name: str | None = None
    practice_type: str | None = None
    practice_address: str | None = None
    practice_phone: str | None = None
    practice_email: str | None = None
    practice_website: str | None = None
    accepting_patients: bool | None = None

    # Hospital
    hospital_affiliations: list[str] | None = None
    department: str | None = None
    title: str | None = None

    # Languages
    clinical_languages: list[str] | None = None

    # Telemedicine
    telemedicine_available: bool = False
    telemedicine_platforms: list[str] | None = None

    # Bio
    professional_bio: str | None = None
    publications: list[str] | None = None
    research_interests: list[str] | None = None


class ProfessionalProfileUpdate(BaseModel):
    license_number: str | None = None
    license_state: str | None = None
    license_country: str | None = None
    license_expiry: str | None = None
    npi_number: str | None = None
    dea_number: str | None = None
    board_certifications: list[str] | None = None
    medical_school: str | None = None
    degree: str | None = None
    graduation_year: int | None = None
    residency_program: str | None = None
    fellowship_program: str | None = None
    specialty: str | None = None
    sub_specialty: str | None = None
    years_of_experience: int | None = None
    practice_name: str | None = None
    practice_type: str | None = None
    practice_address: str | None = None
    practice_phone: str | None = None
    practice_email: str | None = None
    practice_website: str | None = None
    accepting_patients: bool | None = None
    hospital_affiliations: list[str] | None = None
    department: str | None = None
    title: str | None = None
    clinical_languages: list[str] | None = None
    telemedicine_available: bool | None = None
    telemedicine_platforms: list[str] | None = None
    professional_bio: str | None = None
    publications: list[str] | None = None
    research_interests: list[str] | None = None


class ProfessionalProfileResponse(BaseModel):
    id: int
    role_assignment_id: int

    # Credentials
    license_number: str | None = None
    license_state: str | None = None
    license_country: str | None = None
    license_expiry: str | None = None
    npi_number: str | None = None
    dea_number: str | None = None
    board_certifications: list[str] | None = None

    # Education
    medical_school: str | None = None
    degree: str | None = None
    graduation_year: int | None = None
    residency_program: str | None = None
    fellowship_program: str | None = None

    # Practice
    specialty: str | None = None
    sub_specialty: str | None = None
    years_of_experience: int | None = None
    practice_name: str | None = None
    practice_type: str | None = None
    practice_address: str | None = None
    practice_phone: str | None = None
    practice_email: str | None = None
    practice_website: str | None = None
    accepting_patients: bool | None = None

    # Hospital
    hospital_affiliations: list[str] | None = None
    department: str | None = None
    title: str | None = None

    # Languages
    clinical_languages: list[str] | None = None

    # Telemedicine
    telemedicine_available: bool = False
    telemedicine_platforms: list[str] | None = None

    # Verification
    verification_status: str = "unverified"
    verification_date: datetime | None = None

    # Bio
    professional_bio: str | None = None
    publications: list[str] | None = None
    research_interests: list[str] | None = None

    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


# ── User Persona Summary ─────────────────────────────────────────────

class UserPersonaSummary(BaseModel):
    """Returned by /users/me — enriched with persona info."""
    user_id: int
    full_name: str
    email: str
    primary_role: str  # always at least "patient"
    active_roles: list[str]
    role_details: list[RoleAssignmentResponse]
    is_healthcare_professional: bool
    role_categories: list[str]  # e.g. ["physician", "administration"]
    permissions: list[str]  # derived feature-access list


# ── Role Catalog (reference data) ────────────────────────────────────

class RoleCatalogEntry(BaseModel):
    id: str
    name: str
    category: str
    description: str | None = None


class RoleCategoryInfo(BaseModel):
    id: str
    name: str
    roles: list[RoleCatalogEntry]
