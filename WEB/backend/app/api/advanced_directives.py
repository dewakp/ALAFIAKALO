"""Advanced Directives CRUD endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.advanced_directives import AdvancedDirective
from app.schemas.advanced_directives import (
    AdvancedDirectiveCreate, AdvancedDirectiveUpdate, AdvancedDirectiveResponse,
)

router = APIRouter()


@router.get("/", response_model=AdvancedDirectiveResponse | None)
async def get_advanced_directive(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current user's advanced directive (one per user)."""
    result = await db.execute(
        select(AdvancedDirective).where(AdvancedDirective.user_id == current_user.id)
    )
    return result.scalar_one_or_none()


@router.post("/", response_model=AdvancedDirectiveResponse, status_code=201)
async def create_advanced_directive(
    data: AdvancedDirectiveCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create or update advanced directive."""
    result = await db.execute(
        select(AdvancedDirective).where(AdvancedDirective.user_id == current_user.id)
    )
    existing = result.scalar_one_or_none()

    if existing:
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(existing, field, value)
        await db.flush()
        await db.refresh(existing)
        return existing

    directive = AdvancedDirective(**data.model_dump(), user_id=current_user.id)
    db.add(directive)
    await db.flush()
    await db.refresh(directive)
    return directive


@router.put("/", response_model=AdvancedDirectiveResponse)
async def update_advanced_directive(
    data: AdvancedDirectiveUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AdvancedDirective).where(AdvancedDirective.user_id == current_user.id)
    )
    directive = result.scalar_one_or_none()
    if not directive:
        raise HTTPException(status_code=404, detail="No advanced directive found. Create one first.")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(directive, field, value)
    await db.flush()
    await db.refresh(directive)
    return directive


@router.delete("/", status_code=204)
async def delete_advanced_directive(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AdvancedDirective).where(AdvancedDirective.user_id == current_user.id)
    )
    directive = result.scalar_one_or_none()
    if not directive:
        raise HTTPException(status_code=404, detail="Not found")
    await db.delete(directive)
