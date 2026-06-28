"""PostgreSQL-native auth: register / login / refresh / password reset."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
import jwt as pyjwt

from app.config import settings
from app.database import get_db
from app.models import User, UserIdentity, SidLog, ACCOUNT_ROLES
from app.schemas import (
    RegisterRequest, LoginRequest, RefreshRequest, AuthResult, ResetRequest, ResetConfirm,
    MigratePasswordRequest,
)
import hmac
from app.security import (
    hash_password, verify_password, make_tokens, decode_hs, make_reset_token,
)
from app.serializers import user_out
from app import canonical_sid

router = APIRouter(prefix="/identity", tags=["auth"])


async def _by_identifier(db: AsyncSession, identifier: str) -> User | None:
    q = (
        select(User)
        .options(selectinload(User.identity))
        .where(or_(func.lower(User.email) == identifier.lower(),
                   func.lower(User.username) == identifier.lower()))
    )
    return (await db.execute(q)).scalar_one_or_none()


@router.post("/register", response_model=AuthResult, status_code=201)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    if body.account_role not in ACCOUNT_ROLES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"role must be one of {ACCOUNT_ROLES}")

    # Uniqueness across the ONE identity store (email AND username).
    dup = (await db.execute(
        select(User).where(or_(func.lower(User.email) == body.email.lower(),
                               func.lower(User.username) == body.username.lower()))
    )).scalar_one_or_none()
    if dup:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "A 6IGMA account with this email or username already exists — sign in instead.")

    user = User(
        email=str(body.email).lower(),
        username=body.username,
        password_hash=hash_password(body.password),
        account_role=body.account_role,
        tier="flowsheet",            # everyone starts on the FlowSheet (intro) tier
    )
    db.add(user)
    await db.flush()  # assign user.id + created_at

    sex = body.biological_sex or body.gender
    sid = canonical_sid.generate_sid(body.first_name, body.last_name, body.date_of_birth, sex, user.created_at)
    user.system_id = sid

    db.add(UserIdentity(
        user_id=user.id, first_name=body.first_name, last_name=body.last_name,
        date_of_birth=body.date_of_birth, gender=body.gender, biological_sex=body.biological_sex,
    ))
    segs = canonical_sid.segments_for_log(body.first_name, body.last_name, body.date_of_birth, sex, user.created_at)
    db.add(SidLog(user_id=user.id, system_id=sid, **segs))

    await db.flush()
    await db.refresh(user, attribute_names=["identity"])
    return AuthResult(**make_tokens(user), user=user_out(user))


@router.post("/login", response_model=AuthResult)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = await _by_identifier(db, body.identifier)
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    if user.account_status != "active":
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"account {user.account_status}")
    return AuthResult(**make_tokens(user), user=user_out(user))


@router.post("/token/refresh")
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    try:
        claims = decode_hs(body.refresh_token)
    except pyjwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")
    if claims.get("type") != "refresh":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not a refresh token")
    user = (await db.execute(
        select(User).options(selectinload(User.identity)).where(User.id == claims["sub"])
    )).scalar_one_or_none()
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    return make_tokens(user)


@router.post("/internal/migrate-password")
async def migrate_password(body: MigratePasswordRequest, db: AsyncSession = Depends(get_db)):
    """Firebase→IdP bridge. The caller (ALAFIA) has already verified the user's
    legacy Firebase password; we set it as the IdP credential so the account
    becomes PostgreSQL-native and Firebase is no longer needed. Secret-guarded.
    """
    if not hmac.compare_digest(body.secret or "", settings.MIGRATION_SECRET):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid migration secret")
    user = await _by_identifier(db, body.identifier)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    user.password_hash = hash_password(body.new_password)
    if user.account_status != "active":
        user.account_status = "active"
    await db.flush()
    return {"ok": True, "message": "Credential migrated into the identity store."}


@router.post("/password/reset-request")
async def password_reset_request(body: ResetRequest, db: AsyncSession = Depends(get_db)):
    """Issue a signed reset token. Onboards migrated (passwordless) accounts.

    Always 200 (no user enumeration). In dev the token is returned inline; in
    prod it is emailed and omitted from the response.
    """
    user = await _by_identifier(db, body.identifier)
    resp = {"ok": True, "message": "If the account exists, a reset link has been sent."}
    if user:
        token = make_reset_token(str(user.id))
        if settings.ENV != "production":
            resp["reset_token"] = token  # dev convenience only
    return resp


@router.post("/password/reset")
async def password_reset(body: ResetConfirm, db: AsyncSession = Depends(get_db)):
    """Consume a reset token, set a bcrypt password, and activate the account."""
    try:
        claims = decode_hs(body.token)
    except pyjwt.PyJWTError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired reset token")
    if claims.get("type") != "password_reset":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Not a password-reset token")
    user = (await db.execute(select(User).where(User.id == claims["sub"]))).scalar_one_or_none()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    user.password_hash = hash_password(body.new_password)
    user.account_status = "active"
    await db.flush()
    return {"ok": True, "message": "Password updated. You can now sign in."}
