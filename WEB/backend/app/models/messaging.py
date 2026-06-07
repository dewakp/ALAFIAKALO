"""
Messaging models – covers three messaging modes:

1. **Direct Messages** (peer-to-peer, patient↔clinician)  – Conversation + Message
2. **Group Chats** (care-team channels)                    – same Conversation model with type="group"
3. **Community Feed** (Twitter-style public posts)         – CommunityPost, PostReply, PostLike, PostMedia

Key tables
----------
- conversations          – DM / group metadata
- conversation_members   – many-to-many users ↔ conversations
- messages               – individual messages in a conversation
- message_read_receipts  – per-user read tracking
- community_posts        – public timeline posts
- post_replies           – threaded replies
- post_likes             – like / reaction on posts
- post_media             – images / videos attached to a post
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


# ──────────────────────────────────────────────
#  Enums
# ──────────────────────────────────────────────

class ConversationType(str, enum.Enum):
    direct = "direct"
    group = "group"
    clinical = "clinical"            # patient ↔ clinician thread
    care_team = "care_team"          # multi-provider channel


class MessageType(str, enum.Enum):
    text = "text"
    image = "image"
    file = "file"
    voice = "voice"
    system = "system"                # join / leave / assignment notices
    referral = "referral"


class MemberRole(str, enum.Enum):
    owner = "owner"
    admin = "admin"
    member = "member"
    observer = "observer"            # read-only (e.g. supervisors)


class PostVisibility(str, enum.Enum):
    public = "public"
    followers = "followers"
    connections = "connections"       # mutual follow
    private = "private"              # only author can see (drafts)


class ReactionType(str, enum.Enum):
    like = "like"
    love = "love"
    support = "support"
    insightful = "insightful"
    celebrate = "celebrate"


class MediaType(str, enum.Enum):
    image = "image"
    video = "video"
    gif = "gif"


# ──────────────────────────────────────────────
#  Direct / Group Conversations
# ──────────────────────────────────────────────

class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_type: Mapped[str] = mapped_column(
        Enum(ConversationType, name="conversation_type_enum"), nullable=False
    )
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Clinical metadata (for clinical / care_team conversations)
    specialty: Mapped[str | None] = mapped_column(String(100), nullable=True)
    priority: Mapped[str | None] = mapped_column(String(20), nullable=True)          # routine / urgent / stat
    is_urgent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Permissions
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_muted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    allow_replies: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Auto-fields
    created_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_message_preview: Mapped[str | None] = mapped_column(String(300), nullable=True)

    # Relationships
    members = relationship("ConversationMember", back_populates="conversation", cascade="all, delete-orphan")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")
    creator = relationship("User", foreign_keys=[created_by])


class ConversationMember(Base):
    __tablename__ = "conversation_members"
    __table_args__ = (
        UniqueConstraint("conversation_id", "user_id", name="uq_conv_member"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(
        Enum(MemberRole, name="member_role_enum"), default=MemberRole.member, nullable=False
    )
    nickname: Mapped[str | None] = mapped_column(String(100), nullable=True)

    is_muted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    last_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    conversation = relationship("Conversation", back_populates="members")
    user = relationship("User", foreign_keys=[user_id])


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    sender_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    message_type: Mapped[str] = mapped_column(
        Enum(MessageType, name="message_type_enum"), default=MessageType.text, nullable=False
    )
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Attachments
    file_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    file_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Threading
    reply_to_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("messages.id"), nullable=True)

    # Clinical
    is_clinical: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_priority: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Status
    is_edited: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relationships
    conversation = relationship("Conversation", back_populates="messages")
    sender = relationship("User", foreign_keys=[sender_id])
    reply_to = relationship("Message", remote_side="Message.id", foreign_keys=[reply_to_id])
    read_receipts = relationship("MessageReadReceipt", back_populates="message", cascade="all, delete-orphan")


class MessageReadReceipt(Base):
    __tablename__ = "message_read_receipts"
    __table_args__ = (
        UniqueConstraint("message_id", "user_id", name="uq_msg_read"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    message_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("messages.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    read_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    message = relationship("Message", back_populates="read_receipts")
    user = relationship("User", foreign_keys=[user_id])


# ──────────────────────────────────────────────
#  Community Feed (Twitter-style)
# ──────────────────────────────────────────────

class CommunityPost(Base):
    __tablename__ = "community_posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    author_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    content: Mapped[str] = mapped_column(Text, nullable=False)
    visibility: Mapped[str] = mapped_column(
        Enum(PostVisibility, name="post_visibility_enum"), default=PostVisibility.public, nullable=False
    )

    # Hashtag / topic
    topic: Mapped[str | None] = mapped_column(String(100), nullable=True)          # e.g. "mental-health"
    hashtags: Mapped[str | None] = mapped_column(Text, nullable=True)              # comma-separated
    mentions: Mapped[str | None] = mapped_column(Text, nullable=True)              # comma-separated user ids

    # Health context (opt-in sharing)
    health_category: Mapped[str | None] = mapped_column(String(50), nullable=True)  # fitness, nutrition, mood …
    is_anonymous: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Metrics (denormalised for feed performance)
    like_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reply_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    repost_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    view_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Repost support
    is_repost: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    original_post_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("community_posts.id"), nullable=True
    )
    repost_comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Moderation
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_edited: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_flagged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    author = relationship("User", foreign_keys=[author_id])
    original_post = relationship("CommunityPost", remote_side="CommunityPost.id", foreign_keys=[original_post_id])
    replies = relationship("PostReply", back_populates="post", cascade="all, delete-orphan")
    likes = relationship("PostLike", back_populates="post", cascade="all, delete-orphan")
    media = relationship("PostMedia", back_populates="post", cascade="all, delete-orphan")


class PostReply(Base):
    __tablename__ = "post_replies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    post_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("community_posts.id", ondelete="CASCADE"), nullable=False
    )
    author_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Threading – allow reply-to-reply
    parent_reply_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("post_replies.id"), nullable=True
    )

    like_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_edited: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    post = relationship("CommunityPost", back_populates="replies")
    author = relationship("User", foreign_keys=[author_id])
    parent_reply = relationship("PostReply", remote_side="PostReply.id", foreign_keys=[parent_reply_id])


class PostLike(Base):
    __tablename__ = "post_likes"
    __table_args__ = (
        UniqueConstraint("post_id", "user_id", name="uq_post_like"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    post_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("community_posts.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    reaction: Mapped[str] = mapped_column(
        Enum(ReactionType, name="reaction_type_enum"), default=ReactionType.like, nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    post = relationship("CommunityPost", back_populates="likes")
    user = relationship("User", foreign_keys=[user_id])


class PostMedia(Base):
    __tablename__ = "post_media"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    post_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("community_posts.id", ondelete="CASCADE"), nullable=False
    )
    media_type: Mapped[str] = mapped_column(
        Enum(MediaType, name="media_type_enum"), nullable=False
    )
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    thumbnail_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    alt_text: Mapped[str | None] = mapped_column(String(300), nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    post = relationship("CommunityPost", back_populates="media")


class UserFollow(Base):
    """Follower graph for the community feed."""
    __tablename__ = "user_follows"
    __table_args__ = (
        UniqueConstraint("follower_id", "following_id", name="uq_user_follow"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    follower_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    following_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    follower = relationship("User", foreign_keys=[follower_id])
    following = relationship("User", foreign_keys=[following_id])


# Indexes for common queries
Index("ix_messages_conversation", Message.conversation_id, Message.created_at.desc())
Index("ix_community_posts_author", CommunityPost.author_id, CommunityPost.created_at.desc())
Index("ix_community_posts_topic", CommunityPost.topic)
Index("ix_post_replies_post", PostReply.post_id, PostReply.created_at)
Index("ix_user_follows_follower", UserFollow.follower_id)
Index("ix_user_follows_following", UserFollow.following_id)
