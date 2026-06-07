"""Labs / EHR CRUD endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import date

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.notification_engine import notify_lab_anomaly
from app.models.user import User
from app.models.labs import LabResult
from app.schemas.labs import LabResultCreate, LabResultUpdate, LabResultResponse

router = APIRouter()


@router.get("/", response_model=list[LabResultResponse])
async def list_lab_results(
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    category: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(LabResult).where(LabResult.user_id == current_user.id)
    if start_date:
        query = query.where(LabResult.test_date >= start_date)
    if end_date:
        query = query.where(LabResult.test_date <= end_date)
    if category:
        query = query.where(LabResult.category == category)
    query = query.order_by(LabResult.test_date.desc())
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/", response_model=LabResultResponse, status_code=201)
async def create_lab_result(
    lab_in: LabResultCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    lab = LabResult(**lab_in.model_dump(), user_id=current_user.id)
    db.add(lab)
    await db.flush()
    await db.refresh(lab)

    # Notification: lab anomaly detection
    if lab.value is not None:
        is_anomaly = False
        range_str = ""
        if lab.reference_range_low is not None and lab.value < lab.reference_range_low:
            is_anomaly = True
            range_str = f"{lab.reference_range_low}–{lab.reference_range_high or '?'} {lab.unit or ''}"
        elif lab.reference_range_high is not None and lab.value > lab.reference_range_high:
            is_anomaly = True
            range_str = f"{lab.reference_range_low or '?'}–{lab.reference_range_high} {lab.unit or ''}"
        elif lab.is_abnormal:
            is_anomaly = True
            range_str = "flagged abnormal"
        if is_anomaly:
            await notify_lab_anomaly(
                db, user_id=current_user.id, test_name=lab.test_name,
                value=f"{lab.value} {lab.unit or ''}".strip(),
                normal_range=range_str, lab_id=lab.id,
            )

    return lab


@router.get("/{lab_id}", response_model=LabResultResponse)
async def get_lab_result(
    lab_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(LabResult).where(LabResult.id == lab_id, LabResult.user_id == current_user.id)
    )
    lab = result.scalar_one_or_none()
    if not lab:
        raise HTTPException(status_code=404, detail="Lab result not found")
    return lab


@router.patch("/{lab_id}", response_model=LabResultResponse)
async def update_lab_result(
    lab_id: int,
    updates: LabResultUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(LabResult).where(LabResult.id == lab_id, LabResult.user_id == current_user.id)
    )
    lab = result.scalar_one_or_none()
    if not lab:
        raise HTTPException(status_code=404, detail="Lab result not found")
    for field, value in updates.model_dump(exclude_unset=True).items():
        setattr(lab, field, value)
    await db.flush()
    await db.refresh(lab)
    return lab


@router.delete("/{lab_id}", status_code=204)
async def delete_lab_result(
    lab_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(LabResult).where(LabResult.id == lab_id, LabResult.user_id == current_user.id)
    )
    lab = result.scalar_one_or_none()
    if not lab:
        raise HTTPException(status_code=404, detail="Lab result not found")
    raise HTTPException(
        status_code=403,
        detail="Lab entries cannot be deleted. You can modify this entry instead.",
    )
