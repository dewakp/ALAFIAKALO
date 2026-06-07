// alafia_crypto — High-performance cryptographic services for ALAFIA
//
// Modules:
//   hashing  — SHA-512, HMAC-SHA512, data hashing
//   merkle   — Merkle tree build, proof generation, proof verification
//   block    — Block hash computation, signing, chain verification
//   sid      — 255-char System Identifier generation & verification

mod block;
mod hashing;
mod merkle;
mod sid;

use pyo3::prelude::*;

/// Root Python module exposed as `alafia_crypto`.
#[pymodule]
fn alafia_crypto(m: &Bound<'_, PyModule>) -> PyResult<()> {
    // ── hashing ──────────────────────────────────────────────
    m.add_function(wrap_pyfunction!(hashing::sha512_hex, m)?)?;
    m.add_function(wrap_pyfunction!(hashing::hmac_sha512_hex, m)?)?;
    m.add_function(wrap_pyfunction!(hashing::hmac_sha512_verify, m)?)?;
    m.add_function(wrap_pyfunction!(hashing::compute_data_hash, m)?)?;

    // ── block ────────────────────────────────────────────────
    m.add_function(wrap_pyfunction!(block::compute_block_hash, m)?)?;
    m.add_function(wrap_pyfunction!(block::sign_block, m)?)?;
    m.add_function(wrap_pyfunction!(block::verify_block_signature, m)?)?;
    m.add_function(wrap_pyfunction!(block::verify_chain, m)?)?;

    // ── merkle ───────────────────────────────────────────────
    m.add_function(wrap_pyfunction!(merkle::merkle_build, m)?)?;
    m.add_function(wrap_pyfunction!(merkle::merkle_proof, m)?)?;
    m.add_function(wrap_pyfunction!(merkle::merkle_verify_proof, m)?)?;

    // ── sid ──────────────────────────────────────────────────
    m.add_function(wrap_pyfunction!(sid::generate_sid, m)?)?;
    m.add_function(wrap_pyfunction!(sid::verify_sid, m)?)?;
    m.add_function(wrap_pyfunction!(sid::decode_sid, m)?)?;
    m.add_function(wrap_pyfunction!(sid::mask_sid, m)?)?;

    Ok(())
}
