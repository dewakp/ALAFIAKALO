"""Peritoneal Dialysis CRUD endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import date

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.peritoneal_dialysis import PDSession, PDExchange
from app.schemas.peritoneal_dialysis import (
    PDSessionCreate, PDSessionUpdate, PDSessionResponse, PDExchangeCreate, PDExchangeResponse,
)

router = APIRouter()


@router.get("/", response_model=list[PDSessionResponse])
async def list_pd_sessions(
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    modality: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(PDSession).where(PDSession.user_id == current_user.id)
    if start_date:
        query = query.where(PDSession.session_date >= start_date)
    if end_date:
        query = query.where(PDSession.session_date <= end_date)
    if modality:
        query = query.where(PDSession.modality == modality)
    query = query.order_by(PDSession.session_date.desc())
    result = await db.execute(query)
    return result.scalars().unique().all()


@router.post("/", response_model=PDSessionResponse, status_code=201)
async def create_pd_session(
    data: PDSessionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    exchanges_data = data.exchanges
    session_dict = data.model_dump(exclude={"exchanges"})
    session = PDSession(**session_dict, user_id=current_user.id)
    db.add(session)
    await db.flush()

    for ex_data in exchanges_data:
        exchange = PDExchange(**ex_data.model_dump(), session_id=session.id)
        # Auto-calculate UF if not provided
        if exchange.uf_ml is None and exchange.outflow_volume_ml and exchange.inflow_volume_ml:
            exchange.uf_ml = exchange.outflow_volume_ml - exchange.inflow_volume_ml
        db.add(exchange)

    # Auto-calculate total UF
    await db.flush()
    await db.refresh(session)
    if session.total_uf_ml is None and session.exchanges:
        total = sum(ex.uf_ml or 0 for ex in session.exchanges)
        session.total_uf_ml = total
        await db.flush()
        await db.refresh(session)

    return session


@router.get("/{session_id}", response_model=PDSessionResponse)
async def get_pd_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PDSession).where(PDSession.id == session_id, PDSession.user_id == current_user.id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="PD session not found")
    return session


@router.patch("/{session_id}", response_model=PDSessionResponse)
async def update_pd_session(
    session_id: int,
    updates: PDSessionUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PDSession).where(PDSession.id == session_id, PDSession.user_id == current_user.id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="PD session not found")
    for field, value in updates.model_dump(exclude_unset=True).items():
        setattr(session, field, value)
    await db.flush()
    await db.refresh(session)
    return session


@router.delete("/{session_id}", status_code=204)
async def delete_pd_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PDSession).where(PDSession.id == session_id, PDSession.user_id == current_user.id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="PD session not found")
    await db.delete(session)


@router.post("/{session_id}/exchanges", response_model=PDExchangeResponse, status_code=201)
async def add_exchange(
    session_id: int,
    data: PDExchangeCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PDSession).where(PDSession.id == session_id, PDSession.user_id == current_user.id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="PD session not found")

    exchange = PDExchange(**data.model_dump(), session_id=session_id)
    if exchange.uf_ml is None and exchange.outflow_volume_ml and exchange.inflow_volume_ml:
        exchange.uf_ml = exchange.outflow_volume_ml - exchange.inflow_volume_ml
    db.add(exchange)
    await db.flush()
    await db.refresh(exchange)
    return exchange


@router.delete("/{session_id}/exchanges/{exchange_id}", status_code=204)
async def delete_exchange(
    session_id: int,
    exchange_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PDSession).where(PDSession.id == session_id, PDSession.user_id == current_user.id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="PD session not found")

    result = await db.execute(
        select(PDExchange).where(PDExchange.id == exchange_id, PDExchange.session_id == session_id)
    )
    exchange = result.scalar_one_or_none()
    if not exchange:
        raise HTTPException(status_code=404, detail="Exchange not found")
    await db.delete(exchange)
