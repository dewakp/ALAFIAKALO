"""Lifestyle CRUD endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import date

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.lifestyle import LifestyleEntry
from app.schemas.lifestyle import LifestyleEntryCreate, LifestyleEntryUpdate, LifestyleEntryResponse

router = APIRouter()


@router.get("/", response_model=list[LifestyleEntryResponse])
async def list_lifestyle_entries(
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(LifestyleEntry).where(LifestyleEntry.user_id == current_user.id)
    if start_date:
        query = query.where(LifestyleEntry.entry_date >= start_date)
    if end_date:
        query = query.where(LifestyleEntry.entry_date <= end_date)
    query = query.order_by(LifestyleEntry.entry_date.desc())
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/", response_model=LifestyleEntryResponse, status_code=201)
async def create_lifestyle_entry(
    entry_in: LifestyleEntryCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    entry = LifestyleEntry(**entry_in.model_dump(), user_id=current_user.id)
    db.add(entry)
    await db.flush()
    await db.refresh(entry)
    return entry


@router.get("/{entry_id}", response_model=LifestyleEntryResponse)
async def get_lifestyle_entry(
    entry_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(LifestyleEntry).where(LifestyleEntry.id == entry_id, LifestyleEntry.user_id == current_user.id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Lifestyle entry not found")
    return entry


@router.patch("/{entry_id}", response_model=LifestyleEntryResponse)
async def update_lifestyle_entry(
    entry_id: int,
    updates: LifestyleEntryUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(LifestyleEntry).where(LifestyleEntry.id == entry_id, LifestyleEntry.user_id == current_user.id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Lifestyle entry not found")
    for field, value in updates.model_dump(exclude_unset=True).items():
        setattr(entry, field, value)
    await db.flush()
    await db.refresh(entry)
    return entry


@router.delete("/{entry_id}", status_code=204)
async def delete_lifestyle_entry(
    entry_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(LifestyleEntry).where(LifestyleEntry.id == entry_id, LifestyleEntry.user_id == current_user.id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Lifestyle entry not found")
    raise HTTPException(
        status_code=403,
        detail="Lifestyle entries cannot be deleted. You can modify this entry instead.",
    )
