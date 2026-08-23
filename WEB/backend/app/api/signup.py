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

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.age_policy import AgeRestricted, InvalidDateOfBirth, assert_adult
from app.core.rate_limit import limiter
from app.services import email as email_service
from app.services import signup_service as svc

router = APIRouter()
logger = logging.getLogger(__name__)


class SignupStart(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)
    # Required: an account holder must be an adult by their jurisdiction's
    # standard, and we cannot evaluate that rule without a date of birth.
    # `country` selects the threshold — absent, the strictest (16) applies.
    date_of_birth: str = Field(description="ISO YYYY-MM-DD")
    country: str | None = Field(default=None, max_length=2)


class VerifyEmail(BaseModel):
    token: str


class ResendRequest(BaseModel):
    email: EmailStr


class CheckoutStart(BaseModel):
    email: EmailStr
    provider: str = Field(default="stripe", pattern="^stripe$")
    interval: str = Field(default="month", pattern="^(month|year)$")


class CompleteSignup(BaseModel):
    email: EmailStr
    provider: str = Field(default="stripe", pattern="^stripe$")
    reference_id: str


def _sent_message() -> dict:
    # Identical whether or not the address is already in use — signup must not
    # become an oracle for which emails have accounts.
    return {"message": "If that address can receive mail, a verification link has been sent."}


async def _deliver_verification(
    background_tasks: BackgroundTasks, email: str, raw_token: str, pending_id: int | None = None,
) -> dict:
    """Send the verification link, or fail loudly when mail cannot be sent.

    Three cases, deliberately distinct:

      SMTP configured           → queue the mail, return NOTHING about the token.
      not configured, DEBUG     → return the token inline so dev can proceed.
      not configured, prod      → 503. Accepting a signup that can never be
                                  verified would strand the user and quietly
                                  reintroduce the unverified-account problem.
    """
    if email_service.smtp_configured():
        background_tasks.add_task(email_service.send_verification_email, email, raw_token)
        response = _sent_message()
        if pending_id is not None:
            response["pending_id"] = pending_id
        return response

    if settings.DEBUG:
        logger.warning("SMTP not configured — returning verification token inline (DEBUG only)")
        response = _sent_message()
        if pending_id is not None:
            response["pending_id"] = pending_id
        response["verification_token"] = raw_token
        response["warning"] = "SMTP is not configured; token returned inline for development."
        return response

    logger.error("Signup attempted for %s but SMTP is not configured — refusing", email)
    raise HTTPException(
        status_code=503,
        detail="Account signup is temporarily unavailable. Please try again shortly.",
    )


@router.post("/start", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def signup_start(
    request: Request, body: SignupStart, background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Begin a signup. Creates NO account — only a pending record."""
    # Age is gate 0, checked before the verification email and before payment.
    # Refusing someone after they have paid means a refund and a bad first
    # impression; refusing before anything happens costs nothing.
    try:
        assert_adult(body.date_of_birth, body.country)
    except InvalidDateOfBirth as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Date of birth is required to create an account ({exc}).",
        ) from exc
    except AgeRestricted as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"You must be at least {exc.minimum_age} to hold an ALAFIA account "
                "in your country. A parent or guardian can create an account and "
                "add you as a dependent."
            ),
        ) from exc

    if await svc.email_taken(db, body.email):
        # Same response as success, so the endpoint cannot enumerate accounts.
        return _sent_message()

    pending, raw_token = await svc.start(
        db, body.email, body.password, body.full_name,
        date_of_birth=body.date_of_birth, country=body.country,
    )
    await db.commit()
    return await _deliver_verification(background_tasks, body.email, raw_token, pending.id)


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

    # `provider` is pinned to "stripe" by the schema, so an unsupported rail is
    # refused as a 422 on the field rather than a 503 from inside the flow.
    from app.services import subscription_service as subs
    result = await subs.signup_stripe_checkout(pending.email, body.interval)
    return {
        "provider": "stripe",
        "checkout_url": result["checkout_url"],
        "reference_id": result["reference_id"],
        "test_mode": result.get("test_mode", False),
    }


@router.post("/complete")
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def signup_complete(
    request: Request, body: CompleteSignup, db: AsyncSession = Depends(get_db),
):
    """Gate 2 — record payment, then create the account.

    Both gates are re-checked inside `materialise()`, so this endpoint cannot be
    used to create an account for an unverified address.
    """
    pending = await svc.get(db, body.email)
    if pending is None or pending.is_expired():
        raise HTTPException(status_code=400, detail="No signup in progress for that address")
    if not pending.email_verified:
        raise HTTPException(status_code=403, detail="Verify your email address first")

    # Confirm the payment WITH THE PROVIDER before recording it.
    #
    # Taking the caller's word for `reference_id` would mean any string bought
    # an account — the exact hole the two-step flow exists to close. Stripe is
    # asked whether this session is paid AND whether it belongs to this signup.
    if body.provider != "stripe":
        raise HTTPException(status_code=503, detail="Only card checkout is available right now.")

    from app.services import subscription_service as subs
    await subs.signup_stripe_verify(pending.email, body.reference_id)

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
    request: Request, body: ResendRequest, background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
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
    return await _deliver_verification(background_tasks, pending.email, raw)
