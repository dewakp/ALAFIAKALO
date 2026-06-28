"""255-character System Identifier (SID) service.

As of the ALAFIA⇄FlowSheet alignment (Prompt 1.2), the SID is the **canonical
6IGMA algorithm** shared with FlowSheet (the reference):

    S1.FN3.LN3.DOB8.GEN1.EPO10.RND157.SHA256(64)   (255 chars)

The previous ALAFIA layout (RND93 + SHA-512 via the Rust `alafia_crypto`
extension) is **retired**; legacy SIDs are re-minted by the migration
(`scripts/remint_canonical_sids.py`). All logic now lives in the portable
`canonical_sid` module so the identity service and FlowSheet share one algorithm.

Usage:
    sid = generate_sid("Adewole", "Akpose", "1958-04-12", "male")
    assert verify_sid(sid) is True          # also verifies FlowSheet-minted SIDs
    segments = decode_sid(sid)
    masked = mask_sid(sid)                   # "S1.ADE.AKP.19580412.M.[RND…].[SHA…]"
"""

from __future__ import annotations

from app.services import canonical_sid

_VERSION = canonical_sid.VERSION


def generate_sid(
    first_name: str,
    last_name: str,
    date_of_birth: str | None = None,
    gender_at_birth: str | None = None,
) -> str:
    """Generate a new canonical 255-character System Identifier."""
    return canonical_sid.generate_sid(
        first_name, last_name, date_of_birth, gender_at_birth
    )


def verify_sid(sid: str) -> bool:
    """Verify a SID's SHA-256 self-check (works for SIDs minted by either app)."""
    return canonical_sid.verify_sid(sid)


def decode_sid(sid: str) -> dict:
    """Decode a SID into its component segments."""
    return canonical_sid.decode_sid(sid)


def mask_sid(sid: str) -> str:
    """Return a privacy-masked version of the SID."""
    return canonical_sid.mask_sid(sid)


def get_segments_for_log(
    first_name: str,
    last_name: str,
    date_of_birth: str | None,
    gender_at_birth: str | None,
) -> dict:
    """Return the deterministic segment values (for SystemIdLog)."""
    return canonical_sid.segments_for_log(
        first_name, last_name, date_of_birth, gender_at_birth
    )
