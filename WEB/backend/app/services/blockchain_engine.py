"""ALAFIA Blockchain Engine — Core Cryptographic Primitives.

A private, permissioned hash-chain ledger designed for healthcare data
integrity.  NOT a distributed public blockchain — it is a server-side
immutable audit ledger with:

  • SHA-512 hash chaining (each block references the previous hash)
  • Merkle trees for efficient batch verification
  • HMAC signatures for non-repudiation
  • Per-domain chains (health_record, prescription, therapy, messaging,
    session_audit, data_provenance, payment)
  • Tamper detection via full-chain and range verification

Architecture
────────────
  Block ← smallest unit.  Holds one event/action.
  Chain ← ordered sequence of blocks sharing the same chain_type.
  MerkleTree ← built over a batch of blocks for efficient root-hash proofs.
  BlockchainEngine ← stateless utility class that creates blocks, builds
       trees, and verifies integrity.  It does NOT touch the database —
       that is the job of BlockchainLedger (see blockchain_ledger.py).

Supported Chain Types
─────────────────────
  health_record     — vitals, labs, conditions, diagnoses
  prescription      — medication create / update / dispense / discontinue
  therapy           — therapy sessions immutability
  messaging         — message hash chaining & integrity
  session_audit     — login, logout, access events
  data_provenance   — data origin, import, export, transformation
  payment           — (future) payment transaction transparency

Usage
─────
    engine = BlockchainEngine()
    genesis = engine.create_genesis_block("health_record")
    block   = engine.create_block(
        chain_type="health_record",
        index=1,
        previous_hash=genesis.hash,
        data={"event": "vitals_recorded", "user_id": 1, ...},
        actor_id=1,
    )
    valid = engine.verify_chain([genesis, block])
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import alafia_crypto as _rc  # Rust crypto backend


# ══════════════════════════════════════════════════════════════════════
# CONSTANTS
# ══════════════════════════════════════════════════════════════════════

HASH_ALGORITHM = "sha512"
GENESIS_PREVIOUS_HASH = "0" * 128  # 128-char hex zero string
HMAC_SECRET = os.getenv("BLOCKCHAIN_HMAC_SECRET", "alafia-chain-secret-change-in-prod")


class ChainType(str, Enum):
    """Supported ledger domains."""
    health_record = "health_record"
    prescription = "prescription"
    therapy = "therapy"
    messaging = "messaging"
    session_audit = "session_audit"
    data_provenance = "data_provenance"
    payment = "payment"


class EventAction(str, Enum):
    """Common event actions recorded on-chain."""
    # Health records
    record_created = "record_created"
    record_updated = "record_updated"
    record_deleted = "record_deleted"
    record_viewed = "record_viewed"

    # Prescriptions / Medications
    prescription_created = "prescription_created"
    prescription_updated = "prescription_updated"
    prescription_dispensed = "prescription_dispensed"
    prescription_discontinued = "prescription_discontinued"
    medication_started = "medication_started"
    medication_stopped = "medication_stopped"
    medication_refilled = "medication_refilled"

    # Therapy
    therapy_session_created = "therapy_session_created"
    therapy_session_completed = "therapy_session_completed"
    therapy_session_cancelled = "therapy_session_cancelled"
    therapy_notes_added = "therapy_notes_added"
    therapy_metrics_recorded = "therapy_metrics_recorded"

    # Messaging
    message_sent = "message_sent"
    message_delivered = "message_delivered"
    message_read = "message_read"
    message_edited = "message_edited"

    # Session audit
    user_login = "user_login"
    user_logout = "user_logout"
    session_started = "session_started"
    session_expired = "session_expired"
    access_granted = "access_granted"
    access_denied = "access_denied"
    permission_changed = "permission_changed"

    # Data provenance
    data_imported = "data_imported"
    data_exported = "data_exported"
    data_transformed = "data_transformed"
    data_shared = "data_shared"
    consent_granted = "consent_granted"
    consent_revoked = "consent_revoked"
    data_deleted = "data_deleted"

    # Payment (future)
    payment_initiated = "payment_initiated"
    payment_completed = "payment_completed"
    payment_failed = "payment_failed"
    payment_refunded = "payment_refunded"
    insurance_claim_submitted = "insurance_claim_submitted"
    insurance_claim_processed = "insurance_claim_processed"


# ══════════════════════════════════════════════════════════════════════
# BLOCK
# ══════════════════════════════════════════════════════════════════════

@dataclass
class Block:
    """A single immutable block in the chain.

    Fields
    ------
    index         : sequential position in this chain (0 = genesis)
    timestamp     : ISO-8601 UTC when the block was created
    chain_type    : which domain chain this belongs to
    action        : EventAction or free-form string describing what happened
    data          : arbitrary JSON-serialisable payload
    previous_hash : SHA-512 hash of the preceding block
    hash          : SHA-512 hash of this block's contents
    nonce         : random 8-byte hex for uniqueness
    actor_id      : user or system ID that triggered the event
    entity_type   : the model/table affected (e.g. "vitals_log", "medication")
    entity_id     : primary key of the affected record
    merkle_root   : root hash when this block is part of a batch
    signature     : HMAC-SHA512 signature for non-repudiation
    block_uid     : globally unique block identifier (UUID4)
    metadata      : optional extra context (IP, user-agent, etc.)
    """
    index: int
    timestamp: str
    chain_type: str
    action: str
    data: Dict[str, Any]
    previous_hash: str
    hash: str = ""
    nonce: str = field(default_factory=lambda: os.urandom(8).hex())
    actor_id: Optional[int] = None
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None
    merkle_root: Optional[str] = None
    signature: Optional[str] = None
    block_uid: str = field(default_factory=lambda: str(uuid.uuid4()))
    metadata: Optional[Dict[str, Any]] = None

    # ── hashing ───────────────────────────────────────────────────

    def compute_hash(self) -> str:
        """Compute the SHA-512 hash of this block's contents (via Rust).

        The hash covers: index, timestamp, chain_type, action, data,
        previous_hash, nonce, actor_id, entity_type, entity_id, block_uid.
        """
        payload = json.dumps(
            {
                "index": self.index,
                "timestamp": self.timestamp,
                "chain_type": self.chain_type,
                "action": self.action,
                "data": self.data,
                "previous_hash": self.previous_hash,
                "nonce": self.nonce,
                "actor_id": self.actor_id,
                "entity_type": self.entity_type,
                "entity_id": self.entity_id,
                "block_uid": self.block_uid,
            },
            sort_keys=True,
            default=str,
        )
        return _rc.compute_block_hash(payload)

    def sign(self, secret: str = HMAC_SECRET) -> str:
        """Produce an HMAC-SHA512 signature over the block hash (via Rust)."""
        sig = _rc.sign_block(self.hash, secret)
        self.signature = sig
        return sig

    def verify_signature(self, secret: str = HMAC_SECRET) -> bool:
        """Verify the HMAC signature (constant-time, via Rust)."""
        if not self.signature:
            return False
        return _rc.verify_block_signature(self.hash, self.signature, secret)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ══════════════════════════════════════════════════════════════════════
# MERKLE TREE
# ══════════════════════════════════════════════════════════════════════

class MerkleTree:
    """Merkle tree backed by Rust crypto for batch block verification.

    Given a list of block hashes, builds a binary hash tree and
    exposes the `root` hash.  Supports inclusion proofs.
    """

    def __init__(self, hashes: List[str]):
        if not hashes:
            raise ValueError("Cannot build Merkle tree from empty list")
        self.leaves = hashes[:]
        self.root, self.tree = _rc.merkle_build(hashes)

    # ── proofs ────────────────────────────────────────────────────

    def get_proof(self, index: int) -> List[Tuple[str, str]]:
        """Return the Merkle proof for the leaf at `index`.

        Each element is (sibling_hash, side) where side is 'L' or 'R'.
        """
        return _rc.merkle_proof(self.tree, index)

    @staticmethod
    def verify_proof(leaf_hash: str, proof: List[Tuple[str, str]], root: str) -> bool:
        """Verify a Merkle inclusion proof."""
        return _rc.merkle_verify_proof(leaf_hash, proof, root)


# ══════════════════════════════════════════════════════════════════════
# BLOCKCHAIN ENGINE (stateless utility)
# ══════════════════════════════════════════════════════════════════════

class BlockchainEngine:
    """Stateless utility for creating, hashing, signing, and verifying blocks.

    This class does NOT interact with the database.  It provides pure
    cryptographic operations.  Persistence is handled by BlockchainLedger.
    """

    # ── block creation ────────────────────────────────────────────

    @staticmethod
    def create_genesis_block(chain_type: str) -> Block:
        """Create the genesis (index-0) block for a chain."""
        block = Block(
            index=0,
            timestamp=datetime.now(timezone.utc).isoformat(),
            chain_type=chain_type,
            action="genesis",
            data={"event": "chain_initialized", "chain_type": chain_type},
            previous_hash=GENESIS_PREVIOUS_HASH,
            actor_id=None,
            entity_type=None,
            entity_id=None,
        )
        block.hash = block.compute_hash()
        block.sign()
        return block

    @staticmethod
    def create_block(
        chain_type: str,
        index: int,
        previous_hash: str,
        action: str,
        data: Dict[str, Any],
        actor_id: Optional[int] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Block:
        """Create a new block linked to the previous hash."""
        block = Block(
            index=index,
            timestamp=datetime.now(timezone.utc).isoformat(),
            chain_type=chain_type,
            action=action,
            data=data,
            previous_hash=previous_hash,
            actor_id=actor_id,
            entity_type=entity_type,
            entity_id=entity_id,
            metadata=metadata,
        )
        block.hash = block.compute_hash()
        block.sign()
        return block

    # ── verification ──────────────────────────────────────────────

    @staticmethod
    def verify_block_hash(block: Block) -> bool:
        """Verify that a block's stored hash matches its computed hash."""
        return block.hash == block.compute_hash()

    @staticmethod
    def verify_chain_link(previous_block: Block, current_block: Block) -> bool:
        """Verify the hash link between two consecutive blocks."""
        if current_block.previous_hash != previous_block.hash:
            return False
        if current_block.index != previous_block.index + 1:
            return False
        return True

    @classmethod
    def verify_chain(cls, blocks: List[Block]) -> Tuple[bool, Optional[str]]:
        """Verify an entire ordered list of blocks.

        Returns (is_valid, error_message).
        """
        if not blocks:
            return True, None

        # Genesis check
        genesis = blocks[0]
        if genesis.index != 0:
            return False, "Chain does not start with genesis block (index 0)"
        if genesis.previous_hash != GENESIS_PREVIOUS_HASH:
            return False, "Genesis block has invalid previous_hash"
        if not cls.verify_block_hash(genesis):
            return False, "Genesis block hash mismatch at index 0"

        # Walk the chain
        for i in range(1, len(blocks)):
            current = blocks[i]
            previous = blocks[i - 1]

            if not cls.verify_block_hash(current):
                return False, f"Block hash mismatch at index {current.index}"

            if not cls.verify_chain_link(previous, current):
                return False, (
                    f"Chain link broken between index {previous.index} "
                    f"and {current.index}"
                )

            if current.signature and not current.verify_signature():
                return False, f"Signature verification failed at index {current.index}"

        return True, None

    # ── merkle operations ─────────────────────────────────────────

    @staticmethod
    def build_merkle_tree(blocks: List[Block]) -> MerkleTree:
        """Build a Merkle tree over a list of blocks."""
        hashes = [b.hash for b in blocks]
        return MerkleTree(hashes)

    @staticmethod
    def compute_data_hash(data: Any) -> str:
        """Compute a SHA-512 hash of arbitrary data (via Rust)."""
        payload = json.dumps(data, sort_keys=True, default=str)
        return _rc.compute_data_hash(payload)

    # ── helpers ───────────────────────────────────────────────────

    @staticmethod
    def block_from_dict(d: Dict[str, Any]) -> Block:
        """Reconstruct a Block from a dictionary (e.g. from DB)."""
        return Block(
            index=d["index"],
            timestamp=d["timestamp"],
            chain_type=d["chain_type"],
            action=d["action"],
            data=d.get("data", {}),
            previous_hash=d["previous_hash"],
            hash=d.get("hash", ""),
            nonce=d.get("nonce", ""),
            actor_id=d.get("actor_id"),
            entity_type=d.get("entity_type"),
            entity_id=d.get("entity_id"),
            merkle_root=d.get("merkle_root"),
            signature=d.get("signature"),
            block_uid=d.get("block_uid", str(uuid.uuid4())),
            metadata=d.get("metadata"),
        )
