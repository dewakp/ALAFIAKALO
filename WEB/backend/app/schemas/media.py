"""Media schemas for user-captured health images."""

from datetime import datetime
from pydantic import BaseModel, Field


class MediaAssetCreate(BaseModel):
    """Used for legacy JSON base64 uploads (S3 not configured)."""
    category: str = Field(..., examples=["food", "elimination", "medication", "injury", "other"])
    title: str | None = None
    notes: str | None = None
    captured_at: datetime | None = None
    content_type: str | None = None
    file_name: str | None = None
    file_size_bytes: int | None = None
    image_base64: str | None = None
    source: str | None = None


class MediaAssetResponse(BaseModel):
    id: int
    category: str
    title: str | None = None
    notes: str | None = None
    captured_at: datetime | None = None
    content_type: str | None = None
    file_name: str | None = None
    file_size_bytes: int | None = None
    # Clients should prefer storage_url when present; fall back to image_base64
    storage_url: str | None = None
    image_base64: str | None = None
    source: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
