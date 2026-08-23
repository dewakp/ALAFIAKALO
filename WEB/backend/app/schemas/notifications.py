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
    # The DB column really is called "metadata", but `metadata` is RESERVED on a
    # SQLAlchemy declarative class — it is the MetaData object for the whole
    # schema — so the model maps it to the `extra_data` attribute:
    #
    #     extra_data = Column("metadata", Text, nullable=True)
    #
    # Without validation_alias, from_attributes read `Notification.metadata`,
    # got that MetaData object, and raised one ResponseValidationError PER ROW.
    # The endpoint therefore 200'd only for users with zero notifications; the
    # production account got `18 validation errors` and a 500.
    metadata: str | None = Field(default=None, validation_alias="extra_data")
    is_read: bool
    read_at: datetime | None = None
    created_at: datetime

    # populate_by_name keeps `metadata=` working for callers that build this
    # model directly, now that the validation alias points at the attribute.
    model_config = {"from_attributes": True, "populate_by_name": True}


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
