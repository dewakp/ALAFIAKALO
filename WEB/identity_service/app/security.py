"""Auth primitives for the 6IGMA identity service.

- Passwords: **Argon2id** (memory-hard), with bcrypt verify-and-rehash so legacy
  `$2b$` hashes still log in and transparently upgrade. (Password hashing is
  already quantum-adequate — Grover gives only a quadratic speedup.)
- Access tokens: **hybrid EdDSA + ML-DSA-65** (see pqc_jws) — quantum-ready and
  verifiable cross-app via JWKS.
- Refresh/reset tokens: **HS512** — verified only by this issuer, so a symmetric
  (already PQ-safe) HMAC keeps them compact enough for cookies.
"""

import json
import logging
import os
import time
import uuid

import bcrypt
import jwt as pyjwt
from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.config import settings
from app import pqc_jws

log = logging.getLogger(__name__)
_DEV_DEFAULT_SECRETS = {"", "dev-hs-refresh-secret-change-me", "dev-migration-secret-change-me"}

# ── Passwords: Argon2id (+ legacy bcrypt verify/rehash) ──────────────────────

_ph = PasswordHasher()  # argon2id with sane defaults


def hash_password(pw: str) -> str:
    return _ph.hash(pw)


def verify_password(pw: str, hashed: str) -> bool:
    if not hashed:
        return False
    if hashed.startswith("$argon2"):
        try:
            return _ph.verify(hashed, pw)
        except Argon2Error:
            return False
    if hashed.startswith("$2"):  # legacy bcrypt
        try:
            return bcrypt.checkpw(pw.encode("utf-8")[:72], hashed.encode("utf-8"))
        except Exception:
            return False
    return False


def needs_rehash(hashed: str) -> bool:
    """True if the stored hash isn't Argon2id-at-current-params (→ upgrade on login)."""
    if not hashed or not hashed.startswith("$argon2"):
        return True
    try:
        return _ph.check_needs_rehash(hashed)
    except Exception:
        return False


# ── Hybrid PQC signing keys (KEYS_FILE → env → ephemeral; fail-closed in prod) ─

def _load_keys() -> tuple[str, str, str, str]:
    """Return (ed_private_pem, mldsa_secret_b64, mldsa_public_b64, hs_secret)."""
    # 1) Mounted keys file (the production path).
    if settings.KEYS_FILE and os.path.exists(settings.KEYS_FILE):
        with open(settings.KEYS_FILE) as fh:
            d = json.load(fh)
        log.info("identity: loaded persistent signing keys from %s", settings.KEYS_FILE)
        return (d["ed_private_pem"], d["mldsa_secret_b64"], d["mldsa_public_b64"],
                d.get("hs_secret") or settings.HS_SECRET)
    # 2) Individual env vars.
    if settings.JWT_ED_PRIVATE_KEY and settings.MLDSA_SECRET_KEY and settings.MLDSA_PUBLIC_KEY:
        log.info("identity: loaded persistent signing keys from environment")
        return (settings.JWT_ED_PRIVATE_KEY, settings.MLDSA_SECRET_KEY,
                settings.MLDSA_PUBLIC_KEY, settings.HS_SECRET)
    # 3) None configured.
    if settings.ENV == "production":
        raise RuntimeError(
            "No persistent signing keys configured (set IDENTITY_KEYS_FILE or "
            "IDENTITY_JWT_ED_PRIVATE_KEY/IDENTITY_MLDSA_SECRET_KEY/IDENTITY_MLDSA_PUBLIC_KEY). "
            "Refusing to start in production with ephemeral keys."
        )
    log.warning("identity: NO persistent keys — generating an EPHEMERAL dev keypair "
                "(tokens won't survive restart and multi-replica SSO will break).")
    kp = pqc_jws.generate_keypair()
    return kp["ed_private_pem"], kp["mldsa_secret_b64"], kp["mldsa_public_b64"], settings.HS_SECRET


def _enforce_prod_secret_hygiene(hs_secret: str) -> None:
    if settings.ENV != "production":
        return
    if hs_secret in _DEV_DEFAULT_SECRETS:
        raise RuntimeError("IDENTITY_HS_SECRET is unset/dev-default in production.")
    if settings.MIGRATION_SECRET in _DEV_DEFAULT_SECRETS:
        raise RuntimeError("IDENTITY_MIGRATION_SECRET is unset/dev-default in production.")


_ed_pem, _mldsa_sk_b64, _mldsa_pk_b64, _HS_SECRET = _load_keys()
_enforce_prod_secret_hygiene(_HS_SECRET)
_signer = pqc_jws.Signer(_ed_pem, _mldsa_sk_b64, _mldsa_pk_b64)
log.info("identity: ML-DSA backend = %s | signing kid = %s", pqc_jws.mldsa_backend(), _signer.kid)


def jwks() -> dict:
    return _signer.jwks()


# ── Token mint / verify ──────────────────────────────────────────────────────

def _mint_access(claims: dict, ttl_seconds: int) -> str:
    now = int(time.time())
    return _signer.sign({
        **claims,
        "iss": settings.ISSUER, "aud": settings.AUDIENCES,
        "iat": now, "exp": now + ttl_seconds, "jti": str(uuid.uuid4()), "type": "access",
    })


def _mint_hs(claims: dict, ttl_seconds: int, token_type: str) -> str:
    now = int(time.time())
    return pyjwt.encode({
        **claims,
        "iss": settings.ISSUER, "iat": now, "exp": now + ttl_seconds,
        "jti": str(uuid.uuid4()), "type": token_type,
    }, _HS_SECRET, algorithm="HS512")


def make_tokens(user) -> dict:
    base = {
        "sub": str(user.id),
        "sid": (user.system_id or "").strip() or None,
        "email": user.email,
        "username": user.username,
        "role": user.account_role,
        "tier": user.tier,
    }
    return {
        "access_token": _mint_access(base, settings.ACCESS_TTL_MIN * 60),
        "refresh_token": _mint_hs({"sub": base["sub"]}, settings.REFRESH_TTL_DAYS * 86400, "refresh"),
        "token_type": "bearer",
    }


def make_reset_token(user_id: str, ttl_min: int = 30) -> str:
    return _mint_hs({"sub": str(user_id)}, ttl_min * 60, "password_reset")


def decode_access(token: str) -> dict:
    """Verify one of OUR hybrid access tokens (aud enforced by consuming apps)."""
    return pqc_jws.verify_with_jwks(token, _signer.jwks(), verify_aud=False)


def decode_hs(token: str) -> dict:
    """Verify a refresh/reset token (HS512). Raises pyjwt.PyJWTError on failure."""
    return pyjwt.decode(token, _HS_SECRET, algorithms=["HS512"],
                        options={"verify_aud": False})


_bearer = HTTPBearer(auto_error=True)


async def current_claims(cred: HTTPAuthorizationCredentials = Depends(_bearer)) -> dict:
    try:
        claims = decode_access(cred.credentials)
    except pqc_jws.TokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    if claims.get("type") != "access":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not an access token")
    return claims
