"""Hybrid post-quantum compact JWS for 6IGMA identity tokens.

Signs/verifies with BOTH Ed25519 (classical) AND ML-DSA-65 (FIPS 204, PQC) so a
token is trusted only if *both* signatures validate — it stays secure as long as
either algorithm holds (defence-in-depth through the PQC transition). Crypto-agile:
`alg` + `kid` live in the JWS header and the JWKS publishes both public keys
(OKP for Ed25519, AKP for ML-DSA). Stdlib + `cryptography` + `dilithium-py` only —
no python-jose.

Token   = b64url(header) "." b64url(payload) "." b64url(sigblob)
  header  = {"alg":"EdDSA+ML-DSA-65","typ":"JWT","kid":<thumbprint>}
  sigblob = uint16_be(len(ed_sig)) || ed_sig || mldsa_sig

`kid` is a thumbprint of the two public keys, so rotating/regenerating the keypair
changes the kid and consumers refresh their cached JWKS automatically.

ML-DSA backend: a **constant-time liboqs** build (Open Quantum Safe) is used when
available (the signer/identity service installs it), otherwise the pure-Python
dilithium-py is used. Both implement FIPS 204 ML-DSA-65, so a liboqs-signed token
verifies under dilithium-py and vice-versa — verifiers (apps) can stay pure-Python
since verification timing isn't secret-sensitive; only signing needs constant-time.
"""
from __future__ import annotations

import base64
import hashlib
import json
import time

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

ALG = "EdDSA+ML-DSA-65"
PQC_ALG = "ML-DSA-65"
TYP = "JWT"


# ── ML-DSA-65 backend (constant-time liboqs preferred; dilithium-py fallback) ─
try:
    import oqs as _oqs  # liboqs-python — constant-time C implementation
    _HAVE_OQS = True
except Exception:  # pragma: no cover - apps run verify-only on pure Python
    _HAVE_OQS = False

from dilithium_py.ml_dsa import ML_DSA_65 as _DILITHIUM


def mldsa_backend() -> str:
    return "liboqs" if _HAVE_OQS else "dilithium-py"


def _mldsa_keygen() -> tuple[bytes, bytes]:
    if _HAVE_OQS:
        with _oqs.Signature(PQC_ALG) as s:
            pk = s.generate_keypair()
            return pk, s.export_secret_key()
    return _DILITHIUM.keygen()


def _mldsa_sign(sk: bytes, msg: bytes) -> bytes:
    if _HAVE_OQS:
        with _oqs.Signature(PQC_ALG, secret_key=sk) as s:
            return s.sign(msg)
    return _DILITHIUM.sign(sk, msg)


def _mldsa_verify(pk: bytes, msg: bytes, sig: bytes) -> bool:
    if _HAVE_OQS:
        with _oqs.Signature(PQC_ALG) as s:
            return s.verify(msg, sig, pk)
    return _DILITHIUM.verify(pk, msg, sig)


class TokenError(Exception):
    """Any verification failure (bad signature, expired, wrong aud/iss, malformed)."""


class UnknownKid(TokenError):
    """Token's kid is not present in the provided JWKS — caller may refresh JWKS."""


# ── base64url helpers ────────────────────────────────────────────────────────

def _b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


# ── key material ─────────────────────────────────────────────────────────────

def generate_keypair() -> dict:
    """Fresh hybrid signing keypair as serializable strings (for env/persistence)."""
    ed = ed25519.Ed25519PrivateKey.generate()
    ed_priv_pem = ed.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    pk, sk = _mldsa_keygen()
    return {
        "ed_private_pem": ed_priv_pem,
        "mldsa_secret_b64": _b64e(sk),
        "mldsa_public_b64": _b64e(pk),
    }


def thumbprint(ed_pub_raw: bytes, mldsa_pk: bytes) -> str:
    return "6igma-" + _b64e(hashlib.sha256(ed_pub_raw + mldsa_pk).digest())[:16]


# ── signer ───────────────────────────────────────────────────────────────────

class Signer:
    def __init__(self, ed_private_pem: str, mldsa_secret_b64: str, mldsa_public_b64: str):
        self._ed = serialization.load_pem_private_key(ed_private_pem.encode(), password=None)
        self._ed_pub_raw = self._ed.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        self._mldsa_sk = _b64d(mldsa_secret_b64)
        self._mldsa_pk = _b64d(mldsa_public_b64)
        self.kid = thumbprint(self._ed_pub_raw, self._mldsa_pk)

    def sign(self, payload: dict) -> str:
        header = {"alg": ALG, "typ": TYP, "kid": self.kid}
        b64h = _b64e(json.dumps(header, separators=(",", ":"), sort_keys=True).encode())
        b64p = _b64e(json.dumps(payload, separators=(",", ":")).encode())
        signing_input = (b64h + "." + b64p).encode("ascii")
        ed_sig = self._ed.sign(signing_input)
        mldsa_sig = _mldsa_sign(self._mldsa_sk, signing_input)
        blob = len(ed_sig).to_bytes(2, "big") + ed_sig + mldsa_sig
        return b64h + "." + b64p + "." + _b64e(blob)

    def jwks(self) -> dict:
        return build_jwks(self._ed_pub_raw, self._mldsa_pk, self.kid)


def build_jwks(ed_pub_raw: bytes, mldsa_pk: bytes, kid: str) -> dict:
    return {"keys": [
        {"kty": "OKP", "crv": "Ed25519", "use": "sig", "alg": "EdDSA",
         "kid": kid, "x": _b64e(ed_pub_raw)},
        {"kty": "AKP", "use": "sig", "alg": PQC_ALG,
         "kid": kid, "pub": _b64e(mldsa_pk)},
    ]}


# ── verifier ─────────────────────────────────────────────────────────────────

def unverified_header(token: str) -> dict:
    try:
        return json.loads(_b64d(token.split(".", 1)[0]))
    except Exception as e:
        raise TokenError(f"malformed token header: {e}")


def verify_with_jwks(token: str, jwks: dict, *, audience: str | None = None,
                     issuer: str | None = None, verify_aud: bool = True,
                     leeway: int = 60) -> dict:
    """Verify a hybrid token against a JWKS. Raises TokenError/UnknownKid on failure."""
    try:
        b64h, b64p, b64s = token.split(".")
    except ValueError:
        raise TokenError("token must have 3 segments")
    header = unverified_header(token)
    if header.get("alg") != ALG:
        raise TokenError(f"unexpected alg {header.get('alg')!r}")
    kid = header.get("kid")
    keys = (jwks or {}).get("keys", [])
    okp = next((k for k in keys if k.get("kid") == kid and k.get("kty") == "OKP"), None)
    akp = next((k for k in keys if k.get("kid") == kid and k.get("kty") == "AKP"), None)
    if not okp or not akp:
        raise UnknownKid(f"kid {kid!r} not found in JWKS")

    signing_input = (b64h + "." + b64p).encode("ascii")
    blob = _b64d(b64s)
    if len(blob) < 2:
        raise TokenError("bad signature blob")
    ed_len = int.from_bytes(blob[:2], "big")
    ed_sig, mldsa_sig = blob[2:2 + ed_len], blob[2 + ed_len:]

    # Hybrid: BOTH signatures must verify.
    try:
        ed25519.Ed25519PublicKey.from_public_bytes(_b64d(okp["x"])).verify(ed_sig, signing_input)
    except InvalidSignature:
        raise TokenError("Ed25519 signature invalid")
    if not _mldsa_verify(_b64d(akp["pub"]), signing_input, mldsa_sig):
        raise TokenError("ML-DSA signature invalid")

    try:
        claims = json.loads(_b64d(b64p))
    except Exception as e:
        raise TokenError(f"malformed payload: {e}")
    _check_claims(claims, audience, issuer, verify_aud, leeway)
    return claims


def _check_claims(claims: dict, audience, issuer, verify_aud: bool, leeway: int) -> None:
    now = int(time.time())
    exp = claims.get("exp")
    if exp is not None and now > int(exp) + leeway:
        raise TokenError("token expired")
    nbf = claims.get("nbf")
    if nbf is not None and now + leeway < int(nbf):
        raise TokenError("token not yet valid")
    if issuer is not None and claims.get("iss") != issuer:
        raise TokenError("issuer mismatch")
    if verify_aud and audience is not None:
        aud = claims.get("aud")
        aud_list = aud if isinstance(aud, list) else [aud]
        if audience not in aud_list:
            raise TokenError("audience mismatch")
