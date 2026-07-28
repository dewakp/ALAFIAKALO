"""Subscription / billing endpoints.

One membership tier ("ALAFIA Membership"), monthly or annual, four rails:
  • Web  — Stripe Checkout + PayPal ($12/mo or $129/yr) → /checkout, /confirm, /webhook/*
  • Android — Google Play Billing ($14/mo)     → /verify/google
  • iOS  — Apple StoreKit 2 ($14/mo)            → /verify/apple

The backend is the single source of truth for entitlement (GET /status). See
``services/subscription_service`` for the provider integrations.
"""

import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.config import settings
from app.models.user import User
from app.models.subscription import Subscription, SubscriptionProvider
from app.schemas.subscription import (
    PlansResponse, PlanOption, RailPrice, SubscriptionStatusResponse,
    CheckoutRequest, CheckoutResponse, ConfirmRequest,
    GoogleVerifyRequest, AppleVerifyRequest, CancelRequest,
)
from app.services import subscription_service as svc

router = APIRouter()


def _status_response(sub: Subscription | None) -> SubscriptionStatusResponse:
    if sub is None:
        return SubscriptionStatusResponse(
            status="none", provider="none", plan="plus_monthly", entitled=False,
            product_name=settings.SUBSCRIPTION_PRODUCT_NAME, price_usd=None,
        )
    return SubscriptionStatusResponse(
        status=sub.status, provider=sub.provider, plan=sub.plan,
        entitled=svc.is_entitled(sub), product_name=settings.SUBSCRIPTION_PRODUCT_NAME,
        price_usd=sub.price_usd, current_period_end=sub.current_period_end,
        cancel_at_period_end=sub.cancel_at_period_end,
    )


# ── Catalog ─────────────────────────────────────────────────────────────────

@router.get("/plans", response_model=PlansResponse)
async def get_plans():
    """Public pricing catalog — the membership, monthly or annually, per rail."""
    monthly_rails = [
        RailPrice(provider="stripe", price_usd=settings.SUBSCRIPTION_PRICE_WEB_USD),
        RailPrice(provider="paypal", price_usd=settings.SUBSCRIPTION_PRICE_WEB_USD),
        RailPrice(provider="google_play", price_usd=settings.SUBSCRIPTION_PRICE_ANDROID_USD,
                  store_product_id=settings.GOOGLE_PLAY_PRODUCT_ID),
        RailPrice(provider="apple", price_usd=settings.SUBSCRIPTION_PRICE_IOS_USD,
                  store_product_id=settings.APPLE_PRODUCT_ID),
    ]
    # Annual: web (Stripe/PayPal) + iOS (App Store). Google Play annual not offered yet.
    # The App Store price shown on-device comes from StoreKit; this catalog value is a
    # fallback for display only.
    annual_rails = [
        RailPrice(provider="stripe", price_usd=settings.SUBSCRIPTION_PRICE_WEB_ANNUAL_USD),
        RailPrice(provider="paypal", price_usd=settings.SUBSCRIPTION_PRICE_WEB_ANNUAL_USD),
        RailPrice(provider="apple", price_usd=settings.SUBSCRIPTION_PRICE_WEB_ANNUAL_USD,
                  store_product_id=settings.APPLE_PRODUCT_ID_ANNUAL),
    ]
    return PlansResponse(
        product_name=settings.SUBSCRIPTION_PRODUCT_NAME,
        plan="plus_monthly",
        interval="month",
        rails=monthly_rails,  # legacy top-level = monthly
        plans=[
            PlanOption(interval="month", plan="plus_monthly", rails=monthly_rails),
            PlanOption(interval="year", plan="plus_annual", rails=annual_rails),
        ],
    )


@router.get("/status", response_model=SubscriptionStatusResponse)
async def get_status(current_user: User = Depends(get_current_user),
                     db: AsyncSession = Depends(get_db)):
    sub = await svc.get_subscription(db, current_user.id)
    return _status_response(sub)


# ── Web checkout (Stripe / PayPal) ──────────────────────────────────────────

@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout(body: CheckoutRequest,
                          current_user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    if body.provider == "stripe":
        result = await svc.stripe_create_checkout(db, current_user, body.interval)
    else:
        result = await svc.paypal_create_checkout(db, current_user, body.interval)
    return CheckoutResponse(provider=body.provider, **result)


@router.post("/confirm", response_model=SubscriptionStatusResponse)
async def confirm_checkout(body: ConfirmRequest,
                           current_user: User = Depends(get_current_user),
                           db: AsyncSession = Depends(get_db)):
    if body.provider == "stripe":
        sub = await svc.stripe_confirm(db, current_user, body.reference_id)
    else:
        sub = await svc.paypal_confirm(db, current_user, body.reference_id)
    return _status_response(sub)


# ── Provider webhooks (no auth — signature-verified) ────────────────────────

@router.post("/webhook/stripe", include_in_schema=False)
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    payload = await request.body()
    sig = request.headers.get("Stripe-Signature", "")
    if not svc.stripe_verify_signature(payload, sig):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid signature")
    try:
        event = json.loads(payload)
    except json.JSONDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid payload")
    await svc.stripe_handle_webhook(db, event)
    return {"received": True}


@router.post("/webhook/paypal", include_in_schema=False)
async def paypal_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    payload = await request.body()
    try:
        event = json.loads(payload)
    except json.JSONDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid payload")
    headers = {k.lower(): v for k, v in request.headers.items()}
    if not await svc.paypal_verify_webhook(headers, event):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid signature")
    await svc.paypal_handle_webhook(db, event)
    return {"received": True}


# ── Mobile purchase verification (Google Play / Apple StoreKit) ─────────────

@router.post("/verify/google", response_model=SubscriptionStatusResponse)
async def verify_google(body: GoogleVerifyRequest,
                        current_user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    sub = await svc.google_verify(db, current_user, body.purchase_token,
                                  body.product_id, body.order_id)
    return _status_response(sub)


@router.post("/verify/apple", response_model=SubscriptionStatusResponse)
async def verify_apple(body: AppleVerifyRequest,
                       current_user: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    sub = await svc.apple_verify(db, current_user, signed_transaction=body.signed_transaction,
                                 receipt_data=body.receipt_data, transaction_id=body.transaction_id)
    return _status_response(sub)


# ── Cancel (web rails) ──────────────────────────────────────────────────────

@router.post("/cancel", response_model=SubscriptionStatusResponse)
async def cancel(body: CancelRequest,
                 current_user: User = Depends(get_current_user),
                 db: AsyncSession = Depends(get_db)):
    sub = await svc.cancel_subscription(db, current_user, at_period_end=body.at_period_end)
    return _status_response(sub)
