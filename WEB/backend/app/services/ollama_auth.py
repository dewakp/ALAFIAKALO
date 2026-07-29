"""Auth for a private (IAM-protected) Ollama Cloud Run service.

Production runs Ollama as its own GPU Cloud Run service with
``--no-allow-unauthenticated`` (so a GPU LLM isn't open to the internet). Callers
must attach a Google OIDC **ID token** whose audience is the Ollama service URL.
We fetch it from the instance metadata server and cache it until shortly before
expiry.

When ``OLLAMA_BASE_URL`` is *not* a Cloud Run URL (local dev: host.docker.internal
or localhost), no auth is needed and this returns ``{}`` — so the same code path
works locally and in prod. **Only attach these headers to Ollama requests** — the
token is scoped to the Ollama audience and must not leak to other hosts.
"""

import base64
import json
import time

import httpx

from app.core.config import settings

_METADATA_IDENTITY = (
    "http://metadata.google.internal/computeMetadata/v1/instance/"
    "service-accounts/default/identity"
)
_cache: dict = {"token": None, "exp": 0.0, "aud": None}


def _needs_auth() -> bool:
    return ".run.app" in (settings.OLLAMA_BASE_URL or "")


def _jwt_exp(token: str) -> float:
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return float(json.loads(base64.urlsafe_b64decode(payload)).get("exp", 0))
    except Exception:
        return time.time() + 3000  # assume ~50 min if unparriable


async def ollama_auth_headers() -> dict:
    """Authorization header for the private Ollama service, or {} for local dev."""
    if not _needs_auth():
        return {}
    aud = settings.OLLAMA_BASE_URL.rstrip("/")
    now = time.time()
    if _cache["token"] and _cache["aud"] == aud and _cache["exp"] - now > 60:
        return {"Authorization": f"Bearer {_cache['token']}"}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                _METADATA_IDENTITY,
                params={"audience": aud, "format": "full"},
                headers={"Metadata-Flavor": "Google"},
            )
        r.raise_for_status()
        token = r.text.strip()
        _cache.update(token=token, exp=_jwt_exp(token), aud=aud)
        return {"Authorization": f"Bearer {token}"}
    except Exception:
        # Metadata unavailable (e.g. local run without env) — let the caller try
        # unauthenticated; it will fail loudly if the endpoint truly requires auth.
        return {}
