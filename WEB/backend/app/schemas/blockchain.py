"""Pydantic schemas for the blockchain / immutable ledger API."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ══════════════════════════════════════════════════════════════════════
# REQUEST SCHEMAS
# ══════════════════════════════════════════════════════════════════════

class RecordEventRequest(BaseModel):
    """Record a single blockchain event."""

    chain_type: str = Field(
        ...,
        description="Chain domain: health_record, prescription, therapy, messaging, session_audit, data_provenance, payment",
    )
    action: str = Field(..., description="Event action, e.g. 'record_created', 'prescription_dispensed'")
    data: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary event payload")
    entity_type: Optional[str] = Field(None, description="Affected model/table, e.g. 'medication', 'vitals_log'")
    entity_id: Optional[int] = Field(None, description="Primary key of the affected record")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Extra context (IP, user-agent, etc.)")

    class Config:
        json_schema_extra = {
            "example": {
                "chain_type": "prescription",
                "action": "prescription_created",
                "data": {"medication": "Metformin", "dosage": "500mg", "frequency": "twice daily"},
                "entity_type": "medication",
                "entity_id": 42,
            }
        }


class RecordBatchRequest(BaseModel):
    """Record multiple blockchain events atomically with a shared Merkle root."""

    chain_type: str = Field(..., description="Chain domain")
    events: List[Dict[str, Any]] = Field(
        ...,
        min_length=1,
        description="List of events, each with: action, data, entity_type?, entity_id?",
    )
    metadata: Optional[Dict[str, Any]] = Field(None)


class VerifyChainRequest(BaseModel):
    """Request to verify chain integrity."""

    chain_type: str = Field(..., description="Chain domain to verify")
    start_index: int = Field(0, ge=0, description="Start block index (default: 0 = from genesis)")
    end_index: Optional[int] = Field(None, description="End block index (default: latest)")


class VerifyBlockRequest(BaseModel):
    """Request to verify a single block."""

    block_uid: str = Field(..., description="Unique block identifier (UUID)")


# ══════════════════════════════════════════════════════════════════════
# RESPONSE SCHEMAS
# ══════════════════════════════════════════════════════════════════════

class BlockOut(BaseModel):
    """A single block returned from the API."""

    id: Optional[int] = None
    block_uid: str
    index: int
    timestamp: str
    chain_type: str
    action: str
    data: Optional[Dict[str, Any]] = None
    previous_hash: str
    hash: str
    nonce: Optional[str] = None
    actor_id: Optional[int] = None
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None
    merkle_root: Optional[str] = None
    signature: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    blockchain_tx_hash: Optional[str] = None
    blockchain_block_num: Optional[int] = None
    created_at: Optional[str] = None

    class Config:
        from_attributes = True


class ChainInfoOut(BaseModel):
    """Metadata about a specific chain."""

    chain_type: str
    block_count: int
    latest_index: int
    latest_hash: str
    merkle_root: Optional[str] = None
    genesis_hash: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


class VerifyResultOut(BaseModel):
    """Result of a chain or block verification."""

    is_valid: bool
    error: Optional[str] = None
    stats: Optional[Dict[str, Any]] = None


class EntityTrailOut(BaseModel):
    """Full audit trail for an entity."""

    entity_type: str
    entity_id: int
    chain_type: Optional[str] = None
    blocks: List[BlockOut]
    total: int


class ChainsOverviewOut(BaseModel):
    """Overview of all chains in the system."""

    chains: List[ChainInfoOut]
    total_chains: int
    total_blocks: Optional[int] = None


class ChainTypesOut(BaseModel):
    """Available chain types."""

    chain_types: List[Dict[str, str]]


class EventActionsOut(BaseModel):
    """Available event actions."""

    actions: List[Dict[str, str]]
