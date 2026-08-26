"""Marketing unsubscribe — public, unauthenticated, never paywalled.

Mounted on the app directly rather than under `api_router`, because that router
carries `Depends(require_active_subscription)` and an unsubscribe link has to
work for exactly the person most likely to click it: someone whose subscription
lapsed. A paywalled unsubscribe is not an unsubscribe.

Two entry points, both required for a bulk send:

  GET  /unsubscribe?token=…   the human-clickable link in the email body
  POST /unsubscribe           RFC 8058 one-click, used by the mail client's own
                              "Unsubscribe" button via List-Unsubscribe-Post

The token is a signed JWT carrying only the user id and a distinct `type`, so a
leaked marketing link can never be replayed as a session, a password reset, or
anything else. It is long-lived on purpose — a recipient may act on the email
weeks later, and an expired unsubscribe link is a complaint waiting to happen.

Responses never reveal whether a token matched a real account: an unsubscribe
endpoint that says "no such user" is an account-existence oracle, the same
property §3e rate-limits the recipient lookup for.
"""

import logging
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["marketing"])

_TOKEN_TYPE = "marketing_unsubscribe"
_TOKEN_TTL_DAYS = 400


def _signing_key() -> str:
    """The signing key with surrounding whitespace removed.

    These tokens are unusual: they are minted OUTSIDE the running service (by
    the bulk-send script, which reads the secret through `gcloud`) and verified
    INSIDE it. That makes them sensitive to something the app's own tokens never
    notice.

    `alafia-secret-key` is stored with a TRAILING NEWLINE — 65 bytes, ending
    0x0a. Cloud Run mounts a secret's bytes verbatim, so the service verifies
    with all 65. Shell command substitution strips trailing newlines, so
    `SECRET_KEY="$(gcloud secrets versions access …)"` signs with 64. The
    signatures then never match, and — because an unverifiable token is
    deliberately indistinguishable from a forged one here — the endpoint
    answered 200 and recorded nothing. Every unsubscribe link in a batch of
    real mail was inert, and told its reader the opposite.

    Stripping on both sides makes the two agree however the secret is stored.
    It costs no entropy (the newline is not secret) and is confined to these
    tokens; login and password-reset tokens are minted and verified by the same
    process, so they were never exposed to the mismatch.
    """
    return settings.SECRET_KEY.strip()


def create_unsubscribe_token(user_id: int) -> str:
    """Sign a long-lived, single-purpose unsubscribe token."""
    expire = datetime.now(timezone.utc) + timedelta(days=_TOKEN_TTL_DAYS)
    return jwt.encode(
        {"sub": str(user_id), "exp": expire, "type": _TOKEN_TYPE},
        _signing_key(),
        algorithm=settings.ALGORITHM,
    )


def verify_unsubscribe_token(token: str) -> int | None:
    """Return the user id, or None if the token is invalid/expired/wrong type."""
    try:
        payload = jwt.decode(token, _signing_key(), algorithms=[settings.ALGORITHM])
    except jwt.PyJWTError:
        return None
    if payload.get("type") != _TOKEN_TYPE:
        return None
    sub = payload.get("sub")
    try:
        return int(sub) if sub else None
    except (TypeError, ValueError):
        return None


async def _opt_out(db: AsyncSession, token: str) -> None:
    """Record the opt-out. Idempotent, and silent about whether it matched."""
    user_id = verify_unsubscribe_token(token)
    if user_id is None:
        return
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None or user.marketing_opt_out_at is not None:
        return
    user.marketing_opt_out_at = datetime.now(timezone.utc)
    await db.commit()
    logger.info("marketing opt-out recorded for user %s", user_id)


_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Unsubscribed &middot; ALAFIA</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{ margin:0; min-height:100vh; display:grid; place-items:center;
         font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
         background:#f7f8fa; color:#16202a; padding:24px; }}
  .card {{ max-width:34rem; background:#fff; border-radius:14px; padding:2.25rem;
          box-shadow:0 1px 3px rgba(0,0,0,.08); }}
  h1 {{ margin:0 0 .75rem; font-size:1.35rem; }}
  p {{ margin:0 0 1rem; color:#48545f; }}
  .quiet {{ font-size:.875rem; color:#6b7783; }}
  @media (prefers-color-scheme: dark) {{
    body {{ background:#12171c; color:#e8edf2; }}
    .card {{ background:#1b2229; box-shadow:none; }}
    p {{ color:#aab6c2; }} .quiet {{ color:#8593a0; }}
  }}
</style></head>
<body><div class="card">
  <h1>{heading}</h1>
  <p>{body}</p>
  <p class="quiet">You will still receive essential account email — password
  resets, address verification and billing notices. Those are not marketing and
  cannot be turned off while your account is open.</p>
</div></body></html>
"""


def _page(heading: str, body: str) -> HTMLResponse:
    return HTMLResponse(_PAGE.format(heading=heading, body=body))


@router.get("/unsubscribe", response_class=HTMLResponse, include_in_schema=False)
async def unsubscribe_via_link(
    request: Request,
    token: str = Query("", description="Signed unsubscribe token from the email"),
    db: AsyncSession = Depends(get_db),
):
    """Human-clickable unsubscribe. Always renders the same confirmation."""
    await _opt_out(db, token)
    return _page(
        "You&rsquo;re unsubscribed",
        "We won&rsquo;t send you any more product announcements from ALAFIA.",
    )


@router.post("/unsubscribe", include_in_schema=False)
async def unsubscribe_one_click(
    request: Request,
    token: str = Query("", description="Signed unsubscribe token from the email"),
    List_Unsubscribe: str = Form(default="", alias="List-Unsubscribe"),
    db: AsyncSession = Depends(get_db),
):
    """RFC 8058 one-click, triggered by the mail client's own button.

    The body arrives as `List-Unsubscribe=One-Click`; the token stays in the
    query string, which is where the List-Unsubscribe URL puts it. Returns 200
    with an empty body — mail clients read the status, not the page.
    """
    await _opt_out(db, token)
    return {"status": "unsubscribed"}
