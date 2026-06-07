// 255-character System Identifier (SID) generation & verification.
//
// Format: S1.FN3.LN3.DOB8.GEN1.EPOCH10.RND93.SHA512CHK
//   Total = 2+1+3+1+3+1+8+1+1+1+10+1+93+1+128 = 255 characters

use pyo3::prelude::*;
use pyo3::types::PyDict;
use rand::Rng;
use sha2::{Digest, Sha512};
use std::time::{SystemTime, UNIX_EPOCH};

const VERSION: &str = "S1";
const SEP: char = '.';
const FULL_LENGTH: usize = 255;
const RND_LENGTH: usize = 93;
const SAFE_CHARS: &[u8] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-";

fn norm3(name: &str) -> String {
    let alpha: String = name.chars().filter(|c| c.is_ascii_alphabetic()).collect();
    let upper = alpha.to_uppercase();
    let mut result: String = upper.chars().take(3).collect();
    while result.len() < 3 {
        result.push('X');
    }
    result
}

fn sex_code(gender: &str) -> &'static str {
    match gender.trim().to_lowercase().as_str() {
        "male" | "m" => "M",
        "female" | "f" => "F",
        "intersex" | "x" => "X",
        _ => "U",
    }
}

fn dob8(dob: &str) -> String {
    if dob.is_empty() {
        return "00000000".to_string();
    }
    let cleaned: String = dob.chars().filter(|c| c.is_ascii_digit()).collect();
    let mut result = cleaned;
    if result.len() > 8 {
        result.truncate(8);
    }
    while result.len() < 8 {
        result.push('0');
    }
    result
}

fn epoch10() -> String {
    let secs = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs();
    format!("{:0>10}", secs % 10_000_000_000)
}

fn random_string(len: usize) -> String {
    let mut rng = rand::thread_rng();
    (0..len)
        .map(|_| {
            let idx = rng.gen_range(0..SAFE_CHARS.len());
            SAFE_CHARS[idx] as char
        })
        .collect()
}

/// Generate a new 255-character System Identifier.
#[pyfunction]
pub fn generate_sid(
    first_name: &str,
    last_name: &str,
    date_of_birth: &str,
    gender_at_birth: &str,
) -> PyResult<String> {
    let fn3 = norm3(first_name);
    let ln3 = norm3(last_name);
    let dob = dob8(date_of_birth);
    let gen1 = sex_code(gender_at_birth);
    let ep = epoch10();
    let rnd = random_string(RND_LENGTH);

    let prefix = format!(
        "{}{}{}{}{}{}{}{}{}{}{}{}{}",
        VERSION, SEP, fn3, SEP, ln3, SEP, dob, SEP, gen1, SEP, ep, SEP, rnd
    );

    let mut hasher = Sha512::new();
    hasher.update(prefix.as_bytes());
    let checksum = hex::encode(hasher.finalize()); // 128 hex chars

    let sid = format!("{}{}{}", prefix, SEP, checksum);

    if sid.len() != FULL_LENGTH {
        return Err(pyo3::exceptions::PyValueError::new_err(format!(
            "SID length {} != {}",
            sid.len(),
            FULL_LENGTH
        )));
    }

    Ok(sid)
}

/// Verify the SHA-512 checksum of a SID. Returns `true` if valid.
#[pyfunction]
pub fn verify_sid(sid: &str) -> bool {
    if sid.len() != FULL_LENGTH {
        return false;
    }
    // Last 128 chars = checksum; char at -129 must be separator
    let prefix = &sid[..sid.len() - 129]; // everything before ".CHECKSUM"
    let stored_checksum = &sid[sid.len() - 128..];

    let mut hasher = Sha512::new();
    hasher.update(prefix.as_bytes());
    let expected = hex::encode(hasher.finalize());

    expected == stored_checksum
}

/// Decode a SID into its component segments. Returns a Python dict.
#[pyfunction]
pub fn decode_sid(py: Python<'_>, sid: &str) -> PyResult<PyObject> {
    let parts: Vec<&str> = sid.split(SEP).collect();
    if parts.len() < 7 {
        return Err(pyo3::exceptions::PyValueError::new_err(
            "Invalid SID \u{2014} expected at least 7 segments",
        ));
    }

    let dict = PyDict::new(py);
    dict.set_item("version", parts[0])?;
    dict.set_item("fn3", parts[1])?;
    dict.set_item("ln3", parts[2])?;
    dict.set_item("dob8", parts[3])?;
    dict.set_item("gen1", parts[4])?;
    dict.set_item("epoch10", parts[5])?;
    dict.set_item("checksum", *parts.last().unwrap())?;

    Ok(dict.into())
}

/// Return a privacy-masked version of the SID.
///
/// Shows version, name seeds, DOB, and sex — hides random and checksum.
#[pyfunction]
pub fn mask_sid(sid: &str) -> String {
    let parts: Vec<&str> = sid.split(SEP).collect();
    if parts.len() < 7 {
        let truncated: String = sid.chars().take(20).collect();
        return format!("{}\u{2026}", truncated);
    }
    format!(
        "{}.{}.{}.{}.{}.[RND\u{2026}].[SHA\u{2026}]",
        parts[0], parts[1], parts[2], parts[3], parts[4]
    )
}
