"""Client for the shared 6IGMA Identity service.

Verifies identity-issued **hybrid EdDSA + ML-DSA-65** JWTs via the service's JWKS so
ALAFIA accepts a token minted by the identity service (or a FlowSheet session) →
cross-app SSO. Verification is offline after the JWKS is cached.
"""

from __future__ import annotations

import time
import logging

import httpx

from app.core.config import settings
from app.services import pqc_jws

logger = logging.getLogger(__name__)

_jwks_cache: dict | None = None
_jwks_fetched_at: float = 0.0
_JWKS_TTL = 600  # seconds


async def _get_jwks() -> dict | None:
    global _jwks_cache, _jwks_fetched_at
    if _jwks_cache and (time.time() - _jwks_fetched_at) < _JWKS_TTL:
        return _jwks_cache
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{settings.IDENTITY_BASE_URL}/.well-known/jwks.json")
            resp.raise_for_status()
            _jwks_cache = resp.json()
            _jwks_fetched_at = time.time()
    except Exception as exc:
        logger.warning("identity JWKS fetch failed (%s)", exc)
        # keep any stale cache so a transient outage doesn't drop all SSO
    return _jwks_cache


async def verify_identity_token(token: str) -> dict | None:
    """Return claims if `token` is a valid identity-issued access token, else None.

    Returns None (not raising) so callers can fall back to legacy ALAFIA tokens.
    """
    if not settings.IDENTITY_ENABLED:
        return None
    try:
        header = pqc_jws.unverified_header(token)
    except pqc_jws.TokenError:
        return None
    if header.get("alg") != pqc_jws.ALG:
        return None  # not a hybrid identity token → let the legacy path handle it

    jwks = await _get_jwks()
    if not jwks:
        return None
    try:
        claims = pqc_jws.verify_with_jwks(
            token, jwks,
            audience=settings.IDENTITY_AUDIENCE, issuer=settings.IDENTITY_ISSUER,
        )
    except pqc_jws.UnknownKid:
        # key rotation → refresh JWKS once and retry
        global _jwks_fetched_at
        _jwks_fetched_at = 0.0
        jwks = await _get_jwks()
        try:
            claims = pqc_jws.verify_with_jwks(
                token, jwks or {},
                audience=settings.IDENTITY_AUDIENCE, issuer=settings.IDENTITY_ISSUER,
            )
        except pqc_jws.TokenError:
            return None
    except pqc_jws.TokenError:
        return None
    if claims.get("type") != "access":
        return None
    return claims


# ── Proxy helpers so ALAFIA's auth endpoints delegate to the shared IdP ───────

async def identity_login(identifier: str, password: str) -> dict | None:
    """POST /identity/login. Returns the token dict on success, else None."""
    if not settings.IDENTITY_ENABLED:
        return None
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(
                f"{settings.IDENTITY_BASE_URL}/identity/login",
                json={"identifier": identifier, "password": password},
            )
        if resp.status_code == 200:
            return resp.json()
    except Exception as exc:
        logger.warning("identity login proxy failed (%s)", exc)
    return None


async def identity_refresh(refresh_token: str) -> dict | None:
    """POST /identity/token/refresh. Returns a new token dict on success, else None."""
    if not settings.IDENTITY_ENABLED:
        return None
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(
                f"{settings.IDENTITY_BASE_URL}/identity/token/refresh",
                json={"refresh_token": refresh_token},
            )
        if resp.status_code == 200:
            return resp.json()
    except Exception as exc:
        logger.warning("identity refresh proxy failed (%s)", exc)
    return None


async def migrate_password_into_identity(identifier: str, password: str) -> bool:
    """Firebase→IdP bridge: after ALAFIA has verified a legacy Firebase password,
    set it as the user's IdP credential so the account becomes PostgreSQL-native.
    Returns True on success. Secret-guarded on the identity side.
    """
    if not settings.IDENTITY_ENABLED:
        return False
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(
                f"{settings.IDENTITY_BASE_URL}/identity/internal/migrate-password",
                json={"identifier": identifier, "new_password": password,
                      "secret": settings.IDENTITY_MIGRATION_SECRET},
            )
        if resp.status_code == 200:
            return True
        logger.warning("identity password migration failed (%s): %s", resp.status_code, resp.text[:200])
    except Exception as exc:
        logger.warning("identity password migration proxy failed (%s)", exc)
    return False


async def identity_register(payload: dict) -> tuple[int | None, dict | None]:
    """POST /identity/register. Returns (status_code, json|None)."""
    if not settings.IDENTITY_ENABLED:
        return None, None
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(
                f"{settings.IDENTITY_BASE_URL}/identity/register", json=payload
            )
        body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else None
        return resp.status_code, body
    except Exception as exc:
        logger.warning("identity register proxy failed (%s)", exc)
        return None, None
