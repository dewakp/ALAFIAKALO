"""Data Sharing CRUD endpoints — granular permissions for users."""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.notification_engine import create_notification, notify_record_shared
from app.services.email import (
    send_record_shared_email,
    send_share_invitation_email,
)
from app.models.notifications import NotificationCategory, NotificationPriority
from app.models.user import User
from app.models.data_sharing import DataGrant, DataShareInvitation
from app.schemas.data_sharing import (
    DataGrantCreate, DataGrantUpdate, DataGrantResponse,
    DataShareInvitationCreate, DataShareInvitationResponse,
    SHARABLE_DATA_TYPES,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Data Grants ──────────────────────────────────────────────

@router.get("/grants", response_model=list[DataGrantResponse])
async def list_grants(
    direction: str = Query("given", description="'given' or 'received'"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if direction == "received":
        query = select(DataGrant).where(DataGrant.grantee_user_id == current_user.id)
    else:
        query = select(DataGrant).where(DataGrant.owner_id == current_user.id)
    result = await db.execute(query.order_by(DataGrant.created_at.desc()))
    return result.scalars().all()


@router.post("/grants", response_model=DataGrantResponse, status_code=201)
async def create_grant(
    data: DataGrantCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if data.data_type not in SHARABLE_DATA_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid data type. Must be one of: {SHARABLE_DATA_TYPES}")

    # Resolve grantee by email if user_id not provided
    grantee_id = data.grantee_user_id
    if not grantee_id and data.grantee_email:
        result = await db.execute(select(User).where(User.email == data.grantee_email))
        grantee = result.scalar_one_or_none()
        if grantee:
            grantee_id = grantee.id

    grant = DataGrant(
        owner_id=current_user.id,
        grantee_user_id=grantee_id,
        grantee_email=data.grantee_email,
        grantee_display_name=data.grantee_display_name,
        data_type=data.data_type,
        read_access=data.read_access,
        write_access=data.write_access,
        expires_at=data.expires_at,
        notes=data.notes,
    )
    db.add(grant)
    await db.flush()
    await db.refresh(grant)

    # Tell the person the record was shared WITH. Sharing used to be silent on
    # their side: the grant was created and returned to the owner, and the
    # recipient learned nothing — someone could hold access to a patient's labs
    # and never know they had it.
    #
    # Best-effort, and deliberately AFTER the grant exists: a mail outage must
    # never fail the share the patient just made (§3ah, where a non-2xx over an
    # email problem sent Stripe into a multi-day retry cascade).
    await _announce_share(db, grant, current_user)

    return grant


async def _announce_share(db: AsyncSession, grant: DataGrant, owner: User) -> None:
    """In-app notification for a known user, email for whoever we can reach.

    Both, not either: the notification is what they see next time they open the
    app, and the email is what reaches them when they do not.
    """
    owner_name = (owner.full_name or owner.email or "An ALAFIA member").strip()

    if grant.grantee_user_id:
        try:
            await notify_record_shared(
                db,
                grantee_user_id=grant.grantee_user_id,
                owner_name=owner_name,
                data_type=grant.data_type,
                grant_id=grant.id,
                write_access=bool(grant.write_access),
            )
        except Exception:  # noqa: BLE001
            logger.warning("could not notify grantee of share %s", grant.id, exc_info=True)

    # The address to write to: the invited email, or the account's own.
    to = grant.grantee_email
    recipient_name = grant.grantee_display_name
    if not to and grant.grantee_user_id:
        grantee = (await db.execute(
            select(User).where(User.id == grant.grantee_user_id))).scalar_one_or_none()
        if grantee:
            to = grantee.email
            recipient_name = recipient_name or grantee.full_name
    if not to:
        return

    try:
        await send_record_shared_email(
            to,
            owner_name=owner_name,
            data_type=grant.data_type,
            recipient_name=recipient_name,
            read_access=bool(grant.read_access),
            write_access=bool(grant.write_access),
            expires_at=str(grant.expires_at)[:10] if grant.expires_at else None,
        )
    except Exception:  # noqa: BLE001
        # The share stands whether or not the mail went out.
        logger.warning("could not email grantee of share %s", grant.id, exc_info=True)


@router.patch("/grants/{grant_id}", response_model=DataGrantResponse)
async def update_grant(
    grant_id: int,
    updates: DataGrantUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DataGrant).where(DataGrant.id == grant_id, DataGrant.owner_id == current_user.id)
    )
    grant = result.scalar_one_or_none()
    if not grant:
        raise HTTPException(status_code=404, detail="Grant not found")
    for field, value in updates.model_dump(exclude_unset=True).items():
        setattr(grant, field, value)
    await db.flush()
    await db.refresh(grant)
    return grant


@router.delete("/grants/{grant_id}", status_code=204)
async def revoke_grant(
    grant_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DataGrant).where(DataGrant.id == grant_id, DataGrant.owner_id == current_user.id)
    )
    grant = result.scalar_one_or_none()
    if not grant:
        raise HTTPException(status_code=404, detail="Grant not found")
    await db.delete(grant)


@router.get("/types")
async def list_shareable_data_types(
    current_user: User = Depends(get_current_user),
):
    """List available data types that can be shared."""
    return SHARABLE_DATA_TYPES


# ── Invitations ──────────────────────────────────────────────

@router.get("/invitations", response_model=list[DataShareInvitationResponse])
async def list_invitations(
    direction: str = Query("sent", description="'sent' or 'received'"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if direction == "received":
        query = select(DataShareInvitation).where(
            (DataShareInvitation.recipient_user_id == current_user.id) |
            (DataShareInvitation.recipient_email == current_user.email)
        )
    else:
        query = select(DataShareInvitation).where(DataShareInvitation.sender_id == current_user.id)
    result = await db.execute(query.order_by(DataShareInvitation.created_at.desc()))
    return result.scalars().all()


@router.post("/invitations", response_model=DataShareInvitationResponse, status_code=201)
async def send_invitation(
    data: DataShareInvitationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Validate data types
    for dt in data.data_types:
        if dt not in SHARABLE_DATA_TYPES:
            raise HTTPException(status_code=400, detail=f"Invalid data type: {dt}")

    # Check if recipient exists
    result = await db.execute(select(User).where(User.email == data.recipient_email))
    recipient = result.scalar_one_or_none()

    invitation = DataShareInvitation(
        sender_id=current_user.id,
        recipient_email=data.recipient_email,
        recipient_user_id=recipient.id if recipient else None,
        data_types=json.dumps(data.data_types),
        message=data.message,
    )
    db.add(invitation)
    await db.flush()
    await db.refresh(invitation)
    # Despite the name, this used to SEND nothing — the row was written and
    # returned, and the invitee never heard about it. An invitation only
    # discoverable by someone already logged in and looking for it is no
    # invitation at all.
    await _announce_invitation(db, invitation, current_user)

    return invitation


async def _announce_invitation(db: AsyncSession, invitation, owner: User) -> None:
    """Reach the invitee in-app when we know them, and by email regardless."""
    owner_name = (owner.full_name or owner.email or "An ALAFIA member").strip()
    kinds = getattr(invitation, "data_types", None) or getattr(invitation, "data_type", "") or "health"
    if isinstance(kinds, (list, tuple)):
        kinds = ", ".join(str(k) for k in kinds)

    recipient_id = getattr(invitation, "recipient_user_id", None)
    if recipient_id:
        try:
            await create_notification(
                db,
                user_id=recipient_id,
                category=NotificationCategory.RECORD_SHARED,
                priority=NotificationPriority.MEDIUM,
                title=f"{owner_name} wants to share their records",
                message=(f"{owner_name} has invited you to view their {kinds} "
                         f"records. Nothing is shared until you accept."),
                action_url="/share-records",
                metadata_dict={"invitation_id": invitation.id, "data_types": str(kinds)},
            )
        except Exception:  # noqa: BLE001
            logger.warning("could not notify invitee of %s", invitation.id, exc_info=True)

    to = getattr(invitation, "recipient_email", None)
    if not to:
        return
    try:
        await send_share_invitation_email(
            to,
            owner_name=owner_name,
            data_types=str(kinds),
            recipient_name=getattr(invitation, "recipient_display_name", None),
            message=getattr(invitation, "message", None),
        )
    except Exception:  # noqa: BLE001
        logger.warning("could not email invitee of %s", invitation.id, exc_info=True)


@router.post("/invitations/{invitation_id}/accept", response_model=list[DataGrantResponse])
async def accept_invitation(
    invitation_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DataShareInvitation).where(
            DataShareInvitation.id == invitation_id,
            DataShareInvitation.status == "pending",
        )
    )
    invitation = result.scalar_one_or_none()
    if not invitation:
        raise HTTPException(status_code=404, detail="Invitation not found or already processed")

    # Verify current user is the recipient
    if invitation.recipient_user_id and invitation.recipient_user_id != current_user.id:
        if invitation.recipient_email != current_user.email:
            raise HTTPException(status_code=403, detail="Not authorized")

    invitation.status = "accepted"
    invitation.recipient_user_id = current_user.id
    from datetime import datetime, timezone
    invitation.responded_at = datetime.now(timezone.utc)

    # Create grants
    data_types = json.loads(invitation.data_types)
    grants = []
    for dt in data_types:
        grant = DataGrant(
            owner_id=current_user.id,
            grantee_user_id=invitation.sender_id,
            data_type=dt,
            read_access=True,
            write_access=False,
        )
        db.add(grant)
        grants.append(grant)

    await db.flush()
    for g in grants:
        await db.refresh(g)
    return grants


@router.post("/invitations/{invitation_id}/decline")
async def decline_invitation(
    invitation_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DataShareInvitation).where(
            DataShareInvitation.id == invitation_id,
            DataShareInvitation.status == "pending",
        )
    )
    invitation = result.scalar_one_or_none()
    if not invitation:
        raise HTTPException(status_code=404, detail="Invitation not found")

    invitation.status = "declined"
    from datetime import datetime, timezone
    invitation.responded_at = datetime.now(timezone.utc)
    await db.flush()
    return {"status": "declined"}
