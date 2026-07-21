"""Entitlement gating.

``require_plus`` is a FastAPI dependency any premium endpoint can add to require
an active ALAFIA Plus subscription. Entitlement is derived server-side from the
user's ``Subscription`` row (status + period + grace) — never from the client.

Usage::

    from app.core.entitlement import require_plus

    @router.get("/fancy-report")
    async def fancy_report(user: User = Depends(require_plus)):
        ...

When ``SUBSCRIPTION_ENABLED`` is false the gate is a no-op (open beta / self-host).
"""

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.services import subscription_service as svc


async def require_plus(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Allow the request only when the user has an active Plus entitlement."""
    if not settings.SUBSCRIPTION_ENABLED:
        return current_user
    sub = await svc.get_subscription(db, current_user.id)
    if not svc.is_entitled(sub):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="An active ALAFIA Plus subscription is required for this feature.",
        )
    return current_user
