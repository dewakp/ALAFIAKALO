"""Push notification device token model.

Stores APNs (iOS) and FCM (Android) device tokens so the backend can deliver
push notifications to a user's registered devices. A user may have several
devices, so this is a per-token table keyed by the unique device token.
"""

from datetime import datetime, timezone

from sqlalchemy import String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DeviceToken(Base):
    """A single push token registered by a user's device.

    platform is "ios" (APNs) or "android" (FCM). The raw token is unique;
    re-registering the same token updates the owning user / last_seen rather
    than creating a duplicate row.
    """

    __tablename__ = "device_tokens"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token: Mapped[str] = mapped_column(String(512), nullable=False, unique=True, index=True)
    platform: Mapped[str] = mapped_column(String(20), nullable=False, default="ios")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
