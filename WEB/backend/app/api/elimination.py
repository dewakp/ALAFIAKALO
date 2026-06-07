"""Elimination tracking CRUD endpoints (bowel movements, urination, vomiting)."""

from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.elimination import BowelMovement, UrinationLog, VomitingLog
from app.schemas.elimination import (
    BowelMovementCreate, BowelMovementUpdate, BowelMovementResponse,
    UrinationLogCreate, UrinationLogUpdate, UrinationLogResponse,
    VomitingLogCreate, VomitingLogUpdate, VomitingLogResponse,
)

router = APIRouter()


# ── Bowel Movements ───────────────────────────────────────────────────────────

@router.get("/bowel", response_model=list[BowelMovementResponse])
async def list_bowel_movements(
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    limit: int = Query(100, le=500),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(BowelMovement).where(BowelMovement.user_id == current_user.id)
    if start_date:
        q = q.where(BowelMovement.log_date >= start_date)
    if end_date:
        q = q.where(BowelMovement.log_date <= end_date)
    q = q.order_by(desc(BowelMovement.log_date), desc(BowelMovement.log_time)).limit(limit)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("/bowel", response_model=BowelMovementResponse, status_code=201)
async def create_bowel_movement(
    entry_in: BowelMovementCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    entry = BowelMovement(**entry_in.model_dump(), user_id=current_user.id)
    db.add(entry)
    await db.flush()
    await db.refresh(entry)
    return entry


@router.get("/bowel/{entry_id}", response_model=BowelMovementResponse)
async def get_bowel_movement(
    entry_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(BowelMovement).where(
            BowelMovement.id == entry_id, BowelMovement.user_id == current_user.id
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(404, "Bowel movement record not found")
    return entry


@router.patch("/bowel/{entry_id}", response_model=BowelMovementResponse)
async def update_bowel_movement(
    entry_id: int,
    updates: BowelMovementUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(BowelMovement).where(
            BowelMovement.id == entry_id, BowelMovement.user_id == current_user.id
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(404, "Bowel movement record not found")
    for field, value in updates.model_dump(exclude_unset=True).items():
        setattr(entry, field, value)
    await db.flush()
    await db.refresh(entry)
    return entry


@router.delete("/bowel/{entry_id}", status_code=204)
async def delete_bowel_movement(
    entry_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(BowelMovement).where(
            BowelMovement.id == entry_id, BowelMovement.user_id == current_user.id
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(404, "Bowel movement record not found")
    await db.delete(entry)


# ── Urination Logs ────────────────────────────────────────────────────────────

@router.get("/urination", response_model=list[UrinationLogResponse])
async def list_urination_logs(
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    limit: int = Query(100, le=500),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(UrinationLog).where(UrinationLog.user_id == current_user.id)
    if start_date:
        q = q.where(UrinationLog.log_date >= start_date)
    if end_date:
        q = q.where(UrinationLog.log_date <= end_date)
    q = q.order_by(desc(UrinationLog.log_date), desc(UrinationLog.log_time)).limit(limit)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("/urination", response_model=UrinationLogResponse, status_code=201)
async def create_urination_log(
    entry_in: UrinationLogCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    entry = UrinationLog(**entry_in.model_dump(), user_id=current_user.id)
    db.add(entry)
    await db.flush()
    await db.refresh(entry)
    return entry


@router.get("/urination/{entry_id}", response_model=UrinationLogResponse)
async def get_urination_log(
    entry_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(UrinationLog).where(
            UrinationLog.id == entry_id, UrinationLog.user_id == current_user.id
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(404, "Urination log not found")
    return entry


@router.patch("/urination/{entry_id}", response_model=UrinationLogResponse)
async def update_urination_log(
    entry_id: int,
    updates: UrinationLogUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(UrinationLog).where(
            UrinationLog.id == entry_id, UrinationLog.user_id == current_user.id
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(404, "Urination log not found")
    for field, value in updates.model_dump(exclude_unset=True).items():
        setattr(entry, field, value)
    await db.flush()
    await db.refresh(entry)
    return entry


@router.delete("/urination/{entry_id}", status_code=204)
async def delete_urination_log(
    entry_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(UrinationLog).where(
            UrinationLog.id == entry_id, UrinationLog.user_id == current_user.id
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(404, "Urination log not found")
    await db.delete(entry)


# ── Vomiting Logs ─────────────────────────────────────────────────────────────

@router.get("/vomiting", response_model=list[VomitingLogResponse])
async def list_vomiting_logs(
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    limit: int = Query(100, le=500),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(VomitingLog).where(VomitingLog.user_id == current_user.id)
    if start_date:
        q = q.where(VomitingLog.log_date >= start_date)
    if end_date:
        q = q.where(VomitingLog.log_date <= end_date)
    q = q.order_by(desc(VomitingLog.log_date), desc(VomitingLog.log_time)).limit(limit)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("/vomiting", response_model=VomitingLogResponse, status_code=201)
async def create_vomiting_log(
    entry_in: VomitingLogCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    entry = VomitingLog(**entry_in.model_dump(), user_id=current_user.id)
    db.add(entry)
    await db.flush()
    await db.refresh(entry)
    return entry


@router.get("/vomiting/{entry_id}", response_model=VomitingLogResponse)
async def get_vomiting_log(
    entry_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(VomitingLog).where(
            VomitingLog.id == entry_id, VomitingLog.user_id == current_user.id
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(404, "Vomiting log not found")
    return entry


@router.patch("/vomiting/{entry_id}", response_model=VomitingLogResponse)
async def update_vomiting_log(
    entry_id: int,
    updates: VomitingLogUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(VomitingLog).where(
            VomitingLog.id == entry_id, VomitingLog.user_id == current_user.id
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(404, "Vomiting log not found")
    for field, value in updates.model_dump(exclude_unset=True).items():
        setattr(entry, field, value)
    await db.flush()
    await db.refresh(entry)
    return entry


@router.delete("/vomiting/{entry_id}", status_code=204)
async def delete_vomiting_log(
    entry_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(VomitingLog).where(
            VomitingLog.id == entry_id, VomitingLog.user_id == current_user.id
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(404, "Vomiting log not found")
    await db.delete(entry)
