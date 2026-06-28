"""Identity schema — the SINGLE source of truth for user identity (zero dup).

Tables live in the `identity` schema, co-resident on ALAFIA's Postgres cluster.
Seeded conceptually from FlowSheet's 02_users_and_identity.sql + 07_system_identifier.sql.
"""

import uuid
from datetime import datetime, timezone, date

from sqlalchemy import String, Boolean, DateTime, Date, ForeignKey, CHAR, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config import settings
from app.database import Base

SCHEMA = settings.DB_SCHEMA

# Role values mirror FlowSheet's account_role enum (stored as text for portability).
ACCOUNT_ROLES = ("patient", "nurse", "physician", "care_partner", "admin")
# Progressive entitlement: FlowSheet (intro) → full ALAFIA. (Plan §6b "no glitch".)
TIERS = ("flowsheet", "full")


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    account_role: Mapped[str] = mapped_column(String(20), nullable=False, default="patient")
    tier: Mapped[str] = mapped_column(String(20), nullable=False, default="flowsheet")
    account_status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    system_id: Mapped[str | None] = mapped_column(CHAR(255), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    identity: Mapped["UserIdentity"] = relationship(back_populates="user", uselist=False,
                                                    cascade="all, delete-orphan")


class UserIdentity(Base):
    """Canonical profile — the ONLY copy. Apps read this via the identity API."""
    __tablename__ = "user_identity"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.users.id", ondelete="CASCADE"),
        unique=True, nullable=False,
    )
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    gender: Mapped[str | None] = mapped_column(String(30))          # current gender identity
    biological_sex: Mapped[str | None] = mapped_column(String(30))  # feeds the SID GEN1 segment
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    user: Mapped["User"] = relationship(back_populates="identity")


class SidLog(Base):
    """Append-only decoded SID segments (support/audit)."""
    __tablename__ = "user_identity_sid_log"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.users.id", ondelete="CASCADE"), nullable=False)
    system_id: Mapped[str] = mapped_column(CHAR(255), nullable=False)
    seg_version: Mapped[str] = mapped_column(String(2), nullable=False)
    seg_fn3: Mapped[str] = mapped_column(String(3), nullable=False)
    seg_ln3: Mapped[str] = mapped_column(String(3), nullable=False)
    seg_dob8: Mapped[str] = mapped_column(String(8), nullable=False)
    seg_gen1: Mapped[str] = mapped_column(String(1), nullable=False)
    seg_epoch10: Mapped[str] = mapped_column(String(10), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class LegacyAuthLink(Base):
    """Migration-only record of an upstream IdP a user came from (e.g. firebase)."""
    __tablename__ = "legacy_auth_links"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.users.id", ondelete="CASCADE"), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)        # e.g. "firebase"
    provider_uid: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
