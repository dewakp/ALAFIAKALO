"""Authentication endpoints."""

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status, BackgroundTasks
from fastapi.security import OAuth2PasswordRequestForm
from jose import JWTError, jwt
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
    """Register a new user."""
    result = await db.execute(select(User).where(User.email == user_in.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

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
        preferred_language=user_in.preferred_language,
        # Default the measurement system from the signup locale/country
        # (metric everywhere except US/Liberia/Myanmar); an explicit choice wins.
        preferred_units=user_in.preferred_units
        or units_for_locale(user_in.locale, user_in.country),
    )
    db.add(user)
    await db.flush()

    # Generate 255-char System Identifier
    names = user_in.full_name.split()
    first_name = names[0] if names else "XXX"
    last_name = names[-1] if len(names) > 1 else "XXX"
    sid = generate_sid(first_name, last_name, user_in.date_of_birth, user_in.gender_at_birth)
    user.system_id = sid

    # Persist SID audit log
    segments = get_segments_for_log(first_name, last_name, user_in.date_of_birth, user_in.gender_at_birth)
    sid_log = SystemIdLog(user_id=user.id, system_id=sid, **segments)
    db.add(sid_log)

    await db.flush()
    await db.refresh(user)
    return user


@router.post("/login", response_model=Token)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def login(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """Login and receive a JWT token."""
    result = await db.execute(select(User).where(User.email == form_data.username))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    # Try local password first
    local_ok = verify_password(form_data.password, user.hashed_password)

    if not local_ok and user.firebase_uid and user.auth_provider == "password":
        # Migrated Firebase password user — verify against Firebase Auth, then update local hash
        firebase_ok = await _verify_firebase_password(user.email, form_data.password)
        if firebase_ok:
            user.hashed_password = hash_password(form_data.password)
            await db.commit()
            logger.info("Updated local password hash for Firebase user %s", user.email)
            local_ok = True

    if not local_ok:
        # For OAuth-only users, give a more helpful error
        if user.firebase_uid and user.auth_provider != "password":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"This account uses {user.auth_provider} sign-in. Please use the appropriate login method.",
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

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

    try:
        payload = jwt.decode(raw_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid refresh token")
    except JWTError:
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

    user.hashed_password = hash_password(body.new_password)
    await db.flush()
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
