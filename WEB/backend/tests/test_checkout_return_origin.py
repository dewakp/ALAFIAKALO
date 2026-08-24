"""Stripe must return the payer to the origin they started on.

`www.alafia.app` and `alafia.app` BOTH serve the app, with no redirect between
them — verified against production, both answer 200. localStorage is per-origin,
so a user who signs in on www, pays, and is sent back to the apex arrives with no
token: the app reads that as signed out, `/subscription/confirm` never runs, and
they land on a login page having just been charged.

The subscription is real — the webhook still fires — but to the user the payment
plainly failed, which is indistinguishable from a declined card.

The origin comes from a request header, so it is validated before use. An
unvalidated redirect target is an open redirect, and this one is handed to a
payment provider.
"""

import pytest

from app.core.config import settings
from app.services.subscription_service import checkout_return_base


@pytest.fixture(autouse=True)
def _hosts(monkeypatch):
    monkeypatch.setattr(settings, "PUBLIC_WEB_URL", "https://alafia.app")
    monkeypatch.setattr(settings, "CORS_ORIGINS",
                        ["https://alafia.app", "https://www.alafia.app"])


def test_www_comes_back_to_www():
    """The case that stranded a paying user on a login page."""
    assert checkout_return_base("https://www.alafia.app") == "https://www.alafia.app"


def test_apex_comes_back_to_apex():
    assert checkout_return_base("https://alafia.app") == "https://alafia.app"


def test_a_trailing_slash_is_tolerated():
    assert checkout_return_base("https://www.alafia.app/") == "https://www.alafia.app"


def test_no_origin_falls_back_to_the_configured_host():
    assert checkout_return_base(None) == "https://alafia.app"
    assert checkout_return_base("") == "https://alafia.app"


@pytest.mark.parametrize("hostile", [
    "https://evil.example.com",
    "http://alafia.app.evil.example.com",
    "https://alafia.app.attacker.test",
    "//evil.example.com",
    "javascript:alert(1)",
])
def test_an_unknown_origin_is_refused(hostile):
    """A redirect target handed to Stripe must never come from an unchecked header."""
    assert checkout_return_base(hostile) == "https://alafia.app"


def test_scheme_matters():
    """http:// is not the same origin as https:// and must not be honoured."""
    assert checkout_return_base("http://www.alafia.app") == "https://alafia.app"
