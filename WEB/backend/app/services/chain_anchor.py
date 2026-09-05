"""On-chain hash anchoring via private Ethereum node (Anvil / Foundry).

Mirrors the FLOWSHEET portal's blockchain anchoring:
  1. Compute payload_hash for the block
  2. Send a zero-value self-transfer with payload_hash as tx data
  3. Store the resulting tx_hash + block_number back on the BlockRecord

Anchoring is **best-effort** — failures are logged but never block the
application-level operation.  This is a data transparency / immutability
guarantee, not a consensus mechanism.

Usage:
    from app.services.chain_anchor import anchor_block_on_chain

    # After persisting a block to the database:
    tx_hash, block_num = await anchor_block_on_chain(block_record)
    if tx_hash:
        block_record.blockchain_tx_hash = tx_hash
        block_record.blockchain_block_num = block_num
"""

from __future__ import annotations

import logging
import os
from typing import Optional, Tuple


logger = logging.getLogger(__name__)

CHAIN_NODE_URL = os.getenv("CHAIN_NODE_URL", "http://chain:8545")
ANCHOR_TIMEOUT = 10  # seconds to wait for tx receipt

# Lazy singleton
_w3_instance = None


def _get_w3():
    """Lazy-init Web3 connection to Anvil (Foundry)."""
    global _w3_instance
    if _w3_instance is None:
        try:
            from web3 import AsyncWeb3, AsyncHTTPProvider
            _w3_instance = AsyncWeb3(AsyncHTTPProvider(CHAIN_NODE_URL))
        except Exception as exc:
            logger.warning("Web3 init failed (chain anchoring disabled): %s", exc)
            _w3_instance = None
    return _w3_instance


async def anchor_block_on_chain(
    payload_hash: str,
) -> Tuple[Optional[str], Optional[int]]:
    """Anchor a SHA-512 payload hash on the private Ethereum chain.

    Sends a zero-value self-transfer with the hash as calldata.

    Returns:
        (tx_hash_hex, block_number)  on success
        (None, None)                 on failure
    """
    w3 = _get_w3()
    if w3 is None:
        return None, None

    try:
        accounts = await w3.eth.accounts
        if not accounts:
            logger.warning("No Anvil accounts available for anchoring")
            return None, None

        sender = accounts[0]

        # Encode payload_hash as hex calldata
        data_hex = "0x" + payload_hash

        tx_hash = await w3.eth.send_transaction({
            "from": sender,
            "to": sender,
            "value": 0,
            "data": data_hex,
        })

        # Wait for receipt (bounded by ANCHOR_TIMEOUT)
        receipt = await w3.eth.wait_for_transaction_receipt(tx_hash, timeout=ANCHOR_TIMEOUT)

        tx_hash_hex = receipt["transactionHash"].hex() if hasattr(receipt["transactionHash"], "hex") else str(receipt["transactionHash"])
        block_number = receipt["blockNumber"]

        logger.info("Anchored hash %s → tx %s block %d", payload_hash[:16], tx_hash_hex[:16], block_number)
        return tx_hash_hex, block_number

    except Exception as exc:
        logger.warning("Chain anchoring failed (non-fatal): %s", exc)
        return None, None


async def verify_on_chain_anchor(
    tx_hash: str,
    expected_hash: str,
) -> dict:
    """Verify that an on-chain transaction contains the expected payload hash.

    Returns:
        {"valid": bool, "on_chain_data": str, "block": int, "message": str}
    """
    w3 = _get_w3()
    if w3 is None:
        return {"valid": False, "message": "Web3 not available"}

    try:
        tx = await w3.eth.get_transaction(tx_hash)
        on_chain_data = tx["input"].hex() if hasattr(tx["input"], "hex") else str(tx["input"])

        # Strip 0x prefix for comparison
        on_chain_clean = on_chain_data.lstrip("0x")
        expected_clean = expected_hash.lstrip("0x")

        is_valid = on_chain_clean == expected_clean
        return {
            "valid": is_valid,
            "on_chain_data": on_chain_data,
            "expected": expected_hash,
            "block": tx.get("blockNumber"),
            "message": "Match" if is_valid else "Mismatch — possible tampering",
        }
    except Exception as exc:
        return {"valid": False, "message": f"Verification failed: {exc}"}
