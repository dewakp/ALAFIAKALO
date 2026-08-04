"""Authentication endpoints."""

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status, BackgroundTasks
from fastapi.security import OAuth2PasswordRequestForm
import jwt  # PyJWT (maintained); legacy HS512 refresh tokens during migration
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
from app.services.email import send_password_reset_email

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

    from app.services.identity_client import identity_register

    result = await db.execute(select(User).where(User.email == user_in.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    names = user_in.full_name.split()
    first_name = names[0] if names else "XXX"
    last_name = names[-1] if len(names) > 1 else "XXX"

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
    await db.flush()

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
        sso_user = (await db.execute(
            select(User).where(User.email == form_data.username)
        )).scalar_one_or_none()
        if sso_user is not None:
            await _record_login(db, sso_user)
        _set_refresh_cookie(response, ident.get("refresh_token", ""))
        return Token(access_token=ident["access_token"], refresh_token=ident.get("refresh_token", ""))

    result = await db.execute(select(User).where(User.email == form_data.username))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    # Legacy local-password fallback (PostgreSQL `users.hashed_password`) for accounts
    # not yet in the IdP. No Firebase verification — login is PostgreSQL only (canon).
    local_ok = verify_password(form_data.password, user.hashed_password)

    if not local_ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    await _record_login(db, user)
    token = create_access_token(data={"sub": str(user.id)})
    refresh = create_refresh_token(data={"sub": str(user.id)})
    _set_refresh_cookie(response, refresh)
    return Token(access_token=token, refresh_token=refresh)


from pydantic import BaseModel


class FirebaseTokenRequest(BaseModel):
    """Firebase ID token minted client-side by any Firebase Auth provider
    (google.com, apple.com, phone, password)."""
    id_token: str


@router.post("/firebase", response_model=Token)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def login_with_firebase(
    request: Request,
    response: Response,
    body: FirebaseTokenRequest,
    db: AsyncSession = Depends(get_db),
):
    """Exchange a Firebase Auth ID token for an ALAFIA session.

    Supports phone (OTP) and social (Google / Apple) sign-in: the frontend
    completes the provider flow with the Firebase JS SDK, then posts the ID
    token here. We verify it with the Admin SDK, link or create the local
    user (by firebase_uid → email → phone), and issue our JWTs.
    """
    from app.services.firebase_sync import get_firebase_app
    from firebase_admin import auth as firebase_auth

    if get_firebase_app() is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Firebase authentication is not configured on this server.",
        )

    try:
        decoded = await asyncio.to_thread(firebase_auth.verify_id_token, body.id_token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired sign-in token. Please try again.",
        )

    uid = decoded["uid"]
    email = decoded.get("email")
    phone = decoded.get("phone_number")
    name = decoded.get("name") or ""
    sign_in_provider = (decoded.get("firebase") or {}).get("sign_in_provider", "firebase")
    provider = {
        "google.com": "google",
        "apple.com": "apple",
        "phone": "phone",
        "password": "firebase",
    }.get(sign_in_provider, "firebase")

    # Link precedence: firebase_uid → verified email → phone number.
    user = (await db.execute(select(User).where(User.firebase_uid == uid))).scalar_one_or_none()
    if user is None and email:
        user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if user is None and phone:
        user = (await db.execute(select(User).where(User.phone_number == phone))).scalar_one_or_none()

    if user is None:
        if not email and not phone:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Sign-in token carries neither an email nor a phone number.",
            )
        import secrets

        # Phone-only accounts get a synthetic local email (email is NOT NULL/unique).
        # The random password is unguessable; these accounts sign in via Firebase only.
        user = User(
            email=email or f"phone_{uid}@alafia.local",
            hashed_password=hash_password(secrets.token_urlsafe(32)),
            full_name=name or (phone or email.split("@")[0]),
            firebase_uid=uid,
            phone_number=phone,
            auth_provider=provider,
        )
        db.add(user)
        await db.flush()
        await db.refresh(user)
        logger.info("Created user %s via Firebase %s sign-in", user.email, provider)
    else:
        # Keep the linkage current without clobbering existing identifiers.
        if not user.firebase_uid:
            user.firebase_uid = uid
        if phone and not user.phone_number:
            user.phone_number = phone
        if user.auth_provider in (None, "local"):
            user.auth_provider = provider
        await db.flush()

    await _record_login(db, user)
    token = create_access_token(data={"sub": str(user.id)})
    refresh = create_refresh_token(data={"sub": str(user.id)})
    _set_refresh_cookie(response, refresh)
    return Token(access_token=token, refresh_token=refresh)


async def _verify_firebase_password(email: str, password: str) -> bool:
    """
    Verify a password against Firebase Auth using the REST API.
    Firebase Admin SDK cannot verify passwords directly, so we use the
    Firebase Auth REST signInWithPassword endpoint.
    """
    import httpx

    api_key = settings.FIREBASE_WEB_API_KEY
    if not api_key:
        logger.warning("FIREBASE_WEB_API_KEY not configured — cannot verify Firebase passwords")
        return False

    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={api_key}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json={
                "email": email,
                "password": password,
                "returnSecureToken": False,
            })
        if resp.status_code == 200:
            return True
        return False
    except Exception as e:
        logger.error("Firebase password verification failed: %s", e)
        return False


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
    """Request a password reset. Returns reset token (in production, send via email)."""
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    # Always return 200 to avoid email enumeration
    if not user:
        return {"message": "If the email exists, a reset link has been sent."}

    reset_token = create_password_reset_token(user.id)
    background_tasks.add_task(send_password_reset_email, user.email, reset_token)
    response_body = {"message": "If the email exists, a reset link has been sent."}
    # Expose token directly only in debug mode (for dev/test convenience)
    if settings.DEBUG:
        response_body["reset_token"] = reset_token
    return response_body


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
