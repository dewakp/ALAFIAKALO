# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""Hospital stays and surgical procedures.

`GET /hospital/history` is the surface the clients draw, and it comes from
`clinical_sources` — never from a query here. The rest of this module WRITES,
which is why it carries an `ALLOWED` entry in `tests/test_clinical_sources.py`
alongside `api/chronic_conditions.py`.

Why `history` returns three lists rather than a stay tree: `procedures` holds
every procedure INCLUDING those with no admission, and that set is not
derivable from `stays`. A client walking stays→procedures would silently lose
the day-case operations and anything recorded years after the fact — which is
the case this whole model was written for (a parathyroidectomy that explains a
calcium requirement, with no admission attached to it).
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete as sa_delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.hospitalization import Hospitalization, SurgicalProcedure
from app.models.user import User
from app.schemas.hospitalization import (HospitalHistoryResponse,
                                         HospitalizationCreate,
                                         HospitalizationDetail,
                                         HospitalizationResponse,
                                         HospitalizationUpdate,
                                         HospitalizationView,
                                         ProcedureView,
                                         SurgicalProcedureCreate,
                                         SurgicalProcedureResponse,
                                         SurgicalProcedureUpdate)
from app.services import clinical_sources

router = APIRouter()


async def _own_stay(db: AsyncSession, user: User, stay_id: int) -> Hospitalization:
    """A stay belonging to this user, or 404.

    404 and never 403, so the status code cannot confirm that someone else's
    admission exists (§3b).
    """
    stay = (await db.execute(
        select(Hospitalization).where(Hospitalization.id == stay_id,
                                      Hospitalization.user_id == user.id)
    )).scalar_one_or_none()
    if not stay:
        raise HTTPException(status_code=404, detail="Hospitalization not found")
    return stay


async def _own_procedure(db: AsyncSession, user: User, proc_id: int) -> SurgicalProcedure:
    proc = (await db.execute(
        select(SurgicalProcedure).where(SurgicalProcedure.id == proc_id,
                                        SurgicalProcedure.user_id == user.id)
    )).scalar_one_or_none()
    if not proc:
        raise HTTPException(status_code=404, detail="Procedure not found")
    return proc


# ── The canonical read ───────────────────────────────────────────────────────

@router.get("/history", response_model=HospitalHistoryResponse)
async def hospital_history(
    since: date | None = Query(None, description="Only stays/procedures on or after this date"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Stays, EVERY procedure, and what past surgery still does to the patient."""
    stays = await clinical_sources.hospitalizations(db, current_user.id, since=since)
    procedures = await clinical_sources.procedures(db, current_user.id, since=since)
    # `lasting_surgical_effects` is deliberately NOT windowed by `since`: a
    # parathyroidectomy from 2019 still governs this patient's calcium today,
    # and a date filter would hide exactly the fact that matters most.
    effects = await clinical_sources.lasting_surgical_effects(db, current_user.id)
    # Converted explicitly from the reader's dataclasses. Handing the
    # dataclasses straight to the response model would rely on pydantic
    # coercing nested arbitrary objects by attribute, which is a quieter
    # dependency than it looks: it fails as a validation error at RESPONSE
    # time, i.e. a 500 on a patient's history rather than anything a test of
    # the reader would catch.
    return HospitalHistoryResponse(
        stays=[HospitalizationView.model_validate(s) for s in stays],
        procedures=[ProcedureView.model_validate(p) for p in procedures],
        lasting_effects=effects,
    )


# ── Stays ────────────────────────────────────────────────────────────────────

@router.get("/stays", response_model=list[HospitalizationResponse])
async def list_stays(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Raw rows, newest first — for an edit form, not for display.

    Unpaginated on purpose: a patient has a handful of admissions, and §3ad's
    truncation failure (a `LIMIT` reported as a count) is worse here than a
    slightly larger payload.
    """
    return (await db.execute(
        select(Hospitalization)
        .where(Hospitalization.user_id == current_user.id)
        .order_by(Hospitalization.admitted_at.desc())
    )).scalars().all()


@router.post("/stays", response_model=HospitalizationDetail,
             status_code=status.HTTP_201_CREATED)
async def create_stay(
    payload: HospitalizationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a stay, optionally with the procedures performed during it.

    One request, because that is how a discharge summary arrives.
    """
    # `exclude_none=True` is load-bearing. `status` is NOT NULL with a
    # Python-side default, and SQLAlchemy applies that default only when the
    # attribute was never SET — an explicit None inserts NULL and 500s a
    # create that merely omitted the field. PATCH keeps `exclude_unset`
    # instead, because there an explicit null legitimately clears a value.
    data = payload.model_dump(exclude={"procedures"}, exclude_none=True)
    stay = Hospitalization(user_id=current_user.id,
                           source=data.pop("source", None) or "manual",
                           **data)
    db.add(stay)
    await db.flush()

    for proc in payload.procedures:
        db.add(SurgicalProcedure(user_id=current_user.id,
                                 hospitalization_id=stay.id,
                                 **proc.model_dump(exclude={"hospitalization_id"})))
    await db.flush()

    return (await db.execute(
        select(Hospitalization)
        .options(selectinload(Hospitalization.procedures))
        .where(Hospitalization.id == stay.id)
    )).scalar_one()


@router.patch("/stays/{stay_id}", response_model=HospitalizationResponse)
async def update_stay(
    stay_id: int,
    payload: HospitalizationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stay = await _own_stay(db, current_user, stay_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(stay, field, value)
    await db.flush()
    return stay


@router.delete("/stays/{stay_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_stay(
    stay_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete the STAY. The procedures survive it, detached.

    Explicit statements rather than an ORM delete: the relationship is
    `passive_deletes=True` so the database's `ON DELETE SET NULL` governs, and
    detaching here states that outcome at the call site instead of leaving it
    to cascade configuration a later edit could silently change. An operation
    that happened is a fact about the patient's body; deleting a mistyped
    admission must not erase it.
    """
    stay = await _own_stay(db, current_user, stay_id)
    await db.execute(
        update(SurgicalProcedure)
        .where(SurgicalProcedure.hospitalization_id == stay.id,
               SurgicalProcedure.user_id == current_user.id)
        .values(hospitalization_id=None))
    await db.execute(
        sa_delete(Hospitalization).where(Hospitalization.id == stay.id,
                                         Hospitalization.user_id == current_user.id))
    await db.flush()
    return None


# ── Procedures ───────────────────────────────────────────────────────────────

@router.get("/procedures", response_model=list[SurgicalProcedureResponse])
async def list_procedures(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return (await db.execute(
        select(SurgicalProcedure)
        .where(SurgicalProcedure.user_id == current_user.id)
        .order_by(SurgicalProcedure.performed_at.desc().nullslast())
    )).scalars().all()


@router.post("/procedures", response_model=SurgicalProcedureResponse,
             status_code=status.HTTP_201_CREATED)
async def create_procedure(
    payload: SurgicalProcedureCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Record a procedure, with or without an admission.

    Without is the normal case for anything historical — which is why
    `hospitalization_id` is nullable and why this endpoint does not require it.
    """
    if payload.hospitalization_id is not None:
        # Never let a procedure attach to someone else's admission.
        await _own_stay(db, current_user, payload.hospitalization_id)
    proc = SurgicalProcedure(user_id=current_user.id,
                             **payload.model_dump(exclude_none=True))
    if not proc.source:
        proc.source = "manual"
    db.add(proc)
    await db.flush()
    return proc


@router.patch("/procedures/{procedure_id}", response_model=SurgicalProcedureResponse)
async def update_procedure(
    procedure_id: int,
    payload: SurgicalProcedureUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    proc = await _own_procedure(db, current_user, procedure_id)
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("hospitalization_id") is not None:
        await _own_stay(db, current_user, changes["hospitalization_id"])
    for field, value in changes.items():
        setattr(proc, field, value)
    await db.flush()
    return proc


@router.delete("/procedures/{procedure_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_procedure(
    procedure_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    proc = await _own_procedure(db, current_user, procedure_id)
    await db.delete(proc)
    await db.flush()
    return None
