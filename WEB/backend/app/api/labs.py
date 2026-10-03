# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

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
from app.services import active_response

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
        resolved_note = ""
        low, high = lab.reference_range_low, lab.reference_range_high
        if low is None and high is None:
            # A result printing no range is the NORMAL case here, not the
            # exception: of 9,791 production results 9,091 have `is_abnormal`
            # NULL and only 680 carry a range, so this gate could not judge
            # 93% of the record — which is why two lab notifications exist for
            # nearly ten thousand results. §3aa already recorded the display
            # side of the same gap: 137 stored results numerically contradict
            # their own printed range, including a potassium of 6.7 against
            # 3.5-5.5.
            #
            # `reference_ranges` resolves a band without inventing one — this
            # patient's own most recent reported range, then the population
            # mode, then a recorded guideline in `clinical_thresholds`, then a
            # range learned from observed values, and then nothing.
            band = await active_response.resolved_range_for(
                db, current_user.id, lab.test_name)
            if band:
                low, high = band
                resolved_note = " (your previously reported range)"
        unit = lab.unit or ""
        if low is not None and lab.value < low:
            is_anomaly = True
            range_str = f"{low}–{high if high is not None else '?'} {unit}{resolved_note}"
        elif high is not None and lab.value > high:
            is_anomaly = True
            range_str = f"{low if low is not None else '?'}–{high} {unit}{resolved_note}"
        elif lab.is_abnormal:
            is_anomaly = True
            range_str = "flagged abnormal"
        if is_anomaly:
            await notify_lab_anomaly(
                db, user_id=current_user.id, test_name=lab.test_name,
                value=f"{lab.value} {unit}".strip(),
                normal_range=range_str.strip(), lab_id=lab.id,
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
