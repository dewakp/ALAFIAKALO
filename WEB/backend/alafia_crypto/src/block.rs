// Block-level cryptographic operations: hash computation, signing, chain verification.

use pyo3::prelude::*;
use pyo3::types::PyDict;
use serde_json::Value;

use crate::hashing::{hmac_sha512_hex, hmac_sha512_verify, sha512_hex};

/// Compute the SHA-512 hash for a block given its field values.
///
/// Mirrors `Block.compute_hash()` in the Python engine — the caller passes
/// a JSON string that encodes the canonical fields (index, timestamp,
/// chain_type, action, data, previous_hash, nonce, actor_id, entity_type,
/// entity_id, block_uid) with `sort_keys=True, default=str`.
///
/// Returns the 128-char lowercase hex digest.
#[pyfunction]
pub fn compute_block_hash(canonical_json: &str) -> String {
    sha512_hex(canonical_json)
}

/// Produce an HMAC-SHA512 signature over a block hash.
///
/// Returns 128-char hex digest.
#[pyfunction]
pub fn sign_block(block_hash: &str, secret: &str) -> String {
    hmac_sha512_hex(secret, block_hash)
}

/// Verify an HMAC-SHA512 signature (constant-time).
#[pyfunction]
pub fn verify_block_signature(block_hash: &str, signature: &str, secret: &str) -> bool {
    hmac_sha512_verify(secret, block_hash, signature)
}

/// Verify a full ordered chain of blocks.
///
/// Each element in `blocks_json` is a JSON string representing a block with
/// at minimum: index, hash, previous_hash, signature (optional).
/// The `secret` is used for signature verification.
///
/// Returns a Python dict: {"valid": bool, "error": str | None}
#[pyfunction]
pub fn verify_chain(py: Python<'_>, blocks_json: Vec<String>, secret: &str) -> PyResult<PyObject> {
    let dict = PyDict::new(py);

    if blocks_json.is_empty() {
        dict.set_item("valid", true)?;
        dict.set_item("error", py.None())?;
        return Ok(dict.into());
    }

    // Parse all blocks
    let blocks: Vec<Value> = blocks_json
        .iter()
        .map(|s| serde_json::from_str(s))
        .collect::<Result<Vec<_>, _>>()
        .map_err(|e| pyo3::exceptions::PyValueError::new_err(format!("JSON parse error: {e}")))?;

    let genesis = &blocks[0];

    // Genesis checks
    let genesis_index = genesis
        .get("index")
        .and_then(|v| v.as_i64())
        .unwrap_or(-1);
    if genesis_index != 0 {
        dict.set_item("valid", false)?;
        dict.set_item(
            "error",
            "Chain does not start with genesis block (index 0)",
        )?;
        return Ok(dict.into());
    }

    let genesis_prev = genesis
        .get("previous_hash")
        .and_then(|v| v.as_str())
        .unwrap_or("");
    if genesis_prev != "0".repeat(128) {
        dict.set_item("valid", false)?;
        dict.set_item("error", "Genesis block has invalid previous_hash")?;
        return Ok(dict.into());
    }

    // Verify genesis hash
    if let Some(canonical) = genesis.get("_canonical_json") {
        let canonical_str = canonical.as_str().unwrap_or("");
        let expected = sha512_hex(canonical_str);
        let stored = genesis
            .get("hash")
            .and_then(|v| v.as_str())
            .unwrap_or("");
        if expected != stored {
            dict.set_item("valid", false)?;
            dict.set_item("error", "Genesis block hash mismatch at index 0")?;
            return Ok(dict.into());
        }
    }

    // Walk the chain
    for i in 1..blocks.len() {
        let current = &blocks[i];
        let previous = &blocks[i - 1];

        // Verify hash if canonical JSON provided
        if let Some(canonical) = current.get("_canonical_json") {
            let canonical_str = canonical.as_str().unwrap_or("");
            let expected = sha512_hex(canonical_str);
            let stored = current
                .get("hash")
                .and_then(|v| v.as_str())
                .unwrap_or("");
            if expected != stored {
                let idx = current
                    .get("index")
                    .and_then(|v| v.as_i64())
                    .unwrap_or(-1);
                dict.set_item("valid", false)?;
                dict.set_item("error", format!("Block hash mismatch at index {idx}"))?;
                return Ok(dict.into());
            }
        }

        // Verify chain link
        let prev_hash = previous
            .get("hash")
            .and_then(|v| v.as_str())
            .unwrap_or("");
        let curr_prev = current
            .get("previous_hash")
            .and_then(|v| v.as_str())
            .unwrap_or("");
        if curr_prev != prev_hash {
            let prev_idx = previous
                .get("index")
                .and_then(|v| v.as_i64())
                .unwrap_or(-1);
            let curr_idx = current
                .get("index")
                .and_then(|v| v.as_i64())
                .unwrap_or(-1);
            dict.set_item("valid", false)?;
            dict.set_item(
                "error",
                format!("Chain link broken between index {prev_idx} and {curr_idx}"),
            )?;
            return Ok(dict.into());
        }

        // Verify index continuity
        let prev_idx = previous
            .get("index")
            .and_then(|v| v.as_i64())
            .unwrap_or(-1);
        let curr_idx = current
            .get("index")
            .and_then(|v| v.as_i64())
            .unwrap_or(-1);
        if curr_idx != prev_idx + 1 {
            dict.set_item("valid", false)?;
            dict.set_item(
                "error",
                format!("Chain link broken between index {prev_idx} and {curr_idx}"),
            )?;
            return Ok(dict.into());
        }

        // Verify signature if present
        let sig = current
            .get("signature")
            .and_then(|v| v.as_str())
            .unwrap_or("");
        let block_hash = current
            .get("hash")
            .and_then(|v| v.as_str())
            .unwrap_or("");
        if !sig.is_empty() && !hmac_sha512_verify(secret, block_hash, sig) {
            dict.set_item("valid", false)?;
            dict.set_item(
                "error",
                format!("Signature verification failed at index {curr_idx}"),
            )?;
            return Ok(dict.into());
        }
    }

    dict.set_item("valid", true)?;
    dict.set_item("error", py.None())?;
    Ok(dict.into())
}
