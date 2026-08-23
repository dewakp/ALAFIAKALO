"""Subscription / billing service.

The backend owns entitlement. Each billing rail (Stripe on the web, Google Play
on Android, Apple StoreKit on iOS) reports a *verified* purchase and this service
records the resulting active period on the user's ``Subscription`` row. All
provider I/O goes through ``httpx`` + stdlib crypto — no vendor SDKs — so nothing
new has to be installed into the image.

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
from app.services import email as email_service

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
    is how a grandfathered user "extends": Stripe trial_end is
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
    # "incomplete" = created, first invoice never paid. Neither NONE (which reads
    # as "never tried" and leaves the user staring at a plain paywall with no clue
    # their card was declined) nor PAST_DUE (which is ENTITLING — see the note on
    # _ENTITLING_STATUSES; it would hand out a free period for a declined card).
    "incomplete": SubscriptionStatus.INCOMPLETE.value,
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
        # Who this is, stamped where every later event can still see it.
        #
        # `client_reference_id` rides on the checkout SESSION, so it only reaches
        # us via `checkout.session.completed` — which never fires when the first
        # payment fails. The Subscription and its invoices are separate objects
        # and carry none of it, so a declined card produced
        # `customer.subscription.created` + `invoice.payment_failed` that matched
        # no row (the customer id is only learned at completion) and were logged
        # against user_id NULL. The user then saw an ordinary paywall instead of
        # "your card was declined", and nothing linked that Stripe customer back
        # to the account. subscription_data[metadata] is copied onto the
        # Subscription object itself, so it survives the failure.
        "metadata[alafia_user_id]": str(user.id),
        "subscription_data[metadata][alafia_user_id]": str(user.id),
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


def _stripe_signature_debug(sig_header: str) -> dict:
    """What the Stripe-Signature header itself says, without trusting the body."""
    parts = [p.split("=", 1) for p in sig_header.split(",") if "=" in p]
    info: dict = {"header_present": bool(sig_header),
                  "schemes": sorted({k.strip() for k, _ in parts})}
    timestamp = next((v for k, v in parts if k.strip() == "t"), "").strip()
    if timestamp.isdigit():
        # Distinguishes a wrong secret from an expired replay window at a glance.
        info["age_seconds"] = int(time.time()) - int(timestamp)
    return info


def stripe_describe_rejected(payload: bytes, sig_header: str) -> dict:
    """Describe a webhook we are about to REFUSE, so the refusal is not silent.

    The body is untrusted by definition here — its signature did not verify — so
    nothing in it is acted on; it is only named. ``livemode`` and ``account`` are
    what actually identify the sender: a test-mode endpoint, or a second Stripe
    account pointed at this URL, sends perfectly well-formed events signed with a
    secret we do not hold, and every one of them is retried for days.
    """
    info = _stripe_signature_debug(sig_header)
    info["bytes"] = len(payload)
    try:
        event = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError):
        event = None
    if not isinstance(event, dict):
        info["parsed"] = False
        return info
    info.update({
        "parsed": True,
        "event_id": str(event.get("id") or "")[:64],
        "event_type": str(event.get("type") or "")[:64],
        "livemode": event.get("livemode"),
        "account": str(event.get("account") or "")[:64] or None,
        "api_version": str(event.get("api_version") or "")[:32] or None,
    })
    return info


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


def _stripe_metadata_user_id(*objs: dict) -> int | None:
    """Read our own ``alafia_user_id`` stamp off any Stripe object carrying it."""
    for obj in objs:
        if not isinstance(obj, dict):
            continue
        raw = (obj.get("metadata") or {}).get("alafia_user_id")
        if raw is not None and str(raw).strip().isdigit():
            return int(str(raw).strip())
    return None


def _stripe_invoice_subscription_id(obj: dict) -> str | None:
    """The subscription an invoice belongs to — in either payload shape.

    Older API versions put it at ``invoice.subscription``; 2025+ versions moved it
    to ``invoice.parent.subscription_details.subscription``. Reading only one shape
    loses attribution silently the day the account's API version rolls forward.
    """
    for candidate in (obj.get("subscription"),
                      ((obj.get("parent") or {}).get("subscription_details") or {}).get("subscription")):
        if isinstance(candidate, str) and candidate:
            return candidate
        if isinstance(candidate, dict) and candidate.get("id"):
            return candidate["id"]
    return None


def _stripe_event_trace(etype: str, obj: dict) -> dict:
    """Ids — never PII — kept on the audit row so an event stays traceable.

    An event we could not attribute used to be recorded with ``user_id`` NULL and
    ``payload`` NULL, which left nothing at all to reconcile against Stripe later.
    Card details and email are deliberately not copied here.
    """
    trace: dict[str, str] = {"type": etype}
    for key in ("id", "customer"):
        value = obj.get(key)
        if isinstance(value, str) and value:
            trace[key] = value
    sub_id = _stripe_invoice_subscription_id(obj)
    if sub_id:
        trace["subscription"] = sub_id
    return trace


# Stripe's decline codes, in language a person can act on. "Your payment failed"
# tells the reader nothing; "the card didn't have enough available funds" tells
# them exactly what to do next. Codes not listed here fall back to Stripe's own
# sentence rather than to silence.
_STRIPE_DECLINE_REASONS = {
    "insufficient_funds": "the card didn’t have enough available funds",
    "expired_card": "the card has expired",
    "incorrect_cvc": "the security code (CVC) didn’t match",
    "invalid_cvc": "the security code (CVC) was invalid",
    "incorrect_number": "the card number was incorrect",
    "invalid_number": "the card number was invalid",
    "invalid_expiry_month": "the card’s expiry month was invalid",
    "invalid_expiry_year": "the card’s expiry year was invalid",
    "card_not_supported": "the card doesn’t support this kind of purchase",
    "currency_not_supported": "the card doesn’t support payments in this currency",
    "lost_card": "the bank has the card marked as lost",
    "stolen_card": "the bank has the card marked as stolen",
    "pickup_card": "the bank asked for the card to be withheld",
    "do_not_honor": "the bank declined it without giving a reason",
    "generic_decline": "the bank declined it without giving a reason",
    "transaction_not_allowed": "the bank doesn’t allow this kind of transaction",
    "try_again_later": "the bank asked us to try again later",
    "processing_error": "the bank hit a temporary processing error",
    "authentication_required": "the bank needs you to confirm the payment (3-D Secure)",
    "card_velocity_exceeded": "the card has gone past its usage limit",
    "withdrawal_count_limit_exceeded": "the card has gone past its withdrawal limit",
    "card_declined": "the bank declined the charge",
}


def _friendly_decline(err: dict) -> str | None:
    """Map a Stripe error object to one plain-language clause."""
    if not isinstance(err, dict):
        return None
    for key in ("decline_code", "code"):
        mapped = _STRIPE_DECLINE_REASONS.get(str(err.get(key) or ""))
        if mapped:
            return mapped
    message = err.get("message")
    if isinstance(message, str) and message.strip():
        # Stripe's own wording, de-punctuated so the template can punctuate.
        return message.strip().rstrip(".")
    return None


def _stripe_payment_intent_id(obj: dict) -> str | None:
    """The PaymentIntent behind an invoice, across both payload shapes."""
    pi = obj.get("payment_intent")
    if isinstance(pi, str) and pi:
        return pi
    if isinstance(pi, dict) and pi.get("id"):
        return pi["id"]
    # 2025+ shape: invoice.payments.data[].payment.payment_intent
    for payment in ((obj.get("payments") or {}).get("data") or []):
        candidate = ((payment or {}).get("payment") or {}).get("payment_intent")
        if isinstance(candidate, str) and candidate:
            return candidate
        if isinstance(candidate, dict) and candidate.get("id"):
            return candidate["id"]
    return None


async def _stripe_failure_reason(obj: dict) -> str | None:
    """Why the bank refused, in plain language.

    Read from the event payload first and only call Stripe when it carries an id
    where the expanded object would have been. Never raises: a missing reason
    costs the email one sentence, but an exception here would cost the webhook a
    non-2xx and send Stripe into a multi-day retry cascade.
    """
    try:
        pi = obj.get("payment_intent")
        if isinstance(pi, dict):
            reason = _friendly_decline(pi.get("last_payment_error") or {})
            if reason:
                return reason

        charge = obj.get("charge")
        if isinstance(charge, dict):
            outcome = charge.get("outcome") or {}
            reason = _friendly_decline({
                "decline_code": outcome.get("reason"),
                "code": charge.get("failure_code"),
                "message": outcome.get("seller_message") or charge.get("failure_message"),
            })
            if reason:
                return reason

        reason = _friendly_decline(obj.get("last_finalization_error") or {})
        if reason:
            return reason

        pi_id = _stripe_payment_intent_id(obj)
        if pi_id and settings.STRIPE_SECRET_KEY and not _test_mode(settings.STRIPE_SECRET_KEY):
            data = await _stripe_request("GET", f"/v1/payment_intents/{pi_id}")
            return _friendly_decline(data.get("last_payment_error") or {})
    except Exception:
        logger.warning("No decline reason readable off invoice %s", obj.get("id"), exc_info=True)
    return None


def _amount_label(obj: dict) -> str | None:
    amount = obj.get("amount_due")
    if not isinstance(amount, int):
        return None
    return f"{amount / 100:.2f} {str(obj.get('currency') or 'usd').upper()}"


async def _notify_payment_failed(db: AsyncSession, sub: Subscription, obj: dict, *,
                                 first_payment: bool) -> None:
    """Email the user that their card was declined — and say why.

    The failure is otherwise invisible to the one person who can fix it: the
    paywall looks exactly as it did before they tried, so a declined card reads
    as "nothing happened".

    The whole thing is wrapped: a mail outage must never turn into a non-2xx on
    the webhook, which Stripe would retry for days.
    """
    try:
        user = await db.get(User, sub.user_id)
        if user is None or not user.email:
            return
        reason = await _stripe_failure_reason(obj)
        next_attempt = _ts_to_dt(obj.get("next_payment_attempt"))
        sent = await email_service.send_payment_failed_email(
            user.email,
            full_name=user.full_name,
            reason=reason,
            first_payment=first_payment,
            amount_label=_amount_label(obj),
            next_attempt=(f"{next_attempt.day} {next_attempt:%B %Y}" if next_attempt else None),
        )
        logger.info("Payment-failure email for user %s: sent=%s first_payment=%s reason=%r",
                    sub.user_id, sent, first_payment, reason)
    except Exception:
        logger.exception("Could not notify user %s about a declined payment", sub.user_id)


def _stripe_apply_payment_failure(sub: Subscription) -> None:
    """A failed invoice — downgrade only where a downgrade is what it means.

    This used to be an unconditional ``status = PAST_DUE``. PAST_DUE is an
    *entitling* status, so once a first-payment failure became attributable (it
    never was before, which is the only reason this was harmless) that line would
    have granted a full period of free access to any declined card. It also must
    not rewrite the history of someone who genuinely paid and later lapsed.
    """
    if sub.is_entitled(grace_days=0):
        sub.status = SubscriptionStatus.PAST_DUE.value      # a RENEWAL failed; grace applies
    elif sub.status in (SubscriptionStatus.NONE.value, SubscriptionStatus.INCOMPLETE.value):
        sub.status = SubscriptionStatus.INCOMPLETE.value    # never got in; say so, don't let them in


async def _user_exists(db: AsyncSession, user_id: int) -> bool:
    return await db.scalar(select(User.id).where(User.id == user_id)) is not None


async def _stripe_attribute_by_metadata(db: AsyncSession, *objs: dict) -> Subscription | None:
    """Last-resort attribution via the user id we stamped at checkout time."""
    user_id = _stripe_metadata_user_id(*objs)
    if user_id is None or not await _user_exists(db, user_id):
        return None
    return await get_or_create_subscription(db, user_id)


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
        user_id = int(ref) if ref and str(ref).isdigit() else _stripe_metadata_user_id(obj)
        # A reference naming a user who no longer exists would otherwise violate
        # the FK and 500 the webhook, which Stripe then retries for days.
        if user_id and not await _user_exists(db, user_id):
            user_id = None
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
        if sub is None:
            # Nothing on file yet. This is the ordinary case when the FIRST
            # payment fails: the customer id is only learned at completion, so
            # neither lookup above can match and the event used to vanish into a
            # user_id NULL audit row.
            sub = await _stripe_attribute_by_metadata(db, obj)
        if sub:
            user_id = sub.user_id
            _stripe_apply_subscription_object(sub, obj)
    elif etype in ("invoice.payment_succeeded", "invoice.paid", "invoice.payment_failed"):
        # `invoice.paid` is listed because Stripe sends it alongside
        # `invoice.payment_succeeded`; an account subscribed to only the former
        # would otherwise have every renewal fall through unattributed.
        sub = await _stripe_find_by_customer(db, obj.get("customer"))
        if sub is None:
            sub = await _stripe_find_by_sub_id(db, _stripe_invoice_subscription_id(obj))
        if sub is None:
            sub = await _stripe_attribute_by_metadata(
                db, obj, (obj.get("parent") or {}).get("subscription_details") or {})
        if sub:
            user_id = sub.user_id
            if isinstance(obj.get("customer"), str) and not sub.stripe_customer_id:
                sub.stripe_customer_id = obj["customer"]
            if etype == "invoice.payment_failed":
                # Captured BEFORE the downgrade: it is what separates "your
                # membership never started" from "we couldn't renew it", and
                # _stripe_apply_payment_failure is about to change it.
                was_entitled = sub.is_entitled(grace_days=0)
                _stripe_apply_payment_failure(sub)
                await _notify_payment_failed(db, sub, obj, first_payment=not was_entitled)

    if user_id is None:
        # Not an empty state: say so, with the ids needed to reconcile by hand.
        logger.warning("Stripe webhook %s (%s) could not be attributed to a user: %s",
                       event_id, etype, _stripe_event_trace(etype, obj))

    await _record_event(db, provider="stripe", event_id=event_id, event_type=etype,
                        user_id=user_id, payload=_stripe_event_trace(etype, obj))


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
# PayPal — WITHDRAWN RAIL (removed 2026-08-23)
# ════════════════════════════════════════════════════════════════════════════
#
# PayPal was advertised by /plans and rendered as a button on the web paywall
# while no PayPal credential was ever mounted in production, so every tap
# returned 503 "PayPal billing is not configured". The first paying customer to
# hit it pressed it twice before finding the card button. The rail is gone
# rather than gated: an option nobody can complete is worse than no option.
#
# `SubscriptionProvider.PAYPAL` and `subscriptions.paypal_subscription_id`
# survive in the model because the deployed column still has them in its
# domain. Zero rows use either.
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
