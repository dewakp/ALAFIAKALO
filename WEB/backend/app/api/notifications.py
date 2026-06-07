"""Notification API endpoints."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, update, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.notifications import (
    Notification,
    NotificationPreference,
    NotificationCategory,
)
from app.models.device_tokens import DeviceToken
from app.schemas.notifications import (
    NotificationOut,
    NotificationPreferenceOut,
    NotificationPreferenceUpdate,
    UnreadCountOut,
    DeviceTokenRegister,
    DeviceTokenOut,
)

router = APIRouter()


# ── Notifications CRUD ─────────────────────────────────────────────

@router.get("/", response_model=list[NotificationOut])
async def list_notifications(
    category: str | None = Query(None, description="Filter by category"),
    unread_only: bool = Query(False),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List notifications for the current user, newest first."""
    q = select(Notification).where(Notification.user_id == current_user.id)
    if category:
        q = q.where(Notification.category == category)
    if unread_only:
        q = q.where(Notification.is_read == False)  # noqa: E712
    q = q.order_by(desc(Notification.created_at)).offset(skip).limit(limit)
    result = await db.execute(q)
    return result.scalars().all()


@router.get("/unread-count", response_model=UnreadCountOut)
async def unread_count(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the number of unread notifications."""
    result = await db.execute(
        select(func.count(Notification.id)).where(
            Notification.user_id == current_user.id,
            Notification.is_read == False,  # noqa: E712
        )
    )
    return {"count": result.scalar() or 0}


@router.patch("/{notification_id}/read", response_model=NotificationOut)
async def mark_read(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark a single notification as read."""
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == current_user.id,
        )
    )
    notif = result.scalar_one_or_none()
    if not notif:
        raise HTTPException(404, "Notification not found")
    notif.is_read = True
    notif.read_at = datetime.now(timezone.utc)
    return notif


@router.post("/read-all", response_model=dict)
async def mark_all_read(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark all unread notifications as read."""
    now = datetime.now(timezone.utc)
    await db.execute(
        update(Notification)
        .where(
            Notification.user_id == current_user.id,
            Notification.is_read == False,  # noqa: E712
        )
        .values(is_read=True, read_at=now)
    )
    return {"status": "ok"}


@router.delete("/{notification_id}", status_code=204)
async def delete_notification(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a notification."""
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == current_user.id,
        )
    )
    notif = result.scalar_one_or_none()
    if not notif:
        raise HTTPException(404, "Notification not found")
    await db.delete(notif)


# ── Push device tokens ──────────────────────────────────────────────

async def _register_device_token(
    db: AsyncSession, user_id: int, token: str, platform: str
) -> DeviceToken:
    """Upsert a device token by its raw value.

    Re-registering the same token (e.g. after reinstall or login on another
    account) reassigns it to the current user and refreshes last_seen, so a
    physical device never ends up with stale duplicate rows.
    """
    result = await db.execute(select(DeviceToken).where(DeviceToken.token == token))
    existing = result.scalar_one_or_none()
    if existing:
        existing.user_id = user_id
        existing.platform = platform
        existing.last_seen = datetime.now(timezone.utc)
        await db.flush()
        return existing

    device = DeviceToken(user_id=user_id, token=token, platform=platform)
    db.add(device)
    await db.flush()
    await db.refresh(device)
    return device


@router.post("/apns-token", response_model=DeviceTokenOut, status_code=201)
async def register_apns_token(
    body: DeviceTokenRegister,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Register an iOS APNs device token for the current user."""
    return await _register_device_token(db, current_user.id, body.token, "ios")


@router.post("/fcm-token", response_model=DeviceTokenOut, status_code=201)
async def register_fcm_token(
    body: DeviceTokenRegister,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Register an Android FCM device token for the current user."""
    return await _register_device_token(db, current_user.id, body.token, "android")


@router.delete("/device-token", status_code=204)
async def unregister_device_token(
    token: str = Query(..., description="The device token to remove"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a device token (e.g. on logout) so the device stops receiving push."""
    result = await db.execute(
        select(DeviceToken).where(
            DeviceToken.token == token,
            DeviceToken.user_id == current_user.id,
        )
    )
    device = result.scalar_one_or_none()
    if device:
        await db.delete(device)
        await db.flush()


# ── Preferences ─────────────────────────────────────────────────────

@router.get("/preferences", response_model=list[NotificationPreferenceOut])
async def list_preferences(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all notification preferences.

    Returns existing preferences plus defaults for categories without a record.
    """
    result = await db.execute(
        select(NotificationPreference).where(NotificationPreference.user_id == current_user.id)
    )
    prefs = {p.category: p for p in result.scalars().all()}

    out = []
    for cat in NotificationCategory:
        if cat in prefs:
            out.append(prefs[cat])
        else:
            # Return synthetic default
            out.append(
                NotificationPreference(
                    id=0,
                    user_id=current_user.id,
                    category=cat,
                    enabled=True,
                    in_app=True,
                    push=True,
                    email=False,
                    sms=False,
                )
            )
    return out


@router.patch("/preferences/{category}", response_model=NotificationPreferenceOut)
async def update_preference(
    category: str,
    body: NotificationPreferenceUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create or update a notification preference for a category."""
    try:
        cat_enum = NotificationCategory(category)
    except ValueError:
        raise HTTPException(400, f"Invalid category: {category}")

    result = await db.execute(
        select(NotificationPreference).where(
            NotificationPreference.user_id == current_user.id,
            NotificationPreference.category == cat_enum,
        )
    )
    pref = result.scalar_one_or_none()
    if not pref:
        pref = NotificationPreference(user_id=current_user.id, category=cat_enum)
        db.add(pref)

    updates = body.model_dump(exclude_unset=True)
    for k, v in updates.items():
        setattr(pref, k, v)

    await db.flush()
    return pref
