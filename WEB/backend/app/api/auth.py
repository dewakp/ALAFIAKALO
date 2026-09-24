"""Authentication endpoints."""

import logging
import secrets
from datetime import datetime, timezone

from pydantic import BaseModel

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status, BackgroundTasks
from fastapi.security import OAuth2PasswordRequestForm
import jwt  # PyJWT (maintained); legacy HS512 refresh tokens during migration
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.core.database import get_db
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    create_password_reset_token,
    verify_password_reset_token,
    get_current_user,
)
from app.models.user import User
from app.models.system_id import SystemIdLog
from app.schemas.user import (
    UserCreate,
    UserResponse,
    Token,
    RefreshTokenRequest,
    PasswordResetRequest,
    PasswordResetConfirm,
)
from app.services.sid_service import generate_sid, get_segments_for_log, verify_sid, decode_sid, mask_sid
from app.core.rate_limit import limiter
from app.core.units import units_for_locale
from app.core.age_policy import AgeRestricted, InvalidDateOfBirth, assert_adult
from app.services.email import password_reset_url, send_password_reset_email
from app.services.auth_alerts import client_ip, notify_admin_auth_failure
from app.core.phone import phone_candidates
from app.models.user_identity import UserIdentity
from app.services.oidc import OIDCError, verify_id_token

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/csrf-cookie", status_code=204)
async def csrf_cookie():
    """
    No-op GET endpoint whose sole purpose is to trigger the CSRF middleware
    to issue the csrf_token cookie.  Call this once before the first POST
    (e.g. on login page mount) so the double-submit check can succeed.
    """
    return Response(status_code=204)


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    """Set refresh token as httpOnly secure cookie."""
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=not settings.DEBUG,
        samesite="lax",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/api/v1/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(key="refresh_token", path="/api/v1/auth")


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def register(request: Request, user_in: UserCreate, db: AsyncSession = Depends(get_db)):
    """Register a new user.

    Provisions the user in the shared 6IGMA Identity service (the canonical IdP)
    and links the local ALAFIA reference row to it (same UUID + same canonical
    SID → zero duplication). Falls back to a local-only SID if identity is
    unavailable or the identity username collides.
    """
    # Direct registration is closed by default. It handed out a `users` row for
    # one unauthenticated POST, which is how 55 of the 77 accounts in this
    # database became automation leftovers. Leaving it open would make the
    # two-step flow decorative — a robot would simply keep using this door.
    if settings.TWO_STEP_SIGNUP_REQUIRED:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=(
                "Direct registration is closed. Start at /auth/signup/start — "
                "your email is verified and your subscription taken before the "
                "account is created."
            ),
        )

    # An account holder must be an adult by their own jurisdiction's standard.
    # A child is never an account holder — they are a dependent profile under a
    # consenting adult. Enforced HERE, not in the clients: web, iOS and Android
    # all post to this endpoint, and anyone can post to it directly, so a
    # client-side birthday picker is UX and this is the actual gate.
    try:
        assert_adult(user_in.date_of_birth, user_in.country)
    except InvalidDateOfBirth as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Date of birth is required to create an account ({exc}).",
        ) from exc
    except AgeRestricted as exc:
        # Say what the rule is. A bare refusal reads as a bug, and the adult who
        # should be creating this account needs to know they can.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"You must be at least {exc.minimum_age} to hold an ALAFIA account "
                "in your country. A parent or guardian can create an account and "
                "add you as a dependent."
            ),
        ) from exc

    from app.services.identity_client import identity_register

    result = await db.execute(select(User).where(User.email == user_in.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    # The client sends the parts; nothing is guessed and nothing is invented.
    first_name = user_in.first_name.strip()
    last_name = user_in.last_name.strip()

    # 1) Create the canonical identity user (single source of truth).
    istatus, ireg = await identity_register({
        "email": user_in.email,
        "username": user_in.email.split("@")[0],
        "password": user_in.password,
        "first_name": first_name,
        "last_name": last_name,
        "date_of_birth": user_in.date_of_birth,
        "gender": user_in.gender,
        "biological_sex": user_in.gender_at_birth,
        "account_role": "patient",
        "phone": user_in.phone,
    })
    identity_uid = sid = None
    if istatus == 201 and ireg:
        identity_uid = ireg["user"]["id"]
        sid = (ireg["user"].get("system_id") or "").strip() or None
    elif istatus == 409:
        raise HTTPException(status_code=400, detail="Email or username already registered")

    user = User(
        email=user_in.email,
        hashed_password=hash_password(user_in.password),
        full_name=user_in.full_name,
        first_name=first_name,
        last_name=last_name,
        date_of_birth=user_in.date_of_birth,
        gender=user_in.gender,
        gender_at_birth=user_in.gender_at_birth,
        blood_type=user_in.blood_type,
        insurance_id=user_in.insurance_id,
        insurance_provider=user_in.insurance_provider,
        insurance_country=user_in.insurance_country,
        locale=user_in.locale,
        timezone=user_in.timezone,
        country=user_in.country,
        phone_number=user_in.phone,
        preferred_language=user_in.preferred_language,
        preferred_units=user_in.preferred_units
        or units_for_locale(user_in.locale, user_in.country),
        identity_uid=identity_uid,
    )
    db.add(user)
    try:
        await db.flush()
    except IntegrityError:
        # The pre-check above is not a lock. Two registrations for the same
        # address arriving together both pass it, then both insert, and the
        # loser hits ix_users_email — which surfaced as a 500 in production
        # while the FIRST request had already created the account. The user saw
        # a server error for a signup that had actually succeeded, retried, and
        # the retries then tripped the auth rate limiter into 429s.
        #
        # Only the database can settle a uniqueness race, so the answer is the
        # same one the pre-check gives: this address is taken.
        await db.rollback()
        raise HTTPException(status_code=400, detail="Email or username already registered")

    # Use the identity-minted canonical SID; fall back to a local canonical SID.
    if not sid:
        sid = generate_sid(first_name, last_name, user_in.date_of_birth, user_in.gender_at_birth)
    user.system_id = sid

    segments = get_segments_for_log(first_name, last_name, user_in.date_of_birth, user_in.gender_at_birth)
    db.add(SystemIdLog(user_id=user.id, system_id=sid, **segments))

    await db.flush()
    await db.refresh(user)
    return user


async def _record_login(db, user) -> None:
    """Stamp a successful authentication.

    Called from every auth path, so the admin console's "last login" reflects
    reality regardless of how the user signed in. Never raises: a bookkeeping
    write must not turn a good login into a failed one.
    """
    try:
        user.last_login = datetime.now(timezone.utc)
        await db.flush()
    except Exception:
        logger.warning("Could not stamp last_login for user %s", getattr(user, "id", "?"), exc_info=True)


async def _find_by_identifier(db: AsyncSession, identifier: str) -> User | None:
    """Resolve the login identifier, which is an email OR a phone number.

    The login form has had a Phone tab all along and this lookup only ever
    compared `users.email`, so a correct number with a correct password was
    answered "Incorrect email or password" — a real account, refused, with the
    message naming a field the person never filled in.

    Email first: it is the common case and unique. Then the candidate stored
    FORMS of a typed number (§3e) — never a `regexp_replace` in the WHERE
    clause, which would be Postgres-only and unindexable.

    `phone_number` carries a UNIQUE index (`ix_users_phone_number`), so at most
    one row can match — verified against the database, after first assuming the
    opposite. `.first()` is kept anyway: if that index is ever relaxed, a
    duplicated number should refuse the login rather than raise
    MultipleResultsFound and answer 500 to everyone who shares it.
    """
    identifier = (identifier or "").strip()
    if not identifier:
        return None

    user = (await db.execute(
        select(User).where(User.email == identifier)
    )).scalar_one_or_none()
    if user is not None:
        return user

    forms = phone_candidates(identifier)
    if not forms:
        return None
    return (await db.execute(
        select(User).where(User.phone_number.in_(forms)).order_by(User.id)
    )).scalars().first()


#: ONE sentence for every credential failure, so the two can never drift apart.
#: An unknown identifier and a wrong password must be indistinguishable to the
#: caller or the 401 becomes an account-existence oracle (§3e). It says
#: "credentials" rather than "email" because the form also accepts a phone
#: number, and answering "Incorrect email or password" to someone who typed a
#: phone number describes a field they never filled in.
_BAD_CREDENTIALS = "Those credentials did not match an account."


@router.post("/login", response_model=Token)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def login(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """Login and receive a JWT token.

    CANON: authentication is PostgreSQL only — the shared 6IGMA Identity service
    (PostgreSQL-native IdP → one credential set + SSO across ALAFIA and FlowSheet),
    with a legacy local-password fallback (also PostgreSQL) during the migration
    window. Firebase is never consulted for login.
    """
    from app.services.identity_client import identity_login
    ident = await identity_login(form_data.username, form_data.password)
    if ident and ident.get("access_token"):
        # Stamp here too. This branch returns before the local-password path
        # below, and it is the branch most logins actually take (shared IdP →
        # SSO), so skipping it left last_login NULL for everyone.
        sso_user = await _find_by_identifier(db, form_data.username)
        if sso_user is not None:
            await _record_login(db, sso_user)
        _set_refresh_cookie(response, ident.get("refresh_token", ""))
        return Token(access_token=ident["access_token"], refresh_token=ident.get("refresh_token", ""))

    user = await _find_by_identifier(db, form_data.username)

    if not user:
        # The operator is told which address was tried; the CALLER still gets
        # the same sentence as a wrong password, so the response cannot be used
        # to tell a registered address from an unregistered one (§3e).
        await notify_admin_auth_failure(
            kind="login", reason="no_such_account",
            email=form_data.username, client_ip=client_ip(request),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_BAD_CREDENTIALS,
        )

    # Legacy local-password fallback (PostgreSQL `users.hashed_password`) for accounts
    # not yet in the IdP. No Firebase verification — login is PostgreSQL only (canon).
    local_ok = verify_password(form_data.password, user.hashed_password)

    if not local_ok:
        await notify_admin_auth_failure(
            kind="login", reason="bad_password",
            email=form_data.username, client_ip=client_ip(request),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_BAD_CREDENTIALS,
        )

    await _record_login(db, user)
    token = create_access_token(data={"sub": str(user.id)})
    refresh = create_refresh_token(data={"sub": str(user.id)})
    _set_refresh_cookie(response, refresh)
    return Token(access_token=token, refresh_token=refresh)


# NOTE: /auth/firebase is RETIRED (2026-09-24).
#
# Social sign-in now verifies the provider's OWN ID token against Google's or
# Apple's published JWKS — see app/services/oidc.py. Firebase brokered nothing
# that ever worked here: Apple was never configured as a provider at all, and
# this endpoint answered 503 to everything because FIREBASE_SERVICE_ACCOUNT was
# empty while the `firebase-sa` secret sat unmounted in Secret Manager.
#
# Kept as a 410 rather than deleted, so anything still pointed at it is told what
# happened instead of meeting a bare 404 — but nothing is: the web path is gone,
# and both mobile clients' exchange methods had ZERO callers and were removed.
#
# `firebase-admin` itself STAYS: services/firebase_sync.py uses it for the
# Firestore sync, which is a different feature from authentication.
#
# `_verify_firebase_password` went with it — a helper with no callers, which is
# why this range was read before it was deleted rather than swept by line count.
@router.post("/firebase", include_in_schema=False)
async def login_with_firebase_retired():
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail=("Firebase sign-in has been retired. Use POST /auth/oidc with "
                "{provider, id_token}."),
    )


class OIDCLoginRequest(BaseModel):
    """An ID token minted by the provider itself, and which provider minted it.

    The provider is named by the CLIENT because the token must be checked
    against that provider's issuer and JWKS — but it is not trusted: an
    unrecognised name is refused, and a token whose `iss` belongs to the other
    provider fails verification.
    """
    provider: str
    id_token: str


@router.post("/oidc", response_model=Token)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def login_with_oidc(
    request: Request,
    response: Response,
    body: OIDCLoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """Sign in with Google or Apple, verified directly against the provider.

    Resolution order, and each step exists for a reason:

    1. **The stored (provider, subject) link.** `sub` is the only identifier the
       provider guarantees is stable. Apple sends `email` on the FIRST
       authorization only, so on every later sign-in this link is all there is.
    2. **A VERIFIED email matching an existing account**, which then gets linked
       so step 1 answers next time. The verification check is the whole safety
       of this step: matching on an unverified address would let anyone who can
       mint a token for `someone@example.com` walk into that person's account.
    3. **Create**, when `OIDC_ALLOW_SIGNUP` permits it and the email is verified.
    """
    try:
        identity = await verify_id_token(body.provider, body.id_token)
    except OIDCError as exc:
        await notify_admin_auth_failure(
            kind="login", reason=f"oidc_rejected_{body.provider}",
            client_ip=client_ip(request), detail=str(exc),
        )
        # The verifier's sentence already distinguishes an expired token from an
        # unconfigured provider from a JWKS outage (§3ae) — do not flatten it.
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))

    link = (await db.execute(
        select(UserIdentity).where(
            UserIdentity.provider == identity.provider,
            UserIdentity.subject == identity.subject,
        )
    )).scalars().first()

    user = None
    if link is not None:
        user = (await db.execute(
            select(User).where(User.id == link.user_id)
        )).scalar_one_or_none()

    if user is None and identity.email and identity.email_verified:
        user = (await db.execute(
            select(User).where(User.email == identity.email)
        )).scalar_one_or_none()

    if user is None:
        if not settings.OIDC_ALLOW_SIGNUP:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=("No ALAFIA account is linked to that sign-in. Please "
                        "sign up first, then link it from your profile."),
            )
        if not (identity.email and identity.email_verified):
            # Without a verified address there is nothing to key the account on
            # and no proof of mailbox control — the gate two-step signup exists
            # to enforce (§3as).
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=("That sign-in did not supply a verified email address, "
                        "so an account cannot be created from it."),
            )
        user = User(
            email=identity.email,
            # Unguessable: this account signs in through the provider, and a
            # blank or predictable password would be a second way in.
            hashed_password=hash_password(secrets.token_urlsafe(32)),
            full_name=identity.name or identity.email.split("@")[0],
            auth_provider=identity.provider,
        )
        db.add(user)
        await db.flush()
        await db.refresh(user)
        logger.info("Created user %s via %s sign-in", user.id, identity.provider)

    if not user.is_active:
        # A deactivated account must not be revived by a social sign-in.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="That account is not active.",
        )

    now = datetime.now(timezone.utc)
    if link is None:
        db.add(UserIdentity(
            user_id=user.id, provider=identity.provider, subject=identity.subject,
            email=identity.email, last_used_at=now,
        ))
    else:
        link.last_used_at = now
    await db.flush()

    await _record_login(db, user)
    token = create_access_token(data={"sub": str(user.id)})
    refresh = create_refresh_token(data={"sub": str(user.id)})
    _set_refresh_cookie(response, refresh)
    return Token(access_token=token, refresh_token=refresh)


@router.post("/refresh", response_model=Token)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def refresh_token(
    request: Request,
    response: Response,
    body: RefreshTokenRequest | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Exchange a valid refresh token for a new access + refresh token pair."""
    # Accept refresh token from httpOnly cookie or request body
    raw_token = request.cookies.get("refresh_token") or (body.refresh_token if body else None)
    if not raw_token:
        raise HTTPException(status_code=401, detail="Refresh token required")

    # Identity-issued (HS512) refresh tokens → delegate to the shared IdP, which
    # returns a fresh hybrid PQC access token + refresh token.
    from app.services.identity_client import identity_refresh
    ident = await identity_refresh(raw_token)
    if ident and ident.get("access_token"):
        _set_refresh_cookie(response, ident.get("refresh_token", ""))
        return Token(access_token=ident["access_token"], refresh_token=ident.get("refresh_token", ""))

    try:
        payload = jwt.decode(raw_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid refresh token")
    except jwt.PyJWTError:
        _clear_refresh_cookie(response)
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        _clear_refresh_cookie(response)
        raise HTTPException(status_code=401, detail="User not found or inactive")

    new_access = create_access_token(data={"sub": str(user.id)})
    new_refresh = create_refresh_token(data={"sub": str(user.id)})
    _set_refresh_cookie(response, new_refresh)
    return Token(access_token=new_access, refresh_token=new_refresh)


@router.post("/password-reset/request", status_code=status.HTTP_200_OK)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def request_password_reset(
    request: Request,
    body: PasswordResetRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Request a password reset. The token is delivered ONLY by email.

    The reset token is deliberately never part of this response, under any
    setting. It used to be included when DEBUG was true, which meant a single
    boolean stood between the deployment and trivial account takeover: POST any
    address, read the token out of the JSON, own the account. The
    "If the email exists" wording is meant to prevent enumeration, and returning
    a working token in that same response made it theatre.

    Dev convenience is preserved by logging the link server-side (below) — visible
    to whoever runs the backend, which is the person who needs it, and to nobody
    who merely sends it an HTTP request.
    """
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    # Always return 200 to avoid email enumeration
    if not user:
        return {"message": "If the email exists, a reset link has been sent."}

    reset_token = create_password_reset_token(user.id)
    background_tasks.add_task(send_password_reset_email, user.email, reset_token)
    if settings.DEBUG:
        # Local development only: the console is not reachable over the network.
        logger.info("DEBUG password reset link: %s", password_reset_url(reset_token))
    return {"message": "If the email exists, a reset link has been sent."}


@router.post("/password-reset/confirm", status_code=status.HTTP_200_OK)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def confirm_password_reset(
    request: Request,
    body: PasswordResetConfirm,
    db: AsyncSession = Depends(get_db),
):
    """Reset password using a valid reset token."""
    user_id = verify_password_reset_token(body.token)
    if user_id is None:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Update BOTH credential stores.
    #
    # Login consults the shared identity service FIRST and only falls back to
    # this local hash. Writing only the local hash therefore does not revoke the
    # old password: the user's previous credential still authenticates via the
    # IdP, so a "successful" reset leaves TWO working passwords. Verified
    # empirically — after a local-only reset, both old and new returned 200.
    user.hashed_password = hash_password(body.new_password)
    await db.flush()

    # Identity-backed accounts (every migrated user) must be propagated, and a
    # failure here has to surface. Reporting success while the old password
    # still works is the dangerous outcome.
    from app.services.identity_client import migrate_password_into_identity

    if settings.IDENTITY_ENABLED:
        propagated = await migrate_password_into_identity(user.email, body.new_password)
        if not propagated and user.identity_uid:
            logger.error(
                "Password reset for user %s could not be propagated to the identity "
                "service; the previous password may still be valid.", user.id,
            )
            raise HTTPException(
                status_code=503,
                detail=(
                    "Could not complete the password reset. Your previous password "
                    "may still be active — please try again."
                ),
            )

    return {"message": "Password has been reset successfully."}


@router.get("/me/system-id")
async def get_system_id(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the current user's 255-char System Identifier with decoded segments."""
    sid = current_user.system_id
    if not sid:
        raise HTTPException(404, "System Identifier not yet assigned")
    return {
        "system_id": sid,
        "masked": mask_sid(sid),
        "segments": decode_sid(sid),
        "valid": verify_sid(sid),
    }
