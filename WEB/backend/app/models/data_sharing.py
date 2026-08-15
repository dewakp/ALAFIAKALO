"""Data Sharing models — granular permissions for users and groups."""

import enum
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Text, Boolean, Integer, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class SharableDataType(str, enum.Enum):
    VITALS = "vitals"
    LABS = "labs"
    MEDICATIONS = "medications"
    NUTRITION = "nutrition"
    FITNESS = "fitness"
    MOOD = "mood"
    LIFESTYLE = "lifestyle"
    DIALYSIS = "dialysis"
    SYMPTOMS = "symptoms"
    CONDITIONS = "conditions"
    JOURNAL = "journal"
    ELIMINATION = "elimination"
    CONNECTED_RECORDS = "connected_records"
    ALL = "all"


# Every category ALL expands to. `all` is meant literally — all of the
# patient's data — so a category added here is covered by every existing
# `all` grant without the patient having to re-share anything.
ALL_DATA_TYPES = [
    "vitals", "labs", "medications", "nutrition", "fitness", "mood",
    "lifestyle", "dialysis", "symptoms", "conditions", "journal",
    "elimination", "connected_records",
]


def grant_covers(permissions: list[str], category: str) -> bool:
    """True when a grant list covers a category, expanding `all`."""
    return "all" in permissions or category in permissions


class DataGrant(Base):
    __tablename__ = "data_grants"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)

    # Share to user or group
    grantee_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    grantee_email: Mapped[str | None] = mapped_column(String(255))
    grantee_display_name: Mapped[str | None] = mapped_column(String(255))

    # What data is shared
    data_type: Mapped[str] = mapped_column(String(50), nullable=False)  # SharableDataType value
    read_access: Mapped[bool] = mapped_column(Boolean, default=True)
    write_access: Mapped[bool] = mapped_column(Boolean, default=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    owner = relationship("User", foreign_keys=[owner_id], backref="data_grants_given")
    grantee = relationship("User", foreign_keys=[grantee_user_id], backref="data_grants_received")


class DataShareInvitation(Base):
    __tablename__ = "data_share_invitations"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    sender_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    recipient_email: Mapped[str] = mapped_column(String(255), nullable=False)
    recipient_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    data_types: Mapped[str] = mapped_column(Text, nullable=False)  # JSON list of SharableDataType values
    message: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending, accepted, declined, expired

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    sender = relationship("User", foreign_keys=[sender_id], backref="share_invitations_sent")
    recipient = relationship("User", foreign_keys=[recipient_user_id], backref="share_invitations_received")
