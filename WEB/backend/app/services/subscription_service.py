"""Subscription / billing service.

The backend owns entitlement. Each billing rail (Stripe & PayPal on the web,
Google Play on Android, Apple StoreKit on iOS) reports a *verified* purchase and
this service records the resulting active period on the user's ``Subscription``
row. All provider I/O goes through ``httpx`` + stdlib crypto — no vendor SDKs —
so nothing new has to be installed into the image.

Dev **test-mode**: when a rail's credentials are blank *and* ``settings.DEBUG``
is true, the rail returns a synthetic-but-consistent active purchase so the whole
UI + entitlement flow can be exercised without live keys. In production (DEBUG
false) a missing credential raises 503 instead — never a fake entitlement.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import HTTPException, status as http_status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.models.subscription import (
    Subscription,
    SubscriptionEvent,
    SubscriptionStatus,
    SubscriptionProvider,
    PLAN_PLUS_MONTHLY,
    PLAN_PLUS_ANNUAL,
    plan_for_interval,
)
from app.models.user import User

logger = get_logger(__name__)

_HTTP_TIMEOUT = 20.0
_MONTH = timedelta(days=30)
_YEAR = timedelta(days=365)


def _period_delta(plan: str) -> timedelta:
    return _YEAR if plan == PLAN_PLUS_ANNUAL else _MONTH


def _defer_start(sub: Subscription | None) -> datetime | None:
    """If the user still has entitled time (grandfather comp or an existing paid
    period), return its end so newly-purchased billing starts *then* — the paid
    plan stacks on top of what they already have instead of overwriting it. This
    is how a grandfathered user "extends": Stripe trial_end / PayPal start_time is
    set to this instant, so they aren't charged (and don't lose time) until it
    passes. Returns None when there's nothing to preserve (bill immediately)."""
    if sub is None or not sub.is_entitled(grace_days=0):
        return None
    end = sub.current_period_end
    if end is None:
        return None
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    return end if end > datetime.now(timezone.utc) else None


# ── Row helpers ─────────────────────────────────────────────────────────────

async def get_subscription(db: AsyncSession, user_id: int) -> Subscription | None:
    result = await db.execute(select(Subscription).where(Subscription.user_id == user_id))
    return result.scalar_one_or_none()


async def get_or_create_subscription(db: AsyncSession, user_id: int) -> Subscription:
    sub = await get_subscription(db, user_id)
    if sub is None:
        sub = Subscription(user_id=user_id, status=SubscriptionStatus.NONE.value,
                           provider=SubscriptionProvider.NONE.value, plan=PLAN_PLUS_MONTHLY)
        db.add(sub)
        await db.flush()
    return sub


def is_entitled(sub: Subscription | None) -> bool:
    return bool(sub) and sub.is_entitled(grace_days=settings.SUBSCRIPTION_GRACE_DAYS)


async def _already_processed(db: AsyncSession, provider: str, event_id: str) -> bool:
    if not event_id:
        return False
    result = await db.execute(
        select(SubscriptionEvent.id).where(
            SubscriptionEvent.provider == provider,
            SubscriptionEvent.event_id == event_id,
        )
    )
    return result.scalar_one_or_none() is not None


async def _record_event(db: AsyncSession, *, provider: str, event_id: str,
                        event_type: str | None, user_id: int | None,
                        payload: dict | str | None = None) -> None:
    """Append to the idempotency/audit log — idempotent on ``(provider, event_id)``.

    A replayed webhook, a double checkout-redirect, or a shared test-mode
    reference id must be a harmless no-op — not a UniqueViolation that poisons the
    surrounding transaction (the per-user entitlement is already applied on the row
    before this runs). The insert is wrapped in a SAVEPOINT so a conflict rolls back
    only this insert and leaves the outer transaction intact. Race-safe (the DB
    enforces uniqueness) and dialect-agnostic (Postgres in prod, SQLite in tests).
    """
    body = payload if isinstance(payload, str) else (json.dumps(payload)[:8000] if payload else None)
    event = SubscriptionEvent(
        provider=provider, event_id=event_id or f"{provider}:{int(time.time()*1000)}",
        event_type=event_type, user_id=user_id, payload=body,
    )
    try:
        async with db.begin_nested():
            db.add(event)
    except IntegrityError:
        pass  # already recorded — idempotent no-op


def _rail_price(provider: str, plan: str = PLAN_PLUS_MONTHLY) -> float:
    if plan == PLAN_PLUS_ANNUAL:
        return settings.SUBSCRIPTION_PRICE_WEB_ANNUAL_USD  # annual is web-only
    return {
        SubscriptionProvider.STRIPE.value: settings.SUBSCRIPTION_PRICE_WEB_USD,
        SubscriptionProvider.PAYPAL.value: settings.SUBSCRIPTION_PRICE_WEB_USD,
        SubscriptionProvider.GOOGLE_PLAY.value: settings.SUBSCRIPTION_PRICE_ANDROID_USD,
        SubscriptionProvider.APPLE.value: settings.SUBSCRIPTION_PRICE_IOS_USD,
    }.get(provider, settings.SUBSCRIPTION_PRICE_WEB_USD)


def _apply_active_period(sub: Subscription, *, provider: str, status_value: str,
                         period_end: datetime | None, cancel_at_period_end: bool = False,
                         period_start: datetime | None = None, plan: str | None = None) -> None:
    """Record a verified active period from a provider onto the user's row."""
    sub.provider = provider
    if plan is not None:
        sub.plan = plan
    sub.price_usd = _rail_price(provider, sub.plan or PLAN_PLUS_MONTHLY)
    sub.status = status_value
    if period_start is not None:
        sub.current_period_start = period_start
    if period_end is not None:
        sub.current_period_end = period_end
    sub.cancel_at_period_end = cancel_at_period_end
    if status_value == SubscriptionStatus.CANCELED.value and sub.canceled_at is None:
        sub.canceled_at = datetime.now(timezone.utc)


def _test_mode(secret: str) -> bool:
    """A rail runs in synthetic test-mode only when unconfigured AND in DEBUG."""
    return not secret and settings.DEBUG


def _require_configured(secret: str, rail: str) -> None:
    if not secret and not settings.DEBUG:
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"{rail} billing is not configured",
        )


def _ts_to_dt(ts) -> datetime | None:
    if ts in (None, "", 0):
        return None
    try:
        return datetime.fromtimestamp(int(ts) / (1000 if int(ts) > 10_000_000_000 else 1),
                                      tz=timezone.utc)
    except (ValueError, TypeError, OverflowError):
        return None


# ════════════════════════════════════════════════════════════════════════════
# Stripe (web card rail) — Checkout + webhook, via the REST API
# ════════════════════════════════════════════════════════════════════════════

_STRIPE_STATUS_MAP = {
    "trialing": SubscriptionStatus.TRIALING.value,
    "active": SubscriptionStatus.ACTIVE.value,
    "past_due": SubscriptionStatus.PAST_DUE.value,
    "unpaid": SubscriptionStatus.PAST_DUE.value,
    "canceled": SubscriptionStatus.CANCELED.value,
    "incomplete": SubscriptionStatus.NONE.value,
    "incomplete_expired": SubscriptionStatus.EXPIRED.value,
}


async def _stripe_request(method: str, path: str, data: dict | None = None) -> dict:
    headers = {"Authorization": f"Bearer {settings.STRIPE_SECRET_KEY}"}
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        resp = await client.request(method, f"{settings.STRIPE_API_BASE}{path}",
                                    headers=headers, data=data)
    if resp.status_code >= 400:
        logger.warning("Stripe %s %s -> %s %s", method, path, resp.status_code, resp.text[:300])
        raise HTTPException(status_code=http_status.HTTP_502_BAD_GATEWAY,
                            detail="Stripe request failed")
    return resp.json()


async def stripe_create_checkout(db: AsyncSession, user: User, interval: str = "month") -> dict:
    _require_configured(settings.STRIPE_SECRET_KEY, "Stripe")
    plan = plan_for_interval(interval)
    price_id = settings.STRIPE_PRICE_ID_ANNUAL if plan == PLAN_PLUS_ANNUAL else settings.STRIPE_PRICE_ID
    success_url = f"{settings.PUBLIC_WEB_URL}/subscription?status=success&provider=stripe&session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{settings.PUBLIC_WEB_URL}/subscription?status=cancel&provider=stripe"

    if _test_mode(settings.STRIPE_SECRET_KEY):
        return {"checkout_url": f"{settings.PUBLIC_WEB_URL}/subscription?status=success&provider=stripe&session_id=cs_test_dev",
                "reference_id": "cs_test_dev", "test_mode": True}

    form = {
        "mode": "subscription",
        "line_items[0][price]": price_id,
        "line_items[0][quantity]": "1",
        "success_url": success_url,
        "cancel_url": cancel_url,
        "client_reference_id": str(user.id),
        "customer_email": user.email,
    }
    sub = await get_subscription(db, user.id)
    if sub and sub.stripe_customer_id:
        form.pop("customer_email", None)
        form["customer"] = sub.stripe_customer_id
    # Extend: if the user still has entitled time (grandfather comp / paid), defer
    # the first charge to its end so the paid plan stacks on top (no lost time).
    defer = _defer_start(sub)
    if defer is not None:
        form["subscription_data[trial_end]"] = str(int(defer.timestamp()))
    session = await _stripe_request("POST", "/v1/checkout/sessions", form)
    return {"checkout_url": session["url"], "reference_id": session["id"], "test_mode": False}


async def stripe_confirm(db: AsyncSession, user: User, session_id: str) -> Subscription:
    """Finalise a Checkout session synchronously (webhook is still authoritative)."""
    sub = await get_or_create_subscription(db, user.id)

    if _test_mode(settings.STRIPE_SECRET_KEY):
        _apply_active_period(sub, provider=SubscriptionProvider.STRIPE.value,
                             status_value=SubscriptionStatus.ACTIVE.value,
                             period_start=datetime.now(timezone.utc),
                             period_end=datetime.now(timezone.utc) + _MONTH)
        sub.stripe_subscription_id = f"sub_test_{user.id}"
        await _record_event(db, provider="stripe", event_id=session_id or "cs_test_dev",
                            event_type="checkout.confirm.test", user_id=user.id)
        return sub

    _require_configured(settings.STRIPE_SECRET_KEY, "Stripe")
    session = await _stripe_request("GET", f"/v1/checkout/sessions/{session_id}")
    if str(session.get("client_reference_id")) not in (str(user.id), "None", ""):
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN,
                            detail="Checkout session does not belong to this user")
    if session.get("payment_status") not in ("paid", "no_payment_required"):
        raise HTTPException(status_code=http_status.HTTP_402_PAYMENT_REQUIRED,
                            detail="Checkout not completed")
    sub.stripe_customer_id = session.get("customer") or sub.stripe_customer_id
    stripe_sub_id = session.get("subscription")
    if stripe_sub_id:
        await _stripe_sync_subscription(db, sub, stripe_sub_id)
    await _record_event(db, provider="stripe", event_id=session_id,
                        event_type="checkout.session.confirmed", user_id=user.id)
    return sub


async def _stripe_sync_subscription(db: AsyncSession, sub: Subscription, stripe_sub_id: str) -> None:
    data = await _stripe_request("GET", f"/v1/subscriptions/{stripe_sub_id}")
    _stripe_apply_subscription_object(sub, data)


def _stripe_apply_subscription_object(sub: Subscription, data: dict) -> None:
    sub.stripe_subscription_id = data.get("id") or sub.stripe_subscription_id
    if data.get("customer"):
        sub.stripe_customer_id = data["customer"]
    mapped = _STRIPE_STATUS_MAP.get(data.get("status", ""), SubscriptionStatus.NONE.value)
    # Which interval did they buy? Read the price id off the subscription item.
    try:
        price_id = data["items"]["data"][0]["price"]["id"]
    except (KeyError, IndexError, TypeError):
        price_id = None
    plan = (PLAN_PLUS_ANNUAL if price_id and price_id == settings.STRIPE_PRICE_ID_ANNUAL
            else PLAN_PLUS_MONTHLY)
    _apply_active_period(
        sub, provider=SubscriptionProvider.STRIPE.value, status_value=mapped,
        period_start=_ts_to_dt(data.get("current_period_start")),
        period_end=_ts_to_dt(data.get("current_period_end")),
        cancel_at_period_end=bool(data.get("cancel_at_period_end")),
        plan=plan,
    )


def stripe_verify_signature(payload: bytes, sig_header: str) -> bool:
    """Verify a Stripe webhook signature (HMAC-SHA256 over ``t.payload``)."""
    secret = settings.STRIPE_WEBHOOK_SECRET
    if not secret:
        return settings.DEBUG  # unsigned accepted only in dev
    try:
        parts = dict(p.split("=", 1) for p in sig_header.split(","))
        timestamp, sent = parts["t"], parts["v1"]
    except (ValueError, KeyError):
        return False
    signed = f"{timestamp}.".encode() + payload
    expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sent):
        return False
    # Reject events older than 5 minutes (replay protection).
    return abs(time.time() - int(timestamp)) < 300


async def stripe_handle_webhook(db: AsyncSession, event: dict) -> None:
    event_id = event.get("id", "")
    if await _already_processed(db, "stripe", event_id):
        return
    etype = event.get("type", "")
    obj = event.get("data", {}).get("object", {})

    user_id = None
    sub = None
    if etype == "checkout.session.completed":
        ref = obj.get("client_reference_id")
        user_id = int(ref) if ref and ref.isdigit() else None
        if user_id:
            sub = await get_or_create_subscription(db, user_id)
            sub.stripe_customer_id = obj.get("customer") or sub.stripe_customer_id
            if obj.get("subscription"):
                await _stripe_sync_subscription(db, sub, obj["subscription"])
    elif etype in ("customer.subscription.updated", "customer.subscription.deleted",
                   "customer.subscription.created"):
        sub = await _stripe_find_by_customer(db, obj.get("customer"))
        if sub is None and obj.get("id"):
            sub = await _stripe_find_by_sub_id(db, obj["id"])
        if sub:
            user_id = sub.user_id
            _stripe_apply_subscription_object(sub, obj)
    elif etype in ("invoice.payment_succeeded", "invoice.payment_failed"):
        sub = await _stripe_find_by_customer(db, obj.get("customer"))
        if sub:
            user_id = sub.user_id
            if etype == "invoice.payment_failed":
                sub.status = SubscriptionStatus.PAST_DUE.value

    await _record_event(db, provider="stripe", event_id=event_id, event_type=etype, user_id=user_id)


async def _stripe_find_by_customer(db: AsyncSession, customer_id: str | None) -> Subscription | None:
    if not customer_id:
        return None
    r = await db.execute(select(Subscription).where(Subscription.stripe_customer_id == customer_id))
    return r.scalar_one_or_none()


async def _stripe_find_by_sub_id(db: AsyncSession, sub_id: str | None) -> Subscription | None:
    if not sub_id:
        return None
    r = await db.execute(select(Subscription).where(Subscription.stripe_subscription_id == sub_id))
    return r.scalar_one_or_none()


# ════════════════════════════════════════════════════════════════════════════
# PayPal (web alternative rail) — Subscriptions API + webhook
# ════════════════════════════════════════════════════════════════════════════

_PAYPAL_STATUS_MAP = {
    "APPROVAL_PENDING": SubscriptionStatus.NONE.value,
    "APPROVED": SubscriptionStatus.NONE.value,
    "ACTIVE": SubscriptionStatus.ACTIVE.value,
    "SUSPENDED": SubscriptionStatus.PAST_DUE.value,
    "CANCELLED": SubscriptionStatus.CANCELED.value,
    "EXPIRED": SubscriptionStatus.EXPIRED.value,
}


async def _paypal_token() -> str:
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        resp = await client.post(
            f"{settings.PAYPAL_API_BASE}/v1/oauth2/token",
            data={"grant_type": "client_credentials"},
            auth=(settings.PAYPAL_CLIENT_ID, settings.PAYPAL_CLIENT_SECRET),
        )
    if resp.status_code >= 400:
        raise HTTPException(status_code=http_status.HTTP_502_BAD_GATEWAY, detail="PayPal auth failed")
    return resp.json()["access_token"]


async def _paypal_request(method: str, path: str, token: str, json_body: dict | None = None) -> dict:
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        resp = await client.request(method, f"{settings.PAYPAL_API_BASE}{path}",
                                    headers={"Authorization": f"Bearer {token}",
                                             "Content-Type": "application/json"},
                                    json=json_body)
    if resp.status_code >= 400:
        logger.warning("PayPal %s %s -> %s %s", method, path, resp.status_code, resp.text[:300])
        raise HTTPException(status_code=http_status.HTTP_502_BAD_GATEWAY, detail="PayPal request failed")
    return resp.json() if resp.content else {}


async def paypal_create_checkout(db: AsyncSession, user: User, interval: str = "month") -> dict:
    _require_configured(settings.PAYPAL_CLIENT_SECRET, "PayPal")
    plan = plan_for_interval(interval)
    plan_id = settings.PAYPAL_PLAN_ID_ANNUAL if plan == PLAN_PLUS_ANNUAL else settings.PAYPAL_PLAN_ID
    return_url = f"{settings.PUBLIC_WEB_URL}/subscription?status=success&provider=paypal"
    cancel_url = f"{settings.PUBLIC_WEB_URL}/subscription?status=cancel&provider=paypal"

    if _test_mode(settings.PAYPAL_CLIENT_SECRET):
        return {"checkout_url": f"{return_url}&subscription_id=I-TEST-DEV",
                "reference_id": "I-TEST-DEV", "test_mode": True}

    token = await _paypal_token()
    body = {
        "plan_id": plan_id,
        "custom_id": str(user.id),
        "subscriber": {"email_address": user.email},
        "application_context": {
            "brand_name": settings.SUBSCRIPTION_PRODUCT_NAME,
            "user_action": "SUBSCRIBE_NOW",
            "return_url": return_url,
            "cancel_url": cancel_url,
        },
    }
    # Extend: defer first billing to the end of any entitled time they already have
    # (grandfather comp / paid) so the paid plan stacks on top instead of overwriting.
    defer = _defer_start(await get_subscription(db, user.id))
    if defer is not None:
        body["start_time"] = defer.strftime("%Y-%m-%dT%H:%M:%SZ")
    data = await _paypal_request("POST", "/v1/billing/subscriptions", token, body)
    approve = next((l["href"] for l in data.get("links", []) if l.get("rel") == "approve"), None)
    if not approve:
        raise HTTPException(status_code=http_status.HTTP_502_BAD_GATEWAY, detail="PayPal approval link missing")
    return {"checkout_url": approve, "reference_id": data["id"], "test_mode": False}


async def paypal_confirm(db: AsyncSession, user: User, subscription_id: str) -> Subscription:
    sub = await get_or_create_subscription(db, user.id)

    if _test_mode(settings.PAYPAL_CLIENT_SECRET):
        _apply_active_period(sub, provider=SubscriptionProvider.PAYPAL.value,
                             status_value=SubscriptionStatus.ACTIVE.value,
                             period_start=datetime.now(timezone.utc),
                             period_end=datetime.now(timezone.utc) + _MONTH)
        sub.paypal_subscription_id = subscription_id or "I-TEST-DEV"
        await _record_event(db, provider="paypal", event_id=subscription_id or "I-TEST-DEV",
                            event_type="subscription.confirm.test", user_id=user.id)
        return sub

    _require_configured(settings.PAYPAL_CLIENT_SECRET, "PayPal")
    token = await _paypal_token()
    data = await _paypal_request("GET", f"/v1/billing/subscriptions/{subscription_id}", token)
    if str(data.get("custom_id")) not in (str(user.id), "None", ""):
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN,
                            detail="Subscription does not belong to this user")
    sub.paypal_subscription_id = subscription_id
    _paypal_apply(sub, data)
    await _record_event(db, provider="paypal", event_id=subscription_id,
                        event_type="subscription.confirmed", user_id=user.id)
    return sub


def _paypal_apply(sub: Subscription, data: dict) -> None:
    mapped = _PAYPAL_STATUS_MAP.get(data.get("status", ""), SubscriptionStatus.NONE.value)
    plan = (PLAN_PLUS_ANNUAL if data.get("plan_id") and data.get("plan_id") == settings.PAYPAL_PLAN_ID_ANNUAL
            else PLAN_PLUS_MONTHLY)
    next_billing = (data.get("billing_info") or {}).get("next_billing_time")
    period_end = None
    if next_billing:
        try:
            period_end = datetime.fromisoformat(next_billing.replace("Z", "+00:00"))
        except ValueError:
            period_end = None
    if period_end is None and mapped == SubscriptionStatus.ACTIVE.value:
        period_end = datetime.now(timezone.utc) + _period_delta(plan)
    _apply_active_period(sub, provider=SubscriptionProvider.PAYPAL.value,
                         status_value=mapped, period_end=period_end, plan=plan)


async def paypal_verify_webhook(headers: dict, body: dict) -> bool:
    if not settings.PAYPAL_WEBHOOK_ID:
        return settings.DEBUG
    token = await _paypal_token()
    verify_body = {
        "auth_algo": headers.get("paypal-auth-algo"),
        "cert_url": headers.get("paypal-cert-url"),
        "transmission_id": headers.get("paypal-transmission-id"),
        "transmission_sig": headers.get("paypal-transmission-sig"),
        "transmission_time": headers.get("paypal-transmission-time"),
        "webhook_id": settings.PAYPAL_WEBHOOK_ID,
        "webhook_event": body,
    }
    data = await _paypal_request("POST", "/v1/notifications/verify-webhook-signature",
                                 token, verify_body)
    return data.get("verification_status") == "SUCCESS"


async def paypal_handle_webhook(db: AsyncSession, event: dict) -> None:
    event_id = event.get("id", "")
    if await _already_processed(db, "paypal", event_id):
        return
    etype = event.get("event_type", "")
    resource = event.get("resource", {})
    sub_id = resource.get("id") or (resource.get("billing_agreement_id"))
    custom = resource.get("custom_id") or (resource.get("custom"))

    sub = None
    user_id = int(custom) if custom and str(custom).isdigit() else None
    if sub_id:
        r = await db.execute(select(Subscription).where(Subscription.paypal_subscription_id == sub_id))
        sub = r.scalar_one_or_none()
    if sub is None and user_id:
        sub = await get_or_create_subscription(db, user_id)
        sub.paypal_subscription_id = sub_id or sub.paypal_subscription_id
    if sub:
        user_id = sub.user_id
        if etype in ("BILLING.SUBSCRIPTION.ACTIVATED", "BILLING.SUBSCRIPTION.RE-ACTIVATED",
                     "PAYMENT.SALE.COMPLETED"):
            _apply_active_period(sub, provider=SubscriptionProvider.PAYPAL.value,
                                 status_value=SubscriptionStatus.ACTIVE.value,
                                 period_end=datetime.now(timezone.utc) + _MONTH)
        elif etype == "BILLING.SUBSCRIPTION.CANCELLED":
            sub.status = SubscriptionStatus.CANCELED.value
            sub.cancel_at_period_end = True
            sub.canceled_at = datetime.now(timezone.utc)
        elif etype in ("BILLING.SUBSCRIPTION.EXPIRED", "BILLING.SUBSCRIPTION.SUSPENDED"):
            sub.status = (SubscriptionStatus.EXPIRED.value if "EXPIRED" in etype
                          else SubscriptionStatus.PAST_DUE.value)
    await _record_event(db, provider="paypal", event_id=event_id, event_type=etype, user_id=user_id)


# ════════════════════════════════════════════════════════════════════════════
# Google Play Billing (Android) — server-side purchase verification
# ════════════════════════════════════════════════════════════════════════════

def _load_google_sa() -> dict:
    with open(settings.GOOGLE_PLAY_SERVICE_ACCOUNT) as f:
        return json.load(f)


async def _google_access_token() -> str:
    import jwt  # PyJWT — already a dependency (PyJWT[crypto])
    sa = _load_google_sa()
    now = int(time.time())
    assertion = jwt.encode(
        {"iss": sa["client_email"], "scope": "https://www.googleapis.com/auth/androidpublisher",
         "aud": "https://oauth2.googleapis.com/token", "iat": now, "exp": now + 3600},
        sa["private_key"], algorithm="RS256",
    )
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        resp = await client.post("https://oauth2.googleapis.com/token", data={
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion})
    if resp.status_code >= 400:
        raise HTTPException(status_code=http_status.HTTP_502_BAD_GATEWAY, detail="Google auth failed")
    return resp.json()["access_token"]


async def google_verify(db: AsyncSession, user: User, purchase_token: str,
                        product_id: str, order_id: str | None) -> Subscription:
    sub = await get_or_create_subscription(db, user.id)

    if _test_mode(settings.GOOGLE_PLAY_SERVICE_ACCOUNT):
        _apply_active_period(sub, provider=SubscriptionProvider.GOOGLE_PLAY.value,
                             status_value=SubscriptionStatus.ACTIVE.value,
                             period_start=datetime.now(timezone.utc),
                             period_end=datetime.now(timezone.utc) + _MONTH)
        sub.google_purchase_token = purchase_token
        sub.google_order_id = order_id
        await _record_event(db, provider="google_play", event_id=purchase_token or "gp_test",
                            event_type="verify.test", user_id=user.id)
        return sub

    _require_configured(settings.GOOGLE_PLAY_SERVICE_ACCOUNT, "Google Play")
    if await _already_processed(db, "google_play", purchase_token):
        return sub  # idempotent re-submit
    token = await _google_access_token()
    pkg = settings.GOOGLE_PLAY_PACKAGE_NAME
    url = (f"https://androidpublisher.googleapis.com/androidpublisher/v3/applications/"
           f"{pkg}/purchases/subscriptionsv2/tokens/{purchase_token}")
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        resp = await client.get(url, headers={"Authorization": f"Bearer {token}"})
    if resp.status_code >= 400:
        logger.warning("Google verify -> %s %s", resp.status_code, resp.text[:300])
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST,
                            detail="Google purchase verification failed")
    data = resp.json()
    state = data.get("subscriptionState", "")
    line_items = data.get("lineItems", [])
    expiry = None
    for item in line_items:
        if item.get("expiryTime"):
            try:
                expiry = datetime.fromisoformat(item["expiryTime"].replace("Z", "+00:00"))
            except ValueError:
                pass
    entitled = state in ("SUBSCRIPTION_STATE_ACTIVE", "SUBSCRIPTION_STATE_IN_GRACE_PERIOD",
                         "SUBSCRIPTION_STATE_CANCELED")
    status_value = (SubscriptionStatus.ACTIVE.value if state == "SUBSCRIPTION_STATE_ACTIVE"
                    else SubscriptionStatus.CANCELED.value if state == "SUBSCRIPTION_STATE_CANCELED"
                    else SubscriptionStatus.PAST_DUE.value if state == "SUBSCRIPTION_STATE_IN_GRACE_PERIOD"
                    else SubscriptionStatus.EXPIRED.value)
    if not entitled and expiry is None:
        raise HTTPException(status_code=http_status.HTTP_402_PAYMENT_REQUIRED,
                            detail="Purchase is not active")
    _apply_active_period(sub, provider=SubscriptionProvider.GOOGLE_PLAY.value,
                         status_value=status_value, period_end=expiry,
                         cancel_at_period_end=(state == "SUBSCRIPTION_STATE_CANCELED"))
    sub.google_purchase_token = purchase_token
    sub.google_order_id = order_id or data.get("latestOrderId")
    await _record_event(db, provider="google_play", event_id=purchase_token,
                        event_type=f"verify.{state}", user_id=user.id)
    return sub


# ════════════════════════════════════════════════════════════════════════════
# Apple StoreKit 2 (iOS) — signed-transaction / receipt verification
# ════════════════════════════════════════════════════════════════════════════

def _b64url_decode(segment: str) -> bytes:
    pad = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + pad)


def _decode_apple_jws_payload(jws: str) -> dict:
    """Decode the JWS payload of a StoreKit 2 signed transaction.

    NOTE: production must also verify the x5c certificate chain up to Apple's
    root CA (or use the App Store Server API). Here we decode the claims; the
    signature-chain check is a documented hardening follow-up.
    """
    try:
        _, payload_b64, _ = jws.split(".")
        return json.loads(_b64url_decode(payload_b64))
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST,
                            detail="Malformed Apple transaction") from exc


async def _apple_verify_receipt(receipt_data: str) -> dict:
    """Legacy verifyReceipt fallback (auto sandbox retry on 21007)."""
    body = {"receipt-data": receipt_data, "password": settings.APPLE_SHARED_SECRET,
            "exclude-old-transactions": True}
    endpoints = ["https://buy.itunes.apple.com/verifyReceipt",
                 "https://sandbox.itunes.apple.com/verifyReceipt"]
    if settings.APPLE_ENVIRONMENT == "sandbox":
        endpoints.reverse()
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        for url in endpoints:
            resp = await client.post(url, json=body)
            data = resp.json()
            if data.get("status") == 21007 and url == endpoints[0]:
                continue  # prod endpoint got a sandbox receipt → retry sandbox
            if data.get("status") == 0:
                return data
    raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST,
                        detail="Apple receipt verification failed")


async def apple_verify(db: AsyncSession, user: User, *, signed_transaction: str | None,
                       receipt_data: str | None, transaction_id: str | None) -> Subscription:
    sub = await get_or_create_subscription(db, user.id)

    is_test = _test_mode(settings.APPLE_SHARED_SECRET) and not signed_transaction and not receipt_data
    if is_test:
        _apply_active_period(sub, provider=SubscriptionProvider.APPLE.value,
                             status_value=SubscriptionStatus.ACTIVE.value,
                             period_start=datetime.now(timezone.utc),
                             period_end=datetime.now(timezone.utc) + _MONTH)
        sub.apple_original_transaction_id = transaction_id or f"apple_test_{user.id}"
        await _record_event(db, provider="apple", event_id=sub.apple_original_transaction_id,
                            event_type="verify.test", user_id=user.id)
        return sub

    expiry = None
    product_id = None
    original_tx = transaction_id
    latest_tx = transaction_id
    if signed_transaction:
        claims = _decode_apple_jws_payload(signed_transaction)
        if claims.get("bundleId") and claims["bundleId"] != settings.APPLE_BUNDLE_ID:
            raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST,
                                detail="Transaction bundle mismatch")
        expiry = _ts_to_dt(claims.get("expiresDate"))
        product_id = claims.get("productId") or product_id
        original_tx = claims.get("originalTransactionId") or original_tx
        latest_tx = claims.get("transactionId") or latest_tx
    elif receipt_data:
        _require_configured(settings.APPLE_SHARED_SECRET, "Apple")
        data = await _apple_verify_receipt(receipt_data)
        infos = data.get("latest_receipt_info") or []
        latest = max(infos, key=lambda i: int(i.get("expires_date_ms", 0)), default=None)
        if latest:
            expiry = _ts_to_dt(latest.get("expires_date_ms"))
            product_id = latest.get("product_id") or product_id
            original_tx = latest.get("original_transaction_id") or original_tx
            latest_tx = latest.get("transaction_id") or latest_tx
    else:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST,
                            detail="No Apple transaction supplied")

    if original_tx and await _already_processed(db, "apple", f"{original_tx}:{latest_tx}"):
        return sub  # idempotent re-submit of the same transaction
    now = datetime.now(timezone.utc)
    entitled = expiry is not None and expiry > now
    plan = (PLAN_PLUS_ANNUAL if product_id and product_id == settings.APPLE_PRODUCT_ID_ANNUAL
            else PLAN_PLUS_MONTHLY)
    _apply_active_period(sub, provider=SubscriptionProvider.APPLE.value,
                         status_value=(SubscriptionStatus.ACTIVE.value if entitled
                                       else SubscriptionStatus.EXPIRED.value),
                         period_end=expiry, plan=plan)
    sub.apple_original_transaction_id = original_tx
    sub.apple_transaction_id = latest_tx
    await _record_event(db, provider="apple", event_id=f"{original_tx}:{latest_tx}",
                        event_type="verify", user_id=user.id)
    if not entitled:
        raise HTTPException(status_code=http_status.HTTP_402_PAYMENT_REQUIRED,
                            detail="Subscription is not active")
    return sub


# ── Cancel (web rails; mobile cancels happen in the store) ──────────────────

async def cancel_subscription(db: AsyncSession, user: User, at_period_end: bool = True) -> Subscription:
    sub = await get_subscription(db, user.id)
    if sub is None or sub.provider == SubscriptionProvider.NONE.value:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="No active subscription")

    provider = sub.provider
    if provider in (SubscriptionProvider.GOOGLE_PLAY.value, SubscriptionProvider.APPLE.value):
        # Store-managed subscriptions can only be cancelled in the store UI.
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail=("Manage this subscription in the "
                    + ("Google Play Store" if provider == SubscriptionProvider.GOOGLE_PLAY.value
                       else "App Store") + " subscriptions settings."),
        )

    if provider == SubscriptionProvider.STRIPE.value and sub.stripe_subscription_id \
            and not _test_mode(settings.STRIPE_SECRET_KEY):
        if at_period_end:
            data = await _stripe_request("POST", f"/v1/subscriptions/{sub.stripe_subscription_id}",
                                         {"cancel_at_period_end": "true"})
            _stripe_apply_subscription_object(sub, data)
        else:
            data = await _stripe_request("DELETE", f"/v1/subscriptions/{sub.stripe_subscription_id}")
            _stripe_apply_subscription_object(sub, data)
    elif provider == SubscriptionProvider.PAYPAL.value and sub.paypal_subscription_id \
            and not _test_mode(settings.PAYPAL_CLIENT_SECRET):
        token = await _paypal_token()
        await _paypal_request("POST",
                              f"/v1/billing/subscriptions/{sub.paypal_subscription_id}/cancel",
                              token, {"reason": "User requested cancellation"})
        sub.status = SubscriptionStatus.CANCELED.value
        sub.cancel_at_period_end = True
        sub.canceled_at = datetime.now(timezone.utc)
    else:  # test-mode
        sub.status = SubscriptionStatus.CANCELED.value
        sub.cancel_at_period_end = at_period_end
        sub.canceled_at = datetime.now(timezone.utc)
        if not at_period_end:
            sub.current_period_end = datetime.now(timezone.utc)
    return sub


# ── Pre-account checkout (two-step signup) ──────────────────────────────
# Signup takes payment BEFORE a user exists, so these cannot use user.id.
# The pending signup's email is the correlation key, carried through Stripe as
# client_reference_id and re-checked on the way back.

_SIGNUP_REF_PREFIX = "signup:"


def signup_client_reference(email: str) -> str:
    return f"{_SIGNUP_REF_PREFIX}{email.strip().lower()}"


async def signup_stripe_checkout(email: str, interval: str = "month") -> dict:
    """Create a Checkout session for a signup that has no user row yet."""
    _require_configured(settings.STRIPE_SECRET_KEY, "Stripe")
    plan = plan_for_interval(interval)
    price_id = settings.STRIPE_PRICE_ID_ANNUAL if plan == PLAN_PLUS_ANNUAL else settings.STRIPE_PRICE_ID
    email = email.strip().lower()

    success_url = (f"{settings.PUBLIC_WEB_URL}/signup/complete"
                   f"?provider=stripe&session_id={{CHECKOUT_SESSION_ID}}")
    cancel_url = f"{settings.PUBLIC_WEB_URL}/signup?status=cancel"

    if _test_mode(settings.STRIPE_SECRET_KEY):
        # Unconfigured AND DEBUG only — never a path in production.
        return {"checkout_url": f"{success_url.replace('{CHECKOUT_SESSION_ID}', 'cs_test_signup')}",
                "reference_id": "cs_test_signup", "test_mode": True}

    session = await _stripe_request("POST", "/v1/checkout/sessions", {
        "mode": "subscription",
        "line_items[0][price]": price_id,
        "line_items[0][quantity]": "1",
        "success_url": success_url,
        "cancel_url": cancel_url,
        "client_reference_id": signup_client_reference(email),
        "customer_email": email,
    })
    return {"checkout_url": session.get("url"),
            "reference_id": session.get("id"), "test_mode": False}


async def signup_stripe_verify(email: str, session_id: str) -> dict:
    """Confirm a signup's Checkout session with Stripe. Raises unless genuinely paid.

    This is the security boundary for account creation. Without it, `complete`
    would trust a client-supplied reference string — anyone could post an
    arbitrary id and be handed an account. Two things are checked against
    Stripe's own record:

      1. the session is actually paid
      2. its client_reference_id matches THIS signup, so a real session
         belonging to somebody else cannot be replayed to create an account
    """
    email = email.strip().lower()

    if _test_mode(settings.STRIPE_SECRET_KEY):
        return {"paid": True, "test_mode": True, "customer_id": None,
                "subscription_id": f"sub_test_signup", "session_id": session_id}

    _require_configured(settings.STRIPE_SECRET_KEY, "Stripe")
    session = await _stripe_request("GET", f"/v1/checkout/sessions/{session_id}")

    expected = signup_client_reference(email)
    if str(session.get("client_reference_id") or "") != expected:
        logger.warning("Signup checkout session %s does not belong to %s", session_id, email)
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN,
                            detail="Checkout session does not belong to this signup")

    if session.get("payment_status") not in ("paid", "no_payment_required"):
        raise HTTPException(status_code=http_status.HTTP_402_PAYMENT_REQUIRED,
                            detail="Checkout not completed")

    return {"paid": True, "test_mode": False,
            "customer_id": session.get("customer"),
            "subscription_id": session.get("subscription"),
            "session_id": session_id}
