"""Cash App Pay, ACH and friends settle AFTER the checkout session completes.

Stripe's asynchronous payment methods finish the session first and move the
money later: `status: "complete"` with `payment_status: "unpaid"`, then
`checkout.session.async_payment_succeeded` (or `_failed`) minutes later.

Two things were wrong, and together they made such a payment impossible:

  1. `stripe_confirm` answered **402 "Checkout not completed"** for anything that
     was not already `paid` — so a user whose Cash App payment was on its way was
     told their checkout had failed, at the moment they were redirected back.
  2. the webhook handled only `checkout.session.completed`, so when the money
     DID land, nothing activated the subscription. It would have sat at
     "incomplete" forever with the payment taken.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.subscription import Subscription, SubscriptionStatus, PLAN_PLUS_MONTHLY
from app.models.user import User
from app.services import subscription_service as svc


def _event(etype: str, obj: dict, event_id: str) -> dict:
    return {"id": event_id, "type": etype, "data": {"object": obj}}


async def _user(db, email: str) -> User:
    u = User(email=email, hashed_password="x", full_name="Cash App User")
    db.add(u)
    await db.flush()
    return u


@pytest.mark.asyncio
async def test_a_settled_async_payment_activates_the_subscription(db):
    """The settlement event that nothing was listening for."""
    user = await _user(db, "cashapp@example.com")
    now = datetime.now(timezone.utc)

    await svc.stripe_handle_webhook(db, _event("checkout.session.async_payment_succeeded", {
        "id": "cs_async", "customer": "cus_CASH", "subscription": None,
        "client_reference_id": str(user.id), "payment_status": "paid",
        "metadata": {"alafia_user_id": str(user.id)},
    }, "evt_async_ok"))

    sub = await svc.get_subscription(db, user.id)
    assert sub is not None, "settlement must reach the account"
    assert sub.stripe_customer_id == "cus_CASH"


@pytest.mark.asyncio
async def test_a_failed_async_payment_is_recorded_and_grants_nothing(db, monkeypatch):
    sent: list[dict] = []

    async def _capture(to, **kwargs):
        sent.append({"to": to, **kwargs})
        return True

    monkeypatch.setattr(svc.email_service, "send_payment_failed_email", _capture)

    user = await _user(db, "cashfail@example.com")
    await svc.stripe_handle_webhook(db, _event("checkout.session.async_payment_failed", {
        "id": "cs_async_bad", "customer": "cus_CASHBAD",
        "client_reference_id": str(user.id),
        "metadata": {"alafia_user_id": str(user.id)},
    }, "evt_async_fail"))

    sub = await svc.get_subscription(db, user.id)
    assert sub.status == SubscriptionStatus.INCOMPLETE.value
    assert svc.is_entitled(sub) is False, "a failed async payment must not grant access"
    assert sent, "the user must be told, as with a declined card"
    assert sent[0]["first_payment"] is True


@pytest.mark.asyncio
async def test_a_pending_async_payment_is_not_a_failed_checkout(db, monkeypatch):
    """The 402 that told a paying user their checkout had failed."""
    from app.core.config import settings

    user = await _user(db, "pending@example.com")
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_live_fake")
    monkeypatch.setattr(settings, "DEBUG", False)

    async def _fake_stripe(method, path, data=None):
        assert path.startswith("/v1/checkout/sessions")
        return {
            "id": "cs_pending", "client_reference_id": str(user.id),
            "status": "complete",           # the session finished…
            "payment_status": "unpaid",     # …but the money has not landed yet
            "customer": "cus_PENDING", "subscription": "sub_PENDING",
        }

    monkeypatch.setattr(svc, "_stripe_request", _fake_stripe)

    sub = await svc.stripe_confirm(db, user, "cs_pending")

    # No exception: a pending payment is not a failure.
    assert sub.stripe_customer_id == "cus_PENDING"
    assert sub.stripe_subscription_id == "sub_PENDING"   # so settlement attributes
    assert sub.status == SubscriptionStatus.INCOMPLETE.value
    assert svc.is_entitled(sub) is False, "pending is not paid — no access yet"


@pytest.mark.asyncio
async def test_an_abandoned_checkout_is_still_refused(db, monkeypatch):
    """`status: open` means they never finished — that IS a failed checkout."""
    from fastapi import HTTPException
    from app.core.config import settings

    user = await _user(db, "abandoned@example.com")
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_live_fake")
    monkeypatch.setattr(settings, "DEBUG", False)

    async def _fake_stripe(method, path, data=None):
        return {"id": "cs_open", "client_reference_id": str(user.id),
                "status": "open", "payment_status": "unpaid"}

    monkeypatch.setattr(svc, "_stripe_request", _fake_stripe)

    with pytest.raises(HTTPException) as exc:
        await svc.stripe_confirm(db, user, "cs_open")
    assert exc.value.status_code == 402
