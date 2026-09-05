"""Blockchain / Immutable Ledger API endpoints.

Provides:
 - POST /blockchain/record                           — Record event on chain
 - POST /blockchain/batch                             — Record batch events atomically
 - POST /blockchain/verify                            — Verify chain integrity
 - GET  /blockchain/verify/block/{block_uid}          — Verify single block
 - GET  /blockchain/chains                            — All chains overview
 - GET  /blockchain/chains/{chain_type}               — Single chain info
 - GET  /blockchain/trail/entity/{entity_type}/{eid}  — Entity audit trail
 - GET  /blockchain/trail/user/{user_id}              — User audit trail
 - GET  /blockchain/blocks/recent                     — Recent blocks
 - GET  /blockchain/chain-types                       — List chain types
 - GET  /blockchain/actions                           — List event actions
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.blockchain import (
    RecordEventRequest,
    RecordBatchRequest,
    VerifyChainRequest,
    BlockOut,
    ChainInfoOut,
    VerifyResultOut,
    EntityTrailOut,
    ChainsOverviewOut,
    ChainTypesOut,
    EventActionsOut,
)
from app.services.blockchain_engine import ChainType, EventAction
from app.services.blockchain_ledger import BlockchainLedger

router = APIRouter()


# ── helpers ──────────────────────────────────────────────────────────

def _block_record_to_out(rec) -> BlockOut:
    """Convert a BlockRecord ORM object to BlockOut schema."""
    return BlockOut(
        id=rec.id,
        block_uid=rec.block_uid,
        index=rec.index,
        timestamp=rec.timestamp.isoformat() if rec.timestamp else "",
        chain_type=rec.chain_type,
        action=rec.action,
        data=rec.data,
        previous_hash=rec.previous_hash,
        hash=rec.hash,
        nonce=rec.nonce,
        actor_id=rec.actor_id,
        entity_type=rec.entity_type,
        entity_id=rec.entity_id,
        merkle_root=rec.merkle_root,
        signature=rec.signature,
        metadata=rec.metadata_json,
        blockchain_tx_hash=rec.blockchain_tx_hash,
        blockchain_block_num=rec.blockchain_block_num,
        created_at=rec.created_at.isoformat() if rec.created_at else None,
    )


# ══════════════════════════════════════════════════════════════════════
# WRITE ENDPOINTS
# ══════════════════════════════════════════════════════════════════════

@router.post("/record", response_model=BlockOut)
async def record_event(
    body: RecordEventRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Record a single event on a blockchain chain.

    Creates a new block with hash chaining & optional HMAC signature.
    Genesis block is auto-created for new chains.
    """
    # validate chain_type
    try:
        chain = ChainType(body.chain_type)
    except ValueError:
        valid = [ct.value for ct in ChainType]
        raise HTTPException(400, f"Invalid chain_type. Must be one of: {valid}")

    # validate action
    try:
        action = EventAction(body.action)
    except ValueError:
        valid = [ea.value for ea in EventAction]
        raise HTTPException(400, f"Invalid action. Must be one of: {valid}")

    ledger = BlockchainLedger(db)
    rec = await ledger.record_event(
        chain_type=chain,
        action=action,
        actor_id=current_user.id,
        data=body.data,
        entity_type=body.entity_type,
        entity_id=body.entity_id,
        metadata=body.metadata,
    )
    return _block_record_to_out(rec)


@router.post("/batch", response_model=list[BlockOut])
async def record_batch(
    body: RecordBatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Record multiple events atomically on a single chain.

    All blocks share a Merkle root computed from the batch payloads.
    """
    try:
        chain = ChainType(body.chain_type)
    except ValueError:
        valid = [ct.value for ct in ChainType]
        raise HTTPException(400, f"Invalid chain_type. Must be one of: {valid}")

    ledger = BlockchainLedger(db)
    records = await ledger.record_batch(
        chain_type=chain,
        actor_id=current_user.id,
        events=body.events,
        metadata=body.metadata,
    )
    return [_block_record_to_out(r) for r in records]


# ══════════════════════════════════════════════════════════════════════
# VERIFICATION ENDPOINTS
# ══════════════════════════════════════════════════════════════════════

@router.post("/verify", response_model=VerifyResultOut)
async def verify_chain(
    body: VerifyChainRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Verify the integrity of a blockchain chain.

    Checks hash continuity, recomputes each block hash, and
    verifies HMAC signatures (if present).
    """
    try:
        chain = ChainType(body.chain_type)
    except ValueError:
        valid = [ct.value for ct in ChainType]
        raise HTTPException(400, f"Invalid chain_type. Must be one of: {valid}")

    ledger = BlockchainLedger(db)
    is_valid, error, stats = await ledger.verify_chain(
        chain_type=chain,
        start_index=body.start_index,
        end_index=body.end_index,
    )
    return VerifyResultOut(is_valid=is_valid, error=error, stats=stats)


@router.get("/verify/block/{block_uid}", response_model=VerifyResultOut)
async def verify_block(
    block_uid: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Verify the hash integrity and signature of a single block."""
    ledger = BlockchainLedger(db)
    is_valid, error = await ledger.verify_block_by_uid(block_uid)
    return VerifyResultOut(is_valid=is_valid, error=error)


# ══════════════════════════════════════════════════════════════════════
# QUERY ENDPOINTS
# ══════════════════════════════════════════════════════════════════════

@router.get("/chains", response_model=ChainsOverviewOut)
async def list_chains(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all blockchain chains with metadata (block counts, hashes)."""
    ledger = BlockchainLedger(db)
    chains = await ledger.get_all_chains_info()
    total_blocks = sum(c.get("block_count", 0) for c in chains)
    chain_items = [
        ChainInfoOut(
            chain_type=c["chain_type"],
            block_count=c.get("block_count", 0),
            latest_index=c.get("latest_index", 0),
            latest_hash=c.get("latest_hash", ""),
            merkle_root=c.get("merkle_root"),
            genesis_hash=c.get("genesis_hash"),
            created_at=c.get("created_at"),
            updated_at=c.get("updated_at"),
        )
        for c in chains
    ]
    return ChainsOverviewOut(chains=chain_items, total_chains=len(chain_items), total_blocks=total_blocks)


@router.get("/chains/{chain_type}", response_model=ChainInfoOut)
async def get_chain_info(
    chain_type: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get detailed info about a specific blockchain chain."""
    try:
        chain = ChainType(chain_type)
    except ValueError:
        raise HTTPException(400, "Invalid chain_type")

    ledger = BlockchainLedger(db)
    info = await ledger.get_chain_info(chain)
    if info is None:
        raise HTTPException(404, f"Chain '{chain_type}' has no recorded blocks yet")
    return ChainInfoOut(
        chain_type=info["chain_type"],
        block_count=info.get("block_count", 0),
        latest_index=info.get("latest_index", 0),
        latest_hash=info.get("latest_hash", ""),
        merkle_root=info.get("merkle_root"),
        genesis_hash=info.get("genesis_hash"),
        created_at=info.get("created_at"),
        updated_at=info.get("updated_at"),
    )


@router.get("/trail/entity/{entity_type}/{entity_id}", response_model=EntityTrailOut)
async def entity_trail(
    entity_type: str,
    entity_id: int,
    chain_type: Optional[str] = Query(None, description="Filter by chain type"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the immutable audit trail for a specific entity.

    For example, all blockchain events for medication #42.
    """
    ledger = BlockchainLedger(db)
    records = await ledger.get_entity_trail(entity_type, entity_id)

    # optional chain type filter
    if chain_type:
        records = [r for r in records if r.chain_type == chain_type]

    blocks = [_block_record_to_out(r) for r in records]
    return EntityTrailOut(
        entity_type=entity_type,
        entity_id=entity_id,
        chain_type=chain_type,
        blocks=blocks,
        total=len(blocks),
    )


@router.get("/trail/user/{user_id}", response_model=EntityTrailOut)
async def user_trail(
    user_id: int,
    chain_type: Optional[str] = Query(None, description="Filter by chain type"),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all blockchain events attributed to a user.

    Users can view their own trail; admins can view any user's trail.
    """
    # Allow users to view own trail or admin to view others
    if current_user.id != user_id:
        # Simple admin check – extend with role checks as needed
        user_role = getattr(current_user, "role", None) or getattr(current_user, "user_type", None)
        if user_role not in ("admin", "provider"):
            raise HTTPException(403, "You can only view your own audit trail")

    ledger = BlockchainLedger(db)
    records = await ledger.get_user_trail(user_id, limit=limit)

    if chain_type:
        records = [r for r in records if r.chain_type == chain_type]

    blocks = [_block_record_to_out(r) for r in records]
    return EntityTrailOut(
        entity_type="user",
        entity_id=user_id,
        chain_type=chain_type,
        blocks=blocks,
        total=len(blocks),
    )


@router.get("/blocks/recent", response_model=list[BlockOut])
async def recent_blocks(
    chain_type: Optional[str] = Query(None, description="Filter by chain type"),
    limit: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the most recent blocks across all chains or a specific chain."""
    ct = None
    if chain_type:
        try:
            ct = ChainType(chain_type)
        except ValueError:
            raise HTTPException(400, "Invalid chain_type")

    ledger = BlockchainLedger(db)
    records = await ledger.get_recent_blocks(chain_type=ct, limit=limit)
    return [_block_record_to_out(r) for r in records]


# ══════════════════════════════════════════════════════════════════════
# REFERENCE DATA ENDPOINTS
# ══════════════════════════════════════════════════════════════════════

@router.get("/chain-types", response_model=ChainTypesOut)
async def list_chain_types():
    """List all available chain types with descriptions."""
    descriptions = {
        ChainType.health_record: "Immutable health record changes (conditions, vitals, labs)",
        ChainType.prescription: "Medication / prescription lifecycle tracking",
        ChainType.therapy: "Therapy session immutability & audit",
        ChainType.messaging: "Message chaining & delivery integrity",
        ChainType.session_audit: "User session / access audit trail",
        ChainType.data_provenance: "Data origin & transformation tracking",
        ChainType.payment: "Payment transaction transparency (future)",
    }
    items = [{"value": ct.value, "description": descriptions.get(ct, "")} for ct in ChainType]
    return ChainTypesOut(chain_types=items)


@router.get("/actions", response_model=EventActionsOut)
async def list_actions(
    chain_type: Optional[str] = Query(None, description="Filter actions by chain domain"),
):
    """List all available event actions, optionally filtered by chain type."""
    actions = []
    for ea in EventAction:
        entry = {"value": ea.value, "name": ea.name}
        if chain_type:
            # rough domain filter by prefix convention
            if ea.value.startswith(_chain_to_action_prefix(chain_type)):
                actions.append(entry)
        else:
            actions.append(entry)
    return EventActionsOut(actions=actions)


def _chain_to_action_prefix(chain_type: str) -> str:
    """Map chain type to the action name prefix."""
    mapping = {
        "health_record": "record_",
        "prescription": "prescription_",
        "therapy": "therapy_",
        "messaging": "message_",
        "session_audit": "user_",
        "data_provenance": "data_",
        "payment": "payment_",
    }
    return mapping.get(chain_type, "xxx_never_match")


# ══════════════════════════════════════════════════════════════════════
# ON-CHAIN ANCHOR VERIFICATION
# ══════════════════════════════════════════════════════════════════════

@router.get("/verify/on-chain/{block_uid}")
async def verify_on_chain(
    block_uid: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Verify a block's on-chain anchor against the Anvil ledger.

    Returns whether the tx data on the private Ethereum chain matches
    the block's stored hash.
    """
    from app.models.blockchain import BlockRecord as BR
    from app.services.chain_anchor import verify_on_chain_anchor

    stmt = select(BR).where(BR.block_uid == block_uid)
    result = await db.execute(stmt)
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(404, "Block not found")
    if not record.blockchain_tx_hash:
        return {"anchored": False, "message": "Block was not anchored on-chain"}

    verification = await verify_on_chain_anchor(record.blockchain_tx_hash, record.hash)
    return {"anchored": True, **verification}
