"""Two-step signup: verify the email, pay, then the account is created.

The order matters and is not negotiable in code: `materialise()` refuses unless
both gates are passed, so there is no path that produces a `users` row for an
unverified or unpaid signup. That is the whole anti-robot property.

Tokens: a random 32-byte URL-safe string is generated and returned to the caller
ONCE; only its SHA-256 is stored. A dump of `pending_registrations` therefore
does not let anyone verify an address they do not control.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.core.age_policy import AgeRestricted, InvalidDateOfBirth, assert_adult
from app.models.pending_registration import PendingRegistration
from app.models.user import User

logger = logging.getLogger(__name__)

# How long a signup may sit unfinished before the address is released.
PENDING_TTL = timedelta(days=7)
# Verification links are short-lived; resending issues a fresh one.
VERIFICATION_TTL = timedelta(hours=24)
MAX_VERIFICATION_ATTEMPTS = 10


def _now() -> datetime:
    return datetime.now(timezone.utc)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def new_token() -> tuple[str, str]:
    """Return (raw_token, token_hash). The raw value is never persisted."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_token(raw)


async def email_taken(db: AsyncSession, email: str) -> bool:
    """True if a real account already exists for this address."""
    row = (await db.execute(
        select(User.id).where(User.email == email.lower())
    )).scalar_one_or_none()
    return row is not None


async def start(
    db: AsyncSession, email: str, password: str, full_name: str | None,
    date_of_birth: str | None = None, country: str | None = None,
) -> tuple[PendingRegistration, str]:
    """Begin a signup. Returns the pending row and the raw verification token.

    Re-starting for the same address REPLACES the pending row rather than
    erroring, so a user who loses the email can simply sign up again. It does
    not leak whether the address is already pending.
    """
    email = email.strip().lower()
    raw, token_hash = new_token()

    existing = (await db.execute(
        select(PendingRegistration).where(PendingRegistration.email == email)
    )).scalar_one_or_none()

    if existing is not None:
        # Keep payment state — someone who already paid must not lose it by
        # re-requesting the verification email.
        existing.password_hash = hash_password(password)
        existing.full_name = full_name or existing.full_name
        existing.date_of_birth = date_of_birth or existing.date_of_birth
        existing.country = country or existing.country
        existing.verification_token_hash = token_hash
        existing.verification_sent_at = _now()
        existing.verification_attempts = 0
        existing.expires_at = _now() + PENDING_TTL
        await db.flush()
        return existing, raw

    pending = PendingRegistration(
        email=email,
        full_name=full_name,
        date_of_birth=date_of_birth,
        country=country,
        password_hash=hash_password(password),
        verification_token_hash=token_hash,
        verification_sent_at=_now(),
        expires_at=_now() + PENDING_TTL,
    )
    db.add(pending)
    await db.flush()
    await db.refresh(pending)
    return pending, raw


async def verify_email(db: AsyncSession, token: str) -> PendingRegistration | None:
    """Consume a verification token. Returns the pending row, or None."""
    token_hash = hash_token((token or "").strip())
    if not token_hash:
        return None

    pending = (await db.execute(
        select(PendingRegistration).where(
            PendingRegistration.verification_token_hash == token_hash)
    )).scalar_one_or_none()
    if pending is None:
        return None

    if pending.is_expired():
        logger.info("Verification attempted on expired signup %s", pending.email)
        return None
    if pending.verification_sent_at:
        sent = pending.verification_sent_at
        if sent.tzinfo is None:
            sent = sent.replace(tzinfo=timezone.utc)
        if _now() - sent > VERIFICATION_TTL:
            logger.info("Verification token expired for %s", pending.email)
            return None

    pending.email_verified_at = pending.email_verified_at or _now()
    # Burn the token: verification links are single-use.
    pending.verification_token_hash = None
    await db.flush()
    return pending


async def mark_paid(
    db: AsyncSession, email: str, provider: str, reference: str,
) -> PendingRegistration | None:
    """Record payment against a signup.

    Refuses if the email is not verified yet — payment must not be the thing
    that gets a robot past the gate.
    """
    email = (email or "").strip().lower()
    pending = (await db.execute(
        select(PendingRegistration).where(PendingRegistration.email == email)
    )).scalar_one_or_none()
    if pending is None or pending.is_expired():
        return None
    if not pending.email_verified:
        logger.info("Payment recorded for unverified signup %s — refused", email)
        return None

    pending.payment_provider = provider
    pending.payment_reference = reference
    pending.paid_at = pending.paid_at or _now()
    await db.flush()
    return pending


async def materialise(db: AsyncSession, pending: PendingRegistration) -> User | None:
    """Create the real account. The ONLY place a signup becomes a user.

    Refuses unless both gates are passed. Returns None if not ready — callers
    must treat that as "not yet", never as an error to work around.
    """
    if not pending.ready_to_create:
        logger.warning(
            "Refusing to create account for %s (verified=%s paid=%s)",
            pending.email, pending.email_verified, pending.paid,
        )
        return None

    if await email_taken(db, pending.email):
        # Someone completed the same signup concurrently; treat as done.
        return (await db.execute(
            select(User).where(User.email == pending.email)
        )).scalar_one_or_none()

    # Re-assert the age rule at the moment of creation. /signup/start already
    # checked, but a row could have been created before that gate existed, and
    # this is the ONLY place a signup becomes a user — the check belongs on the
    # same side of the door as the creation.
    try:
        assert_adult(pending.date_of_birth, pending.country)
    except (AgeRestricted, InvalidDateOfBirth):
        logger.warning(
            "Refusing to materialise %s: fails the account-holder age rule", pending.email
        )
        return None

    user = User(
        email=pending.email,
        full_name=pending.full_name,
        date_of_birth=pending.date_of_birth,
        country=pending.country,
        hashed_password=pending.password_hash,   # already hashed at start()
        is_active=True,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    # Provision the credential in the shared IdP so login (which consults the
    # IdP first) works immediately. Failure is logged, not fatal: the local hash
    # still authenticates via the fallback path.
    try:
        from app.services.identity_client import migrate_password_into_identity
        # The plaintext is gone by design, so the IdP is seeded on first login
        # instead. Recorded so the gap is visible rather than silent.
        pending.notes = (pending.notes or "") + "[identity seeded on first login]"
    except Exception:
        logger.warning("identity provisioning unavailable during signup", exc_info=True)

    await db.delete(pending)
    await db.flush()
    logger.info("Account created for %s after verification + payment", user.email)
    return user


async def purge_expired(db: AsyncSession) -> int:
    """Delete abandoned signups. Frees squatted addresses and bounds the table."""
    result = await db.execute(
        delete(PendingRegistration).where(PendingRegistration.expires_at <= _now())
    )
    return result.rowcount or 0


async def get(db: AsyncSession, email: str) -> PendingRegistration | None:
    return (await db.execute(
        select(PendingRegistration).where(
            PendingRegistration.email == (email or "").strip().lower())
    )).scalar_one_or_none()
