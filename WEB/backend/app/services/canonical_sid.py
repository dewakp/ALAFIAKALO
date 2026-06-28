"""Canonical 6IGMA System Identifier (SID) — the ONE algorithm shared by ALAFIA
and FlowSheet.

This is a faithful, dependency-free (stdlib-only) port of FlowSheet's
`fn_generate_system_id` (db/init/07_system_identifier.sql), which is the
reference. A SID minted by FlowSheet's PostgreSQL function and a SID minted here
verify identically, because `verify_sid` only re-hashes the human-readable
payload — see `docs/IDENTITY_ARCHITECTURE.md` / `alafia_flowsheet_alignment_plan.md`
(Prompt 1.2).

LAYOUT (dot-separated, exactly 255 chars):
    S1 . FN3 . LN3 . DOB8 . GEN1 . EPO10 . RND157 . SHA256(64)
    2    3     3     8      1      10      157       64        + 7 dots = 255

  VER     "S1" (schema version)
  FN3     first 3 alpha chars of first name, UPPER, right-padded with 'X'
  LN3     first 3 alpha chars of last name,  UPPER, right-padded with 'X'
  DOB8    date of birth YYYYMMDD  (00000000 if unknown)
  GEN1    M=male F=female X=intersex N=prefer_not_to_say U=unknown
  EPO10   unix epoch seconds of account creation, zero-padded to 10
  RND157  157 cryptographically-random chars from A-Z0-9 (modulo-bias rejected)
  HSH64   sha256_hex( "VER.FN3.LN3.DOB8.GEN1.EPO10.RND157" )  → self-verifying

NOTE: RND157 makes the SID a per-account credential, NOT a deterministic hash of
identity — re-generating for the same person yields a different SID. The durable
cross-app key is the stored SID; identity de-dup is by email/username.
"""

from __future__ import annotations

import hashlib
import secrets
import time
from datetime import date, datetime

VERSION = "S1"
ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"  # 36 chars
_ALPHA_LEN = 36
_REJECT_AT = 252  # 7 * 36 — reject bytes >= 252 to eliminate modulo bias
SID_LENGTH = 255
RND_LEN = 157


# ── segment builders ─────────────────────────────────────────────────────────

def _name3(name: str | None) -> str:
    alpha = "".join(c for c in (name or "") if c.isalpha())[:3].upper()
    return alpha.ljust(3, "X")


def _dob8(dob) -> str:
    if not dob:
        return "00000000"
    if isinstance(dob, (date, datetime)):
        return dob.strftime("%Y%m%d")
    digits = str(dob).replace("-", "").replace("/", "").strip()
    return digits[:8] if len(digits) >= 8 and digits[:8].isdigit() else "00000000"


def _gen1(sex: str | None) -> str:
    s = (sex or "").strip().lower()
    return {
        "male": "M", "m": "M",
        "female": "F", "f": "F",
        "intersex": "X", "x": "X",
        "prefer_not_to_say": "N", "n": "N",
    }.get(s, "U")


def _epoch10(created_at=None) -> str:
    if created_at is None:
        ts = time.time()
    elif isinstance(created_at, (int, float)):
        ts = float(created_at)
    elif isinstance(created_at, datetime):
        ts = created_at.timestamp()
    else:
        ts = time.time()
    return str(int(ts)).zfill(10)


def _rnd(n: int = RND_LEN) -> str:
    """n cryptographically-random A-Z0-9 chars, modulo-bias rejected."""
    out: list[str] = []
    while len(out) < n:
        for b in secrets.token_bytes(256):
            if b < _REJECT_AT:
                out.append(ALPHABET[b % _ALPHA_LEN])
                if len(out) == n:
                    break
    return "".join(out)


def _sha256_hex(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ── public API ───────────────────────────────────────────────────────────────

def generate_sid(
    first_name: str,
    last_name: str,
    date_of_birth=None,
    biological_sex: str | None = None,
    created_at=None,
) -> str:
    """Mint a canonical 255-char SID. `created_at` defaults to now."""
    fn3 = _name3(first_name)
    ln3 = _name3(last_name)
    dob8 = _dob8(date_of_birth)
    gen1 = _gen1(biological_sex)
    epo10 = _epoch10(created_at)
    rnd157 = _rnd()
    payload = ".".join([VERSION, fn3, ln3, dob8, gen1, epo10, rnd157])
    sid = payload + "." + _sha256_hex(payload)
    if len(sid) != SID_LENGTH:
        raise ValueError(f"SID length {len(sid)} != {SID_LENGTH}")
    return sid


def decode_sid(sid: str) -> dict:
    """Split a SID into its segments (+ a `valid` flag). Tolerant of CHAR padding."""
    parts = (sid or "").rstrip().split(".")
    if len(parts) != 8:
        return {"valid": False, "error": "expected 8 dot-separated segments"}
    ver, fn3, ln3, dob8, gen1, epo10, rnd157, hash64 = parts
    return {
        "version": ver, "fn3": fn3, "ln3": ln3, "dob8": dob8,
        "gen1": gen1, "epoch10": epo10, "rnd157": rnd157, "hash64": hash64,
        "valid": verify_sid(sid),
    }


def verify_sid(sid: str) -> bool:
    """True iff the SHA-256 over the first 7 segments matches the trailing hash.

    Verifies SIDs minted by EITHER app (FlowSheet SQL or this module)."""
    try:
        s = (sid or "").rstrip()
        if len(s) != SID_LENGTH:
            return False
        parts = s.split(".")
        if len(parts) != 8 or parts[0] != VERSION:
            return False
        payload = ".".join(parts[:7])
        return secrets.compare_digest(_sha256_hex(payload), parts[7].lower())
    except Exception:
        return False


def mask_sid(sid: str) -> str:
    """Privacy-masked SID, e.g. 'S1.ADE.AKP.19580412.M.[RND…].[SHA…]'."""
    d = decode_sid(sid)
    if not d.get("version"):
        return "[invalid-sid]"
    return f"{d['version']}.{d['fn3']}.{d['ln3']}.{d['dob8']}.{d['gen1']}.[RND…].[SHA…]"


def segments_for_log(
    first_name: str,
    last_name: str,
    date_of_birth=None,
    biological_sex: str | None = None,
    created_at=None,
) -> dict:
    """Deterministic, non-random segments for an audit-log row (no crypto)."""
    return {
        "seg_version": VERSION,
        "seg_fn3": _name3(first_name),
        "seg_ln3": _name3(last_name),
        "seg_dob8": _dob8(date_of_birth),
        "seg_gen1": _gen1(biological_sex),
        "seg_epoch10": _epoch10(created_at),
    }
