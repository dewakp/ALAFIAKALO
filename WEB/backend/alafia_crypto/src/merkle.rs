// Merkle tree: build, proof generation, proof verification.

use pyo3::prelude::*;
use sha2::{Digest, Sha512};

/// Build a Merkle tree from a list of leaf hashes.
///
/// Returns `(root_hash, tree_levels)` where `tree_levels` is a list of lists,
/// level 0 being the leaves and the last level being `[root]`.
#[pyfunction]
pub fn merkle_build(leaves: Vec<String>) -> PyResult<(String, Vec<Vec<String>>)> {
    if leaves.is_empty() {
        return Err(pyo3::exceptions::PyValueError::new_err(
            "Cannot build Merkle tree from empty list",
        ));
    }

    let mut tree: Vec<Vec<String>> = Vec::new();
    let mut level = leaves;
    tree.push(level.clone());

    while level.len() > 1 {
        let mut next_level: Vec<String> = Vec::new();
        let mut i = 0;
        while i < level.len() {
            let left = &level[i];
            let right = if i + 1 < level.len() {
                &level[i + 1]
            } else {
                &level[i] // duplicate if odd
            };
            let combined = format!("{}{}", left, right);
            let mut hasher = Sha512::new();
            hasher.update(combined.as_bytes());
            next_level.push(hex::encode(hasher.finalize()));
            i += 2;
        }
        tree.push(next_level.clone());
        level = next_level;
    }

    let root = level[0].clone();
    Ok((root, tree))
}

/// Generate a Merkle inclusion proof for the leaf at `index`.
///
/// `tree_levels` is the full tree as returned by `merkle_build`.
/// Returns a list of `(sibling_hash, side)` where side is "L" or "R".
#[pyfunction]
pub fn merkle_proof(tree_levels: Vec<Vec<String>>, index: usize) -> PyResult<Vec<(String, String)>> {
    if tree_levels.is_empty() {
        return Err(pyo3::exceptions::PyValueError::new_err("Empty tree"));
    }
    if index >= tree_levels[0].len() {
        return Err(pyo3::exceptions::PyIndexError::new_err(format!(
            "Leaf index {} out of range",
            index
        )));
    }

    let mut proof: Vec<(String, String)> = Vec::new();
    let mut idx = index;

    // Iterate over all levels except the root level
    for level in tree_levels.iter().take(tree_levels.len().saturating_sub(1)) {
        if idx % 2 == 0 {
            let sibling_idx = idx + 1;
            if sibling_idx < level.len() {
                proof.push((level[sibling_idx].clone(), "R".to_string()));
            } else {
                proof.push((level[idx].clone(), "R".to_string())); // self-duplicate
            }
        } else {
            let sibling_idx = idx - 1;
            proof.push((level[sibling_idx].clone(), "L".to_string()));
        }
        idx /= 2;
    }

    Ok(proof)
}

/// Verify a Merkle inclusion proof.
///
/// Starting from `leaf_hash`, apply each `(sibling, side)` pair to walk
/// up the tree.  Returns `true` if the computed root matches `root`.
#[pyfunction]
pub fn merkle_verify_proof(leaf_hash: &str, proof: Vec<(String, String)>, root: &str) -> bool {
    let mut current = leaf_hash.to_string();
    for (sibling, side) in &proof {
        let combined = if side == "R" {
            format!("{}{}", current, sibling)
        } else {
            format!("{}{}", sibling, current)
        };
        let mut hasher = Sha512::new();
        hasher.update(combined.as_bytes());
        current = hex::encode(hasher.finalize());
    }
    current == root
}
