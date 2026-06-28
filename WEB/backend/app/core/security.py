"""Authentication & authorization utilities."""

from datetime import datetime, timedelta, timezone

import jwt  # PyJWT (maintained); legacy HS512 tokens during the migration window
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.core.database import get_db

# Argon2id for new hashes; bcrypt kept so legacy $2b$ hashes still verify (and can
# be rehashed). Password hashing is already quantum-adequate (Grover = quadratic).
pwd_context = CryptContext(schemes=["argon2", "bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_password_reset_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES
    )
    return jwt.encode(
        {"sub": str(user_id), "exp": expire, "type": "password_reset"},
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )


def verify_password_reset_token(token: str) -> int | None:
    """Decode a password-reset token and return the user_id, or None if invalid."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("type") != "password_reset":
            return None
        user_id = payload.get("sub")
        return int(user_id) if user_id else None
    except jwt.PyJWTError:
        return None


async def _resolve_or_provision_identity_user(db: AsyncSession, claims: dict):
    """Map a verified identity-JWT to a local ALAFIA user (the reference row).

    Resolution order: identity_uid → system_id (SID) → email. If none match, a
    thin local reference user is provisioned (enables the FlowSheet→ALAFIA
    "no-glitch" transition — identity owns the profile; ALAFIA stores only the FK).
    """
    from app.models.user import User  # avoid circular import

    identity_uid = claims.get("sub")
    sid = (claims.get("sid") or "").strip() or None
    email = (claims.get("email") or "").strip().lower() or None

    async def _find(col, val):
        if not val:
            return None
        return (await db.execute(select(User).where(col == val))).scalar_one_or_none()

    user = await _find(User.identity_uid, identity_uid)
    if user is None and sid:
        user = await _find(User.system_id, sid)
    if user is None and email:
        user = await _find(User.email, email)

    if user is not None:
        # Link the reference key (and adopt the canonical SID) if not yet set.
        if not user.identity_uid:
            user.identity_uid = identity_uid
        if sid and not user.system_id:
            user.system_id = sid
        await db.flush()
        return user

    # Provision a thin local reference row (no credentials/profile copied here).
    user = User(
        email=email or f"{identity_uid}@identity.local",
        full_name=claims.get("username") or (email.split("@")[0] if email else "User"),
        hashed_password="identity-managed-no-local-password",
        identity_uid=identity_uid,
        system_id=sid,
        auth_provider="identity",
        is_active=True,
    )
    db.add(user)
    await db.flush()
    return user


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
):
    """Resolve the current user from a JWT.

    Accepts (1) a shared-identity hybrid EdDSA+ML-DSA JWT (verified via JWKS → SSO
    across apps), or (2) a legacy ALAFIA HS512 token (during the migration window).
    """
    from app.models.user import User  # avoid circular import
    from app.services.identity_client import verify_identity_token

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # 1) Shared identity token (preferred).
    claims = await verify_identity_token(token)
    if claims is not None:
        return await _resolve_or_provision_identity_user(db, claims)

    # 2) Legacy ALAFIA-issued token.
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception

    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_exception
    return user
