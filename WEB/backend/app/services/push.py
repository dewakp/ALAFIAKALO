# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""Send the notification to the phone. Nothing in the backend ever did.

Measured on production 2026-10-02, before this module existed:

    device_tokens          21 tokens / 4 users, all platform='ios'
                           every one 64 characters, pure hex, no colon
                           -> RAW APNs device tokens
    notifications          21 rows, 19 of them UNREAD
    senders anywhere       none

`device_tokens`'s own docstring says it stores tokens "so the backend can
deliver", `api/notifications.py` has registered them since August, Android ships
a `FirebaseMessagingService` ready to render one — and no line of code ever sent
anything. §3ar's dead control, on the delivery channel itself: a patient only
ever learned something had happened if they opened the app and looked.

WHY TWO TRANSPORTS AND NOT ONE
==============================
The stored tokens decide this, not preference. A **raw APNs token cannot be
addressed by FCM** — Firebase v1 requires its own registration token, which the
iOS app does not produce (`PushNotificationManager.handleDeviceToken` hex-encodes
the APNs `Data` and posts it verbatim). So:

    ios      -> APNs HTTP/2 directly, ES256 JWT signed with an Apple .p8 key
    android  -> FCM, via the `firebase-admin` already in requirements

Sending to iOS through FCM would need the Firebase iOS SDK, a new App Store
build, AND the same Apple key — while APNs reaches the 21 tokens **already
registered by already-shipped builds**, which no source change can reach. That
is the same argument `_naive_session_payload` turns on (§3av).

EVERY TRANSPORT IS GATED ON ITS OWN CREDENTIAL, AND SAYS SO
===========================================================
§3ah: PayPal was advertised and unbuyable for weeks because `/plans` listed a
rail no credential backed, and every tap answered 503. A push sender with no key
is the same failure. So each transport reports `configured: False` with the
reason, `status()` surfaces it, and an unconfigured transport is a no-op that
logs once rather than an exception per notification.

This follows deploy.sh's existing idiom for Stripe, Resend and SMTP: the secret
is mounted only if it exists, and the rail "lights up the moment you
`gcloud secrets create` its key: no code change, no app release."

IT NEVER SENDS INLINE
=====================
`create_notification` runs inside a request transaction while a patient waits
for a clinical save. A push is a network round trip to Apple or Google, so doing
it there would couple every meal log to Apple's availability. This mirrors
`inference_corpus` exactly (§3ay): the caller does the smallest possible thing
(put a dict on a BOUNDED queue) and a drain task delivers with its own session.

The queue is bounded and drops loudly. An unbounded one turns an APNs outage
into memory exhaustion, and losing an alert beats failing the write that caused
it (§3ah).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import async_session
from app.models.device_tokens import DeviceToken
from app.models.notifications import NotificationPreference

logger = logging.getLogger(__name__)

#: Deliveries queued before new ones are dropped. A patient's phone falling
#: behind must never become the backend's memory problem.
MAX_QUEUED = 2000
#: Apple refuses a payload over 4 KB. Truncate the body rather than have the
#: whole push rejected for a long clinical message.
APNS_BODY_LIMIT = 300

_queue: "asyncio.Queue | None" = None
_drain: "asyncio.Task | None" = None
_dropped = 0
_sent = 0
_failed = 0
_pruned = 0
_last_error: str | None = None


@dataclass
class Delivery:
    """One notification, on its way to whatever devices a user has."""

    user_id: int
    title: str
    body: str
    category: str
    notification_id: int | None = None
    action_url: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


# ── Credentials ───────────────────────────────────────────────────────────


def _apns_config() -> dict[str, str] | None:
    """The Apple key, or None with the reason logged once.

    Four separate facts are needed and three of them are not secrets — the key
    id, the team id and the bundle id identify which app this is, and getting
    any of them wrong produces a 403 from Apple rather than a delivery.
    """
    key = (settings.APNS_AUTH_KEY or "").strip()
    key_id = (settings.APNS_KEY_ID or "").strip()
    team_id = (settings.APNS_TEAM_ID or "").strip()
    bundle = (settings.APNS_BUNDLE_ID or "").strip()
    if not (key and key_id and team_id and bundle):
        return None
    return {"key": key, "key_id": key_id, "team_id": team_id, "bundle": bundle}


def _apns_unconfigured_reason() -> str:
    missing = [n for n, v in (
        ("APNS_AUTH_KEY", settings.APNS_AUTH_KEY),
        ("APNS_KEY_ID", settings.APNS_KEY_ID),
        ("APNS_TEAM_ID", settings.APNS_TEAM_ID),
        ("APNS_BUNDLE_ID", settings.APNS_BUNDLE_ID),
    ) if not (v or "").strip()]
    return "missing " + ", ".join(missing) if missing else ""


def _fcm_app():
    """The Firebase app, reusing the one `firebase_sync` already initialises.

    A second `initialize_app` raises, and two singletons for one credential is
    the drift this codebase keeps paying for.
    """
    try:
        from app.services.firebase_sync import get_firebase_app
        return get_firebase_app()
    except Exception as exc:
        logger.warning("push: Firebase app unavailable (%s: %s)",
                       type(exc).__name__, str(exc)[:120])
        return None


# ── APNs ──────────────────────────────────────────────────────────────────

_apns_jwt: tuple[float, str] | None = None
#: Apple accepts a provider token for an hour; refresh well inside that.
_APNS_JWT_TTL = 2400.0


def _apns_token(cfg: dict[str, str]) -> str:
    """ES256 provider token, cached. Apple rate-limits token minting."""
    global _apns_jwt
    now = time.time()
    if _apns_jwt and _apns_jwt[0] > now:
        return _apns_jwt[1]

    import jwt  # PyJWT, already a dependency

    token = jwt.encode(
        {"iss": cfg["team_id"], "iat": int(now)},
        cfg["key"],
        algorithm="ES256",
        headers={"kid": cfg["key_id"]},
    )
    _apns_jwt = (now + _APNS_JWT_TTL, token)
    return token


async def _send_apns(tokens: list[str], d: Delivery) -> set[str]:
    """Deliver to iOS. Returns the tokens Apple says are dead.

    APNs is HTTP/2 only — hence `h2` in requirements. A plain HTTP/1.1 client
    cannot talk to it at all, which is why this needed a dependency rather than
    just a URL.
    """
    global _sent, _failed, _last_error
    cfg = _apns_config()
    if not cfg:
        return set()

    import httpx

    host = ("api.sandbox.push.apple.com" if settings.APNS_USE_SANDBOX
            else "api.push.apple.com")
    payload = {
        "aps": {
            "alert": {"title": d.title, "body": d.body[:APNS_BODY_LIMIT]},
            "sound": "default",
            # A clinical alert the patient has not read is still waiting for
            # them; the badge is what says so on the home screen.
            "badge": 1,
        },
        "category": d.category,
        "notification_id": d.notification_id,
        "action_url": d.action_url,
    }
    headers = {
        "authorization": f"bearer {_apns_token(cfg)}",
        "apns-topic": cfg["bundle"],
        "apns-push-type": "alert",
        "apns-priority": "10",
    }

    dead: set[str] = set()
    try:
        async with httpx.AsyncClient(http2=True, timeout=10.0,
                                     base_url=f"https://{host}") as client:
            for token in tokens:
                try:
                    resp = await client.post(f"/3/device/{token}",
                                             json=payload, headers=headers)
                except Exception as exc:
                    _failed += 1
                    _last_error = f"apns {type(exc).__name__}: {str(exc)[:120]}"
                    logger.warning("push: APNs request failed (%s)", _last_error)
                    continue

                if resp.status_code == 200:
                    _sent += 1
                    continue
                _failed += 1
                reason = ""
                try:
                    reason = (resp.json() or {}).get("reason", "")
                except Exception:
                    reason = resp.text[:120]
                # 410 Gone, or 400 BadDeviceToken: the app was uninstalled or
                # the token was issued for the other environment. Prune it —
                # a token nobody can deliver to is noise on every later send.
                if resp.status_code == 410 or reason in (
                        "BadDeviceToken", "Unregistered", "DeviceTokenNotForTopic"):
                    dead.add(token)
                _last_error = f"apns {resp.status_code} {reason}"
                logger.warning("push: APNs refused (%s)", _last_error)
    except Exception as exc:
        _last_error = f"apns client {type(exc).__name__}: {str(exc)[:120]}"
        logger.warning("push: APNs transport failed (%s)", _last_error)
    return dead


# ── FCM ───────────────────────────────────────────────────────────────────


async def _send_fcm(tokens: list[str], d: Delivery) -> set[str]:
    """Deliver to Android. Returns the tokens Google says are dead."""
    global _sent, _failed, _last_error
    app = _fcm_app()
    if app is None:
        return set()

    from firebase_admin import messaging

    message = messaging.MulticastMessage(
        tokens=tokens,
        notification=messaging.Notification(title=d.title, body=d.body),
        # The Android service reads `category` out of `data` to pick its
        # channel, so these keys are a contract with that client.
        data={
            "category": d.category,
            "title": d.title,
            "body": d.body,
            "notification_id": str(d.notification_id or ""),
            "action_url": d.action_url or "",
        },
        android=messaging.AndroidConfig(priority="high"),
    )

    dead: set[str] = set()
    try:
        # `send_each_for_multicast`, not the deprecated `send_multicast`:
        # verified present on firebase-admin 6.8.0 rather than assumed.
        batch = await asyncio.to_thread(messaging.send_each_for_multicast, message)
    except Exception as exc:
        _failed += len(tokens)
        _last_error = f"fcm {type(exc).__name__}: {str(exc)[:120]}"
        logger.warning("push: FCM send failed (%s)", _last_error)
        return dead

    for token, resp in zip(tokens, batch.responses):
        if resp.success:
            _sent += 1
            continue
        _failed += 1
        exc = resp.exception
        _last_error = f"fcm {type(exc).__name__}: {str(exc)[:120]}"
        if isinstance(exc, (messaging.UnregisteredError,
                            messaging.SenderIdMismatchError)):
            dead.add(token)
        else:
            logger.warning("push: FCM refused a token (%s)", _last_error)
    return dead


# ── Preferences and tokens ────────────────────────────────────────────────


async def _push_allowed(db: AsyncSession, user_id: int, category: str) -> bool:
    """Does this patient want a PUSH for this category?

    `notification_preferences.push` has existed as long as the table and
    `_is_enabled` only ever read `enabled` — so the push column was a second
    dead control sitting inside the first one. Absent row means enabled, which
    is what stops a new category being silently dropped for every existing user.
    """
    row = (await db.execute(
        select(NotificationPreference).where(
            NotificationPreference.user_id == user_id,
            NotificationPreference.category == category,
        )
    )).scalar_one_or_none()
    if row is None:
        return True
    return bool(row.enabled and row.push)


async def _tokens_for(db: AsyncSession, user_id: int) -> dict[str, list[str]]:
    rows = (await db.execute(
        select(DeviceToken).where(DeviceToken.user_id == user_id)
    )).scalars().all()
    out: dict[str, list[str]] = {}
    for r in rows:
        out.setdefault((r.platform or "ios").lower(), []).append(r.token)
    return out


async def _prune(db: AsyncSession, tokens: set[str]) -> int:
    """Delete tokens the store itself called dead.

    Only ever on an explicit `Unregistered`/`BadDeviceToken` — never on a
    timeout or a 5xx, which say nothing about the token and would delete a
    working device because Apple had a bad minute.
    """
    global _pruned
    if not tokens:
        return 0
    rows = (await db.execute(
        select(DeviceToken).where(DeviceToken.token.in_(list(tokens)))
    )).scalars().all()
    for r in rows:
        await db.delete(r)
    await db.flush()
    _pruned += len(rows)
    if rows:
        logger.info("push: pruned %d dead device token(s)", len(rows))
    return len(rows)


# ── The queue ─────────────────────────────────────────────────────────────


def enqueue(*, user_id: int, title: str, body: str, category: str,
            notification_id: int | None = None,
            action_url: str | None = None) -> bool:
    """Hand a delivery to the drain. Returns False if it was dropped.

    Called from `create_notification`, inside a request transaction. It must do
    nothing that can fail or block: no DB read, no network, no await.
    """
    global _dropped
    if _queue is None:
        # Not started (a test, a script, a worker that never called start()).
        # Silent by design: a notification must still be WRITTEN.
        return False
    delivery = Delivery(user_id=user_id, title=title, body=body,
                        category=category, notification_id=notification_id,
                        action_url=action_url)
    try:
        _queue.put_nowait(delivery)
        return True
    except asyncio.QueueFull:
        _dropped += 1
        if _dropped % 100 == 1:
            logger.warning(
                "push: queue full, %d deliveries dropped so far "
                "(the notifications themselves are unaffected)", _dropped)
        return False


async def deliver(delivery: Delivery, db: AsyncSession) -> int:
    """Send one delivery. Returns how many devices accepted it.

    Never raises: it is called from the drain loop, and a push failure must not
    end the loop that serves every other patient.
    """
    try:
        if not await _push_allowed(db, delivery.user_id, delivery.category):
            return 0
        by_platform = await _tokens_for(db, delivery.user_id)
        if not by_platform:
            return 0

        before = _sent
        dead: set[str] = set()
        ios = by_platform.get("ios") or []
        android = by_platform.get("android") or []

        if ios:
            if _apns_config():
                dead |= await _send_apns(ios, delivery)
            else:
                _unconfigured_once("apns", len(ios))
        if android:
            if _fcm_app() is not None:
                dead |= await _send_fcm(android, delivery)
            else:
                _unconfigured_once("fcm", len(android))

        await _prune(db, dead)
        await db.commit()
        return _sent - before
    except Exception:
        logger.exception("push: delivery failed for user %s", delivery.user_id)
        return 0


_warned: set[str] = set()


def _unconfigured_once(transport: str, held: int) -> None:
    """Say it once, with the fix, instead of per notification.

    A rail with no credential must be legible — §3ae's month-long outage was
    indistinguishable from "the template was fine" because nothing logged why.
    """
    if transport in _warned:
        return
    _warned.add(transport)
    if transport == "apns":
        logger.warning(
            "push: %d iOS token(s) registered and APNs is NOT configured (%s). "
            "Create the Apple key secret and redeploy; no app release needed.",
            held, _apns_unconfigured_reason())
    else:
        logger.warning(
            "push: %d Android token(s) registered and FCM is NOT configured "
            "(FIREBASE_SERVICE_ACCOUNT unset or unreadable). Mount the "
            "firebase-sa secret and redeploy.", held)


async def _drain_loop() -> None:
    assert _queue is not None
    while True:
        delivery = await _queue.get()
        try:
            async with async_session() as db:
                await deliver(delivery, db)
        except Exception:
            logger.exception("push: drain iteration failed")
        finally:
            _queue.task_done()


def start() -> None:
    """Begin delivering. Safe to call twice."""
    global _queue, _drain
    if _queue is not None:
        return
    _queue = asyncio.Queue(maxsize=MAX_QUEUED)
    _drain = asyncio.create_task(_drain_loop())
    apns = "configured" if _apns_config() else f"NOT configured ({_apns_unconfigured_reason()})"
    logger.info("push: started — apns %s", apns)


async def stop() -> None:
    global _queue, _drain
    task, _drain = _drain, None
    _queue = None
    if task is not None:
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass


def status() -> dict[str, Any]:
    """What admin health should show. An unconfigured rail must be visible."""
    return {
        "running": _queue is not None,
        "queued": _queue.qsize() if _queue is not None else 0,
        "apns_configured": bool(_apns_config()),
        "apns_reason": _apns_unconfigured_reason() or None,
        "apns_environment": "sandbox" if settings.APNS_USE_SANDBOX else "production",
        "fcm_configured": _fcm_app() is not None,
        "sent": _sent,
        "failed": _failed,
        "dropped": _dropped,
        "pruned": _pruned,
        "last_error": _last_error,
    }
