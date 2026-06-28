"""Sleep log CRUD endpoints (Basis collection domain: sleep)."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.sleep import SleepLog
from app.schemas.sleep import SleepLogCreate, SleepLogUpdate, SleepLogResponse

router = APIRouter()


@router.get("/", response_model=list[SleepLogResponse])
async def list_sleep(
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(SleepLog).where(SleepLog.user_id == current_user.id)
    if start_date:
        query = query.where(SleepLog.sleep_date >= start_date)
    if end_date:
        query = query.where(SleepLog.sleep_date <= end_date)
    query = query.order_by(SleepLog.sleep_date.desc(), SleepLog.id.desc())
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/", response_model=SleepLogResponse, status_code=201)
async def create_sleep(
    entry_in: SleepLogCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    entry = SleepLog(**entry_in.model_dump(), user_id=current_user.id)
    db.add(entry)
    await db.flush()
    await db.refresh(entry)
    return entry


@router.get("/{entry_id}", response_model=SleepLogResponse)
async def get_sleep(
    entry_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SleepLog).where(SleepLog.id == entry_id, SleepLog.user_id == current_user.id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Sleep log not found")
    return entry


@router.patch("/{entry_id}", response_model=SleepLogResponse)
async def update_sleep(
    entry_id: int,
    updates: SleepLogUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SleepLog).where(SleepLog.id == entry_id, SleepLog.user_id == current_user.id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Sleep log not found")
    for field, value in updates.model_dump(exclude_unset=True).items():
        setattr(entry, field, value)
    await db.flush()
    await db.refresh(entry)
    return entry


@router.delete("/{entry_id}", status_code=204)
async def delete_sleep(
    entry_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SleepLog).where(SleepLog.id == entry_id, SleepLog.user_id == current_user.id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Sleep log not found")
    await db.delete(entry)
    await db.flush()
