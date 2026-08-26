"""The unsubscribe boundary.

`/personalization` and `/planners` shipped with zero tests and three AI panels
stayed dead for 27 days behind 696 passing ones (CLAUDE.md §3ae). An unsubscribe
link carries the same shape of risk: nothing else in the app exercises it, and
it is only ever used by people who are already annoyed. If it 404s, 402s, or
silently fails to write, we find out from a spam complaint.

What must hold:
  * it works with no auth and no subscription, and is NOT under /api/v1
  * a valid token records the opt-out, once
  * a token minted for another purpose cannot be replayed here
  * garbage, expired, forged and absent tokens neither 500 nor reveal whether
    an account exists
"""

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from sqlalchemy import select

from app.api.marketing import create_unsubscribe_token, verify_unsubscribe_token
from app.core.config import settings
from app.models.user import User


async def _user(db, email: str) -> User:
    u = User(email=email, hashed_password="x", full_name="Unsub Tester")
    db.add(u)
    await db.flush()
    return u


# ── Token handling (no DB) ──────────────────────────────────────────────


def test_token_roundtrip():
    assert verify_unsubscribe_token(create_unsubscribe_token(4242)) == 4242


def test_password_reset_token_is_not_accepted():
    """A token minted for another purpose must not unsubscribe anyone.

    Both are signed with SECRET_KEY, so only the `type` claim separates them.
    """
    from app.core.security import create_password_reset_token

    assert verify_unsubscribe_token(create_password_reset_token(4242)) is None


def test_expired_token_rejected():
    stale = jwt.encode(
        {
            "sub": "1",
            "exp": datetime.now(timezone.utc) - timedelta(days=1),
            "type": "marketing_unsubscribe",
        },
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    assert verify_unsubscribe_token(stale) is None


def test_token_signed_with_another_key_rejected():
    forged = jwt.encode(
        {
            "sub": "1",
            "exp": datetime.now(timezone.utc) + timedelta(days=1),
            "type": "marketing_unsubscribe",
        },
        "not-the-secret-key",
        algorithm=settings.ALGORITHM,
    )
    assert verify_unsubscribe_token(forged) is None


@pytest.mark.parametrize("bad", ["", "   ", "not-a-jwt", "a.b.c"])
def test_garbage_tokens_return_none(bad):
    assert verify_unsubscribe_token(bad) is None


@pytest.mark.parametrize("stored", [
    "supersecret\n",      # how `gcloud secrets create` from a file stores it
    "supersecret",        # how `$(gcloud secrets versions access …)` returns it
    "  supersecret  ",
])
def test_trailing_newline_in_the_secret_cannot_break_verification(monkeypatch, stored):
    """A newline on the secret must not silently invalidate every link.

    These tokens are minted OUTSIDE the service by the bulk-send script and
    verified INSIDE it. `alafia-secret-key` is stored with a trailing newline;
    Cloud Run mounts all 65 bytes while shell command substitution strips to 64.
    Signed on one side and verified on the other, the signatures never matched —
    and because an unverifiable token is deliberately indistinguishable from a
    forged one, the endpoint returned 200 and wrote nothing. A whole batch of
    real mail carried unsubscribe links that were inert and said otherwise.

    Signing and verifying must agree no matter which form the key arrives in.
    """
    monkeypatch.setattr(settings, "SECRET_KEY", stored)
    token = create_unsubscribe_token(4242)

    for other in ("supersecret\n", "supersecret", "  supersecret  "):
        monkeypatch.setattr(settings, "SECRET_KEY", other)
        assert verify_unsubscribe_token(token) == 4242, (
            f"token signed with {stored!r} did not verify under {other!r}"
        )


# ── The endpoint ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unsubscribe_records_opt_out(client, db):
    """The happy path actually writes, with no Authorization header."""
    user = await _user(db, "optout@example.com")
    await db.commit()
    assert user.marketing_opt_out_at is None

    resp = await client.get(f"/unsubscribe?token={create_unsubscribe_token(user.id)}")

    assert resp.status_code == 200
    assert "unsubscribed" in resp.text.lower()

    fresh = (await db.execute(select(User).where(User.id == user.id))).scalar_one()
    await db.refresh(fresh)
    assert fresh.marketing_opt_out_at is not None


@pytest.mark.asyncio
async def test_unsubscribe_is_idempotent(client, db):
    user = await _user(db, "twice@example.com")
    await db.commit()
    token = create_unsubscribe_token(user.id)

    await client.get(f"/unsubscribe?token={token}")
    fresh = (await db.execute(select(User).where(User.id == user.id))).scalar_one()
    await db.refresh(fresh)
    first = fresh.marketing_opt_out_at

    await client.get(f"/unsubscribe?token={token}")
    await db.refresh(fresh)

    assert fresh.marketing_opt_out_at == first, "second click moved the timestamp"


@pytest.mark.asyncio
async def test_one_click_post_works(client, db):
    """RFC 8058: the mail client POSTs List-Unsubscribe=One-Click."""
    user = await _user(db, "oneclick@example.com")
    await db.commit()

    resp = await client.post(
        f"/unsubscribe?token={create_unsubscribe_token(user.id)}",
        data={"List-Unsubscribe": "One-Click"},
    )

    assert resp.status_code == 200
    fresh = (await db.execute(select(User).where(User.id == user.id))).scalar_one()
    await db.refresh(fresh)
    assert fresh.marketing_opt_out_at is not None


@pytest.mark.asyncio
async def test_invalid_token_does_not_leak_account_existence(client):
    """Same status and same body for a bad token as for a good-shaped one."""
    a = await client.get(f"/unsubscribe?token={create_unsubscribe_token(99_999_999)}")
    b = await client.get("/unsubscribe?token=garbage")

    assert a.status_code == b.status_code == 200
    assert a.text == b.text


@pytest.mark.asyncio
async def test_missing_token_does_not_500(client):
    assert (await client.get("/unsubscribe")).status_code == 200


@pytest.mark.asyncio
async def test_route_is_not_under_api_v1(client, db):
    """It must not sit behind the paywall dependency.

    If someone later moves this under `api_router`, this fails: /api/v1 carries
    require_active_subscription, and a lapsed user could no longer opt out of a
    list they asked to leave.
    """
    user = await _user(db, "notapi@example.com")
    await db.commit()
    resp = await client.get(f"/api/v1/unsubscribe?token={create_unsubscribe_token(user.id)}")
    assert resp.status_code == 404
