"""User/profile + SID lookup endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import User
from app.schemas import UserOut, ProfileUpdate, LookupOut, SidVerifyRequest, SidVerifyOut
from app.security import current_claims
from app.serializers import user_out
from app import canonical_sid

router = APIRouter(prefix="/identity", tags=["users"])


async def _load(db: AsyncSession, user_id: str) -> User:
    user = (await db.execute(
        select(User).options(selectinload(User.identity)).where(User.id == user_id)
    )).scalar_one_or_none()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return user


@router.get("/me", response_model=UserOut)
async def me(claims: dict = Depends(current_claims), db: AsyncSession = Depends(get_db)):
    return user_out(await _load(db, claims["sub"]))


@router.patch("/me", response_model=UserOut)
async def update_me(body: ProfileUpdate, claims: dict = Depends(current_claims),
                    db: AsyncSession = Depends(get_db)):
    user = await _load(db, claims["sub"])
    prof = user.identity
    if prof is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No profile to update")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(prof, field, value)
    await db.flush()
    await db.refresh(user, attribute_names=["identity"])
    return user_out(user)


@router.get("/lookup", response_model=LookupOut)
async def lookup(email: str | None = Query(None), username: str | None = Query(None),
                 db: AsyncSession = Depends(get_db)):
    email_taken = username_taken = False
    if email:
        email_taken = (await db.execute(
            select(User.id).where(func.lower(User.email) == email.lower()))).first() is not None
    if username:
        username_taken = (await db.execute(
            select(User.id).where(func.lower(User.username) == username.lower()))).first() is not None
    return LookupOut(email_taken=email_taken, username_taken=username_taken)


@router.get("/users/{sid}", response_model=UserOut)
async def get_by_sid(sid: str, claims: dict = Depends(current_claims),
                     db: AsyncSession = Depends(get_db)):
    # Service-to-service resolve by SID (Phase 1.4 will add a service-token scope).
    user = (await db.execute(
        select(User).options(selectinload(User.identity)).where(User.system_id == sid)
    )).scalar_one_or_none()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No user for that SID")
    return user_out(user)


@router.post("/sid/verify", response_model=SidVerifyOut)
async def sid_verify(body: SidVerifyRequest):
    valid = canonical_sid.verify_sid(body.sid)
    return SidVerifyOut(valid=valid, segments=canonical_sid.decode_sid(body.sid))
