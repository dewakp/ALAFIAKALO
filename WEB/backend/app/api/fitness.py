"""Fitness CRUD endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import date

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.fitness import FitnessLog
from app.schemas.fitness import FitnessLogCreate, FitnessLogUpdate, FitnessLogResponse

router = APIRouter()


@router.get("/", response_model=list[FitnessLogResponse])
async def list_fitness_logs(
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    activity_type: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(FitnessLog).where(FitnessLog.user_id == current_user.id)
    if start_date:
        query = query.where(FitnessLog.log_date >= start_date)
    if end_date:
        query = query.where(FitnessLog.log_date <= end_date)
    if activity_type:
        query = query.where(FitnessLog.activity_type == activity_type)
    query = query.order_by(FitnessLog.log_date.desc())
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/", response_model=FitnessLogResponse, status_code=201)
async def create_fitness_log(
    log_in: FitnessLogCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    log = FitnessLog(**log_in.model_dump(), user_id=current_user.id)
    db.add(log)
    await db.flush()
    await db.refresh(log)
    return log


@router.get("/{log_id}", response_model=FitnessLogResponse)
async def get_fitness_log(
    log_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(FitnessLog).where(FitnessLog.id == log_id, FitnessLog.user_id == current_user.id)
    )
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="Fitness log not found")
    return log


@router.patch("/{log_id}", response_model=FitnessLogResponse)
async def update_fitness_log(
    log_id: int,
    updates: FitnessLogUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(FitnessLog).where(FitnessLog.id == log_id, FitnessLog.user_id == current_user.id)
    )
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="Fitness log not found")
    for field, value in updates.model_dump(exclude_unset=True).items():
        setattr(log, field, value)
    await db.flush()
    await db.refresh(log)
    return log


@router.delete("/{log_id}", status_code=204)
async def delete_fitness_log(
    log_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(FitnessLog).where(FitnessLog.id == log_id, FitnessLog.user_id == current_user.id)
    )
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="Fitness log not found")
    raise HTTPException(
        status_code=403,
        detail="Fitness entries cannot be deleted. You can modify this entry instead.",
    )
