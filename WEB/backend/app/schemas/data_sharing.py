"""Data Sharing schemas."""

from datetime import datetime
from pydantic import BaseModel


from app.models.data_sharing import ALL_DATA_TYPES

SHARABLE_DATA_TYPES = ALL_DATA_TYPES + ["all"]


class DataGrantCreate(BaseModel):
    grantee_user_id: int | None = None
    grantee_email: str | None = None
    grantee_display_name: str | None = None
    data_type: str
    read_access: bool = True
    write_access: bool = False
    expires_at: datetime | None = None
    notes: str | None = None


class DataGrantUpdate(BaseModel):
    read_access: bool | None = None
    write_access: bool | None = None
    is_active: bool | None = None
    expires_at: datetime | None = None
    notes: str | None = None


class DataGrantResponse(BaseModel):
    id: int
    owner_id: int
    grantee_user_id: int | None = None
    grantee_email: str | None = None
    grantee_display_name: str | None = None
    data_type: str
    read_access: bool
    write_access: bool
    is_active: bool
    expires_at: datetime | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class DataShareInvitationCreate(BaseModel):
    recipient_email: str
    data_types: list[str]
    message: str | None = None


class DataShareInvitationResponse(BaseModel):
    id: int
    sender_id: int
    recipient_email: str
    recipient_user_id: int | None = None
    data_types: str
    message: str | None = None
    status: str
    created_at: datetime
    responded_at: datetime | None = None
    model_config = {"from_attributes": True}
