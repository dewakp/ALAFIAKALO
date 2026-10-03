# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""The notification reaches the phone — and says so honestly when it cannot.

Measured on production 2026-10-02, before `app/services/push.py` existed:

    device_tokens   21 tokens / 4 users, EVERY ONE platform='ios',
                    64 characters, pure hex, no colon -> raw APNs tokens
    android tokens  ZERO — `onNewToken` held a `// TODO: Send this token`
    senders         none anywhere in the backend
    notifications   21 rows, 19 UNREAD

So the tokens were collected for two months and never addressed, and a patient
learned of a clinical alert only by opening the app and looking (§3ar, on the
delivery channel itself).

WHAT THESE TESTS PIN
====================
Mostly the REFUSALS, because an unconfigured push rail is how §3ah's PayPal
failure happened: `/plans` advertised a rail no credential backed and every tap
answered 503 for weeks. A sender with no key must be a quiet no-op that reports
itself, never an exception per notification and never a claim of delivery.

They are offline by construction: no test here reaches Apple or Google. The
transports are substituted, and what is asserted is the ROUTING, the preference
gate, the pruning rule, and that nothing escapes to the caller.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from conftest import TestSession

from app.models.device_tokens import DeviceToken
from app.models.notifications import (
    NotificationCategory,
    NotificationPreference,
)
from app.models.user import User
from app.services import push


async def _user(db, email="push@example.com") -> User:
    u = User(email=email, hashed_password="x", full_name="Push Test")
    db.add(u)
    await db.flush()
    return u


async def _token(db, user_id: int, token: str, platform: str) -> DeviceToken:
    t = DeviceToken(user_id=user_id, token=token, platform=platform)
    db.add(t)
    await db.flush()
    return t


def _delivery(user_id: int, category="nutrition_alert") -> push.Delivery:
    return push.Delivery(user_id=user_id, title="Potassium is high",
                         body="Today's potassium is 2500 mg", category=category,
                         notification_id=1, action_url="/nutrition")


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    """Each test starts with no credentials and a clean warn-once set."""
    monkeypatch.setattr(push.settings, "APNS_AUTH_KEY", "", raising=False)
    monkeypatch.setattr(push.settings, "APNS_KEY_ID", "", raising=False)
    monkeypatch.setattr(push.settings, "APNS_TEAM_ID", "", raising=False)
    monkeypatch.setattr(push.settings, "APNS_BUNDLE_ID", "com.alafia.app",
                        raising=False)
    push._warned.clear()


class TestAnUnconfiguredRailIsHonest:
    def test_apns_is_unconfigured_and_names_what_is_missing(self):
        assert push._apns_config() is None
        reason = push._apns_unconfigured_reason()
        for field in ("APNS_AUTH_KEY", "APNS_KEY_ID", "APNS_TEAM_ID"):
            assert field in reason, reason

    def test_a_partial_credential_is_still_unconfigured(self, monkeypatch):
        """Three of four values is not a key.

        Sending with a missing team id produces a 403 from Apple on every
        notification, which looks like a dead device rather than a config error.
        """
        monkeypatch.setattr(push.settings, "APNS_AUTH_KEY", "-----BEGIN-----")
        monkeypatch.setattr(push.settings, "APNS_KEY_ID", "ABC1234567")
        assert push._apns_config() is None
        assert "APNS_TEAM_ID" in push._apns_unconfigured_reason()

    def test_status_reports_the_truth_rather_than_a_boolean(self):
        s = push.status()
        assert s["apns_configured"] is False
        assert s["apns_reason"]
        assert s["apns_environment"] in ("sandbox", "production")

    def test_configured_and_DELIVERABLE_are_separate_facts(self):
        """REGRESSION GUARD. `apns ok` once meant only "credentials present".

        Measured 2026-10-03: a process with all four values set reported
        `apns_configured: True` and then failed every send with
        `ImportError: Using http2=True, but the 'h2' package is not
        installed` — APNs is HTTP/2 only. A rail that reports healthy and
        cannot deliver is §3ah's PayPal failure, here inside the probe built
        to prevent it.
        """
        s = push.status()
        for key in ("apns_transport_ok", "apns_transport_reason",
                    "apns_deliverable"):
            assert key in s, f"status() must report {key}"
        # Credentials are blanked by the fixture, so deliverable must be False
        # whatever the transport happens to be in this environment.
        assert s["apns_deliverable"] is False
        ok, reason = push._transport_ok()
        assert isinstance(ok, bool)
        assert (reason is None) == ok, "a failure must carry its reason"

    def test_h2_is_PINNED_so_the_transport_cannot_silently_vanish(self):
        """The dependency, asserted at the SOURCE rather than the environment.

        Checking `import h2` would make this test pass or fail according to
        which image it runs in — and the suite was green at 1,895 tests with
        h2 absent, because every test here stubs `_send_apns`. Pinning is the
        fact that matters, and it is the same in every environment.
        """
        import pathlib
        req = pathlib.Path(__file__).resolve().parents[1] / "requirements.txt"
        text = req.read_text()
        assert "h2==" in text, (
            "APNs is HTTP/2 only; httpx raises ImportError at construction "
            "without h2, so it must stay pinned in requirements.txt")

    @pytest.mark.asyncio
    async def test_delivering_with_no_credential_sends_nothing_and_raises_nothing(
            self, db):
        user = await _user(db, "noconf@example.com")
        await _token(db, user.id, "a" * 64, "ios")
        assert await push.deliver(_delivery(user.id), db) == 0

    @pytest.mark.asyncio
    async def test_it_warns_ONCE_not_per_notification(self, db, caplog):
        """A per-notification error log buries the one line that matters."""
        import logging
        user = await _user(db, "warnonce@example.com")
        await _token(db, user.id, "b" * 64, "ios")
        with caplog.at_level(logging.WARNING):
            await push.deliver(_delivery(user.id), db)
            await push.deliver(_delivery(user.id), db)
            await push.deliver(_delivery(user.id), db)
        apns_warnings = [r for r in caplog.records if "APNs is NOT configured" in r.message]
        assert len(apns_warnings) == 1


class TestIOSNeverGoesThroughFirebase:
    """The operator's explicit instruction, and a hard constraint besides.

    A raw APNs device token cannot be addressed by FCM at all — v1 requires its
    own registration token — so routing iOS through Firebase would fail
    silently on every one of the 21 tokens already on file.
    """

    @pytest.mark.asyncio
    async def test_an_ios_token_is_never_handed_to_fcm(self, db, monkeypatch):
        user = await _user(db, "iosonly@example.com")
        await _token(db, user.id, "c" * 64, "ios")

        fcm_calls, apns_calls = [], []

        async def _fake_fcm(tokens, d):
            fcm_calls.append(tokens)
            return set()

        async def _fake_apns(tokens, d):
            apns_calls.append(tokens)
            return set()

        monkeypatch.setattr(push, "_send_fcm", _fake_fcm)
        monkeypatch.setattr(push, "_send_apns", _fake_apns)
        monkeypatch.setattr(push, "_apns_config", lambda: {
            "key": "k", "key_id": "i", "team_id": "t", "bundle": "b"})

        await push.deliver(_delivery(user.id), db)
        assert apns_calls == [["c" * 64]]
        assert fcm_calls == [], "iOS must never reach Firebase"

    @pytest.mark.asyncio
    async def test_an_android_token_goes_to_fcm_and_not_apns(self, db, monkeypatch):
        user = await _user(db, "androidonly@example.com")
        await _token(db, user.id, "fcm-registration-token:abc", "android")

        fcm_calls, apns_calls = [], []

        async def _fake_fcm(tokens, d):
            fcm_calls.append(tokens)
            return set()

        async def _fake_apns(tokens, d):
            apns_calls.append(tokens)
            return set()

        monkeypatch.setattr(push, "_send_fcm", _fake_fcm)
        monkeypatch.setattr(push, "_send_apns", _fake_apns)
        monkeypatch.setattr(push, "_fcm_app", lambda: object())

        await push.deliver(_delivery(user.id), db)
        assert fcm_calls == [["fcm-registration-token:abc"]]
        assert apns_calls == []


class TestThePushPreferenceIsFinallyREAD:
    """`notification_preferences.push` has existed as long as the table and
    `_is_enabled` only ever read `enabled` — a dead control inside a live one."""

    @pytest.mark.asyncio
    async def test_no_preference_row_means_allowed(self, db):
        user = await _user(db, "defaultpref@example.com")
        assert await push._push_allowed(db, user.id, "nutrition_alert") is True

    @pytest.mark.asyncio
    async def test_push_false_suppresses_while_the_category_stays_enabled(self, db):
        user = await _user(db, "nopush@example.com")
        db.add(NotificationPreference(
            user_id=user.id, category=NotificationCategory.NUTRITION_ALERT,
            enabled=True, push=False))
        await db.flush()
        assert await push._push_allowed(db, user.id, "nutrition_alert") is False

    @pytest.mark.asyncio
    async def test_a_disabled_category_suppresses_the_push_too(self, db):
        user = await _user(db, "offcat@example.com")
        db.add(NotificationPreference(
            user_id=user.id, category=NotificationCategory.LAB_ANOMALY,
            enabled=False, push=True))
        await db.flush()
        assert await push._push_allowed(db, user.id, "lab_anomaly") is False

    @pytest.mark.asyncio
    async def test_a_suppressed_push_reaches_no_transport(self, db, monkeypatch):
        user = await _user(db, "suppressed@example.com")
        await _token(db, user.id, "d" * 64, "ios")
        db.add(NotificationPreference(
            user_id=user.id, category=NotificationCategory.NUTRITION_ALERT,
            enabled=True, push=False))
        await db.flush()

        called = []
        async def _fake_apns(tokens, d):
            called.append(tokens)
            return set()
        monkeypatch.setattr(push, "_send_apns", _fake_apns)
        monkeypatch.setattr(push, "_apns_config", lambda: {
            "key": "k", "key_id": "i", "team_id": "t", "bundle": "b"})

        assert await push.deliver(_delivery(user.id), db) == 0
        assert called == []


class TestOnlyAProvablyDeadTokenIsPruned:
    @pytest.mark.asyncio
    async def test_a_token_the_store_called_dead_is_deleted(self, db):
        user = await _user(db, "dead@example.com")
        await _token(db, user.id, "e" * 64, "ios")
        assert await push._prune(db, {"e" * 64}) == 1
        left = (await db.execute(select(DeviceToken).where(
            DeviceToken.user_id == user.id))).scalars().all()
        assert left == []

    @pytest.mark.asyncio
    async def test_pruning_nothing_is_not_an_error(self, db):
        assert await push._prune(db, set()) == 0

    def test_only_UNREGISTERED_and_410_count_as_proof_of_death(self):
        """REGRESSION GUARD. `BadDeviceToken` must NOT prune.

        Apple returns `BadDeviceToken` both for a malformed token AND for one
        registered in the OTHER environment — its own documentation says to
        "verify that the token matches the environment". This record's 21
        tokens span 2026-08-21..09-28, a window containing both
        distribution-signed builds (Release entitlement:
        aps-environment=production) and local debug builds (development), so a
        mismatch is EXPECTED. Pruning on it would delete working devices on the
        very first send, and the patient would then silently stop receiving
        alerts with nothing to explain it.

        `DeviceTokenNotForTopic` is a bundle-id mismatch: our config is wrong,
        the device is fine.

        Read off the source so the rule cannot drift from its comment.
        """
        import inspect
        src = inspect.getsource(push._send_apns)
        prune_line = next(
            (ln for ln in src.splitlines()
             if "dead.add(token)" in ln or "resp.status_code == 410" in ln), "")
        assert "Unregistered" in src
        # The pruning CONDITION must not mention the ambiguous reasons.
        cond = src.split("dead.add(token)")[0].splitlines()[-3:]
        cond_text = " ".join(cond)
        assert "BadDeviceToken" not in cond_text, (
            f"BadDeviceToken must not gate pruning; found: {cond_text!r}")
        assert "DeviceTokenNotForTopic" not in cond_text, (
            f"DeviceTokenNotForTopic must not gate pruning; found: {cond_text!r}")

    @pytest.mark.asyncio
    async def test_a_transport_failure_prunes_NOTHING(self, db, monkeypatch):
        """A timeout says nothing about the token.

        Deleting on a 5xx or a dropped connection would unregister working
        devices because Apple had a bad minute — and the patient would then
        silently stop receiving alerts with nothing to explain it.
        """
        user = await _user(db, "flaky@example.com")
        await _token(db, user.id, "f" * 64, "ios")

        async def _boom(tokens, d):
            raise TimeoutError("apns unreachable")

        monkeypatch.setattr(push, "_send_apns", _boom)
        monkeypatch.setattr(push, "_apns_config", lambda: {
            "key": "k", "key_id": "i", "team_id": "t", "bundle": "b"})

        await push.deliver(_delivery(user.id), db)
        left = (await db.execute(select(DeviceToken).where(
            DeviceToken.user_id == user.id))).scalars().all()
        assert len(left) == 1, "a working device must survive an outage"


class TestItNeverCostsTheNotificationOrTheSave:
    def test_enqueue_before_start_returns_false_and_does_not_raise(self):
        """A script, a worker or a test writes notifications with no drain
        running. That must be silent: the notification is still WRITTEN."""
        assert push._queue is None
        assert push.enqueue(user_id=1, title="t", body="b",
                            category="system") is False

    @pytest.mark.asyncio
    async def test_a_transport_exception_never_escapes_deliver(self, db, monkeypatch):
        user = await _user(db, "noescape@example.com")
        await _token(db, user.id, "g" * 64, "ios")

        async def _boom(tokens, d):
            raise RuntimeError("apple is down")

        monkeypatch.setattr(push, "_send_apns", _boom)
        monkeypatch.setattr(push, "_apns_config", lambda: {
            "key": "k", "key_id": "i", "team_id": "t", "bundle": "b"})
        assert await push.deliver(_delivery(user.id), db) == 0

    @pytest.mark.asyncio
    async def test_a_user_with_no_devices_is_not_an_error(self, db):
        user = await _user(db, "nodevice@example.com")
        assert await push.deliver(_delivery(user.id), db) == 0

    @pytest.mark.asyncio
    async def test_writing_a_notification_still_works_with_push_unstarted(self, db):
        """The §3ah rule: a side channel must never fail the thing it observes."""
        from app.core.notification_engine import create_notification
        from app.models.notifications import Notification, NotificationPriority

        user = await _user(db, "stillwrites@example.com")
        note = await create_notification(
            db, user_id=user.id,
            category=NotificationCategory.NUTRITION_ALERT,
            priority=NotificationPriority.HIGH,
            title="Potassium is high", message="2500 mg today",
            metadata_dict={"nutrient": "potassium_mg"})
        await db.flush()
        assert note is not None
        rows = (await db.execute(select(Notification).where(
            Notification.user_id == user.id))).scalars().all()
        assert len(rows) == 1


class TestTheQueueActuallyDELIVERS:
    """The STARTED path — that `enqueue` reaches a transport.

    Everything above proves the sender does no HARM: unconfigured rails are
    quiet, refusals are honest, failures do not escape. None of it proves it
    does its JOB. A sender tested only in its unconfigured state is §3ar in
    test form — nothing would notice if `enqueue` put rows on a queue that no
    drain ever read, which is precisely the class of defect this whole feature
    exists to correct.
    """

    @pytest.mark.asyncio
    async def test_an_enqueued_delivery_reaches_the_transport(self, db, monkeypatch):
        import asyncio

        user = await _user(db, "drains@example.com")
        await _token(db, user.id, "h" * 64, "ios")
        # The drain opens its OWN session (the request's is closed by then), so
        # the seed has to be COMMITTED or it cannot see the user or the token.
        await db.commit()

        seen: list[tuple[list[str], str]] = []

        async def _fake_apns(tokens, d):
            seen.append((list(tokens), d.title))
            return set()

        monkeypatch.setattr(push, "_send_apns", _fake_apns)
        monkeypatch.setattr(push, "_apns_config", lambda: {
            "key": "k", "key_id": "i", "team_id": "t", "bundle": "b"})
        # The drain opens its own session from `async_session`, which is built
        # from DATABASE_URL — `localhost:5435` — and inside this container
        # `localhost` is the container itself, not the compose `db` service, so
        # it reaches NO database (§3aa). `deliver` swallows its own failures, so
        # without this the assertion below would go red for an environment
        # reason rather than a real one: §0, blaming code for an artifact of the
        # environment. Swapping only the factory keeps the real queue -> drain
        # -> deliver -> transport path under test. Same fix as
        # `test_auth_alerts.py`, which hit this first.
        monkeypatch.setattr(push, "async_session", TestSession)

        push.start()
        try:
            assert push.enqueue(
                user_id=user.id, title="Potassium is high",
                body="Today's potassium is 2500 mg",
                category="nutrition_alert", notification_id=7,
                action_url="/nutrition") is True
            # Wait for the drain to finish the item rather than sleeping: a
            # fixed sleep is how a test becomes flaky on a slow machine.
            await asyncio.wait_for(push._queue.join(), timeout=15)
        finally:
            await push.stop()

        assert seen == [(["h" * 64], "Potassium is high")], (
            "the queued delivery must actually reach a transport")

    @pytest.mark.asyncio
    async def test_a_full_queue_DROPS_rather_than_growing(self, monkeypatch):
        """An unbounded queue turns an Apple outage into memory exhaustion.

        Losing an alert beats failing the clinical write that caused it (§3ah),
        so the drop is deliberate — but it must be counted, or a silent loss
        is indistinguishable from nothing having happened.
        """
        import asyncio

        monkeypatch.setattr(push, "_queue", asyncio.Queue(maxsize=1))
        monkeypatch.setattr(push, "_dropped", 0)

        assert push.enqueue(user_id=1, title="a", body="b",
                            category="system") is True
        assert push.enqueue(user_id=1, title="c", body="d",
                            category="system") is False
        assert push._dropped == 1

    @pytest.mark.asyncio
    async def test_stop_leaves_no_queue_behind(self, monkeypatch):
        """`start()` is idempotent and `stop()` must actually clear state, or
        the next caller enqueues onto a drain that is no longer running."""
        push.start()
        push.start()          # second call must be a no-op, not a second drain
        assert push._queue is not None
        await push.stop()
        assert push._queue is None
        assert push.status()["running"] is False
