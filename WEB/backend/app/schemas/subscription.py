"""Subscription / billing schemas."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


# ── Catalog ───────────────────────────────────────────────────────────────

class RailPrice(BaseModel):
    """Price for a single billing rail."""

    provider: str            # stripe | paypal | google_play | apple
    price_usd: float
    store_product_id: str | None = None  # native store product id (mobile)


class PlanOption(BaseModel):
    """One billing interval of the membership and its per-rail pricing."""

    interval: str            # "month" | "year"
    plan: str                # plus_monthly | plus_annual
    rails: list[RailPrice]


class PlansResponse(BaseModel):
    """The membership tier, offered monthly or annually, priced per rail.

    ``plans`` carries every interval (monthly + annual). The top-level ``plan`` /
    ``interval`` / ``rails`` are kept for backward compatibility with older
    (mobile) clients and mirror the monthly option.
    """

    product_name: str
    plan: str
    currency: str = "USD"
    interval: str = "month"
    rails: list[RailPrice]
    plans: list[PlanOption] = []


# ── Status ────────────────────────────────────────────────────────────────

class SubscriptionStatusResponse(BaseModel):
    """A user's current entitlement, derived server-side."""

    status: str
    provider: str
    plan: str
    entitled: bool
    product_name: str
    price_usd: float | None = None
    current_period_end: datetime | None = None
    cancel_at_period_end: bool = False


# ── Web checkout (Stripe / PayPal) ────────────────────────────────────────

class CheckoutRequest(BaseModel):
    provider: Literal["stripe", "paypal"]
    # Billing interval. Defaults to monthly for older clients that don't send it.
    interval: Literal["month", "year"] = "month"


class CheckoutResponse(BaseModel):
    provider: str
    # For Stripe: the hosted Checkout URL. For PayPal: the approval URL.
    checkout_url: str
    # Provider handle the client returns with on success (Stripe session id /
    # PayPal subscription id) so a confirm call can finalise without a webhook.
    reference_id: str
    test_mode: bool = False


class ConfirmRequest(BaseModel):
    """Finalise a web checkout after the provider redirects back.

    Webhooks are the durable source of truth, but a synchronous confirm keeps
    the UX immediate (and is the only activation path in dev test-mode / when
    webhooks aren't yet configured). Idempotent.
    """

    provider: Literal["stripe", "paypal"]
    reference_id: str


# ── Mobile purchase verification (Google Play / Apple StoreKit) ───────────

class GoogleVerifyRequest(BaseModel):
    purchase_token: str
    product_id: str
    order_id: str | None = None


class AppleVerifyRequest(BaseModel):
    # StoreKit 2 signed transaction (JWS) is preferred; the base64 unified
    # receipt (verifyReceipt) is accepted as a fallback for older clients.
    signed_transaction: str | None = None
    receipt_data: str | None = None
    transaction_id: str | None = None


class CancelRequest(BaseModel):
    # Cancel at period end (default) rather than immediately, so the user keeps
    # access they've already paid for.
    at_period_end: bool = True
