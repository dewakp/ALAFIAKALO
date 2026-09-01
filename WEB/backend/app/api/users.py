"""User profile endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.units import units_for_locale
from app.core import units
import logging

logger = logging.getLogger(__name__)
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


def _age_years(dob: str | None) -> float | None:
    """Whole years from the String(10) date_of_birth column, or None."""
    if not dob:
        return None
    try:
        from datetime import date as _date
        y, m, d = (int(x) for x in str(dob)[:10].split("-"))
        born = _date(y, m, d)
    except (ValueError, TypeError):
        return None
    today = _date.today()
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


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

    # ── Units travel with the value ───────────────────────────────────────
    # The patient's locale sets their default system, they may change it in
    # Profile and toggle freely, and a reading can arrive in whatever unit the
    # device in front of them printed. So the client may name the unit and the
    # backend converts to what the column stores. A value with no unit is taken
    # as canonical — the field name says which.
    height_unit = changed.pop("height_unit", None)
    weight_unit = changed.pop("weight_unit", None)
    acknowledged = bool(changed.pop("acknowledge_unusual", None))
    try:
        if "height_cm" in changed:
            changed["height_cm"] = units.to_canonical(
                changed["height_cm"], "length", height_unit)
        for field in ("current_weight_kg", "target_weight_kg"):
            if field in changed:
                changed[field] = units.to_canonical(
                    changed[field], "mass", weight_unit)
    except units.UnknownUnitError as exc:
        # Naming a unit we cannot read must fail loudly. Falling back to
        # "assume metric" is precisely how a number lands in the wrong unit.
        raise HTTPException(status_code=422, detail=str(exc))

    # A BARE height is checked against this patient's AGE, not a constant.
    # 70 cm is a real height for a one-year-old and impossible for the
    # 52-year-old this was found on, where 70 inches (178 cm) is unremarkable.
    # An explicit unit is always obeyed — this only fills in a missing one.
    age_years = _age_years(current_user.date_of_birth)
    if height_unit is None and not acknowledged and changed.get("height_cm") is not None:
        inferred = units.infer_length_unit(changed["height_cm"], age_years)
        if inferred:
            original = changed["height_cm"]
            changed["height_cm"] = units.to_canonical(original, "length", inferred)
            logger.info(
                "user %s: height %s read as %s (%.1f cm) — impossible as cm at age %s",
                current_user.id, original, inferred, changed["height_cm"], age_years,
            )

    # Whatever survives must still be possible for someone this age.
    height = changed.get("height_cm")
    if height is not None and not acknowledged:
        low, high = units.plausible_height_range_cm(age_years)
        if not (low <= float(height) <= high):
            raise HTTPException(
                status_code=422,
                detail=(
                    f"A height of {height} cm is not possible"
                    + (f" at age {age_years:.0f}" if age_years is not None else "")
                    + f" (expected {low:.0f}-{high:.0f} cm). "
                    "Send height_unit if the value was not in centimetres, or "
                    "acknowledge_unusual=true if it is genuinely correct."
                ),
            )

    for field, low, high, label in (
        ("current_weight_kg", 0.5, 700.0, "weight"),
        ("target_weight_kg", 0.5, 700.0, "target weight"),
    ):
        value = changed.get(field)
        if value is not None and not (low <= float(value) <= high):
            raise HTTPException(
                status_code=422,
                detail=(
                    f"{label} of {value} is outside the plausible range "
                    f"({low}-{high} kg)."
                    + ("" if weight_unit else
                       " Send weight_unit alongside the value if it was not metric.")
                ),
            )

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
