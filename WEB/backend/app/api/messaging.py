"""
Messaging REST API
──────────────────
Covers:
  • Conversations  — CRUD + members
  • Messages       — CRUD + read-receipts
  • Community Feed — posts, replies, likes, reposts
  • Follows        — follow / unfollow, follower/following lists
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import and_, false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import get_db
from app.core.rate_limit import limiter
from app.core.security import get_current_user
from app.models.messaging import (
    CommunityPost,
    Conversation,
    ConversationMember,
    MemberRole,
    Message,
    MessageReadReceipt,
    PostLike,
    PostReply,
    UserFollow,
)
from app.models.data_sharing import DataGrant
from app.models.user import User
from app.schemas.messaging import (
    ConversationCreate,
    ConversationMemberResponse,
    ConversationResponse,
    ConversationUpdate,
    FollowResponse,
    MemberAdd,
    MemberUpdate,
    MessageCreate,
    MessageResponse,
    MessageUpdate,
    PostCreate,
    PostLikeResponse,
    PostReplyResponse,
    PostResponse,
    PostUpdate,
    RecipientMatch,
    ReplyCreate,
    VALID_CONVERSATION_TYPES,
    VALID_HEALTH_CATEGORIES,
    VALID_MEMBER_ROLES,
    VALID_MESSAGE_TYPES,
    VALID_POST_VISIBILITIES,
    VALID_REACTION_TYPES,
)

router = APIRouter()


# ─────────────────────────────────────────────
# helpers
# ─────────────────────────────────────────────

async def _get_conversation(db: AsyncSession, conv_id: int):
    result = await db.execute(
        select(Conversation)
        .options(selectinload(Conversation.members))
        .where(Conversation.id == conv_id)
    )
    conv = result.scalars().first()
    if not conv:
        raise HTTPException(404, "Conversation not found")
    return conv


async def _verify_membership(db: AsyncSession, conv_id: int, user_id: int):
    result = await db.execute(
        select(ConversationMember).where(
            ConversationMember.conversation_id == conv_id,
            ConversationMember.user_id == user_id,
            ConversationMember.left_at.is_(None),
        )
    )
    member = result.scalars().first()
    if not member:
        raise HTTPException(403, "Not a member of this conversation")
    return member


def _conv_to_response(conv: Conversation, unread: int = 0) -> dict:
    d = {c.key: getattr(conv, c.key) for c in conv.__table__.columns}
    d["members"] = [
        {c.key: getattr(m, c.key) for c in m.__table__.columns}
        for m in (conv.members or [])
    ]
    d["unread_count"] = unread
    return d


# ═══════════════════════════════════════════════
#  R E C I P I E N T   L O O K U P
# ═══════════════════════════════════════════════

#: A compose box has to find people by something a human actually knows — a name,
#: an email, a phone number. A lookup that answered any partial string would also
#: let one account walk the entire patient list, so two rules bound it:
#:
#:   * a COMPLETE identifier (full email, or a phone number) always resolves —
#:     the caller had to know it already in order to type it;
#:   * a PARTIAL name only matches people the caller demonstrably already deals
#:     with: a shared conversation, or a follow edge in either direction.
#:
#: So a patient can reach the nephrologist whose card they were handed, and can
#: find "Dr Adeyemi" among their own care team, but cannot browse the directory.
#: Contact details come back masked unless the caller was already entitled to
#: them — see `RecipientMatch`.
_RECIPIENT_MIN_QUERY = 2
_RECIPIENT_MAX_LIMIT = 25

#: Below this a string is a name fragment, not a phone number.
_MIN_PHONE_DIGITS = 7


def _digits(value: str | None) -> str:
    return "".join(ch for ch in (value or "") if ch.isdigit())


def _mask_email(email: str | None) -> str | None:
    """`dew@6igma.com` -> `d•••@6igma.com` — enough to tell two people apart.

    Fixed width on purpose: padding to the real length would leak how long the
    address is, which is free information for anyone guessing at it.
    """
    if not email or "@" not in email:
        return None
    local, _, domain = email.partition("@")
    return f"{local[:1]}•••@{domain}"


def _mask_phone(phone: str | None) -> str | None:
    digits = _digits(phone)
    return f"•••• {digits[-4:]}" if len(digits) >= 4 else None


def _phone_candidates(term: str) -> list[str]:
    """Plausible stored forms of a typed number.

    Numbers are stored E.164 (`+15551234567`) but people type `(555) 123-4567`.
    Rather than a Postgres-only `regexp_replace` in the WHERE clause, compare
    against the handful of forms the same digits could have been stored as.
    """
    digits = _digits(term)
    if len(digits) < _MIN_PHONE_DIGITS:
        return []
    forms = {digits, f"+{digits}"}
    if not digits.startswith("1"):
        forms |= {f"+1{digits}", f"1{digits}"}
    return sorted(forms)


async def _connected_user_ids(db: AsyncSession, user_id: int) -> set[int]:
    """This user's shared contacts — the only people a partial name may match.

    "Shared" is meant in this app's own sense, and a data grant is the strongest
    form of it: sharing labs or dialysis history with someone is a far more
    deliberate act than following them. Three sources, any of which counts:

      * an active `DataGrant` in either direction — they share data with you, or
        you with them;
      * a conversation you are both still in — you are already talking;
      * a follow edge in either direction.

    Everyone else is unreachable by partial name and can only be found by typing
    their full email or phone number.
    """
    my_conversations = select(ConversationMember.conversation_id).where(
        ConversationMember.user_id == user_id,
        ConversationMember.left_at.is_(None),
    )
    shared_conversation = (await db.execute(
        select(ConversationMember.user_id).where(
            ConversationMember.conversation_id.in_(my_conversations),
            ConversationMember.left_at.is_(None),
        )
    )).scalars().all()
    following = (await db.execute(
        select(UserFollow.following_id).where(UserFollow.follower_id == user_id)
    )).scalars().all()
    followers = (await db.execute(
        select(UserFollow.follower_id).where(UserFollow.following_id == user_id)
    )).scalars().all()

    # An expired or revoked grant is not a contact.
    live_grant = and_(
        DataGrant.is_active.is_(True),
        or_(DataGrant.expires_at.is_(None), DataGrant.expires_at > datetime.now(timezone.utc)),
    )
    granted_to = (await db.execute(
        select(DataGrant.grantee_user_id).where(live_grant, DataGrant.owner_id == user_id)
    )).scalars().all()
    granted_by = (await db.execute(
        select(DataGrant.owner_id).where(live_grant, DataGrant.grantee_user_id == user_id)
    )).scalars().all()

    everyone = (*shared_conversation, *following, *followers, *granted_to, *granted_by)
    return {uid for uid in everyone if uid and uid != user_id}


@router.get("/recipients", response_model=list[RecipientMatch])
@limiter.limit(settings.RATE_LIMIT_LOOKUP)
async def find_recipients(
    request: Request,
    q: str = Query("", description="Name, full email address, or phone number"),
    limit: int = Query(10, ge=1, le=_RECIPIENT_MAX_LIMIT),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Find people to start a conversation with, by name, email or phone.

    This exists so the compose form can stop asking for raw member ids. An id is
    an internal handle; nobody knows their nephrologist's primary key.
    """
    term = (q or "").strip()
    if len(term) < _RECIPIENT_MIN_QUERY:
        return []

    connected = await _connected_user_ids(db, current_user.id)
    lowered = term.lower()

    identifier_clauses = [func.lower(User.email) == lowered]
    phone_forms = _phone_candidates(term)
    if phone_forms:
        identifier_clauses.append(User.phone_number.in_(phone_forms))
    by_identifier = or_(*identifier_clauses)

    # Partial matching is confined to people already connected; with nobody
    # connected it must match no one, not everyone.
    by_name = and_(
        User.id.in_(connected) if connected else false(),
        or_(
            func.lower(User.full_name).like(f"%{lowered}%"),
            func.lower(User.email).like(f"{lowered}%"),
        ),
    )

    rows = (await db.execute(
        select(User)
        .where(
            User.id != current_user.id,
            User.is_active.is_(True),
            or_(by_identifier, by_name),
        )
        .order_by(User.full_name, User.id)
        .limit(limit)
    )).scalars().all()

    matches: list[dict] = []
    for user in rows:
        is_connected = user.id in connected
        matched_email = (user.email or "").lower() == lowered
        matched_phone = bool(phone_forms) and user.phone_number in phone_forms
        # A full identifier comes back only to a caller who already had it. For
        # a shared contact found by name, the masked hint is enough to tell two
        # people apart, and scraping a contact list yields no addresses.
        entitled = matched_email or matched_phone
        matches.append({
            "id": user.id,
            "full_name": user.full_name,
            "email": user.email if entitled else None,
            "phone_number": user.phone_number if entitled else None,
            "email_hint": _mask_email(user.email),
            "phone_hint": _mask_phone(user.phone_number),
            "matched_on": "email" if matched_email else "phone" if matched_phone else "name",
            "connected": is_connected,
        })
    return matches


# ═══════════════════════════════════════════════
#  C O N V E R S A T I O N S
# ═══════════════════════════════════════════════

@router.get("/conversations", response_model=list[ConversationResponse])
async def list_conversations(
    conversation_type: Optional[str] = None,
    is_archived: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List conversations the current user belongs to."""
    q = (
        select(Conversation)
        .join(ConversationMember)
        .options(selectinload(Conversation.members))
        .where(
            ConversationMember.user_id == current_user.id,
            ConversationMember.left_at.is_(None),
            Conversation.is_archived == is_archived,
        )
    )
    if conversation_type:
        q = q.where(Conversation.conversation_type == conversation_type)
    q = q.order_by(Conversation.last_message_at.desc().nullslast(), Conversation.created_at.desc())
    result = await db.execute(q)
    convs = result.scalars().unique().all()

    out = []
    for conv in convs:
        # unread count
        member = next((m for m in conv.members if m.user_id == current_user.id), None)
        unread = 0
        if member and member.last_read_at:
            r = await db.execute(
                select(func.count(Message.id)).where(
                    Message.conversation_id == conv.id,
                    Message.created_at > member.last_read_at,
                    Message.sender_id != current_user.id,
                )
            )
            unread = r.scalar() or 0
        elif member:
            r = await db.execute(
                select(func.count(Message.id)).where(
                    Message.conversation_id == conv.id,
                    Message.sender_id != current_user.id,
                )
            )
            unread = r.scalar() or 0
        out.append(_conv_to_response(conv, unread))
    return out


@router.post("/conversations", response_model=ConversationResponse, status_code=201)
async def create_conversation(
    data: ConversationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if data.conversation_type not in VALID_CONVERSATION_TYPES:
        raise HTTPException(400, f"Invalid type. Must be one of {VALID_CONVERSATION_TYPES}")

    # Member ids used to be written straight into `conversation_members`, so a
    # typo produced a conversation with a member row pointing at nobody — it
    # looked created, and the recipient never heard about it. Resolve them first.
    requested = {uid for uid in data.member_ids if uid != current_user.id}
    if requested:
        found = set((await db.execute(
            select(User.id).where(User.id.in_(requested), User.is_active.is_(True))
        )).scalars().all())
        missing = sorted(requested - found)
        if missing:
            raise HTTPException(400, f"No active user for member id(s): {missing}")

    # For DMs, check if one already exists between these two users
    if data.conversation_type == "direct":
        if len(data.member_ids) != 1:
            raise HTTPException(400, "Direct conversations require exactly 1 other member_id")
        other_id = data.member_ids[0]
        existing = await db.execute(
            select(Conversation)
            .join(ConversationMember)
            .where(
                Conversation.conversation_type == "direct",
                ConversationMember.user_id.in_([current_user.id, other_id]),
                ConversationMember.left_at.is_(None),
            )
            .group_by(Conversation.id)
            .having(func.count(ConversationMember.id) == 2)
        )
        existing_conv = existing.scalars().first()
        if existing_conv:
            conv = await _get_conversation(db, existing_conv.id)
            return _conv_to_response(conv)

    conv = Conversation(
        conversation_type=data.conversation_type,
        title=data.title,
        description=data.description,
        avatar_url=data.avatar_url,
        specialty=data.specialty,
        priority=data.priority,
        is_urgent=data.is_urgent,
        created_by=current_user.id,
    )
    db.add(conv)
    await db.flush()

    # Add creator as owner
    db.add(ConversationMember(
        conversation_id=conv.id,
        user_id=current_user.id,
        role=MemberRole.owner,
    ))

    # Add other members
    for uid in data.member_ids:
        if uid == current_user.id:
            continue
        db.add(ConversationMember(
            conversation_id=conv.id,
            user_id=uid,
            role=MemberRole.member,
        ))
    await db.flush()

    conv = await _get_conversation(db, conv.id)
    await db.commit()
    return _conv_to_response(conv)


@router.get("/conversations/{conv_id}", response_model=ConversationResponse)
async def get_conversation(
    conv_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _verify_membership(db, conv_id, current_user.id)
    conv = await _get_conversation(db, conv_id)
    return _conv_to_response(conv)


@router.patch("/conversations/{conv_id}", response_model=ConversationResponse)
async def update_conversation(
    conv_id: int,
    data: ConversationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    member = await _verify_membership(db, conv_id, current_user.id)
    if member.role not in ("owner", "admin"):
        raise HTTPException(403, "Only owners/admins can update conversation settings")
    conv = await _get_conversation(db, conv_id)
    for k, v in data.model_dump(exclude_none=True).items():
        setattr(conv, k, v)
    await db.commit()
    conv = await _get_conversation(db, conv_id)
    return _conv_to_response(conv)


@router.delete("/conversations/{conv_id}", status_code=204)
async def delete_conversation(
    conv_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    member = await _verify_membership(db, conv_id, current_user.id)
    if member.role != "owner":
        raise HTTPException(403, "Only the owner can delete a conversation")
    conv = await _get_conversation(db, conv_id)
    await db.delete(conv)
    await db.commit()


# ── Members ──

@router.get("/conversations/{conv_id}/members", response_model=list[ConversationMemberResponse])
async def list_members(
    conv_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _verify_membership(db, conv_id, current_user.id)
    r = await db.execute(
        select(ConversationMember).where(
            ConversationMember.conversation_id == conv_id,
            ConversationMember.left_at.is_(None),
        )
    )
    return r.scalars().all()


@router.post("/conversations/{conv_id}/members", response_model=ConversationMemberResponse, status_code=201)
async def add_member(
    conv_id: int,
    data: MemberAdd,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    member = await _verify_membership(db, conv_id, current_user.id)
    if member.role not in ("owner", "admin"):
        raise HTTPException(403, "Only owners/admins can add members")
    if data.role and data.role not in VALID_MEMBER_ROLES:
        raise HTTPException(400, f"Invalid role. Must be one of {VALID_MEMBER_ROLES}")

    # Check not already member
    existing = await db.execute(
        select(ConversationMember).where(
            ConversationMember.conversation_id == conv_id,
            ConversationMember.user_id == data.user_id,
            ConversationMember.left_at.is_(None),
        )
    )
    if existing.scalars().first():
        raise HTTPException(409, "User is already a member")

    m = ConversationMember(
        conversation_id=conv_id,
        user_id=data.user_id,
        role=data.role or MemberRole.member,
    )
    db.add(m)
    await db.commit()
    await db.refresh(m)
    return m


@router.patch("/conversations/{conv_id}/members/{user_id}", response_model=ConversationMemberResponse)
async def update_member(
    conv_id: int,
    user_id: int,
    data: MemberUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    me = await _verify_membership(db, conv_id, current_user.id)
    # Only owner/admin can change other members' roles
    if data.role and me.role not in ("owner", "admin"):
        raise HTTPException(403, "Only owners/admins can change roles")
    target = await _verify_membership(db, conv_id, user_id)
    for k, v in data.model_dump(exclude_none=True).items():
        setattr(target, k, v)
    await db.commit()
    await db.refresh(target)
    return target


@router.delete("/conversations/{conv_id}/members/{user_id}", status_code=204)
async def remove_member(
    conv_id: int,
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    me = await _verify_membership(db, conv_id, current_user.id)
    if user_id != current_user.id and me.role not in ("owner", "admin"):
        raise HTTPException(403, "Only owners/admins can remove other members")
    target = await _verify_membership(db, conv_id, user_id)
    target.left_at = datetime.now(timezone.utc)
    await db.commit()


# ═══════════════════════════════════════════════
#  M E S S A G E S
# ═══════════════════════════════════════════════

@router.get("/conversations/{conv_id}/messages", response_model=list[MessageResponse])
async def list_messages(
    conv_id: int,
    limit: int = Query(50, ge=1, le=200),
    before_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _verify_membership(db, conv_id, current_user.id)
    q = (
        select(Message)
        .options(selectinload(Message.read_receipts))
        .where(Message.conversation_id == conv_id, Message.is_deleted == False)
    )
    if before_id:
        q = q.where(Message.id < before_id)
    q = q.order_by(Message.created_at.desc()).limit(limit)
    r = await db.execute(q)
    return list(reversed(r.scalars().all()))


@router.post("/conversations/{conv_id}/messages", response_model=MessageResponse, status_code=201)
async def send_message(
    conv_id: int,
    data: MessageCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _verify_membership(db, conv_id, current_user.id)
    conv = await _get_conversation(db, conv_id)
    if not conv.allow_replies:
        raise HTTPException(403, "Replies are disabled for this conversation")

    if data.message_type not in VALID_MESSAGE_TYPES:
        raise HTTPException(400, f"Invalid message type. Must be one of {VALID_MESSAGE_TYPES}")

    msg = Message(
        conversation_id=conv_id,
        sender_id=current_user.id,
        **data.model_dump(),
    )
    db.add(msg)
    await db.flush()

    # Update conversation preview
    conv.last_message_at = datetime.now(timezone.utc)
    preview = (data.content or "")[:300]
    if data.message_type == "image":
        preview = "📷 Image"
    elif data.message_type == "file":
        preview = f"📎 {data.file_name or 'File'}"
    elif data.message_type == "voice":
        preview = "🎤 Voice message"
    conv.last_message_preview = preview

    # Mark sender as read
    me = await _verify_membership(db, conv_id, current_user.id)
    me.last_read_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(msg)
    r = await db.execute(
        select(Message).options(selectinload(Message.read_receipts)).where(Message.id == msg.id)
    )
    return r.scalars().first()


@router.patch("/conversations/{conv_id}/messages/{msg_id}", response_model=MessageResponse)
async def edit_message(
    conv_id: int,
    msg_id: int,
    data: MessageUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _verify_membership(db, conv_id, current_user.id)
    r = await db.execute(
        select(Message).options(selectinload(Message.read_receipts)).where(
            Message.id == msg_id, Message.conversation_id == conv_id
        )
    )
    msg = r.scalars().first()
    if not msg:
        raise HTTPException(404, "Message not found")
    if msg.sender_id != current_user.id:
        raise HTTPException(403, "Can only edit your own messages")
    if data.content is not None:
        msg.content = data.content
        msg.is_edited = True
        msg.edited_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(msg)
    return msg


@router.delete("/conversations/{conv_id}/messages/{msg_id}", status_code=204)
async def delete_message(
    conv_id: int,
    msg_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _verify_membership(db, conv_id, current_user.id)
    r = await db.execute(
        select(Message).where(Message.id == msg_id, Message.conversation_id == conv_id)
    )
    msg = r.scalars().first()
    if not msg:
        raise HTTPException(404, "Message not found")
    if msg.sender_id != current_user.id:
        raise HTTPException(403, "Can only delete your own messages")
    msg.is_deleted = True
    msg.content = None
    await db.commit()


@router.post("/conversations/{conv_id}/messages/{msg_id}/read", status_code=201)
async def mark_message_read(
    conv_id: int,
    msg_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _verify_membership(db, conv_id, current_user.id)
    existing = await db.execute(
        select(MessageReadReceipt).where(
            MessageReadReceipt.message_id == msg_id,
            MessageReadReceipt.user_id == current_user.id,
        )
    )
    if existing.scalars().first():
        return {"detail": "Already read"}
    db.add(MessageReadReceipt(message_id=msg_id, user_id=current_user.id))
    # Also update member last_read_at
    member = await _verify_membership(db, conv_id, current_user.id)
    member.last_read_at = datetime.now(timezone.utc)
    await db.commit()
    return {"detail": "Marked as read"}


@router.post("/conversations/{conv_id}/read", status_code=200)
async def mark_conversation_read(
    conv_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    member = await _verify_membership(db, conv_id, current_user.id)
    member.last_read_at = datetime.now(timezone.utc)
    await db.commit()
    return {"detail": "Conversation marked as read"}


# ═══════════════════════════════════════════════
#  C O M M U N I T Y   F E E D
# ═══════════════════════════════════════════════

@router.get("/feed", response_model=list[PostResponse])
async def list_feed(
    topic: Optional[str] = None,
    health_category: Optional[str] = None,
    author_id: Optional[int] = None,
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = (
        select(CommunityPost)
        .options(
            selectinload(CommunityPost.media),
            selectinload(CommunityPost.likes),
        )
        .where(CommunityPost.is_deleted == False)
    )
    if topic:
        q = q.where(CommunityPost.topic == topic)
    if health_category:
        q = q.where(CommunityPost.health_category == health_category)
    if author_id:
        q = q.where(CommunityPost.author_id == author_id)
    q = q.order_by(CommunityPost.created_at.desc()).offset(offset).limit(limit)
    r = await db.execute(q)
    posts = r.scalars().unique().all()

    out = []
    for p in posts:
        d = {c.key: getattr(p, c.key) for c in p.__table__.columns}
        d["media"] = [{c.key: getattr(m, c.key) for c in m.__table__.columns} for m in (p.media or [])]
        d["replies"] = []
        d["likes"] = [{c.key: getattr(lk, c.key) for c in lk.__table__.columns} for lk in (p.likes or [])]
        user_like = next((lk for lk in (p.likes or []) if lk.user_id == current_user.id), None)
        d["user_liked"] = user_like is not None
        d["user_reaction"] = user_like.reaction if user_like else None
        out.append(d)
    return out


@router.post("/feed", response_model=PostResponse, status_code=201)
async def create_post(
    data: PostCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if data.visibility not in VALID_POST_VISIBILITIES:
        raise HTTPException(400, f"Invalid visibility. Must be one of {VALID_POST_VISIBILITIES}")
    if data.health_category and data.health_category not in VALID_HEALTH_CATEGORIES:
        raise HTTPException(400, f"Invalid health category. Must be one of {VALID_HEALTH_CATEGORIES}")

    post_data = data.model_dump()
    # Handle repost
    if data.original_post_id:
        orig = await db.execute(
            select(CommunityPost).where(CommunityPost.id == data.original_post_id)
        )
        orig_post = orig.scalars().first()
        if not orig_post:
            raise HTTPException(404, "Original post not found")
        post_data["is_repost"] = True
        # Increment repost count
        orig_post.repost_count += 1

    post = CommunityPost(author_id=current_user.id, **post_data)
    db.add(post)
    await db.commit()
    await db.refresh(post)
    r = await db.execute(
        select(CommunityPost)
        .options(selectinload(CommunityPost.media), selectinload(CommunityPost.likes))
        .where(CommunityPost.id == post.id)
    )
    p = r.scalars().first()
    d = {c.key: getattr(p, c.key) for c in p.__table__.columns}
    d["media"] = []
    d["replies"] = []
    d["likes"] = []
    d["user_liked"] = False
    d["user_reaction"] = None
    return d


@router.get("/feed/{post_id}", response_model=PostResponse)
async def get_post(
    post_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    r = await db.execute(
        select(CommunityPost)
        .options(
            selectinload(CommunityPost.media),
            selectinload(CommunityPost.replies),
            selectinload(CommunityPost.likes),
        )
        .where(CommunityPost.id == post_id, CommunityPost.is_deleted == False)
    )
    p = r.scalars().first()
    if not p:
        raise HTTPException(404, "Post not found")
    # Increment view count
    p.view_count += 1
    await db.commit()

    d = {c.key: getattr(p, c.key) for c in p.__table__.columns}
    d["media"] = [{c.key: getattr(m, c.key) for c in m.__table__.columns} for m in (p.media or [])]
    d["replies"] = [{c.key: getattr(rp, c.key) for c in rp.__table__.columns} for rp in (p.replies or [])]
    d["likes"] = [{c.key: getattr(lk, c.key) for c in lk.__table__.columns} for lk in (p.likes or [])]
    user_like = next((lk for lk in (p.likes or []) if lk.user_id == current_user.id), None)
    d["user_liked"] = user_like is not None
    d["user_reaction"] = user_like.reaction if user_like else None
    return d


@router.patch("/feed/{post_id}", response_model=PostResponse)
async def update_post(
    post_id: int,
    data: PostUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    r = await db.execute(
        select(CommunityPost)
        .options(selectinload(CommunityPost.media), selectinload(CommunityPost.likes))
        .where(CommunityPost.id == post_id)
    )
    p = r.scalars().first()
    if not p:
        raise HTTPException(404, "Post not found")
    if p.author_id != current_user.id:
        raise HTTPException(403, "Can only edit your own posts")
    for k, v in data.model_dump(exclude_none=True).items():
        setattr(p, k, v)
    p.is_edited = True
    await db.commit()
    await db.refresh(p)
    d = {c.key: getattr(p, c.key) for c in p.__table__.columns}
    d["media"] = [{c.key: getattr(m, c.key) for c in m.__table__.columns} for m in (p.media or [])]
    d["replies"] = []
    d["likes"] = [{c.key: getattr(lk, c.key) for c in lk.__table__.columns} for lk in (p.likes or [])]
    user_like = next((lk for lk in (p.likes or []) if lk.user_id == current_user.id), None)
    d["user_liked"] = user_like is not None
    d["user_reaction"] = user_like.reaction if user_like else None
    return d


@router.delete("/feed/{post_id}", status_code=204)
async def delete_post(
    post_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    r = await db.execute(select(CommunityPost).where(CommunityPost.id == post_id))
    p = r.scalars().first()
    if not p:
        raise HTTPException(404, "Post not found")
    if p.author_id != current_user.id:
        raise HTTPException(403, "Can only delete your own posts")
    p.is_deleted = True
    p.content = "[deleted]"
    await db.commit()


# ── Replies ──

@router.get("/feed/{post_id}/replies", response_model=list[PostReplyResponse])
async def list_replies(
    post_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    r = await db.execute(
        select(PostReply)
        .where(PostReply.post_id == post_id, PostReply.is_deleted == False)
        .order_by(PostReply.created_at)
    )
    return r.scalars().all()


@router.post("/feed/{post_id}/replies", response_model=PostReplyResponse, status_code=201)
async def create_reply(
    post_id: int,
    data: ReplyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Verify post exists
    r = await db.execute(select(CommunityPost).where(CommunityPost.id == post_id, CommunityPost.is_deleted == False))
    post = r.scalars().first()
    if not post:
        raise HTTPException(404, "Post not found")

    reply = PostReply(
        post_id=post_id,
        author_id=current_user.id,
        content=data.content,
        parent_reply_id=data.parent_reply_id,
    )
    db.add(reply)
    post.reply_count += 1
    await db.commit()
    await db.refresh(reply)
    return reply


@router.delete("/feed/{post_id}/replies/{reply_id}", status_code=204)
async def delete_reply(
    post_id: int,
    reply_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    r = await db.execute(
        select(PostReply).where(PostReply.id == reply_id, PostReply.post_id == post_id)
    )
    reply = r.scalars().first()
    if not reply:
        raise HTTPException(404, "Reply not found")
    if reply.author_id != current_user.id:
        raise HTTPException(403, "Can only delete your own replies")
    reply.is_deleted = True
    reply.content = "[deleted]"
    # Decrement count
    pr = await db.execute(select(CommunityPost).where(CommunityPost.id == post_id))
    post = pr.scalars().first()
    if post and post.reply_count > 0:
        post.reply_count -= 1
    await db.commit()


# ── Likes ──

@router.post("/feed/{post_id}/like", response_model=PostLikeResponse, status_code=201)
async def like_post(
    post_id: int,
    reaction: str = Query("like"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if reaction not in VALID_REACTION_TYPES:
        raise HTTPException(400, f"Invalid reaction. Must be one of {VALID_REACTION_TYPES}")
    existing = await db.execute(
        select(PostLike).where(PostLike.post_id == post_id, PostLike.user_id == current_user.id)
    )
    like = existing.scalars().first()
    if like:
        # Update reaction
        like.reaction = reaction
        await db.commit()
        await db.refresh(like)
        return like

    like = PostLike(post_id=post_id, user_id=current_user.id, reaction=reaction)
    db.add(like)
    # Increment count
    r = await db.execute(select(CommunityPost).where(CommunityPost.id == post_id))
    post = r.scalars().first()
    if post:
        post.like_count += 1
    await db.commit()
    await db.refresh(like)
    return like


@router.delete("/feed/{post_id}/like", status_code=204)
async def unlike_post(
    post_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    r = await db.execute(
        select(PostLike).where(PostLike.post_id == post_id, PostLike.user_id == current_user.id)
    )
    like = r.scalars().first()
    if not like:
        raise HTTPException(404, "Like not found")
    await db.delete(like)
    # Decrement count
    pr = await db.execute(select(CommunityPost).where(CommunityPost.id == post_id))
    post = pr.scalars().first()
    if post and post.like_count > 0:
        post.like_count -= 1
    await db.commit()


# ═══════════════════════════════════════════════
#  F O L L O W S
# ═══════════════════════════════════════════════

@router.post("/follow/{user_id}", response_model=FollowResponse, status_code=201)
async def follow_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if user_id == current_user.id:
        raise HTTPException(400, "Cannot follow yourself")
    # Check user exists
    r = await db.execute(select(User).where(User.id == user_id))
    if not r.scalars().first():
        raise HTTPException(404, "User not found")
    existing = await db.execute(
        select(UserFollow).where(
            UserFollow.follower_id == current_user.id,
            UserFollow.following_id == user_id,
        )
    )
    if existing.scalars().first():
        raise HTTPException(409, "Already following this user")
    follow = UserFollow(follower_id=current_user.id, following_id=user_id)
    db.add(follow)
    await db.commit()
    await db.refresh(follow)
    return follow


@router.delete("/follow/{user_id}", status_code=204)
async def unfollow_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    r = await db.execute(
        select(UserFollow).where(
            UserFollow.follower_id == current_user.id,
            UserFollow.following_id == user_id,
        )
    )
    follow = r.scalars().first()
    if not follow:
        raise HTTPException(404, "Not following this user")
    await db.delete(follow)
    await db.commit()


@router.get("/followers/{user_id}", response_model=list[FollowResponse])
async def list_followers(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    r = await db.execute(
        select(UserFollow).where(UserFollow.following_id == user_id).order_by(UserFollow.created_at.desc())
    )
    return r.scalars().all()


@router.get("/following/{user_id}", response_model=list[FollowResponse])
async def list_following(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    r = await db.execute(
        select(UserFollow).where(UserFollow.follower_id == user_id).order_by(UserFollow.created_at.desc())
    )
    return r.scalars().all()
