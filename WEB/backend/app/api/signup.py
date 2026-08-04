"""Two-step signup: verify email → pay → account created.

Replaces direct registration. `/auth/register` created a `users` row on request,
which is how 55 of 77 accounts in this database became automation leftovers.
Here nothing exists until a real mailbox is proven AND a subscription is paid.

    POST /signup/start          begin; returns a verification token (dev) or mails it
    POST /signup/verify-email   consume the token — gate 1
    POST /signup/checkout       start payment; refuses unless verified
    POST /signup/complete       record payment and CREATE the account — gate 2
    GET  /signup/status         where a signup has got to
    POST /signup/resend         new verification email, rate limited

A robot that never reads mail and never pays leaves one expiring row here.
"""

# NOTE: deliberately NO `from __future__ import annotations` here.
#
# PEP 563 turns every annotation into a string, and the @limiter.limit wrapper
# stops FastAPI resolving those forward refs on this module. The result is not
# an error — it is worse: `body: SignupStart` silently degrades to a QUERY
# parameter, every request 422s with {"loc": ["query", "body"]}, and OpenAPI
# generation crashes on the unresolvable ref. Keep annotations concrete.

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.rate_limit import limiter
from app.services import signup_service as svc

router = APIRouter()
logger = logging.getLogger(__name__)


class SignupStart(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)


class VerifyEmail(BaseModel):
    token: str


class ResendRequest(BaseModel):
    email: EmailStr


class CheckoutStart(BaseModel):
    email: EmailStr
    provider: str = Field(default="stripe", pattern="^(stripe|paypal)$")
    interval: str = Field(default="month", pattern="^(month|year)$")


class CompleteSignup(BaseModel):
    email: EmailStr
    provider: str = Field(default="stripe", pattern="^(stripe|paypal)$")
    reference_id: str


def _sent_message() -> dict:
    # Identical whether or not the address is already in use — signup must not
    # become an oracle for which emails have accounts.
    return {"message": "If that address can receive mail, a verification link has been sent."}


@router.post("/start", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def signup_start(
    request: Request, body: SignupStart, db: AsyncSession = Depends(get_db),
):
    """Begin a signup. Creates NO account — only a pending record."""
    if await svc.email_taken(db, body.email):
        # Same response as success, so the endpoint cannot enumerate accounts.
        return _sent_message()

    pending, raw_token = await svc.start(db, body.email, body.password, body.full_name)
    await db.commit()

    # TODO(email): SMTP is deferred in this project, so nothing is delivered yet.
    # Until it ships, DEBUG returns the token inline (same convention as the
    # password-reset flow) and production returns none — meaning production
    # signup CANNOT complete until email sending exists. That is deliberate: it
    # is better than silently issuing accounts to unverified addresses.
    response = _sent_message()
    response["pending_id"] = pending.id
    if settings.DEBUG:
        response["verification_token"] = raw_token
    return response


@router.post("/verify-email")
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def signup_verify_email(
    request: Request, body: VerifyEmail, db: AsyncSession = Depends(get_db),
):
    """Gate 1. Consumes a single-use token."""
    pending = await svc.verify_email(db, body.token)
    if pending is None:
        raise HTTPException(status_code=400, detail="Invalid or expired verification link")
    await db.commit()
    return {
        "email": pending.email,
        "email_verified": True,
        "paid": pending.paid,
        "next": "checkout" if not pending.paid else "complete",
    }


@router.post("/checkout")
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def signup_checkout(
    request: Request, body: CheckoutStart, db: AsyncSession = Depends(get_db),
):
    """Start payment. Refuses until the email is verified."""
    pending = await svc.get(db, body.email)
    if pending is None or pending.is_expired():
        raise HTTPException(status_code=404, detail="No signup in progress for that address")
    if not pending.email_verified:
        raise HTTPException(status_code=403, detail="Verify your email address first")

    # Provider checkout for a not-yet-existing user needs a customer reference
    # that is not a user id. Not wired: the subscription rails 503 without live
    # provider keys anyway (see DEPLOYMENT_TASKS.md), so pretending otherwise
    # would be inventing a flow that cannot be tested.
    raise HTTPException(
        status_code=503,
        detail=(
            "Payment is not yet available for pre-account signup. "
            "The account will be created once payment is recorded."
        ),
    )


@router.post("/complete")
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def signup_complete(
    request: Request, body: CompleteSignup, db: AsyncSession = Depends(get_db),
):
    """Gate 2 — record payment, then create the account.

    Both gates are re-checked inside `materialise()`, so this endpoint cannot be
    used to create an account for an unverified address.
    """
    pending = await svc.mark_paid(db, body.email, body.provider, body.reference_id)
    if pending is None:
        raise HTTPException(
            status_code=400,
            detail="No verified signup in progress for that address",
        )

    user = await svc.materialise(db, pending)
    if user is None:
        raise HTTPException(status_code=409, detail="Signup is not ready to complete")

    await db.commit()
    return {
        "message": "Account created. You can now sign in.",
        "user_id": user.id,
        "email": user.email,
    }


@router.get("/status")
async def signup_status(email: str, db: AsyncSession = Depends(get_db)):
    """Where a signup has got to. Returns 404 for unknown addresses."""
    pending = await svc.get(db, email)
    if pending is None:
        raise HTTPException(status_code=404, detail="No signup in progress")
    return {
        "email": pending.email,
        "email_verified": pending.email_verified,
        "paid": pending.paid,
        "expired": pending.is_expired(),
        "next": (
            "verify-email" if not pending.email_verified
            else "checkout" if not pending.paid
            else "complete"
        ),
    }


@router.post("/resend")
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def signup_resend(
    request: Request, body: ResendRequest, db: AsyncSession = Depends(get_db),
):
    """Issue a fresh verification token for a pending signup."""
    pending = await svc.get(db, body.email)
    if pending is None or pending.is_expired() or pending.email_verified:
        return _sent_message()

    if pending.verification_attempts >= svc.MAX_VERIFICATION_ATTEMPTS:
        raise HTTPException(status_code=429, detail="Too many verification emails requested")

    raw, token_hash = svc.new_token()
    pending.verification_token_hash = token_hash
    pending.verification_sent_at = svc._now()
    pending.verification_attempts += 1
    await db.commit()

    response = _sent_message()
    if settings.DEBUG:
        response["verification_token"] = raw
    return response
