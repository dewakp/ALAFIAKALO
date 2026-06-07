"""Blockchain / Immutable Ledger database models.

Two tables:
  • block_records  — individual blocks in the hash chains
  • chain_meta     — per-chain metadata (latest hash, block count, etc.)
"""

from datetime import datetime, timezone

from sqlalchemy import (
    String,
    DateTime,
    Integer,
    Float,
    Text,
    ForeignKey,
    Index,
    JSON,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class BlockRecord(Base):
    """A single immutable block persisted in the database."""

    __tablename__ = "block_records"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # ── identity ──────────────────────────────────────────────────
    block_uid: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    index: Mapped[int] = mapped_column(Integer, nullable=False)
    chain_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # ── content ───────────────────────────────────────────────────
    timestamp: Mapped[str] = mapped_column(String(50), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    data: Mapped[dict | None] = mapped_column(JSON)

    # ── hash chain ────────────────────────────────────────────────
    previous_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    nonce: Mapped[str | None] = mapped_column(String(32))

    # ── provenance ────────────────────────────────────────────────
    actor_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), index=True
    )
    entity_type: Mapped[str | None] = mapped_column(String(100), index=True)
    entity_id: Mapped[int | None] = mapped_column(Integer, index=True)

    # ── merkle / signature ────────────────────────────────────────
    merkle_root: Mapped[str | None] = mapped_column(String(128))
    signature: Mapped[str | None] = mapped_column(String(128))

    # ── extra ─────────────────────────────────────────────────────
    metadata_json: Mapped[dict | None] = mapped_column(JSON)

    # ── on-chain anchoring (Anvil / private Ethereum) ─────────────
    blockchain_tx_hash: Mapped[str | None] = mapped_column(String(66), nullable=True)
    blockchain_block_num: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ── timestamps ────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    # ── composite indexes for common query patterns ───────────────
    __table_args__ = (
        Index("ix_block_chain_index", "chain_type", "index"),
        Index("ix_block_entity", "entity_type", "entity_id"),
        Index("ix_block_actor_chain", "actor_id", "chain_type"),
    )


class ChainMeta(Base):
    """Metadata for each chain type — one row per chain."""

    __tablename__ = "chain_meta"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    chain_type: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True
    )

    genesis_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    latest_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    latest_index: Mapped[int] = mapped_column(Integer, default=0)
    block_count: Mapped[int] = mapped_column(Integer, default=1)
    merkle_root: Mapped[str | None] = mapped_column(String(128))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
