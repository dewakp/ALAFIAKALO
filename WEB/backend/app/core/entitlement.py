"""Entitlement gating.

``require_plus`` is a FastAPI dependency any premium endpoint can add to require
an active ALAFIA Membership. Entitlement is derived server-side from the
user's ``Subscription`` row (status + period + grace) — never from the client.

Usage::

    from app.core.entitlement import require_plus

    @router.get("/fancy-report")
    async def fancy_report(user: User = Depends(require_plus)):
        ...

When ``SUBSCRIPTION_ENABLED`` is false the gate is a no-op (open beta / self-host).
"""

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.services import subscription_service as svc

# Endpoints that MUST work without a subscription, so an unsubscribed user can still
# sign in, view their status, manage their account, and pay. Everything else is gated
# when SUBSCRIPTION_REQUIRED is on.
_PAYWALL_OPEN_PREFIXES = (
    "/api/v1/auth",          # login / register / logout / refresh / csrf / password reset
    "/api/v1/subscription",  # plans / status / checkout / confirm / verify / webhook / cancel
    "/api/v1/users",         # profile + /me + roles/personas (needed to load the app + paywall)
)


def _paywall_open_path(path: str) -> bool:
    return any(path.startswith(p) for p in _PAYWALL_OPEN_PREFIXES)


def is_paywall_exempt(user: User | None) -> bool:
    """True for owner/staff emails that bypass the paywall entirely.

    Public because the exemption has to be visible everywhere entitlement is
    *answered*, not just where it is enforced. It used to be honoured only by
    ``require_active_subscription``, which was invisible on web (the 402 that
    would have revealed the gap never fired for these accounts) — but the iOS and
    Android clients gate the whole app on ``GET /subscription/status``, so an
    exempt owner with no subscription row would have been walled out of both.
    """
    exempt = {e.strip().lower() for e in settings.SUBSCRIPTION_EXEMPT_EMAILS if e.strip()}
    return bool(user and user.email and user.email.lower() in exempt)


async def _user_from_bearer(request: Request, db: AsyncSession) -> User | None:
    """Resolve the user from a Bearer token WITHOUT raising (None if absent/invalid)."""
    auth = request.headers.get("Authorization", "")
    if not auth.lower().startswith("bearer "):
        return None
    try:
        return await get_current_user(token=auth.split(" ", 1)[1], db=db)
    except HTTPException:
        return None


async def require_active_subscription(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> None:
    """App-wide paywall (router dependency). When ``SUBSCRIPTION_REQUIRED`` is on,
    any authenticated request to a gated path needs an active subscription — except
    exempt (owner) emails. Open paths (auth/subscription/users) and unauthenticated
    requests pass through (the endpoint's own auth still applies)."""
    if not settings.SUBSCRIPTION_REQUIRED or _paywall_open_path(request.url.path):
        return
    user = await _user_from_bearer(request, db)
    if user is None or is_paywall_exempt(user):
        return
    if not svc.is_entitled(await svc.get_subscription(db, user.id)):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="An active ALAFIA Membership is required to use ALAFIA.",
        )


async def require_plus(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Allow the request only when the user has an active Plus entitlement."""
    if not settings.SUBSCRIPTION_ENABLED or is_paywall_exempt(current_user):
        return current_user
    sub = await svc.get_subscription(db, current_user.id)
    if not svc.is_entitled(sub):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="An active ALAFIA Membership is required for this feature.",
        )
    return current_user
