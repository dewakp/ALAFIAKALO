"""Multi-insurance CRUD endpoints + locale-aware provider catalog."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.insurance import (
    Insurance,
    INSURANCE_PROVIDERS_BY_COUNTRY,
    COUNTRIES_BY_REGION,
    InsuranceRegion,
)
from app.schemas.insurance import InsuranceCreate, InsuranceUpdate, InsuranceResponse

router = APIRouter()


# ── Reference / catalog endpoints ─────────────────

@router.get("/regions")
async def list_regions():
    """Return all supported regions with their countries."""
    return COUNTRIES_BY_REGION


@router.get("/providers/{country_code}")
async def list_providers(country_code: str):
    """Return the insurance providers available for a given ISO country code."""
    country_code = country_code.upper()
    providers = INSURANCE_PROVIDERS_BY_COUNTRY.get(country_code)
    if providers is None:
        raise HTTPException(status_code=404, detail=f"No providers registered for country {country_code}")
    return providers


# ── User insurance CRUD ───────────────────────────

@router.get("/", response_model=list[InsuranceResponse])
async def list_insurances(
    active_only: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(Insurance).where(Insurance.user_id == current_user.id)
    if active_only:
        query = query.where(Insurance.is_active == True)
    query = query.order_by(Insurance.is_primary.desc(), Insurance.created_at.desc())
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/", response_model=InsuranceResponse, status_code=201)
async def create_insurance(
    ins_in: InsuranceCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # If the new plan is marked primary, demote existing primary plans
    if ins_in.is_primary:
        existing = await db.execute(
            select(Insurance).where(
                Insurance.user_id == current_user.id,
                Insurance.is_primary == True,
            )
        )
        for plan in existing.scalars().all():
            plan.is_primary = False

    ins = Insurance(**ins_in.model_dump(), user_id=current_user.id)
    db.add(ins)
    await db.flush()
    await db.refresh(ins)
    return ins


@router.get("/{ins_id}", response_model=InsuranceResponse)
async def get_insurance(
    ins_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Insurance).where(Insurance.id == ins_id, Insurance.user_id == current_user.id)
    )
    ins = result.scalar_one_or_none()
    if not ins:
        raise HTTPException(status_code=404, detail="Insurance plan not found")
    return ins


@router.patch("/{ins_id}", response_model=InsuranceResponse)
async def update_insurance(
    ins_id: int,
    updates: InsuranceUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Insurance).where(Insurance.id == ins_id, Insurance.user_id == current_user.id)
    )
    ins = result.scalar_one_or_none()
    if not ins:
        raise HTTPException(status_code=404, detail="Insurance plan not found")

    data = updates.model_dump(exclude_unset=True)

    # Handle primary promotion
    if data.get("is_primary"):
        existing = await db.execute(
            select(Insurance).where(
                Insurance.user_id == current_user.id,
                Insurance.is_primary == True,
                Insurance.id != ins_id,
            )
        )
        for plan in existing.scalars().all():
            plan.is_primary = False

    for field, value in data.items():
        setattr(ins, field, value)

    await db.flush()
    await db.refresh(ins)
    return ins


@router.delete("/{ins_id}", status_code=204)
async def delete_insurance(
    ins_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Insurance).where(Insurance.id == ins_id, Insurance.user_id == current_user.id)
    )
    ins = result.scalar_one_or_none()
    if not ins:
        raise HTTPException(status_code=404, detail="Insurance plan not found")
    await db.delete(ins)


@router.post("/{ins_id}/set-primary", response_model=InsuranceResponse)
async def set_primary_insurance(
    ins_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Promote a plan to primary and demote all others."""
    result = await db.execute(
        select(Insurance).where(Insurance.id == ins_id, Insurance.user_id == current_user.id)
    )
    ins = result.scalar_one_or_none()
    if not ins:
        raise HTTPException(status_code=404, detail="Insurance plan not found")

    # Demote others
    existing = await db.execute(
        select(Insurance).where(
            Insurance.user_id == current_user.id,
            Insurance.is_primary == True,
            Insurance.id != ins_id,
        )
    )
    for plan in existing.scalars().all():
        plan.is_primary = False

    ins.is_primary = True
    await db.flush()
    await db.refresh(ins)
    return ins
