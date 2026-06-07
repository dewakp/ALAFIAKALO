"""Firebase integration endpoints — SSO bridge & sync triggers."""

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import create_access_token, create_refresh_token, get_current_user
from app.models.user import User
from app.services.firebase_sync import (
    verify_firebase_token,
    get_or_create_user_from_firebase,
    sync_pipeline,
)

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────

class FirebaseLoginRequest(BaseModel):
    id_token: str


class FirebaseLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int


class SyncResponse(BaseModel):
    status: str
    message: str
    records_synced: int = 0


class SyncStatusResponse(BaseModel):
    firebase_linked: bool
    last_sync_at: datetime | None = None
    message: str


# ── Firebase SSO Login ────────────────────────────────────

@router.post("/firebase-login", response_model=FirebaseLoginResponse)
async def firebase_login(
    body: FirebaseLoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Authenticate via Firebase ID token.
    Verifies the token with Firebase Admin SDK, finds or creates a local user,
    and returns an ALAFIA JWT access token.
    """
    claims = await verify_firebase_token(body.id_token)
    if claims is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired Firebase token",
        )

    user_id = await get_or_create_user_from_firebase(db, claims)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create local user from Firebase credentials",
        )

    access_token = create_access_token(data={"sub": str(user_id)})

    return FirebaseLoginResponse(
        access_token=access_token,
        user_id=user_id,
    )


# ── Sync Endpoints ────────────────────────────────────────

@router.post("/sync", response_model=SyncResponse)
async def trigger_sync(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Trigger a Firebase→PostgreSQL sync for the current user.
    Runs in background if user has a firebase_uid.
    """
    if not current_user.firebase_uid:
        return SyncResponse(
            status="skipped",
            message="No Firebase account linked to this user",
        )

    count = await sync_pipeline.sync_single_user(db, current_user.firebase_uid)
    return SyncResponse(
        status="completed",
        message=f"Synced {count} new records from Firebase",
        records_synced=count,
    )


@router.post("/sync-all", response_model=SyncResponse)
async def trigger_sync_all(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Trigger a full sync for ALL Firebase-linked users.
    Requires superuser privileges.
    """
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superuser access required",
        )

    results = await sync_pipeline.sync_all_users(db)
    total = sum(v for v in results.values() if v > 0)
    return SyncResponse(
        status="completed",
        message=f"Synced {total} records across {len(results)} users",
        records_synced=total,
    )


# ── Status Endpoint ───────────────────────────────────────

@router.get("/status", response_model=SyncStatusResponse)
async def sync_status(
    current_user: User = Depends(get_current_user),
):
    """Return Firebase link status and last successful sync time for the current user."""
    if not current_user.firebase_uid:
        return SyncStatusResponse(
            firebase_linked=False,
            message="No Firebase account linked to this user",
        )

    last_sync = sync_pipeline._last_sync.get(current_user.firebase_uid)
    return SyncStatusResponse(
        firebase_linked=True,
        last_sync_at=last_sync,
        message="Synced" if last_sync else "No sync has run yet this session",
    )
