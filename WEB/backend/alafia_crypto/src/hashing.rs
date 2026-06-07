// Core hashing primitives: SHA-512, HMAC-SHA512, data hash.

use hmac::{Hmac, Mac};
use pyo3::prelude::*;
use sha2::{Digest, Sha512};
use subtle::ConstantTimeEq;

type HmacSha512 = Hmac<Sha512>;

/// Compute the SHA-512 hex digest of an arbitrary byte string.
#[pyfunction]
pub fn sha512_hex(data: &str) -> String {
    let mut hasher = Sha512::new();
    hasher.update(data.as_bytes());
    hex::encode(hasher.finalize())
}

/// Compute an HMAC-SHA512 hex digest.
#[pyfunction]
pub fn hmac_sha512_hex(key: &str, message: &str) -> String {
    let mut mac =
        HmacSha512::new_from_slice(key.as_bytes()).expect("HMAC can take key of any size");
    mac.update(message.as_bytes());
    hex::encode(mac.finalize().into_bytes())
}

/// Constant-time comparison of an HMAC-SHA512 digest against an expected hex string.
#[pyfunction]
pub fn hmac_sha512_verify(key: &str, message: &str, expected_hex: &str) -> bool {
    let computed = hmac_sha512_hex(key, message);
    let a = computed.as_bytes();
    let b = expected_hex.as_bytes();
    if a.len() != b.len() {
        return false;
    }
    a.ct_eq(b).into()
}

/// Compute a SHA-512 hash of a JSON string (used for data provenance hashing).
///
/// The caller is responsible for producing deterministic JSON (sorted keys).
/// This function simply hashes whatever string is passed in.
#[pyfunction]
pub fn compute_data_hash(json_payload: &str) -> String {
    sha512_hex(json_payload)
}
