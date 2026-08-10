"""Authorization for the admin console.

The boundary is here, in the API. Serving the console on its own hostname
(/minister) is routing, not security: anyone can send a request to
`/api/v1/admin/*` with any Host header they like, so every admin endpoint
depends on `require_admin` and none of them trust the hostname.

Two conditions must both hold:

  1. the caller's email is in `settings.ADMIN_EMAILS` (default: dew@6igma.com)
  2. the account is active

`is_superuser` is deliberately NOT sufficient on its own. That flag is currently
set on a leftover test account in this database (`crossapp_…@example.com`), and
a single stray UPDATE should not be able to grant console access.

Every allowed and refused call is logged with the caller's identity, because an
admin console over patient data needs an access trail.
"""

from __future__ import annotations

import logging

from fastapi import Depends, HTTPException, Request, status

from app.core.config import settings
from app.core.security import get_current_user
from app.models.user import User

logger = logging.getLogger("app.admin.access")


def _normalized_admin_emails() -> set[str]:
    return {e.strip().lower() for e in (settings.ADMIN_EMAILS or []) if e and e.strip()}


def is_admin(user: User | None) -> bool:
    if user is None or not getattr(user, "is_active", False):
        return False
    email = (getattr(user, "email", "") or "").strip().lower()
    return bool(email) and email in _normalized_admin_emails()


async def require_admin(
    request: Request,
    current_user: User = Depends(get_current_user),
) -> User:
    """Gate an endpoint to the admin account. 404s non-admins.

    Returns 404 rather than 403 so the console's existence is not confirmed to a
    logged-in non-admin probing the API.
    """
    if not is_admin(current_user):
        logger.warning(
            "admin access DENIED user_id=%s email=%s path=%s ip=%s",
            getattr(current_user, "id", None),
            getattr(current_user, "email", None),
            request.url.path,
            request.client.host if request.client else "-",
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")

    logger.info(
        "admin access user_id=%s email=%s path=%s",
        current_user.id, current_user.email, request.url.path,
    )
    return current_user
