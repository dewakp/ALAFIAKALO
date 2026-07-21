"""Regression tests for subscription entitlement + event idempotency.

Focus: the test-mode web rails (Stripe/PayPal) share a constant reference id, so
``_record_event`` MUST be idempotent on the unique ``(provider, event_id)`` index —
otherwise the *second* user (or a double checkout-redirect) 500s on a UniqueViolation.
Runs against the SQLite test DB, so it also guards the fix's dialect-agnosticism.
"""

import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.models.user import User
from app.models.subscription import SubscriptionEvent
from app.services import subscription_service as svc


@pytest.fixture
def stripe_test_mode(monkeypatch):
    """Force the Stripe rail into synthetic test-mode (blank creds + DEBUG)."""
    monkeypatch.setattr(settings, "DEBUG", True)
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "")
    assert svc._test_mode(settings.STRIPE_SECRET_KEY) is True


async def _make_user(db, email: str) -> User:
    user = User(email=email, hashed_password="x", full_name="Test User")
    db.add(user)
    await db.flush()
    return user


@pytest.mark.asyncio
async def test_stripe_confirm_entitles_user(db, stripe_test_mode):
    user = await _make_user(db, "sub1@example.com")
    sub = await svc.stripe_confirm(db, user, "cs_test_dev")
    assert sub.provider == "stripe"
    assert svc.is_entitled(sub) is True
    assert sub.price_usd == settings.SUBSCRIPTION_PRICE_WEB_USD


@pytest.mark.asyncio
async def test_same_user_double_confirm_is_idempotent(db, stripe_test_mode):
    """A double checkout-redirect must not raise and must leave one event row."""
    user = await _make_user(db, "sub2@example.com")
    await svc.stripe_confirm(db, user, "cs_test_dev")
    sub = await svc.stripe_confirm(db, user, "cs_test_dev")  # would 500 pre-fix
    assert svc.is_entitled(sub) is True
    count = await db.scalar(
        select(func.count()).select_from(SubscriptionEvent).where(
            SubscriptionEvent.provider == "stripe",
            SubscriptionEvent.event_id == "cs_test_dev",
        )
    )
    assert count == 1


@pytest.mark.asyncio
async def test_second_user_shares_constant_ref_without_collision(db, stripe_test_mode):
    """The regression: user B confirming with the same constant test ref as user A
    must still be entitled (per-user row) and must not hit the unique constraint."""
    user_a = await _make_user(db, "a@example.com")
    user_b = await _make_user(db, "b@example.com")
    await svc.stripe_confirm(db, user_a, "cs_test_dev")
    sub_b = await svc.stripe_confirm(db, user_b, "cs_test_dev")  # 500 pre-fix
    assert svc.is_entitled(sub_b) is True
    # Both users have their own entitled subscription row.
    sub_a = await svc.get_subscription(db, user_a.id)
    assert svc.is_entitled(sub_a) is True
    assert sub_a.id != sub_b.id
