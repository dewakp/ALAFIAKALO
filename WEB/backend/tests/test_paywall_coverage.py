"""What an unpaid, signed-in account can still reach.

Login is deliberately open — a lapsed member has to be able to sign in to
renew, and someone who has not paid has to be able to reach checkout. That is
only safe if the token they get grants nothing else. It did not:

  * `_PAYWALL_OPEN_PREFIXES` held `"/api/v1/users"` as a PREFIX so the app
    could load `/users/me` and draw the paywall — but `user_roles.py` is
    mounted under `/users` too, so the same line opened ten more endpoints,
    including `POST /users/roles` and `PUT /users/roles/{id}/profile`.
  * the four WebSocket endpoints are mounted without the paywall dependency
    (it is a Request dependency; a handshake carries a WebSocket) and did no
    entitlement check of their own. Real-time messaging, the activity feed and
    telehealth were reachable by anyone holding a valid token.

Gating HTTP while leaving sockets open gates nothing, so both are pinned here.
"""

import inspect

from app.core import entitlement


# ── the open list is exact where it needs to be ────────────────────────


def test_users_me_stays_open():
    """Without it the app cannot render the paywall the user pays from."""
    assert entitlement._paywall_open_path("/api/v1/users/me")
    assert entitlement._paywall_open_path("/api/v1/users/me/")


def test_auth_and_subscription_stay_open():
    """A lapsed member must be able to sign in and reach checkout."""
    for path in (
        "/api/v1/auth/login",
        "/api/v1/auth/refresh",
        "/api/v1/auth/password-reset/request",
        "/api/v1/subscription/plans",
        "/api/v1/subscription/status",
        "/api/v1/subscription/checkout",
        "/api/v1/subscription/webhook/stripe",
    ):
        assert entitlement._paywall_open_path(path), path


def test_roles_endpoints_are_NOT_open():
    """The prefix that opened /users/me also opened all of user_roles.py."""
    for path in (
        "/api/v1/users/roles",
        "/api/v1/users/roles/me",
        "/api/v1/users/roles/catalog",
        "/api/v1/users/roles/7/profile",
        "/api/v1/users/roles/7/primary",
    ):
        assert not entitlement._paywall_open_path(path), path


def test_ordinary_feature_paths_are_not_open():
    for path in (
        "/api/v1/nutrition/",
        "/api/v1/medications/dose-logs",
        "/api/v1/chronic/therapy-sessions",
        "/api/v1/ai/chat",
        "/api/v1/notifications/unread-count",
        "/api/v1/messaging/recipients",
    ):
        assert not entitlement._paywall_open_path(path), path


def test_open_list_is_not_a_bare_users_prefix():
    """Regression: a startswith() on a shared prefix grants whatever anyone
    mounts beneath it later. That is how roles became reachable."""
    assert "/api/v1/users" not in entitlement._PAYWALL_OPEN_PREFIXES


# ── every websocket checks entitlement ─────────────────────────────────


def _ws_source():
    from app.api import ws_messaging, ws_telehealth
    return inspect.getsource(ws_messaging) + inspect.getsource(ws_telehealth)


def test_every_websocket_endpoint_checks_entitlement():
    """One check per socket endpoint. There are four."""
    src = _ws_source()
    assert src.count("is_user_entitled") >= 4, (
        "a WebSocket endpoint is missing its entitlement check — sockets are "
        "mounted outside the paywalled router and get no gate for free")


def test_websockets_refuse_with_a_distinct_code():
    """4402 mirrors HTTP 402, so a client can tell 'not paid' from 'not
    allowed' (4003) and 'bad token' (4001)."""
    src = _ws_source()
    assert "4402" in src


def test_all_four_socket_routes_still_exist():
    """If a route is added later it must be gated too — this fails loudly
    when the count changes rather than silently leaving a new hole."""
    from app.api import ws_messaging, ws_telehealth
    src = inspect.getsource(ws_messaging) + inspect.getsource(ws_telehealth)
    assert src.count("@router.websocket(") == 4, (
        "socket route count changed — gate the new one and update this test")


# ── the switch itself ──────────────────────────────────────────────────


def test_nothing_is_gated_when_the_paywall_is_off(monkeypatch):
    monkeypatch.setattr(entitlement.settings, "SUBSCRIPTION_REQUIRED", False)
    # _paywall_open_path is unaffected by the flag; the dependency short-circuits.
    src = inspect.getsource(entitlement.require_active_subscription)
    assert "if not settings.SUBSCRIPTION_REQUIRED" in src
