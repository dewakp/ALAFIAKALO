"""Model → API shape helpers."""

from app.models import User
from app.schemas import UserOut, ProfileOut


def user_out(u: User) -> UserOut:
    prof = u.identity
    return UserOut(
        id=str(u.id),
        email=u.email,
        username=u.username,
        account_role=u.account_role,
        tier=u.tier,
        email_verified=u.email_verified,
        system_id=(u.system_id.strip() if u.system_id else None),
        created_at=u.created_at,
        profile=ProfileOut.model_validate(prof) if prof else None,
    )
