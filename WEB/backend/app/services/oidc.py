"""Verifying a Google or Apple ID token directly — no Firebase in the path.

Social sign-in used to be brokered by Firebase: the browser completed the
provider flow with the Firebase JS SDK and posted the resulting Firebase token
to `/auth/firebase`, which verified it with the Admin SDK. That arrangement was
never working in production — Apple was never configured as a provider at all,
and the Admin credential was never mounted, so every exchange answered 503 — and
it sat against canon, which says authentication is PostgreSQL-only and that
provider strategy is a backend concern.

So the provider's OWN token is verified here instead. The browser (or the phone)
completes the flow with Google or Apple directly and posts the resulting
`id_token`; we check its signature against the provider's published JWKS and its
claims against what we expect. That removes a client SDK, a second identity
store, and an entire class of failure (popup domains, reCAPTCHA, an Admin
credential nobody mounted).

**The audience is a SET, not a value — this is the part that is easy to get
wrong.** The same human signing into the same account presents a token with a
different `aud` depending on where they are:

    web  (Google Identity Services)  aud = the WEB OAuth client id
    iOS  (native Google Sign-In)     aud = the iOS OAuth client id
    web  (Sign in with Apple JS)     aud = the Apple SERVICES id
    iOS  (native Sign in with Apple) aud = the app's BUNDLE id

Pinning a single client id therefore works on one platform and rejects the other
two, which is exactly the shape of bug §3 exists to prevent. Each provider
accepts a configured LIST.

**Fail closed.** Unlike the RxNorm guard (§3aj), which fails open because a
third-party outage must not block a clinical record, an unverifiable identity
token must never be accepted: it is the credential itself.
"""

import asyncio
import logging
from dataclasses import dataclass

import jwt

from app.core.config import settings

logger = logging.getLogger(__name__)

GOOGLE = "google"
APPLE = "apple"

#: Google publishes two spellings of its issuer and honours both.
_ISSUERS = {
    GOOGLE: ("https://accounts.google.com", "accounts.google.com"),
    APPLE: ("https://appleid.apple.com",),
}

_JWKS_URI = {
    GOOGLE: "https://www.googleapis.com/oauth2/v3/certs",
    APPLE: "https://appleid.apple.com/auth/keys",
}

#: Both providers sign with RS256 today. Listing algorithms explicitly is not
#: pedantry: accepting whatever the token's own header asks for is how a token
#: signed with "none" — or with the public key as an HMAC secret — gets in.
_ALGORITHMS = ["RS256", "ES256"]

#: PyJWKClient caches keys and refetches on an unknown `kid`, so providers can
#: rotate without a deploy. One client per provider, built lazily.
_jwk_clients: dict[str, jwt.PyJWKClient] = {}


class OIDCError(Exception):
    """The token could not be trusted. The message is safe to show a user."""


@dataclass(frozen=True)
class OIDCIdentity:
    provider: str
    subject: str          # the provider's stable user id (`sub`)
    email: str | None
    email_verified: bool
    name: str | None


def _audiences(provider: str) -> list[str]:
    """Every client id we accept a token for, across web and native."""
    raw = (settings.GOOGLE_OAUTH_CLIENT_IDS if provider == GOOGLE
           else settings.APPLE_CLIENT_IDS) or ""
    return [a.strip() for a in raw.split(",") if a.strip()]


def _client(provider: str) -> jwt.PyJWKClient:
    if provider not in _jwk_clients:
        _jwk_clients[provider] = jwt.PyJWKClient(_JWKS_URI[provider], cache_keys=True)
    return _jwk_clients[provider]


def _verify_sync(provider: str, token: str, audiences: list[str]) -> dict:
    signing_key = _client(provider).get_signing_key_from_jwt(token)
    return jwt.decode(
        token,
        signing_key.key,
        algorithms=_ALGORITHMS,
        audience=audiences,
        issuer=list(_ISSUERS[provider]),
        options={"require": ["exp", "iat", "sub"]},
    )


async def verify_id_token(provider: str, token: str) -> OIDCIdentity:
    """Verify an ID token and return who it says they are.

    Raises OIDCError for anything that cannot be trusted, with a sentence the
    caller may show. Never returns a partially-verified identity.
    """
    if provider not in _ISSUERS:
        raise OIDCError(f"Unsupported sign-in provider: {provider}")
    if not token:
        raise OIDCError("No sign-in token was supplied.")

    audiences = _audiences(provider)
    if not audiences:
        # Configured with nothing to check against, every token would be
        # accepted. Refuse loudly rather than authenticate anyone (§3ae: never
        # gate on a provider-specific key, but DO refuse when the thing you
        # verify against is missing).
        logger.error("%s sign-in attempted but no client ids are configured", provider)
        raise OIDCError("This sign-in method is not configured on this server.")

    try:
        # PyJWKClient does blocking HTTP on a cache miss; keep it off the loop.
        claims = await asyncio.to_thread(_verify_sync, provider, token, audiences)
    except jwt.ExpiredSignatureError:
        raise OIDCError("That sign-in has expired. Please try again.") from None
    except jwt.InvalidAudienceError:
        # Names the actual cause: a platform whose client id we never listed.
        logger.warning("%s token rejected: audience not in %s", provider, audiences)
        raise OIDCError("That sign-in was issued for a different application.") from None
    except jwt.InvalidTokenError as exc:
        logger.warning("%s token rejected: %s", provider, type(exc).__name__)
        raise OIDCError("That sign-in could not be verified. Please try again.") from None
    except Exception as exc:
        # A JWKS fetch failure lands here. It is an outage, not a bad token, and
        # must not be reported as "invalid credentials".
        logger.exception("%s JWKS verification failed", provider)
        raise OIDCError(
            "Could not reach the sign-in provider. Please try again shortly."
        ) from exc

    subject = claims.get("sub")
    if not subject:
        raise OIDCError("That sign-in carried no account identifier.")

    email = claims.get("email")
    # Google sends a real boolean; Apple sends the string "true". Treating the
    # string as truthy-by-accident would let an UNVERIFIED address link to an
    # existing account by email, which is account takeover.
    raw_verified = claims.get("email_verified")
    email_verified = raw_verified is True or str(raw_verified).lower() == "true"

    return OIDCIdentity(
        provider=provider,
        subject=str(subject),
        email=email.lower() if isinstance(email, str) else None,
        email_verified=email_verified,
        name=claims.get("name") or None,
    )
