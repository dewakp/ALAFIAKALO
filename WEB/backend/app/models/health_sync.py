"""Health data sync models – tracks external health platform integrations and
prevents duplicate records from being ingested."""

from datetime import datetime, timezone

from sqlalchemy import (
    String, Integer, DateTime, ForeignKey, Text, Boolean, UniqueConstraint, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class HealthSyncConnection(Base):
    """Represents a user's connection to an external health platform
    (Apple HealthKit, Android Health Connect, etc.)."""

    __tablename__ = "health_sync_connections"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    platform: Mapped[str] = mapped_column(String(50), nullable=False)  # healthkit | health_connect
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    enabled_data_types: Mapped[str | None] = mapped_column(Text)  # JSON list of enabled data types
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_sync_status: Mapped[str | None] = mapped_column(String(20))  # success | partial | failed
    last_sync_records: Mapped[int | None] = mapped_column(Integer)   # count of records synced
    last_sync_duplicates: Mapped[int | None] = mapped_column(Integer)  # count of duplicates skipped
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    user = relationship("User", back_populates="health_sync_connections")

    __table_args__ = (
        UniqueConstraint("user_id", "platform", name="uq_user_platform"),
    )


class SyncedRecord(Base):
    """Deduplication ledger – stores a fingerprint for every record already
    ingested so we can reject duplicates at the database level."""

    __tablename__ = "synced_records"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    platform: Mapped[str] = mapped_column(String(50), nullable=False)  # healthkit | health_connect
    data_type: Mapped[str] = mapped_column(String(50), nullable=False)  # steps, heart_rate, workout, sleep, etc.
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)  # UUID from the source platform
    target_table: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g. fitness_logs
    target_record_id: Mapped[int | None] = mapped_column(Integer)  # FK to the created record
    source_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        UniqueConstraint("user_id", "platform", "data_type", "external_id",
                         name="uq_synced_record"),
        Index("ix_synced_lookup", "user_id", "platform", "data_type"),
    )
