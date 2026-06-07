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

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.messaging import (
    CommunityPost,
    Conversation,
    ConversationMember,
    ConversationType,
    MemberRole,
    Message,
    MessageReadReceipt,
    MessageType,
    PostLike,
    PostMedia,
    PostReply,
    PostVisibility,
    ReactionType,
    UserFollow,
)
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
    ReplyCreate,
    ReplyUpdate,
    UserProfileBrief,
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
