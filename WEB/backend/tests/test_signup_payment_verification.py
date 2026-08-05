"""Payment verification for pre-account signup.

`/auth/signup/complete` creates the account, so whatever it trusts is the thing
that buys an account. It must not trust the caller's `reference_id`: without a
provider-side check, any string would mint a user — precisely the hole the
two-step flow exists to close.

These tests stub Stripe's HTTP layer so the real checks run offline. They cannot
run against live Stripe here (no key in this environment), so the checks
themselves are pinned instead.
"""

import pytest
from fastapi import HTTPException

from app.services import subscription_service as subs


@pytest.fixture(autouse=True)
def _live_stripe(monkeypatch):
    """Force the real (non-test-mode) path.

    With no key AND DEBUG, `_test_mode` short-circuits verification and accepts
    anything — fine for local dev, useless for testing the guard. A key is set
    so the code under test is the code that runs in production.
    """
    monkeypatch.setattr(subs.settings, "STRIPE_SECRET_KEY", "sk_test_dummy")
    monkeypatch.setattr(subs.settings, "DEBUG", False)


def _stub_session(monkeypatch, **overrides):
    session = {
        "id": "cs_real_123",
        "client_reference_id": "signup:buyer@example.org",
        "payment_status": "paid",
        "customer": "cus_1",
        "subscription": "sub_1",
    }
    session.update(overrides)

    async def fake_request(method, path, data=None):
        return session

    monkeypatch.setattr(subs, "_stripe_request", fake_request)
    return session


def test_reference_is_namespaced_and_normalised():
    assert subs.signup_client_reference("  Buyer@Example.ORG ") == "signup:buyer@example.org"


@pytest.mark.asyncio
async def test_paid_session_for_this_signup_is_accepted(monkeypatch):
    _stub_session(monkeypatch)
    result = await subs.signup_stripe_verify("buyer@example.org", "cs_real_123")
    assert result["paid"] is True
    assert result["subscription_id"] == "sub_1"


@pytest.mark.asyncio
async def test_session_belonging_to_someone_else_is_refused(monkeypatch):
    """A REAL, genuinely paid session must not be replayable by another signup.

    Otherwise one paid checkout could be used to create unlimited accounts.
    """
    _stub_session(monkeypatch, client_reference_id="signup:someone.else@example.org")
    with pytest.raises(HTTPException) as exc:
        await subs.signup_stripe_verify("buyer@example.org", "cs_real_123")
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_session_with_no_reference_is_refused(monkeypatch):
    """A forged/unknown id resolves to a session without our namespace."""
    _stub_session(monkeypatch, client_reference_id=None)
    with pytest.raises(HTTPException) as exc:
        await subs.signup_stripe_verify("buyer@example.org", "cs_totally_made_up")
    assert exc.value.status_code == 403


@pytest.mark.parametrize("payment_status", ["unpaid", "no_payment", "", None])
@pytest.mark.asyncio
async def test_unpaid_session_is_refused(monkeypatch, payment_status):
    _stub_session(monkeypatch, payment_status=payment_status)
    with pytest.raises(HTTPException) as exc:
        await subs.signup_stripe_verify("buyer@example.org", "cs_real_123")
    assert exc.value.status_code == 402


@pytest.mark.asyncio
async def test_no_payment_required_is_accepted(monkeypatch):
    """100%-discount coupons legitimately settle as 'no_payment_required'."""
    _stub_session(monkeypatch, payment_status="no_payment_required")
    assert (await subs.signup_stripe_verify("buyer@example.org", "cs_real_123"))["paid"] is True


@pytest.mark.asyncio
async def test_email_case_does_not_break_the_match(monkeypatch):
    _stub_session(monkeypatch, client_reference_id="signup:buyer@example.org")
    assert await subs.signup_stripe_verify("BUYER@Example.ORG", "cs_real_123")


@pytest.mark.asyncio
async def test_unconfigured_stripe_refuses_outside_debug(monkeypatch):
    """No key and not DEBUG must 503, never fall through to accepting."""
    monkeypatch.setattr(subs.settings, "STRIPE_SECRET_KEY", "")
    monkeypatch.setattr(subs.settings, "DEBUG", False)
    with pytest.raises(HTTPException) as exc:
        await subs.signup_stripe_verify("buyer@example.org", "cs_x")
    assert exc.value.status_code == 503
