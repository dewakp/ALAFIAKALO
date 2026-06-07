"""255-character System Identifier (SID) service.

All cryptographic operations (SHA-512 checksum, random generation) are
handled by the Rust `alafia_crypto` native extension for performance
and constant-time safety.

Format: S1.FN3.LN3.DOB8.GEN1.EPOCH10.RND93.SHA512CHK  (255 chars)

Usage:
    sid = generate_sid("Adewole", "Akpose", "1958-04-12", "male")
    segments = decode_sid(sid)
    assert verify_sid(sid) is True
    masked = mask_sid(sid)   # "S1.ADE.AKP.19580412.M.[RND…].[SHA…]"
"""

from __future__ import annotations

import time
from typing import Optional

import alafia_crypto as _rc


_VERSION = "S1"


def generate_sid(
    first_name: str,
    last_name: str,
    date_of_birth: str | None = None,
    gender_at_birth: str | None = None,
) -> str:
    """Generate a new 255-character System Identifier (Rust backend)."""
    return _rc.generate_sid(
        first_name,
        last_name,
        date_of_birth or "",
        gender_at_birth or "",
    )


def verify_sid(sid: str) -> bool:
    """Verify the SHA-512 checksum of a SID (Rust backend)."""
    return _rc.verify_sid(sid)


def decode_sid(sid: str) -> dict:
    """Decode a SID into its component segments (Rust backend)."""
    return _rc.decode_sid(sid)


def mask_sid(sid: str) -> str:
    """Return a privacy-masked version of the SID (Rust backend)."""
    return _rc.mask_sid(sid)


def get_segments_for_log(
    first_name: str,
    last_name: str,
    date_of_birth: str | None,
    gender_at_birth: str | None,
) -> dict:
    """Return the deterministic segment values (for SystemIdLog).

    This is a thin Python helper — no crypto involved."
    """
    def _norm3(name: str) -> str:
        alpha = "".join(c for c in name if c.isalpha())[:3].upper()
        return alpha.ljust(3, "X")

    def _sex_code(g: str | None) -> str:
        if not g:
            return "U"
        gl = g.strip().lower()
        if gl in ("male", "m"):
            return "M"
        if gl in ("female", "f"):
            return "F"
        if gl in ("intersex", "x"):
            return "X"
        return "U"

    def _dob8(dob: str | None) -> str:
        if not dob:
            return "00000000"
        try:
            return dob.replace("-", "")[:8].ljust(8, "0")
        except Exception:
            return "00000000"

    return {
        "seg_version": _VERSION,
        "seg_fn3": _norm3(first_name),
        "seg_ln3": _norm3(last_name),
        "seg_dob8": _dob8(date_of_birth),
        "seg_gen1": _sex_code(gender_at_birth),
        "seg_epoch10": str(int(time.time())).zfill(10)[-10:],
    }
