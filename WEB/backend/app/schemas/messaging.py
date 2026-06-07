"""Pydantic schemas for the Messaging system."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

# ── Validation constants ──

VALID_CONVERSATION_TYPES = {"direct", "group", "clinical", "care_team"}
VALID_MESSAGE_TYPES = {"text", "image", "file", "voice", "system", "referral"}
VALID_MEMBER_ROLES = {"owner", "admin", "member", "observer"}
VALID_POST_VISIBILITIES = {"public", "followers", "connections", "private"}
VALID_REACTION_TYPES = {"like", "love", "support", "insightful", "celebrate"}
VALID_MEDIA_TYPES = {"image", "video", "gif"}
VALID_PRIORITIES = {"routine", "urgent", "stat"}
VALID_HEALTH_CATEGORIES = {
    "fitness", "nutrition", "mood", "mental_health", "medications",
    "labs", "lifestyle", "general", "community_health",
}

# ══════════════════════════════════════════════
#  Conversations
# ══════════════════════════════════════════════

class ConversationCreate(BaseModel):
    conversation_type: str = Field("direct", description="direct | group | clinical | care_team")
    title: Optional[str] = None
    description: Optional[str] = None
    avatar_url: Optional[str] = None
    specialty: Optional[str] = None
    priority: Optional[str] = None
    is_urgent: bool = False
    member_ids: List[int] = Field(default_factory=list, description="User IDs to add")


class ConversationUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    avatar_url: Optional[str] = None
    specialty: Optional[str] = None
    priority: Optional[str] = None
    is_urgent: Optional[bool] = None
    is_archived: Optional[bool] = None
    is_muted: Optional[bool] = None
    allow_replies: Optional[bool] = None


class ConversationMemberResponse(BaseModel):
    id: int
    conversation_id: int
    user_id: int
    role: str
    nickname: Optional[str] = None
    is_muted: bool = False
    is_pinned: bool = False
    notifications_enabled: bool = True
    last_read_at: Optional[datetime] = None
    joined_at: datetime
    left_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ConversationResponse(BaseModel):
    id: int
    conversation_type: str
    title: Optional[str] = None
    description: Optional[str] = None
    avatar_url: Optional[str] = None
    specialty: Optional[str] = None
    priority: Optional[str] = None
    is_urgent: bool = False
    is_archived: bool = False
    is_muted: bool = False
    allow_replies: bool = True
    created_by: int
    created_at: datetime
    updated_at: datetime
    last_message_at: Optional[datetime] = None
    last_message_preview: Optional[str] = None
    members: List[ConversationMemberResponse] = []
    unread_count: int = 0

    model_config = {"from_attributes": True}


# ══════════════════════════════════════════════
#  Members
# ══════════════════════════════════════════════

class MemberAdd(BaseModel):
    user_id: int
    role: str = "member"


class MemberUpdate(BaseModel):
    role: Optional[str] = None
    nickname: Optional[str] = None
    is_muted: Optional[bool] = None
    is_pinned: Optional[bool] = None
    notifications_enabled: Optional[bool] = None


# ══════════════════════════════════════════════
#  Messages
# ══════════════════════════════════════════════

class MessageCreate(BaseModel):
    message_type: str = "text"
    content: Optional[str] = None
    file_url: Optional[str] = None
    file_name: Optional[str] = None
    file_size: Optional[int] = None
    file_mime_type: Optional[str] = None
    reply_to_id: Optional[int] = None
    is_clinical: bool = False
    is_priority: bool = False


class MessageUpdate(BaseModel):
    content: Optional[str] = None


class MessageReadReceiptResponse(BaseModel):
    id: int
    message_id: int
    user_id: int
    read_at: datetime

    model_config = {"from_attributes": True}


class MessageResponse(BaseModel):
    id: int
    conversation_id: int
    sender_id: int
    message_type: str
    content: Optional[str] = None
    file_url: Optional[str] = None
    file_name: Optional[str] = None
    file_size: Optional[int] = None
    file_mime_type: Optional[str] = None
    reply_to_id: Optional[int] = None
    is_clinical: bool = False
    is_priority: bool = False
    is_edited: bool = False
    is_deleted: bool = False
    edited_at: Optional[datetime] = None
    created_at: datetime
    read_receipts: List[MessageReadReceiptResponse] = []

    model_config = {"from_attributes": True}


# ══════════════════════════════════════════════
#  Community Posts
# ══════════════════════════════════════════════

class PostCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)
    visibility: str = "public"
    topic: Optional[str] = None
    hashtags: Optional[str] = None
    mentions: Optional[str] = None
    health_category: Optional[str] = None
    is_anonymous: bool = False
    # Repost
    original_post_id: Optional[int] = None
    repost_comment: Optional[str] = None


class PostUpdate(BaseModel):
    content: Optional[str] = Field(None, min_length=1, max_length=5000)
    visibility: Optional[str] = None
    topic: Optional[str] = None
    hashtags: Optional[str] = None
    health_category: Optional[str] = None
    is_pinned: Optional[bool] = None


class PostMediaResponse(BaseModel):
    id: int
    post_id: int
    media_type: str
    url: str
    thumbnail_url: Optional[str] = None
    alt_text: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    duration_seconds: Optional[float] = None
    sort_order: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}


class PostReplyResponse(BaseModel):
    id: int
    post_id: int
    author_id: int
    content: str
    parent_reply_id: Optional[int] = None
    like_count: int = 0
    is_edited: bool = False
    is_deleted: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PostLikeResponse(BaseModel):
    id: int
    post_id: int
    user_id: int
    reaction: str
    created_at: datetime

    model_config = {"from_attributes": True}


class PostResponse(BaseModel):
    id: int
    author_id: int
    content: str
    visibility: str
    topic: Optional[str] = None
    hashtags: Optional[str] = None
    mentions: Optional[str] = None
    health_category: Optional[str] = None
    is_anonymous: bool = False
    like_count: int = 0
    reply_count: int = 0
    repost_count: int = 0
    view_count: int = 0
    is_repost: bool = False
    original_post_id: Optional[int] = None
    repost_comment: Optional[str] = None
    is_pinned: bool = False
    is_edited: bool = False
    is_deleted: bool = False
    is_flagged: bool = False
    created_at: datetime
    updated_at: datetime
    media: List[PostMediaResponse] = []
    replies: List[PostReplyResponse] = []
    likes: List[PostLikeResponse] = []
    user_liked: bool = False
    user_reaction: Optional[str] = None

    model_config = {"from_attributes": True}


# ══════════════════════════════════════════════
#  Replies
# ══════════════════════════════════════════════

class ReplyCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)
    parent_reply_id: Optional[int] = None


class ReplyUpdate(BaseModel):
    content: Optional[str] = Field(None, min_length=1, max_length=2000)


# ══════════════════════════════════════════════
#  Follows
# ══════════════════════════════════════════════

class FollowResponse(BaseModel):
    id: int
    follower_id: int
    following_id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class UserProfileBrief(BaseModel):
    id: int
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    follower_count: int = 0
    following_count: int = 0
    is_following: bool = False

    model_config = {"from_attributes": True}


# ── Forward-ref rebuild ──
ConversationResponse.model_rebuild()
MessageResponse.model_rebuild()
PostResponse.model_rebuild()
