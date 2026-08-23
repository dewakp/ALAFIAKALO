"""Stripe webhook attribution, and what a DECLINED CARD is allowed to buy.

The production incident these pin: a user registered, opened the paywall, and
paid with a card that was declined. Stripe sent `customer.subscription.created`
and two `invoice.payment_failed`. Every one of them was recorded against
`user_id` NULL, because the only thing that ever wrote `stripe_customer_id` was
`checkout.session.completed` — which never fires when the first payment fails.
So there was no row to match, nothing on the account said a payment had been
attempted, and nothing linked that Stripe customer back to the user.

Two separate things are asserted here, and the second is the dangerous one:

  1. the events attribute to the right user (via the `alafia_user_id` we now
     stamp on the subscription at checkout-creation time), and
  2. attributing them does NOT let anyone in. `invoice.payment_failed` used to
     set PAST_DUE unconditionally, and PAST_DUE is an *entitling* status against
     a `current_period_end` Stripe fills in the moment a subscription is created
     — before a cent is collected. Fixing (1) without (2) would have turned a
     declined card into a free month.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models.subscription import (
    Subscription, SubscriptionEvent, SubscriptionStatus, PLAN_PLUS_MONTHLY,
)
from app.models.user import User
from app.schemas.subscription import CheckoutRequest
from app.services import subscription_service as svc


def _ts(dt: datetime) -> int:
    return int(dt.timestamp())


def _event(etype: str, obj: dict, event_id: str) -> dict:
    return {"id": event_id, "type": etype, "data": {"object": obj}}


def _subscription_object(user_id: int | None, *, status: str, customer: str = "cus_TEST",
                         sub_id: str = "sub_TEST", period_days: int = 30) -> dict:
    now = datetime.now(timezone.utc)
    obj = {
        "id": sub_id,
        "customer": customer,
        "status": status,
        "current_period_start": _ts(now),
        "current_period_end": _ts(now + timedelta(days=period_days)),
        "items": {"data": [{"price": {"id": settings.STRIPE_PRICE_ID or "price_monthly"}}]},
    }
    if user_id is not None:
        obj["metadata"] = {"alafia_user_id": str(user_id)}
    return obj


async def _make_user(db, email: str) -> User:
    user = User(email=email, hashed_password="x", full_name="Test User")
    db.add(user)
    await db.flush()
    return user


# ── 1. The incident, end to end ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_failed_first_payment_is_attributed_but_grants_nothing(db):
    user = await _make_user(db, "declined@example.com")

    # Stripe creates the subscription, then the first invoice is declined.
    await svc.stripe_handle_webhook(db, _event(
        "customer.subscription.created",
        _subscription_object(user.id, status="incomplete"), "evt_created"))
    await svc.stripe_handle_webhook(db, _event(
        "invoice.payment_failed",
        {"id": "in_1", "customer": "cus_TEST", "subscription": "sub_TEST"}, "evt_failed"))

    sub = await svc.get_subscription(db, user.id)
    assert sub is not None, "the failed attempt must leave a row on the account"
    assert sub.stripe_customer_id == "cus_TEST"   # reconcilable against Stripe
    assert sub.status == SubscriptionStatus.INCOMPLETE.value
    assert svc.is_entitled(sub) is False, "a declined card must not buy access"

    # And the audit rows now name the user instead of being NULL.
    rows = (await db.execute(
        select(SubscriptionEvent).where(SubscriptionEvent.provider == "stripe")
    )).scalars().all()
    assert {r.event_id for r in rows} == {"evt_created", "evt_failed"}
    assert all(r.user_id == user.id for r in rows)


@pytest.mark.asyncio
async def test_period_on_an_unpaid_subscription_does_not_entitle(db):
    """The trap: Stripe stamps a full period on an `incomplete` subscription."""
    user = await _make_user(db, "unpaid@example.com")
    await svc.stripe_handle_webhook(db, _event(
        "customer.subscription.created",
        _subscription_object(user.id, status="incomplete", period_days=365), "evt_year"))

    sub = await svc.get_subscription(db, user.id)
    assert sub.current_period_end is not None      # a year in the future…
    assert svc.is_entitled(sub) is False           # …and worth nothing


@pytest.mark.asyncio
async def test_renewal_failure_keeps_a_paying_member_in_grace(db):
    """The other half: PAST_DUE must still mean 'was paying, renewal failed'."""
    user = await _make_user(db, "renewal@example.com")
    db.add(Subscription(
        user_id=user.id, status=SubscriptionStatus.ACTIVE.value, provider="stripe",
        plan=PLAN_PLUS_MONTHLY, stripe_customer_id="cus_PAYING",
        current_period_end=datetime.now(timezone.utc) + timedelta(days=5),
    ))
    await db.flush()

    await svc.stripe_handle_webhook(db, _event(
        "invoice.payment_failed", {"id": "in_2", "customer": "cus_PAYING"}, "evt_renewal"))

    sub = await svc.get_subscription(db, user.id)
    assert sub.status == SubscriptionStatus.PAST_DUE.value
    assert svc.is_entitled(sub) is True, "access already paid for continues during grace"


@pytest.mark.asyncio
async def test_lapsed_member_is_not_relabelled_incomplete(db):
    """A failure after the period ended must not rewrite a paid history."""
    user = await _make_user(db, "lapsed@example.com")
    db.add(Subscription(
        user_id=user.id, status=SubscriptionStatus.ACTIVE.value, provider="stripe",
        plan=PLAN_PLUS_MONTHLY, stripe_customer_id="cus_LAPSED",
        current_period_end=datetime.now(timezone.utc) - timedelta(days=60),
    ))
    await db.flush()

    await svc.stripe_handle_webhook(db, _event(
        "invoice.payment_failed", {"id": "in_3", "customer": "cus_LAPSED"}, "evt_lapsed"))

    sub = await svc.get_subscription(db, user.id)
    assert sub.status == SubscriptionStatus.ACTIVE.value  # left alone, not "incomplete"
    assert svc.is_entitled(sub) is False


# ── 2. Attribution paths ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_invoice_attributes_via_the_2025_payload_shape(db):
    """`invoice.subscription` moved under `parent.subscription_details`."""
    user = await _make_user(db, "shape@example.com")
    db.add(Subscription(
        user_id=user.id, status=SubscriptionStatus.NONE.value, provider="none",
        plan=PLAN_PLUS_MONTHLY, stripe_subscription_id="sub_SHAPE",
    ))
    await db.flush()

    await svc.stripe_handle_webhook(db, _event("invoice.payment_failed", {
        "id": "in_4",
        "parent": {"subscription_details": {"subscription": "sub_SHAPE"}},
    }, "evt_shape"))

    row = (await db.execute(
        select(SubscriptionEvent).where(SubscriptionEvent.event_id == "evt_shape")
    )).scalar_one()
    assert row.user_id == user.id


@pytest.mark.asyncio
async def test_invoice_paid_is_attributed(db):
    """Stripe sends `invoice.paid` beside `invoice.payment_succeeded`."""
    user = await _make_user(db, "paid@example.com")
    db.add(Subscription(
        user_id=user.id, status=SubscriptionStatus.ACTIVE.value, provider="stripe",
        plan=PLAN_PLUS_MONTHLY, stripe_customer_id="cus_PAID",
        current_period_end=datetime.now(timezone.utc) + timedelta(days=20),
    ))
    await db.flush()

    await svc.stripe_handle_webhook(db, _event(
        "invoice.paid", {"id": "in_5", "customer": "cus_PAID"}, "evt_paid"))

    row = (await db.execute(
        select(SubscriptionEvent).where(SubscriptionEvent.event_id == "evt_paid")
    )).scalar_one()
    assert row.user_id == user.id


@pytest.mark.asyncio
async def test_unattributable_event_still_records_the_ids(db):
    """Genuinely unknown events stay unattributed — but stop being a dead end."""
    await svc.stripe_handle_webhook(db, _event(
        "customer.subscription.created",
        _subscription_object(None, status="active", customer="cus_STRANGER",
                             sub_id="sub_STRANGER"), "evt_stranger"))

    row = (await db.execute(
        select(SubscriptionEvent).where(SubscriptionEvent.event_id == "evt_stranger")
    )).scalar_one()
    assert row.user_id is None
    assert "cus_STRANGER" in (row.payload or ""), "payload must carry the ids to reconcile"


@pytest.mark.asyncio
async def test_metadata_naming_a_missing_user_is_ignored(db):
    """A stale user id must not raise a foreign-key error mid-webhook."""
    await svc.stripe_handle_webhook(db, _event(
        "customer.subscription.created",
        _subscription_object(999_999, status="incomplete", customer="cus_GHOST"),
        "evt_ghost"))

    row = (await db.execute(
        select(SubscriptionEvent).where(SubscriptionEvent.event_id == "evt_ghost")
    )).scalar_one()
    assert row.user_id is None


# ── 3. A refused webhook names itself ──────────────────────────────────────

def test_rejected_webhook_is_describable():
    """21 of 31 production deliveries were refused here and logged nothing."""
    body = (b'{"id":"evt_x","type":"invoice.paid","livemode":false,'
            b'"account":"acct_1","api_version":"2025-01-01"}')
    info = svc.stripe_describe_rejected(body, "t=1700000000,v1=deadbeef")

    assert info["parsed"] is True
    assert info["event_id"] == "evt_x"
    assert info["livemode"] is False        # names a test-mode sender outright
    assert info["account"] == "acct_1"
    assert info["schemes"] == ["t", "v1"]
    assert "age_seconds" in info            # separates a bad secret from a replay


def test_rejected_webhook_description_survives_garbage():
    info = svc.stripe_describe_rejected(b"\xff\xfe not json", "")
    assert info["parsed"] is False
    assert info["header_present"] is False


# ── 4. PayPal is no longer offered ─────────────────────────────────────────

def test_checkout_refuses_the_withdrawn_paypal_rail():
    """Refused at the boundary as a 422, not a 503 from inside the service."""
    with pytest.raises(Exception):
        CheckoutRequest(provider="paypal")
    assert CheckoutRequest(provider="stripe").provider == "stripe"


@pytest.mark.asyncio
async def test_plans_does_not_advertise_paypal(client):
    resp = await client.get("/api/v1/subscription/plans")
    assert resp.status_code == 200
    data = resp.json()
    providers = {r["provider"] for r in data["rails"]}
    for option in data["plans"]:
        providers |= {r["provider"] for r in option["rails"]}
    assert "paypal" not in providers, "a rail that cannot be completed must not be listed"
    assert "stripe" in providers


# ── 5. Telling the user, with the bank's reason ────────────────────────────

def _decline_invoice(customer: str, code: str = "insufficient_funds") -> dict:
    """An invoice whose PaymentIntent is expanded — no Stripe call needed."""
    return {
        "id": "in_decline",
        "customer": customer,
        "amount_due": 1200,
        "currency": "usd",
        "next_payment_attempt": int(datetime(2026, 9, 1, tzinfo=timezone.utc).timestamp()),
        "payment_intent": {
            "id": "pi_1",
            "last_payment_error": {"code": "card_declined", "decline_code": code,
                                   "message": "Your card has insufficient funds."},
        },
    }


@pytest.mark.asyncio
async def test_declined_first_payment_emails_the_user_with_the_reason(db, monkeypatch):
    sent: list[dict] = []

    async def _capture(to, **kwargs):
        sent.append({"to": to, **kwargs})
        return True

    monkeypatch.setattr(svc.email_service, "send_payment_failed_email", _capture)

    user = await _make_user(db, "tellme@example.com")
    await svc.stripe_handle_webhook(db, _event(
        "customer.subscription.created",
        _subscription_object(user.id, status="incomplete", customer="cus_TELL"), "evt_c"))
    await svc.stripe_handle_webhook(db, _event(
        "invoice.payment_failed", _decline_invoice("cus_TELL"), "evt_f"))

    assert len(sent) == 1, "the one person who can fix this must hear about it"
    assert sent[0]["to"] == "tellme@example.com"
    assert sent[0]["reason"] == "the card didn’t have enough available funds"
    assert sent[0]["first_payment"] is True     # "never started", not "couldn't renew"
    assert sent[0]["amount_label"] == "12.00 USD"
    assert sent[0]["next_attempt"] == "1 September 2026"


@pytest.mark.asyncio
async def test_renewal_failure_is_worded_as_a_renewal(db, monkeypatch):
    sent: list[dict] = []

    async def _capture(to, **kwargs):
        sent.append({"to": to, **kwargs})
        return True

    monkeypatch.setattr(svc.email_service, "send_payment_failed_email", _capture)

    user = await _make_user(db, "renew-mail@example.com")
    db.add(Subscription(
        user_id=user.id, status=SubscriptionStatus.ACTIVE.value, provider="stripe",
        plan=PLAN_PLUS_MONTHLY, stripe_customer_id="cus_RENEW",
        current_period_end=datetime.now(timezone.utc) + timedelta(days=4),
    ))
    await db.flush()

    await svc.stripe_handle_webhook(db, _event(
        "invoice.payment_failed", _decline_invoice("cus_RENEW", "expired_card"), "evt_r"))

    assert sent[0]["first_payment"] is False
    assert sent[0]["reason"] == "the card has expired"


@pytest.mark.asyncio
async def test_a_mail_outage_does_not_fail_the_webhook(db, monkeypatch):
    """A non-2xx here sends Stripe into a multi-day retry cascade."""
    async def _boom(*_a, **_k):
        raise RuntimeError("smtp is down")

    monkeypatch.setattr(svc.email_service, "send_payment_failed_email", _boom)

    user = await _make_user(db, "outage@example.com")
    await svc.stripe_handle_webhook(db, _event(
        "customer.subscription.created",
        _subscription_object(user.id, status="incomplete", customer="cus_OUT"), "evt_oc"))
    await svc.stripe_handle_webhook(db, _event(
        "invoice.payment_failed", _decline_invoice("cus_OUT"), "evt_of"))

    sub = await svc.get_subscription(db, user.id)
    assert sub.status == SubscriptionStatus.INCOMPLETE.value   # the state still applied


@pytest.mark.asyncio
async def test_unknown_decline_code_falls_back_to_stripes_own_words(db):
    reason = await svc._stripe_failure_reason({
        "payment_intent": {"last_payment_error": {
            "code": "some_new_code_stripe_added",
            "message": "The bank returned an unusual response.",
        }},
    })
    assert reason == "The bank returned an unusual response"


@pytest.mark.asyncio
async def test_reason_reads_the_2025_payments_shape_without_calling_stripe(db):
    """Only an id is present and Stripe is unconfigured — must not raise."""
    reason = await svc._stripe_failure_reason({
        "id": "in_x",
        "payments": {"data": [{"payment": {"payment_intent": "pi_only_an_id"}}]},
    })
    assert reason is None
    assert svc._stripe_payment_intent_id({
        "payments": {"data": [{"payment": {"payment_intent": "pi_only_an_id"}}]},
    }) == "pi_only_an_id"


@pytest.mark.asyncio
async def test_no_email_when_the_event_cannot_be_attributed(db, monkeypatch):
    sent: list[dict] = []

    async def _capture(to, **kwargs):
        sent.append({"to": to})
        return True

    monkeypatch.setattr(svc.email_service, "send_payment_failed_email", _capture)
    await svc.stripe_handle_webhook(db, _event(
        "invoice.payment_failed", _decline_invoice("cus_NOBODY"), "evt_nobody"))
    assert sent == []


# ── 6. The gate must agree with what the paywall enforces ──────────────────

@pytest.mark.asyncio
async def test_exempt_owner_reads_as_entitled(db, monkeypatch):
    """Mobile gates the WHOLE app on this field.

    The exemption used to live only in `require_active_subscription`, so an
    owner account with no subscription row got a silent bypass on the API and
    `entitled: false` from /status. On web that was invisible; on iOS/Android it
    is the difference between using the app and being locked out of it.
    """
    from app.api.subscription import _status_response

    monkeypatch.setattr(settings, "SUBSCRIPTION_EXEMPT_EMAILS", ["owner@alafia.app"])
    owner = await _make_user(db, "owner@alafia.app")
    payer = await _make_user(db, "payer@example.com")

    assert _status_response(None, owner).entitled is True
    assert _status_response(None, payer).entitled is False
    assert _status_response(None, None).entitled is False
