"""Notification schemas."""

from datetime import datetime
from pydantic import BaseModel, Field


class NotificationOut(BaseModel):
    id: int
    user_id: int
    category: str
    priority: str
    title: str
    message: str
    action_url: str | None = None
    metadata: str | None = None
    is_read: bool
    read_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class NotificationPreferenceOut(BaseModel):
    id: int
    user_id: int
    category: str
    enabled: bool
    in_app: bool
    push: bool
    email: bool
    sms: bool

    model_config = {"from_attributes": True}


class NotificationPreferenceUpdate(BaseModel):
    enabled: bool | None = None
    in_app: bool | None = None
    push: bool | None = None
    email: bool | None = None
    sms: bool | None = None


class UnreadCountOut(BaseModel):
    count: int


# ── Push device tokens ──────────────────────────────────────────────

class DeviceTokenRegister(BaseModel):
    """Body for registering an APNs / FCM device token."""

    token: str = Field(..., min_length=1, max_length=512)
    platform: str | None = None  # "ios" | "android"; inferred from route when omitted


class DeviceTokenOut(BaseModel):
    id: int
    user_id: int
    token: str
    platform: str

    model_config = {"from_attributes": True}
