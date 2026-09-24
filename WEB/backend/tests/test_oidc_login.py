"""Signing in with Google or Apple, verified directly against the provider.

`services/oidc.py` is tested separately for token verification; this file is
about what happens AFTER a token is trusted — which account it resolves to, and
which cases must be refused.

The one that matters most is matching by email: doing it without checking
`email_verified` would let anyone who can mint a token naming someone else's
address walk straight into that account.
"""

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.core.security import hash_password
from app.models.user import User
from app.models.user_identity import UserIdentity
from app.services.oidc import OIDCError, OIDCIdentity
from app.services import auth_alerts

URL = "/api/v1/auth/oidc"


@pytest.fixture(autouse=True)
def quiet_alerts(monkeypatch):
    async def _noop(**_kw):
        return True

    monkeypatch.setattr(auth_alerts, "send_email", _noop)
    auth_alerts._recent.clear()


@pytest.fixture
def token_says(monkeypatch):
    """Make the verifier return a chosen identity, or raise."""
    def _set(identity=None, error=None):
        async def _verify(provider, token):
            if error:
                raise error
            return identity
        # Patched where auth.py LOOKED IT UP, not where it is defined: auth.py
        # imported the name, so patching the service module would miss it.
        monkeypatch.setattr("app.api.auth.verify_id_token", _verify)
    return _set


def _identity(**kw):
    base = dict(provider="google", subject="google-sub-1",
                email="social@example.com", email_verified=True, name="Ada Social")
    base.update(kw)
    return OIDCIdentity(**base)


async def _seed(db, *, email, active=True) -> User:
    user = User(email=email, hashed_password=hash_password("x" * 20),
                full_name="Seeded", is_active=active)
    db.add(user)
    await db.flush()
    await db.commit()
    return user


async def _post(client, provider="google", token="tok"):
    return await client.post(URL, json={"provider": provider, "id_token": token})


# ── Resolution order ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_stored_link_resolves_to_its_account(client, db, token_says):
    user = await _seed(db, email="linked@example.com")
    db.add(UserIdentity(user_id=user.id, provider="google", subject="google-sub-1"))
    await db.commit()

    # Apple sends `email` on the FIRST authorization only, so a later sign-in
    # may carry none at all — the stored subject has to be enough.
    token_says(_identity(email=None, email_verified=False))
    res = await _post(client)

    assert res.status_code == 200, res.text
    assert res.json()["access_token"]


@pytest.mark.asyncio
async def test_a_verified_email_links_an_existing_account(client, db, token_says):
    user = await _seed(db, email="social@example.com")

    token_says(_identity())
    assert (await _post(client)).status_code == 200

    # …and the link is stored, so next time step 1 answers.
    rows = (await db.execute(
        select(UserIdentity).where(UserIdentity.user_id == user.id)
    )).scalars().all()
    assert len(rows) == 1
    assert rows[0].provider == "google" and rows[0].subject == "google-sub-1"


@pytest.mark.asyncio
async def test_an_UNVERIFIED_email_does_not_take_over_an_account(client, db, token_says):
    """The account-takeover case. Without the `email_verified` check, a token
    naming someone else's address would sign the attacker into their account."""
    await _seed(db, email="victim@example.com")

    token_says(_identity(email="victim@example.com", email_verified=False,
                         subject="attacker-sub"))
    res = await _post(client)

    # It must NOT resolve to the victim. With signup allowed it is refused for
    # want of a verified address; either way it never reaches that account.
    assert res.status_code != 200, res.text
    linked = (await db.execute(select(UserIdentity))).scalars().all()
    assert linked == []


# ── Creation policy ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_an_unknown_verified_identity_creates_an_account(client, db, token_says):
    token_says(_identity(email="brand.new@example.com"))

    res = await _post(client)

    assert res.status_code == 200, res.text
    user = (await db.execute(
        select(User).where(User.email == "brand.new@example.com")
    )).scalar_one_or_none()
    assert user is not None
    assert user.auth_provider == "google"


@pytest.mark.asyncio
async def test_creation_can_be_turned_off(client, db, token_says, monkeypatch):
    """Link-only is one env var, not a code change."""
    monkeypatch.setattr(settings, "OIDC_ALLOW_SIGNUP", False)
    token_says(_identity(email="brand.new@example.com"))

    res = await _post(client)

    assert res.status_code == 403
    assert "sign up" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_no_verified_email_cannot_create_an_account(client, db, token_says):
    token_says(_identity(email=None, email_verified=False, subject="unknown-sub"))

    res = await _post(client)

    assert res.status_code == 400
    assert (await db.execute(select(User))).scalars().all() == []


# ── Refusals ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_rejected_token_is_401_with_the_verifier_s_reason(client, db, token_says):
    """§3ae: an expired token, an unconfigured provider and a JWKS outage are
    different events, and the verifier already words them differently."""
    token_says(error=OIDCError("That sign-in has expired. Please try again."))

    res = await _post(client)

    assert res.status_code == 401
    assert "expired" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_a_deactivated_account_is_not_revived_by_a_social_sign_in(client, db, token_says):
    user = await _seed(db, email="gone@example.com", active=False)
    db.add(UserIdentity(user_id=user.id, provider="google", subject="google-sub-1"))
    await db.commit()

    token_says(_identity(email="gone@example.com"))
    res = await _post(client)

    assert res.status_code == 403


@pytest.mark.asyncio
async def test_an_unknown_provider_never_reaches_the_database(client, db, monkeypatch):
    """The client names the provider, so the name is input, not fact."""
    res = await client.post(URL, json={"provider": "facebook", "id_token": "x"})

    assert res.status_code == 401
    assert (await db.execute(select(User))).scalars().all() == []
