"""ALAFIA Blockchain Ledger — Persistence & High-Level Operations.

This is the application-level service that sits on top of
BlockchainEngine.  It handles:

  • Persisting blocks to PostgreSQL
  • Lazy chain initialization (auto-creates genesis on first write)
  • Batch recording with Merkle roots
  • Full-chain and range verification
  • Entity-specific audit trail queries
  • Convenience helpers for every chain domain

All public methods accept an AsyncSession so they participate in the
caller's transaction.  The ledger NEVER commits — it flushes and lets
the surrounding endpoint/service commit.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, asc, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:  # hints only — these are quoted, so nothing evaluates them at
    # runtime, but without the import no type checker or IDE can resolve
    # `-> "BlockRecord"`, and a future `response_model=` on one of these would
    # fail at import time instead of in review.
    from app.models.blockchain import BlockRecord, ChainMeta

from app.services.blockchain_engine import (
    Block,
    BlockchainEngine,
    ChainType,
    EventAction,
)

logger = logging.getLogger(__name__)


class BlockchainLedger:
    """High-level ledger that persists blocks and provides query/verify APIs.

    Usage
    ─────
        ledger = BlockchainLedger(db)

        # Record a single event
        block = await ledger.record_event(
            chain_type=ChainType.prescription,
            action=EventAction.prescription_created,
            data={"medication": "Metformin", "dosage": "500mg"},
            actor_id=current_user.id,
            entity_type="medication",
            entity_id=42,
        )

        # Verify chain integrity
        valid, error = await ledger.verify_chain(ChainType.prescription)

        # Query audit trail
        trail = await ledger.get_entity_trail("medication", 42)
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.engine = BlockchainEngine()

    # ══════════════════════════════════════════════════════════════
    # CORE OPERATIONS
    # ══════════════════════════════════════════════════════════════

    async def record_event(
        self,
        chain_type: str | ChainType,
        action: str | EventAction,
        data: Dict[str, Any],
        actor_id: Optional[int] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "BlockRecord":
        """Record a single event on the appropriate chain.

        Automatically creates the genesis block if the chain does not exist.
        """

        chain_str = chain_type.value if isinstance(chain_type, ChainType) else chain_type
        action_str = action.value if isinstance(action, EventAction) else action

        # Get or create chain metadata
        chain_meta = await self._get_or_create_chain(chain_str)

        # Get previous block
        prev_block = await self._get_latest_block(chain_str)
        if prev_block is None:
            # Should not happen after _get_or_create_chain, but safety
            genesis = self.engine.create_genesis_block(chain_str)
            prev_record = await self._persist_block(genesis)
            prev_hash = genesis.hash
            next_index = 1
        else:
            prev_hash = prev_block.hash
            next_index = prev_block.index + 1

        # Create the block
        block = self.engine.create_block(
            chain_type=chain_str,
            index=next_index,
            previous_hash=prev_hash,
            action=action_str,
            data=data,
            actor_id=actor_id,
            entity_type=entity_type,
            entity_id=entity_id,
            metadata=metadata,
        )

        # Persist
        record = await self._persist_block(block)

        # Update chain metadata
        chain_meta.block_count = next_index + 1
        chain_meta.latest_hash = block.hash
        chain_meta.latest_index = next_index
        chain_meta.updated_at = datetime.now(timezone.utc)

        await self.db.flush()
        return record

    async def record_batch(
        self,
        chain_type: str | ChainType,
        events: List[Dict[str, Any]],
        actor_id: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List["BlockRecord"]:
        """Record multiple events atomically with a shared Merkle root.

        Each event dict should have: action, data, entity_type?, entity_id?

        All blocks in the batch share the same merkle_root computed
        over the entire batch.
        """

        if not events:
            return []

        chain_str = chain_type.value if isinstance(chain_type, ChainType) else chain_type
        chain_meta = await self._get_or_create_chain(chain_str)

        prev_block = await self._get_latest_block(chain_str)
        if prev_block is None:
            genesis = self.engine.create_genesis_block(chain_str)
            await self._persist_block(genesis)
            prev_hash = genesis.hash
            next_index = 1
        else:
            prev_hash = prev_block.hash
            next_index = prev_block.index + 1

        # Create all blocks
        blocks: List[Block] = []
        for evt in events:
            action_raw = evt.get("action", "record_created")
            action_str = action_raw.value if isinstance(action_raw, EventAction) else str(action_raw)

            block = self.engine.create_block(
                chain_type=chain_str,
                index=next_index,
                previous_hash=prev_hash,
                action=action_str,
                data=evt.get("data", {}),
                actor_id=actor_id,
                entity_type=evt.get("entity_type"),
                entity_id=evt.get("entity_id"),
                metadata=metadata,
            )
            blocks.append(block)
            prev_hash = block.hash
            next_index += 1

        # Build Merkle tree over the batch
        tree = self.engine.build_merkle_tree(blocks)
        for b in blocks:
            b.merkle_root = tree.root

        # Persist all
        records = []
        for b in blocks:
            record = await self._persist_block(b)
            records.append(record)

        # Update chain
        chain_meta.block_count = next_index
        chain_meta.latest_hash = blocks[-1].hash
        chain_meta.latest_index = blocks[-1].index
        chain_meta.merkle_root = tree.root
        chain_meta.updated_at = datetime.now(timezone.utc)

        await self.db.flush()
        return records

    # ══════════════════════════════════════════════════════════════
    # VERIFICATION
    # ══════════════════════════════════════════════════════════════

    async def verify_chain(
        self,
        chain_type: str | ChainType,
        start_index: int = 0,
        end_index: Optional[int] = None,
    ) -> Tuple[bool, Optional[str], Dict[str, Any]]:
        """Verify the integrity of a chain or a range of blocks.

        Returns (is_valid, error_message, stats).
        """
        from app.models.blockchain import BlockRecord

        chain_str = chain_type.value if isinstance(chain_type, ChainType) else chain_type

        stmt = (
            select(BlockRecord)
            .where(BlockRecord.chain_type == chain_str)
            .order_by(asc(BlockRecord.index))
        )
        if end_index is not None:
            stmt = stmt.where(
                and_(BlockRecord.index >= start_index, BlockRecord.index <= end_index)
            )
        else:
            stmt = stmt.where(BlockRecord.index >= start_index)

        result = await self.db.execute(stmt)
        records = result.scalars().all()

        if not records:
            return True, None, {"blocks_checked": 0}

        # Reconstruct Block objects
        blocks = [self._record_to_block(r) for r in records]

        # Verify
        if start_index == 0:
            is_valid, error = self.engine.verify_chain(blocks)
        else:
            # Range verification — check internal links + hashes
            is_valid = True
            error = None
            for i, block in enumerate(blocks):
                if not self.engine.verify_block_hash(block):
                    is_valid = False
                    error = f"Block hash mismatch at index {block.index}"
                    break
                if i > 0 and not self.engine.verify_chain_link(blocks[i - 1], block):
                    is_valid = False
                    error = f"Chain link broken between index {blocks[i-1].index} and {block.index}"
                    break

        stats = {
            "chain_type": chain_str,
            "blocks_checked": len(blocks),
            "start_index": blocks[0].index,
            "end_index": blocks[-1].index,
            "verified_at": datetime.now(timezone.utc).isoformat(),
        }

        return is_valid, error, stats

    async def verify_block_by_uid(self, block_uid: str) -> Tuple[bool, Optional[str]]:
        """Verify a single block's hash and signature by its UID."""
        from app.models.blockchain import BlockRecord

        stmt = select(BlockRecord).where(BlockRecord.block_uid == block_uid)
        result = await self.db.execute(stmt)
        record = result.scalar_one_or_none()
        if not record:
            return False, f"Block {block_uid} not found"

        block = self._record_to_block(record)

        if not self.engine.verify_block_hash(block):
            return False, "Hash mismatch — block may have been tampered with"

        if block.signature and not block.verify_signature():
            return False, "Signature verification failed"

        return True, None

    # ══════════════════════════════════════════════════════════════
    # QUERY METHODS
    # ══════════════════════════════════════════════════════════════

    async def get_entity_trail(
        self,
        entity_type: str,
        entity_id: int,
        chain_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get the full audit trail for a specific entity (e.g. medication #42)."""
        from app.models.blockchain import BlockRecord

        stmt = (
            select(BlockRecord)
            .where(
                and_(
                    BlockRecord.entity_type == entity_type,
                    BlockRecord.entity_id == entity_id,
                )
            )
            .order_by(asc(BlockRecord.index))
        )
        if chain_type:
            stmt = stmt.where(BlockRecord.chain_type == chain_type)

        result = await self.db.execute(stmt)
        records = result.scalars().all()
        return [self._record_to_dict(r) for r in records]

    async def get_user_trail(
        self,
        user_id: int,
        chain_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Get all blocks created by or affecting a user."""
        from app.models.blockchain import BlockRecord

        stmt = (
            select(BlockRecord)
            .where(BlockRecord.actor_id == user_id)
            .order_by(desc(BlockRecord.created_at))
            .limit(limit)
        )
        if chain_type:
            stmt = stmt.where(BlockRecord.chain_type == chain_type)

        result = await self.db.execute(stmt)
        records = result.scalars().all()
        return [self._record_to_dict(r) for r in records]

    async def get_chain_info(self, chain_type: str | ChainType) -> Optional[Dict[str, Any]]:
        """Get metadata about a specific chain."""
        from app.models.blockchain import ChainMeta

        chain_str = chain_type.value if isinstance(chain_type, ChainType) else chain_type
        stmt = select(ChainMeta).where(ChainMeta.chain_type == chain_str)
        result = await self.db.execute(stmt)
        meta = result.scalar_one_or_none()
        if not meta:
            return None

        return {
            "chain_type": meta.chain_type,
            "block_count": meta.block_count,
            "latest_index": meta.latest_index,
            "latest_hash": meta.latest_hash,
            "merkle_root": meta.merkle_root,
            "genesis_hash": meta.genesis_hash,
            "created_at": meta.created_at.isoformat() if meta.created_at else None,
            "updated_at": meta.updated_at.isoformat() if meta.updated_at else None,
        }

    async def get_all_chains_info(self) -> List[Dict[str, Any]]:
        """Get metadata for all existing chains."""
        from app.models.blockchain import ChainMeta

        stmt = select(ChainMeta).order_by(asc(ChainMeta.chain_type))
        result = await self.db.execute(stmt)
        metas = result.scalars().all()

        return [
            {
                "chain_type": m.chain_type,
                "block_count": m.block_count,
                "latest_index": m.latest_index,
                "latest_hash": m.latest_hash,
                "merkle_root": m.merkle_root,
                "created_at": m.created_at.isoformat() if m.created_at else None,
                "updated_at": m.updated_at.isoformat() if m.updated_at else None,
            }
            for m in metas
        ]

    async def get_recent_blocks(
        self,
        chain_type: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Get the most recent blocks across all chains or a specific chain."""
        from app.models.blockchain import BlockRecord

        stmt = (
            select(BlockRecord)
            .order_by(desc(BlockRecord.created_at))
            .limit(limit)
        )
        if chain_type:
            stmt = stmt.where(BlockRecord.chain_type == chain_type)

        result = await self.db.execute(stmt)
        records = result.scalars().all()
        return [self._record_to_dict(r) for r in records]

    # ══════════════════════════════════════════════════════════════
    # DOMAIN-SPECIFIC CONVENIENCE METHODS
    # ══════════════════════════════════════════════════════════════

    async def record_health_event(
        self,
        action: str | EventAction,
        data: Dict[str, Any],
        actor_id: int,
        entity_type: str,
        entity_id: int,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "BlockRecord":
        """Record a health record event (vitals, labs, conditions, etc.)."""
        return await self.record_event(
            chain_type=ChainType.health_record,
            action=action,
            data=data,
            actor_id=actor_id,
            entity_type=entity_type,
            entity_id=entity_id,
            metadata=metadata,
        )

    async def record_prescription_event(
        self,
        action: str | EventAction,
        data: Dict[str, Any],
        actor_id: int,
        entity_id: int,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "BlockRecord":
        """Record a prescription / medication event."""
        return await self.record_event(
            chain_type=ChainType.prescription,
            action=action,
            data=data,
            actor_id=actor_id,
            entity_type="medication",
            entity_id=entity_id,
            metadata=metadata,
        )

    async def record_therapy_event(
        self,
        action: str | EventAction,
        data: Dict[str, Any],
        actor_id: int,
        entity_id: int,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "BlockRecord":
        """Record a therapy session event."""
        return await self.record_event(
            chain_type=ChainType.therapy,
            action=action,
            data=data,
            actor_id=actor_id,
            entity_type="therapy_session",
            entity_id=entity_id,
            metadata=metadata,
        )

    async def record_message_event(
        self,
        action: str | EventAction,
        data: Dict[str, Any],
        actor_id: int,
        entity_id: int,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "BlockRecord":
        """Record a messaging event."""
        return await self.record_event(
            chain_type=ChainType.messaging,
            action=action,
            data=data,
            actor_id=actor_id,
            entity_type="message",
            entity_id=entity_id,
            metadata=metadata,
        )

    async def record_session_event(
        self,
        action: str | EventAction,
        data: Dict[str, Any],
        actor_id: int,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "BlockRecord":
        """Record a session audit event (login, logout, access)."""
        return await self.record_event(
            chain_type=ChainType.session_audit,
            action=action,
            data=data,
            actor_id=actor_id,
            entity_type="session",
            entity_id=None,
            metadata=metadata,
        )

    async def record_provenance_event(
        self,
        action: str | EventAction,
        data: Dict[str, Any],
        actor_id: int,
        entity_type: str,
        entity_id: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "BlockRecord":
        """Record a data provenance event (import, export, share, transform)."""
        # Include a data hash for provenance tracking
        if "data_hash" not in data and "payload" in data:
            data["data_hash"] = BlockchainEngine.compute_data_hash(data["payload"])

        return await self.record_event(
            chain_type=ChainType.data_provenance,
            action=action,
            data=data,
            actor_id=actor_id,
            entity_type=entity_type,
            entity_id=entity_id,
            metadata=metadata,
        )

    async def record_payment_event(
        self,
        action: str | EventAction,
        data: Dict[str, Any],
        actor_id: int,
        entity_id: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "BlockRecord":
        """Record a payment transaction event (future)."""
        return await self.record_event(
            chain_type=ChainType.payment,
            action=action,
            data=data,
            actor_id=actor_id,
            entity_type="payment",
            entity_id=entity_id,
            metadata=metadata,
        )

    # ══════════════════════════════════════════════════════════════
    # INTERNAL HELPERS
    # ══════════════════════════════════════════════════════════════

    async def _get_or_create_chain(self, chain_type: str) -> "ChainMeta":
        """Get existing chain metadata or create it with a genesis block."""
        from app.models.blockchain import ChainMeta

        stmt = select(ChainMeta).where(ChainMeta.chain_type == chain_type)
        result = await self.db.execute(stmt)
        meta = result.scalar_one_or_none()

        if meta is not None:
            return meta

        # Create genesis block
        genesis = self.engine.create_genesis_block(chain_type)
        genesis_record = await self._persist_block(genesis)

        # Create chain metadata
        meta = ChainMeta(
            chain_type=chain_type,
            genesis_hash=genesis.hash,
            latest_hash=genesis.hash,
            latest_index=0,
            block_count=1,
        )
        self.db.add(meta)
        await self.db.flush()
        return meta

    async def _get_latest_block(self, chain_type: str) -> Optional["BlockRecord"]:
        """Get the most recent block in a chain."""
        from app.models.blockchain import BlockRecord

        stmt = (
            select(BlockRecord)
            .where(BlockRecord.chain_type == chain_type)
            .order_by(desc(BlockRecord.index))
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _persist_block(self, block: Block) -> "BlockRecord":
        """Write a Block to the database and fire on-chain anchoring."""
        from app.models.blockchain import BlockRecord

        record = BlockRecord(
            block_uid=block.block_uid,
            index=block.index,
            timestamp=block.timestamp,
            chain_type=block.chain_type,
            action=block.action,
            data=block.data,
            previous_hash=block.previous_hash,
            hash=block.hash,
            nonce=block.nonce,
            actor_id=block.actor_id,
            entity_type=block.entity_type,
            entity_id=block.entity_id,
            merkle_root=block.merkle_root,
            signature=block.signature,
            metadata_json=block.metadata,
        )
        self.db.add(record)
        await self.db.flush()

        # Best-effort on-chain anchoring (non-blocking). Only the id and hash
        # cross into the task: the ORM instance belongs to a session that is
        # closed by the time the anchor returns.
        asyncio.ensure_future(
            self._anchor_on_chain(record.id, record.hash, record.block_uid))

        return record

    @staticmethod
    async def _anchor_on_chain(record_id: int, block_hash: str, block_uid: str) -> None:
        """Anchor a block hash on the private chain and PERSIST the receipt.

        This used to take the ORM instance and assign `record.blockchain_tx_hash`
        on it. The assignment happened after the request's session had closed, so
        nothing ever wrote it: the transaction was mined — anvil's block height
        rose — and the tx hash was discarded. `verify_on_chain_anchor` then had no
        hash to check, which made every anchored block look unanchored.

        Same rule as the nutrition background worker (canon §3c): a task that
        outlives the request gets its OWN session, and never raises into the
        caller.
        """
        try:
            from app.services.chain_anchor import anchor_block_on_chain
            tx_hash, block_num = await anchor_block_on_chain(block_hash)
            if not tx_hash:
                return
            from app.core.database import async_session
            from app.models.blockchain import BlockRecord

            async with async_session() as db:
                row = await db.get(BlockRecord, record_id)
                if row is not None:
                    row.blockchain_tx_hash = tx_hash
                    row.blockchain_block_num = block_num
                    await db.commit()
        except Exception as exc:
            logger.debug("On-chain anchor skipped for block %s: %s", block_uid, exc)

    @staticmethod
    def _record_to_block(record: "BlockRecord") -> Block:
        """Convert a DB record back to an in-memory Block."""
        return Block(
            index=record.index,
            timestamp=record.timestamp,
            chain_type=record.chain_type,
            action=record.action,
            data=record.data or {},
            previous_hash=record.previous_hash,
            hash=record.hash,
            nonce=record.nonce or "",
            actor_id=record.actor_id,
            entity_type=record.entity_type,
            entity_id=record.entity_id,
            merkle_root=record.merkle_root,
            signature=record.signature,
            block_uid=record.block_uid,
            metadata=record.metadata_json,
        )

    @staticmethod
    def _record_to_dict(record: "BlockRecord") -> Dict[str, Any]:
        """Convert a DB record to a JSON-friendly dict."""
        return {
            "id": record.id,
            "block_uid": record.block_uid,
            "index": record.index,
            "timestamp": record.timestamp,
            "chain_type": record.chain_type,
            "action": record.action,
            "data": record.data,
            "previous_hash": record.previous_hash,
            "hash": record.hash,
            "nonce": record.nonce,
            "actor_id": record.actor_id,
            "entity_type": record.entity_type,
            "entity_id": record.entity_id,
            "merkle_root": record.merkle_root,
            "signature": record.signature,
            "metadata": record.metadata_json,
            "blockchain_tx_hash": record.blockchain_tx_hash,
            "blockchain_block_num": record.blockchain_block_num,
            "created_at": record.created_at.isoformat() if record.created_at else None,
        }
