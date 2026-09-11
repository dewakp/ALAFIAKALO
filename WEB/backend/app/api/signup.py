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
    # Two fields, not one. A single `full_name` cannot be sorted, greeted or
    # matched on — a clinician list cannot render "Okafor, N." from it without
    # guessing which word is the surname.
    #
    # min_length=3: "longer than 2 letters" as specified. Real short names exist
    # (Li, Ng, Bo), so this WILL turn some real people away — a deliberate rule,
    # applied at the boundary rather than hidden in the UI, so every client
    # enforces the same thing.
    first_name: str = Field(min_length=3, max_length=100)
    last_name: str = Field(min_length=3, max_length=100)
    # Accepted for older clients; derived from the parts when absent.
    full_name: str | None = Field(default=None, max_length=255)
    # Required: an account holder must be an adult by their jurisdiction's
    # standard, and we cannot evaluate that rule without a date of birth.
    # `country` selects the threshold — absent, the strictest (16) applies.
    date_of_birth: str = Field(description="ISO YYYY-MM-DD")
    # Optional, and the reason it is here at all: the one-step form this flow
    # replaced collected it, and the login path looks accounts up by it.
    phone: str | None = Field(default=None, max_length=32)
    country: str | None = Field(default=None, max_length=2)


class VerifyEmail(BaseModel):
    token: str


class ResendRequest(BaseModel):
    email: EmailStr


class CheckoutStart(BaseModel):
    email: EmailStr
    provider: str = Field(default="stripe", pattern="^stripe$")
    interval: str = Field(default="month", pattern="^(month|year)$")


class CompleteMobileSignup(BaseModel):
    """Store-billed completion. No provider reference: there is no payment yet."""

    email: EmailStr


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

    # `full_name` is DERIVED, never asked for twice. Keeping it in step here
    # means every existing reader — greetings, clinician lists, the 85 rows that
    # predate the split — keeps working without a second source of truth.
    display_name = (body.full_name
                    or f"{body.first_name.strip()} {body.last_name.strip()}".strip())
    pending, raw_token = await svc.start(
        db, body.email, body.password, display_name,
        date_of_birth=body.date_of_birth, country=body.country,
        first_name=body.first_name.strip(), last_name=body.last_name.strip(),
        phone=(body.phone or "").strip() or None,
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
    """Start payment.

    Payment no longer waits on the verification click. Requiring it first meant
    leaving the app, opening a mailbox and coming back — and the signup that
    prompted this change never got that far: the account was created silently,
    with no mail and no payment, and the person had no way to tell.

    The mailbox is still proven before the ACCOUNT exists (`/complete`); what
    changed is that the money can be taken while the person is still here.

    Because payment now precedes proof, a typo becomes someone who paid and
    cannot be reached. `can_receive_mail` is the cheap guard against that: a
    domain with no MX record can never accept mail, whoever typed it. It fails
    OPEN, so a DNS wobble does not refuse a paying customer.
    """
    pending = await svc.get(db, body.email)
    if pending is None or pending.is_expired():
        raise HTTPException(status_code=404, detail="No signup in progress for that address")

    if not pending.email_verified:
        from app.services.email_deliverability import can_receive_mail

        deliverable, reason = await can_receive_mail(body.email)
        if not deliverable:
            raise HTTPException(status_code=422, detail=reason)

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

    # The receipt goes out on PAYMENT, not on account creation. Money has
    # changed hands and the payer is entitled to a record of it whether or not
    # they have clicked the verification link yet — waiting would leave a paid
    # customer with nothing in writing. Best-effort: a mail outage must never
    # fail a completed payment (§3ah).
    # Deliberately does NOT mint a new token. Only the hash is stored, so a
    # fresh token would overwrite it and silently BREAK the link already sitting
    # in their inbox — the one they are most likely to click. Tested: doing that
    # made a correct verification fail after payment.
    #
    # The receipt therefore points at the signup page, which can resend on
    # request, rather than carrying a link that invalidates another one.
    verify_url = (f"{settings.PUBLIC_WEB_URL.rstrip('/')}/signup?email="
                  f"{pending.email}") if not pending.email_verified else None
    try:
        await email_service.send_signup_receipt_email(
            pending.email,
            full_name=pending.full_name,
            plan_label="ALAFIA Membership",
            verification_pending=not pending.email_verified,
            verify_url=verify_url,
        )
    except Exception:  # noqa: BLE001
        logger.warning("could not send signup receipt to %s", pending.email, exc_info=True)

    # The ACCOUNT still waits on a proven mailbox. Payment alone does not make
    # one: "nothing exists until a real mailbox is proven AND a subscription is
    # paid" is the whole point of this flow.
    if not pending.email_verified:
        await db.commit()
        return {
            "message": ("Payment received. Check your email and confirm your "
                        "address to finish setting up your account."),
            "paid": True,
            "email_verified": False,
            "email": pending.email,
        }

    user = await svc.materialise(db, pending)
    if user is None:
        raise HTTPException(status_code=409, detail="Signup is not ready to complete")

    await db.commit()
    return {
        "message": "Account created. You can now sign in.",
        "paid": True,
        "email_verified": True,
        "user_id": user.id,
        "email": user.email,
    }


@router.post("/complete-mobile")
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def signup_complete_mobile(
    request: Request,
    body: CompleteMobileSignup,
    db: AsyncSession = Depends(get_db),
):
    """Finish a signup whose payment is billed by the app store.

    iOS and Android CANNOT use the Stripe leg. Apple and Google require digital
    subscriptions to be sold through their own in-app purchase, and an IAP
    receipt has to be attached to an account — which does not exist yet. So the
    order that works on web (verify, pay, create) is impossible on a phone.

    What this path does NOT do is grant entitlement. The account is created
    **verified and unpaid**, and every gated route still answers 402 until a
    real subscription exists — `SUBSCRIPTION_REQUIRED` is on in production and
    both clients gate the whole app on `GET /subscription/status` (§3ah). So
    the purchase still has to happen; it happens at the paywall, one screen
    later, instead of before the account exists.

    The gate this DOES enforce is the one mobile was missing entirely: the
    address is verified before an account is made. `/auth/register` created a
    loginable account for any address anyone typed, which is how a real person
    ended up with an account they could not get into and no email to tell them.

    It is deliberately NOT a way to skip payment on web. Creating an account
    here buys nothing a paywalled 402 does not already refuse, and the flow is
    rate limited like every other auth route.
    """
    pending = await svc.get(db, body.email)
    if pending is None or pending.is_expired():
        raise HTTPException(status_code=400, detail="No signup in progress for that address")

    # Email verification is NOT waived — it is the whole point of this path.
    if not pending.email_verified:
        raise HTTPException(
            status_code=409,
            detail="Confirm your email address first — check your inbox for the link.",
        )

    user = await svc.materialise(db, pending, require_paid=False)
    await db.commit()
    return {
        "message": "Account created. Sign in and choose a plan to start.",
        "email_verified": True,
        # Stated plainly so a client cannot mistake this for an entitlement.
        "paid": False,
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
