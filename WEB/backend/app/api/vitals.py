"""Vitals CRUD endpoints — standalone vital-signs data collection.

Vitals are their own domain (not lifestyle): this reads/writes the vitals_logs
table that the Firebase sync also targets, so synced and app-entered vitals share
one running log + trends.
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.vitals import VitalsLog
from app.schemas.vitals import VitalsLogCreate, VitalsLogUpdate, VitalsLogResponse

router = APIRouter()


@router.get("/", response_model=list[VitalsLogResponse])
async def list_vitals(
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(VitalsLog).where(VitalsLog.user_id == current_user.id)
    if start_date:
        query = query.where(VitalsLog.log_date >= start_date)
    if end_date:
        query = query.where(VitalsLog.log_date <= end_date)
    query = query.order_by(VitalsLog.log_date.desc(), VitalsLog.id.desc())
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/", response_model=VitalsLogResponse, status_code=201)
async def create_vitals(
    entry_in: VitalsLogCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    payload = entry_in.model_dump()
    # Auto-compute BMI when weight + height are present and BMI wasn't supplied.
    if payload.get("bmi") is None and payload.get("weight_kg") and payload.get("height_cm"):
        h_m = payload["height_cm"] / 100.0
        if h_m > 0:
            payload["bmi"] = round(payload["weight_kg"] / (h_m * h_m), 1)
    entry = VitalsLog(**payload, user_id=current_user.id)
    db.add(entry)
    await db.flush()
    await db.refresh(entry)
    return entry


@router.get("/{entry_id}", response_model=VitalsLogResponse)
async def get_vitals(
    entry_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(VitalsLog).where(VitalsLog.id == entry_id, VitalsLog.user_id == current_user.id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Vitals entry not found")
    return entry


@router.patch("/{entry_id}", response_model=VitalsLogResponse)
async def update_vitals(
    entry_id: int,
    updates: VitalsLogUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(VitalsLog).where(VitalsLog.id == entry_id, VitalsLog.user_id == current_user.id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Vitals entry not found")
    for field, value in updates.model_dump(exclude_unset=True).items():
        setattr(entry, field, value)
    await db.flush()
    await db.refresh(entry)
    return entry


@router.delete("/{entry_id}", status_code=204)
async def delete_vitals(
    entry_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(VitalsLog).where(VitalsLog.id == entry_id, VitalsLog.user_id == current_user.id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Vitals entry not found")
    await db.delete(entry)
    await db.flush()
