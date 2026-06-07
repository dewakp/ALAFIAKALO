"""EHR connection endpoints (FHIR-only scaffolding)."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.ehr import EHRConnection
from app.models.user import User
from app.schemas.ehr import (
    EHRConnectionCreate,
    EHRConnectionUpdate,
    EHRConnectionResponse,
)

router = APIRouter(prefix="/ehr", tags=["EHR"])

FHIR_PROVIDERS = [
    {
        "id": "epic",
        "name": "Epic",
        "auth_type": "smart_on_fhir",
        "supports": ["Patient", "Condition", "Observation", "MedicationStatement"],
    },
    {
        "id": "siemens",
        "name": "Siemens Healthineers",
        "auth_type": "smart_on_fhir",
        "supports": ["Patient", "Condition", "Observation", "MedicationStatement"],
    },
    {
        "id": "cerner",
        "name": "Cerner",
        "auth_type": "smart_on_fhir",
        "supports": ["Patient", "Condition", "Observation", "MedicationStatement"],
    },
]


@router.get("/providers")
async def list_providers():
    return FHIR_PROVIDERS


@router.get("/connections", response_model=list[EHRConnectionResponse])
async def list_connections(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(EHRConnection)
        .where(EHRConnection.user_id == current_user.id)
        .order_by(EHRConnection.created_at.desc())
    )
    return result.scalars().all()


@router.post("/connections", response_model=EHRConnectionResponse, status_code=status.HTTP_201_CREATED)
async def create_connection(
    payload: EHRConnectionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    connection = EHRConnection(
        user_id=current_user.id,
        provider=payload.provider,
        status=payload.status or "pending",
        fhir_base_url=payload.fhir_base_url,
        patient_id=payload.patient_id,
        scopes=payload.scopes,
        notes=payload.notes,
    )
    db.add(connection)
    await db.flush()
    await db.refresh(connection)
    return connection


@router.put("/connections/{connection_id}", response_model=EHRConnectionResponse)
async def update_connection(
    connection_id: int,
    payload: EHRConnectionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(EHRConnection).where(
            EHRConnection.id == connection_id,
            EHRConnection.user_id == current_user.id,
        )
    )
    connection = result.scalar_one_or_none()
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")

    updates = payload.model_dump(exclude_unset=True)
    if "last_sync_at" in updates and isinstance(updates["last_sync_at"], datetime):
        connection.last_sync_at = updates.pop("last_sync_at")

    for field, value in updates.items():
        setattr(connection, field, value)

    await db.flush()
    await db.refresh(connection)
    return connection


@router.delete("/connections/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_connection(
    connection_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(EHRConnection).where(
            EHRConnection.id == connection_id,
            EHRConnection.user_id == current_user.id,
        )
    )
    connection = result.scalar_one_or_none()
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")

    await db.delete(connection)
    return None
