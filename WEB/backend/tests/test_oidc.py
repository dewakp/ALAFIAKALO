"""Verifying a provider's own ID token, with Firebase out of the path.

These sign real RS256 tokens with a throwaway key and let the real `jwt.decode`
run, so signature and claim checking are genuinely exercised — only the JWKS
fetch is stubbed. A test that mocks the verification proves nothing about the
thing whose entire job is verification.

The case that matters most is the AUDIENCE. The same person signing into the
same account presents a different `aud` on web than on iOS, so pinning one
client id works on one platform and silently locks out the others.
"""

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core.config import settings
from app.services import oidc

WEB_ID = "214891981468-web.apps.googleusercontent.com"
IOS_ID = "214891981468-ios.apps.googleusercontent.com"
APPLE_SERVICES_ID = "com.alafia.app.web"
APPLE_BUNDLE_ID = "com.alafia.app"


@pytest.fixture(scope="module")
def keypair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key, key.public_key()


@pytest.fixture(autouse=True)
def stub_jwks(monkeypatch, keypair):
    """Serve the public key instead of fetching the provider's JWKS."""
    _, public = keypair

    class _Stub:
        def get_signing_key_from_jwt(self, _token):
            return type("K", (), {"key": public})()

    monkeypatch.setattr(oidc, "_client", lambda _provider: _Stub())
    oidc._jwk_clients.clear()


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    # Deliberately NOT `raising=False`. Pydantic refuses to set a field it never
    # declared, so these settings must genuinely exist — and suppressing that
    # would let a renamed setting pass here while the endpoint it configures
    # quietly authenticates nobody.
    monkeypatch.setattr(settings, "GOOGLE_OAUTH_CLIENT_IDS",
                        f"{WEB_ID},{IOS_ID}")
    monkeypatch.setattr(settings, "APPLE_CLIENT_IDS",
                        f"{APPLE_SERVICES_ID},{APPLE_BUNDLE_ID}")


def _token(keypair, *, iss, aud, sub="provider-subject-1", exp_delta=600, **extra):
    private, _ = keypair
    now = int(time.time())
    claims = {"iss": iss, "aud": aud, "sub": sub,
              "iat": now, "exp": now + exp_delta, **extra}
    return jwt.encode(claims, private, algorithm="RS256")


GOOGLE_ISS = "https://accounts.google.com"
APPLE_ISS = "https://appleid.apple.com"


# ── The audience is a set ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_web_token_is_accepted(keypair):
    t = _token(keypair, iss=GOOGLE_ISS, aud=WEB_ID,
               email="user@example.com", email_verified=True, name="Ada")

    ident = await oidc.verify_id_token(oidc.GOOGLE, t)

    assert ident.provider == "google"
    assert ident.subject == "provider-subject-1"
    assert ident.email == "user@example.com"
    assert ident.email_verified is True
    assert ident.name == "Ada"


@pytest.mark.asyncio
async def test_a_native_token_with_a_different_client_id_is_also_accepted(keypair):
    """The bug this guards: pinning one client id locks out the other platforms."""
    t = _token(keypair, iss=GOOGLE_ISS, aud=IOS_ID, email="user@example.com",
               email_verified=True)

    ident = await oidc.verify_id_token(oidc.GOOGLE, t)

    assert ident.subject == "provider-subject-1"


@pytest.mark.asyncio
async def test_an_unlisted_audience_is_refused(keypair):
    t = _token(keypair, iss=GOOGLE_ISS, aud="someone-elses-app.apps.googleusercontent.com")

    with pytest.raises(oidc.OIDCError) as e:
        await oidc.verify_id_token(oidc.GOOGLE, t)
    assert "different application" in str(e.value)


# ── Refusals ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_an_expired_token_is_refused(keypair):
    t = _token(keypair, iss=GOOGLE_ISS, aud=WEB_ID, exp_delta=-60)

    with pytest.raises(oidc.OIDCError) as e:
        await oidc.verify_id_token(oidc.GOOGLE, t)
    assert "expired" in str(e.value).lower()


@pytest.mark.asyncio
async def test_a_token_from_the_wrong_issuer_is_refused(keypair):
    """An Apple-issued token must not authenticate a Google sign-in."""
    t = _token(keypair, iss=APPLE_ISS, aud=WEB_ID)

    with pytest.raises(oidc.OIDCError):
        await oidc.verify_id_token(oidc.GOOGLE, t)


@pytest.mark.asyncio
async def test_a_token_with_no_subject_is_refused(keypair):
    private, _ = keypair
    now = int(time.time())
    t = jwt.encode({"iss": GOOGLE_ISS, "aud": WEB_ID, "iat": now, "exp": now + 600},
                   private, algorithm="RS256")

    with pytest.raises(oidc.OIDCError):
        await oidc.verify_id_token(oidc.GOOGLE, t)


@pytest.mark.asyncio
async def test_an_unconfigured_provider_authenticates_nobody(keypair, monkeypatch):
    """With no client ids to check against, every token would otherwise pass."""
    monkeypatch.setattr(settings, "GOOGLE_OAUTH_CLIENT_IDS", "")
    t = _token(keypair, iss=GOOGLE_ISS, aud=WEB_ID)

    with pytest.raises(oidc.OIDCError) as e:
        await oidc.verify_id_token(oidc.GOOGLE, t)
    assert "not configured" in str(e.value)


@pytest.mark.asyncio
async def test_an_unknown_provider_is_refused(keypair):
    with pytest.raises(oidc.OIDCError):
        await oidc.verify_id_token("facebook", "whatever")


# ── email_verified, where the two providers disagree on type ────────────

@pytest.mark.asyncio
async def test_apples_string_true_counts_as_verified(keypair):
    """Apple sends "true" as a STRING. Read naively it is truthy either way —
    but so is the string "false", which would let an UNVERIFIED address link to
    an existing account by email."""
    t = _token(keypair, iss=APPLE_ISS, aud=APPLE_SERVICES_ID,
               email="user@privaterelay.appleid.com", email_verified="true")

    ident = await oidc.verify_id_token(oidc.APPLE, t)

    assert ident.email_verified is True


@pytest.mark.asyncio
async def test_the_string_false_is_NOT_verified(keypair):
    t = _token(keypair, iss=APPLE_ISS, aud=APPLE_BUNDLE_ID,
               email="user@example.com", email_verified="false")

    ident = await oidc.verify_id_token(oidc.APPLE, t)

    assert ident.email_verified is False


@pytest.mark.asyncio
async def test_an_absent_email_verified_is_not_verified(keypair):
    t = _token(keypair, iss=GOOGLE_ISS, aud=WEB_ID, email="user@example.com")

    ident = await oidc.verify_id_token(oidc.GOOGLE, t)

    assert ident.email_verified is False


# ── An outage is not a bad credential ───────────────────────────────────

@pytest.mark.asyncio
async def test_a_jwks_outage_is_reported_as_an_outage(keypair, monkeypatch):
    """§3ae: unreachable upstream and invalid input are different events.
    Telling someone their sign-in was wrong when our fetch failed sends them to
    reset a password that was never the problem."""
    def _boom(_provider):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(oidc, "_client", _boom)
    t = _token(keypair, iss=GOOGLE_ISS, aud=WEB_ID)

    with pytest.raises(oidc.OIDCError) as e:
        await oidc.verify_id_token(oidc.GOOGLE, t)
    assert "could not reach" in str(e.value).lower()
