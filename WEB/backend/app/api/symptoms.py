"""Symptom log CRUD endpoints (Basis collection domain: symptoms)."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.conditions import SymptomLog
from app.schemas.symptoms import SymptomLogCreate, SymptomLogUpdate, SymptomLogResponse

router = APIRouter()


@router.get("/", response_model=list[SymptomLogResponse])
async def list_symptoms(
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(SymptomLog).where(SymptomLog.user_id == current_user.id)
    if start_date:
        query = query.where(SymptomLog.log_date >= start_date)
    if end_date:
        query = query.where(SymptomLog.log_date <= end_date)
    query = query.order_by(SymptomLog.log_date.desc(), SymptomLog.id.desc())
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/", response_model=SymptomLogResponse, status_code=201)
async def create_symptom(
    entry_in: SymptomLogCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    entry = SymptomLog(**entry_in.model_dump(), user_id=current_user.id)
    db.add(entry)
    await db.flush()
    await db.refresh(entry)
    return entry


@router.get("/{entry_id}", response_model=SymptomLogResponse)
async def get_symptom(
    entry_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SymptomLog).where(SymptomLog.id == entry_id, SymptomLog.user_id == current_user.id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Symptom log not found")
    return entry


@router.patch("/{entry_id}", response_model=SymptomLogResponse)
async def update_symptom(
    entry_id: int,
    updates: SymptomLogUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SymptomLog).where(SymptomLog.id == entry_id, SymptomLog.user_id == current_user.id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Symptom log not found")
    for field, value in updates.model_dump(exclude_unset=True).items():
        setattr(entry, field, value)
    await db.flush()
    await db.refresh(entry)
    return entry


@router.delete("/{entry_id}", status_code=204)
async def delete_symptom(
    entry_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SymptomLog).where(SymptomLog.id == entry_id, SymptomLog.user_id == current_user.id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Symptom log not found")
    await db.delete(entry)
    await db.flush()
