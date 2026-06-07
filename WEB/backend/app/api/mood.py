"""Mood / Mental Health CRUD endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import date

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.mood import MoodEntry
from app.schemas.mood import MoodEntryCreate, MoodEntryUpdate, MoodEntryResponse

router = APIRouter()


@router.get("/", response_model=list[MoodEntryResponse])
async def list_mood_entries(
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(MoodEntry).where(MoodEntry.user_id == current_user.id)
    if start_date:
        query = query.where(MoodEntry.entry_date >= start_date)
    if end_date:
        query = query.where(MoodEntry.entry_date <= end_date)
    query = query.order_by(MoodEntry.entry_date.desc())
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/", response_model=MoodEntryResponse, status_code=201)
async def create_mood_entry(
    entry_in: MoodEntryCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    entry = MoodEntry(**entry_in.model_dump(), user_id=current_user.id)
    db.add(entry)
    await db.flush()
    await db.refresh(entry)
    return entry


@router.get("/{entry_id}", response_model=MoodEntryResponse)
async def get_mood_entry(
    entry_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(MoodEntry).where(MoodEntry.id == entry_id, MoodEntry.user_id == current_user.id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Mood entry not found")
    return entry


@router.patch("/{entry_id}", response_model=MoodEntryResponse)
async def update_mood_entry(
    entry_id: int,
    updates: MoodEntryUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(MoodEntry).where(MoodEntry.id == entry_id, MoodEntry.user_id == current_user.id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Mood entry not found")
    for field, value in updates.model_dump(exclude_unset=True).items():
        setattr(entry, field, value)
    await db.flush()
    await db.refresh(entry)
    return entry


@router.delete("/{entry_id}", status_code=204)
async def delete_mood_entry(
    entry_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(MoodEntry).where(MoodEntry.id == entry_id, MoodEntry.user_id == current_user.id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Mood entry not found")
    raise HTTPException(
        status_code=403,
        detail="Mood entries cannot be deleted. You can modify this entry instead.",
    )
