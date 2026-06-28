"""User profile endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.units import units_for_locale
from app.models.user import User
from app.models.user_roles import UserRoleAssignment
from app.schemas.user import UserResponse, UserUpdate, IMMUTABLE_FIELDS

router = APIRouter()


def _enrich_user_response(user: User, assignments: list) -> dict:
    """Add persona fields to user dict."""
    active_roles = ["patient"] + [a.role for a in assignments if a.role != "patient" and a.is_active]
    primary = next((a.role for a in assignments if a.is_primary and a.is_active), "patient")
    is_pro = any(r != "patient" for r in active_roles)
    data = {c.key: getattr(user, c.key) for c in User.__table__.columns}
    data["primary_role"] = primary
    data["active_roles"] = active_roles
    data["is_healthcare_professional"] = is_pro
    return data


@router.get("/me", response_model=UserResponse)
async def get_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current user profile with persona info."""
    result = await db.execute(
        select(UserRoleAssignment).where(
            UserRoleAssignment.user_id == current_user.id,
        )
    )
    assignments = result.scalars().all()
    return _enrich_user_response(current_user, assignments)


@router.patch("/me", response_model=UserResponse)
async def update_profile(
    updates: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update current user profile.

    Set-once fields (date_of_birth, gender_at_birth, blood_type) can be
    provided initially but cannot be changed once a value exists.
    """
    changed = updates.model_dump(exclude_unset=True)

    # Enforce immutability on set-once fields
    blocked: list[str] = []
    for field in IMMUTABLE_FIELDS:
        if field not in changed:
            continue
        current_value = getattr(current_user, field, None)
        if current_value is not None and changed[field] != current_value:
            blocked.append(field)

    if blocked:
        raise HTTPException(
            status_code=422,
            detail=f"The following fields cannot be changed once set: {', '.join(blocked)}",
        )

    for field, value in changed.items():
        setattr(current_user, field, value)

    # When the locale changes, the measurement system follows it (metric
    # everywhere except US/Liberia/Myanmar) — unless the user explicitly set
    # preferred_units in the same request, in which case that choice wins.
    if "locale" in changed and "preferred_units" not in changed:
        current_user.preferred_units = units_for_locale(
            current_user.locale, current_user.country
        )

    # Mirror Profile insurance edits into the user's Insurance Plans (primary plan).
    if any(k in changed for k in ("insurance_id", "insurance_provider", "insurance_country")):
        from app.services.insurance_sync import sync_profile_to_plan
        await sync_profile_to_plan(db, current_user)

    await db.flush()
    await db.refresh(current_user)
    result = await db.execute(
        select(UserRoleAssignment).where(
            UserRoleAssignment.user_id == current_user.id,
        )
    )
    assignments = result.scalars().all()
    return _enrich_user_response(current_user, assignments)
