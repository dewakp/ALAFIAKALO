"""Ground-truth CRUD: genetic markers + environmental/social logs (Basis req #3).

Minimal CRUD — these feed the AI context and the relationship/forecast engines.
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.ground_truth import GeneticMarker, EnvSocialLog
from app.schemas.ground_truth import (
    GeneticMarkerCreate, GeneticMarkerResponse,
    EnvSocialLogCreate, EnvSocialLogResponse,
)

router = APIRouter()


# ── Genetic markers ──
@router.get("/genetics", response_model=list[GeneticMarkerResponse])
async def list_genetics(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(GeneticMarker).where(GeneticMarker.user_id == current_user.id)
        .order_by(GeneticMarker.gene)
    )
    return result.scalars().all()


@router.post("/genetics", response_model=GeneticMarkerResponse, status_code=201)
async def create_genetic(
    entry_in: GeneticMarkerCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    entry = GeneticMarker(**entry_in.model_dump(), user_id=current_user.id)
    db.add(entry)
    await db.flush()
    await db.refresh(entry)
    return entry


@router.delete("/genetics/{entry_id}", status_code=204)
async def delete_genetic(
    entry_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(GeneticMarker).where(GeneticMarker.id == entry_id, GeneticMarker.user_id == current_user.id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Genetic marker not found")
    await db.delete(entry)
    await db.flush()


# ── Environmental / social factors ──
@router.get("/env-social", response_model=list[EnvSocialLogResponse])
async def list_env_social(
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(EnvSocialLog).where(EnvSocialLog.user_id == current_user.id)
    if start_date:
        query = query.where(EnvSocialLog.log_date >= start_date)
    if end_date:
        query = query.where(EnvSocialLog.log_date <= end_date)
    result = await db.execute(query.order_by(EnvSocialLog.log_date.desc()))
    return result.scalars().all()


@router.post("/env-social", response_model=EnvSocialLogResponse, status_code=201)
async def create_env_social(
    entry_in: EnvSocialLogCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    entry = EnvSocialLog(**entry_in.model_dump(), user_id=current_user.id)
    db.add(entry)
    await db.flush()
    await db.refresh(entry)
    return entry


@router.delete("/env-social/{entry_id}", status_code=204)
async def delete_env_social(
    entry_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(EnvSocialLog).where(EnvSocialLog.id == entry_id, EnvSocialLog.user_id == current_user.id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    await db.delete(entry)
    await db.flush()
