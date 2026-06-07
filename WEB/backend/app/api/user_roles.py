"""User roles & professional-profile endpoints.

Every user is a *patient* by default.  This module lets users claim additional
professional roles, attach professional profiles (credentials, practice info),
and query the full role catalog.
"""

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.user_roles import (
    UserRoleAssignment,
    ProfessionalProfile,
    UserRole,
    VerificationStatus,
    ROLE_CATEGORIES,
    role_display_name,
    role_category,
)
from app.schemas.user_roles import (
    RoleAssignmentCreate,
    RoleAssignmentResponse,
    ProfessionalProfileCreate,
    ProfessionalProfileUpdate,
    ProfessionalProfileResponse,
    UserPersonaSummary,
    RoleCatalogEntry,
    RoleCategoryInfo,
)

router = APIRouter()

_JSON_LIST_FIELDS = [
    "board_certifications", "hospital_affiliations", "clinical_languages",
    "telemedicine_platforms", "publications", "research_interests",
]


def _json_loads(val: str | None) -> list | None:
    if val is None:
        return None
    try:
        return json.loads(val)
    except Exception:
        return None


def _json_dumps(val: list | None) -> str | None:
    if val is None:
        return None
    return json.dumps(val)


def _assignment_to_response(ra: UserRoleAssignment) -> dict:
    prof = None
    if ra.professional_profiles:
        p = ra.professional_profiles[0]
        prof = _profile_to_response(p)
    return {
        "id": ra.id,
        "user_id": ra.user_id,
        "role": ra.role,
        "is_primary": ra.is_primary,
        "is_active": ra.is_active,
        "granted_at": ra.granted_at,
        "professional_profile": prof,
    }


def _profile_to_response(p: ProfessionalProfile) -> dict:
    d = {
        "id": p.id,
        "role_assignment_id": p.role_assignment_id,
        "license_number": p.license_number,
        "license_state": p.license_state,
        "license_country": p.license_country,
        "license_expiry": p.license_expiry,
        "npi_number": p.npi_number,
        "dea_number": p.dea_number,
        "board_certifications": _json_loads(p.board_certifications),
        "medical_school": p.medical_school,
        "degree": p.degree,
        "graduation_year": p.graduation_year,
        "residency_program": p.residency_program,
        "fellowship_program": p.fellowship_program,
        "specialty": p.specialty,
        "sub_specialty": p.sub_specialty,
        "years_of_experience": p.years_of_experience,
        "practice_name": p.practice_name,
        "practice_type": p.practice_type,
        "practice_address": p.practice_address,
        "practice_phone": p.practice_phone,
        "practice_email": p.practice_email,
        "practice_website": p.practice_website,
        "accepting_patients": p.accepting_patients,
        "hospital_affiliations": _json_loads(p.hospital_affiliations),
        "department": p.department,
        "title": p.title,
        "clinical_languages": _json_loads(p.clinical_languages),
        "telemedicine_available": p.telemedicine_available,
        "telemedicine_platforms": _json_loads(p.telemedicine_platforms),
        "verification_status": p.verification_status,
        "verification_date": p.verification_date,
        "professional_bio": p.professional_bio,
        "publications": _json_loads(p.publications),
        "research_interests": _json_loads(p.research_interests),
        "created_at": p.created_at,
        "updated_at": p.updated_at,
    }
    return d


def _derive_permissions(roles: list[str]) -> list[str]:
    """Derive feature-access permissions from active roles."""
    perms = {"patient_dashboard", "personal_health_records", "self_tracking"}
    for r in roles:
        cat = role_category(r)
        if cat in ("physician", "surgeon", "nursing", "therapy", "mental_health"):
            perms.update([
                "view_patient_records", "prescribe_medications",
                "order_labs", "clinical_notes", "treatment_plans",
                "referral_management",
            ])
        if cat in ("physician", "surgeon"):
            perms.update(["sign_orders", "discharge_summaries"])
        if cat == "nursing":
            perms.update(["nursing_assessments", "medication_administration", "care_coordination"])
        if cat == "mental_health":
            perms.update(["therapy_sessions", "psychological_assessments", "treatment_plans"])
        if cat == "social_work":
            perms.update(["social_assessments", "case_management", "resource_referrals", "care_coordination"])
        if cat == "pharmacy":
            perms.update(["medication_review", "drug_interaction_check", "dispensing"])
        if cat == "diagnostics":
            perms.update(["lab_results_entry", "diagnostic_reports"])
        if cat == "emergency":
            perms.update(["triage", "emergency_protocols", "ems_reports"])
        if cat == "public_health":
            perms.update(["population_analytics", "outbreak_tracking", "community_reports_admin", "health_program_management"])
        if cat == "administration":
            perms.update([
                "user_management", "facility_management", "scheduling",
                "billing_overview", "quality_metrics", "compliance_reports",
                "staff_management",
            ])
        if cat == "dental":
            perms.update(["dental_records", "dental_imaging", "treatment_plans"])
        if cat == "allied_health":
            perms.update(["clinical_notes", "treatment_plans"])
        if cat == "research":
            perms.update(["research_data_access", "clinical_trials", "publications_management"])
    return sorted(perms)


# ── Role Catalog (reference data) ────────────────────────────────────

@router.get("/roles/catalog", response_model=list[RoleCategoryInfo])
async def get_role_catalog():
    """Return the full catalog of available roles, grouped by category."""
    result = []
    for cat_id, members in ROLE_CATEGORIES.items():
        roles = [
            RoleCatalogEntry(
                id=r,
                name=role_display_name(r),
                category=cat_id,
            )
            for r in members
        ]
        result.append(RoleCategoryInfo(
            id=cat_id,
            name=cat_id.replace("_", " ").title(),
            roles=roles,
        ))
    return result


@router.get("/roles/categories")
async def get_role_categories():
    """Return just the category list."""
    return [
        {"id": k, "name": k.replace("_", " ").title(), "count": len(v)}
        for k, v in ROLE_CATEGORIES.items()
    ]


# ── User Persona ─────────────────────────────────────────────────────

@router.get("/roles/me", response_model=UserPersonaSummary)
async def get_my_persona(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the current user's full persona summary."""
    result = await db.execute(
        select(UserRoleAssignment)
        .where(
            UserRoleAssignment.user_id == current_user.id,
            UserRoleAssignment.is_active == True,
        )
        .options(selectinload(UserRoleAssignment.professional_profiles))
    )
    assignments = result.scalars().all()

    active_roles = ["patient"] + [a.role for a in assignments if a.role != "patient"]
    primary = next((a.role for a in assignments if a.is_primary), "patient")
    cats = list({role_category(r) for r in active_roles if role_category(r)})
    is_pro = any(r != "patient" for r in active_roles)

    role_details = [_assignment_to_response(a) for a in assignments]

    return UserPersonaSummary(
        user_id=current_user.id,
        full_name=current_user.full_name,
        email=current_user.email,
        primary_role=primary,
        active_roles=active_roles,
        role_details=role_details,
        is_healthcare_professional=is_pro,
        role_categories=sorted(cats),
        permissions=_derive_permissions(active_roles),
    )


# ── Role Assignments CRUD ────────────────────────────────────────────

@router.get("/roles", response_model=list[RoleAssignmentResponse])
async def list_my_roles(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all role assignments for the current user."""
    result = await db.execute(
        select(UserRoleAssignment)
        .where(UserRoleAssignment.user_id == current_user.id)
        .options(selectinload(UserRoleAssignment.professional_profiles))
        .order_by(UserRoleAssignment.is_primary.desc(), UserRoleAssignment.granted_at)
    )
    return [_assignment_to_response(a) for a in result.scalars().all()]


@router.post("/roles", response_model=RoleAssignmentResponse, status_code=201)
async def add_role(
    body: RoleAssignmentCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Claim a new professional role."""
    # Validate role value
    try:
        UserRole(body.role)
    except ValueError:
        raise HTTPException(400, f"Invalid role: {body.role}")

    # Check duplicate
    existing = await db.execute(
        select(UserRoleAssignment).where(
            UserRoleAssignment.user_id == current_user.id,
            UserRoleAssignment.role == body.role,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(400, f"Role '{body.role}' already assigned")

    # If setting as primary, un-primary others
    if body.is_primary:
        others = await db.execute(
            select(UserRoleAssignment).where(
                UserRoleAssignment.user_id == current_user.id,
                UserRoleAssignment.is_primary == True,
            )
        )
        for o in others.scalars().all():
            o.is_primary = False

    ra = UserRoleAssignment(
        user_id=current_user.id,
        role=body.role,
        is_primary=body.is_primary,
    )
    db.add(ra)
    await db.flush()
    await db.refresh(ra, attribute_names=["professional_profiles"])
    return _assignment_to_response(ra)


@router.delete("/roles/{role_id}", status_code=204)
async def remove_role(
    role_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a role assignment (and associated professional profile)."""
    result = await db.execute(
        select(UserRoleAssignment).where(
            UserRoleAssignment.id == role_id,
            UserRoleAssignment.user_id == current_user.id,
        )
    )
    ra = result.scalar_one_or_none()
    if not ra:
        raise HTTPException(404, "Role assignment not found")
    await db.delete(ra)
    await db.flush()


@router.put("/roles/{role_id}/primary", response_model=RoleAssignmentResponse)
async def set_primary_role(
    role_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Set a role as the primary role."""
    result = await db.execute(
        select(UserRoleAssignment).where(
            UserRoleAssignment.id == role_id,
            UserRoleAssignment.user_id == current_user.id,
        )
        .options(selectinload(UserRoleAssignment.professional_profiles))
    )
    ra = result.scalar_one_or_none()
    if not ra:
        raise HTTPException(404, "Role assignment not found")

    # Un-primary all others
    others = await db.execute(
        select(UserRoleAssignment).where(
            UserRoleAssignment.user_id == current_user.id,
            UserRoleAssignment.is_primary == True,
        )
    )
    for o in others.scalars().all():
        o.is_primary = False

    ra.is_primary = True
    await db.flush()
    await db.refresh(ra, attribute_names=["professional_profiles"])
    return _assignment_to_response(ra)


# ── Professional Profile CRUD ────────────────────────────────────────

@router.get("/roles/{role_id}/profile", response_model=ProfessionalProfileResponse)
async def get_professional_profile(
    role_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the professional profile for a specific role assignment."""
    result = await db.execute(
        select(ProfessionalProfile)
        .join(UserRoleAssignment)
        .where(
            UserRoleAssignment.id == role_id,
            UserRoleAssignment.user_id == current_user.id,
        )
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(404, "Professional profile not found")
    return _profile_to_response(profile)


@router.put("/roles/{role_id}/profile", response_model=ProfessionalProfileResponse)
async def upsert_professional_profile(
    role_id: int,
    body: ProfessionalProfileCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create or update the professional profile for a role assignment."""
    # Verify ownership
    ra_result = await db.execute(
        select(UserRoleAssignment).where(
            UserRoleAssignment.id == role_id,
            UserRoleAssignment.user_id == current_user.id,
        )
    )
    ra = ra_result.scalar_one_or_none()
    if not ra:
        raise HTTPException(404, "Role assignment not found")

    # Find existing profile
    prof_result = await db.execute(
        select(ProfessionalProfile).where(ProfessionalProfile.role_assignment_id == role_id)
    )
    profile = prof_result.scalar_one_or_none()

    data = body.model_dump(exclude_unset=True)
    # Convert list fields to JSON strings
    for f in _JSON_LIST_FIELDS:
        if f in data and data[f] is not None:
            data[f] = json.dumps(data[f])

    if profile:
        for k, v in data.items():
            setattr(profile, k, v)
    else:
        profile = ProfessionalProfile(role_assignment_id=role_id, **data)
        db.add(profile)

    await db.flush()
    await db.refresh(profile)
    return _profile_to_response(profile)


@router.patch("/roles/{role_id}/profile", response_model=ProfessionalProfileResponse)
async def patch_professional_profile(
    role_id: int,
    body: ProfessionalProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Partially update the professional profile."""
    prof_result = await db.execute(
        select(ProfessionalProfile)
        .join(UserRoleAssignment)
        .where(
            UserRoleAssignment.id == role_id,
            UserRoleAssignment.user_id == current_user.id,
        )
    )
    profile = prof_result.scalar_one_or_none()
    if not profile:
        raise HTTPException(404, "Professional profile not found")

    data = body.model_dump(exclude_unset=True)
    for f in _JSON_LIST_FIELDS:
        if f in data and data[f] is not None:
            data[f] = json.dumps(data[f])

    for k, v in data.items():
        setattr(profile, k, v)

    await db.flush()
    await db.refresh(profile)
    return _profile_to_response(profile)
