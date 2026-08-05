"""Admin console authorization.

This is the security boundary for a console over patient-adjacent data, so the
rules are pinned here rather than left to the hostname or the UI.
"""

import pytest

from app.core.admin_auth import is_admin


class FakeUser:
    def __init__(self, email, is_active=True, is_superuser=False):
        self.id = 1
        self.email = email
        self.is_active = is_active
        self.is_superuser = is_superuser


def test_configured_admin_is_allowed():
    assert is_admin(FakeUser("dew@6igma.com")) is True


@pytest.mark.parametrize("email", [
    "DEW@6IGMA.COM", "  dew@6igma.com  ", "Dew@6Igma.Com",
])
def test_email_match_is_case_and_whitespace_insensitive(email):
    """A capitalised address must not silently lock the operator out."""
    assert is_admin(FakeUser(email)) is True


def test_other_users_are_refused():
    assert is_admin(FakeUser("developer@hntsolutions.com")) is False
    assert is_admin(FakeUser("attacker@example.com")) is False


def test_superuser_flag_alone_does_not_grant_access():
    """`is_superuser` is set on a leftover test account in this database.

    Console access must not follow from one stray UPDATE, so the flag is not
    sufficient — the email allowlist is the gate.
    """
    assert is_admin(FakeUser("crossapp_1782548450@example.com", is_superuser=True)) is False


def test_deactivated_admin_is_refused():
    assert is_admin(FakeUser("dew@6igma.com", is_active=False)) is False


@pytest.mark.parametrize("user", [None, FakeUser(""), FakeUser(None)])
def test_missing_or_empty_identity_is_refused(user):
    assert is_admin(user) is False


def test_admin_emails_are_read_from_settings(monkeypatch):
    """The allowlist is configuration, not a hardcoded constant."""
    from app.core import admin_auth
    monkeypatch.setattr(admin_auth.settings, "ADMIN_EMAILS", ["someone.else@example.com"])
    assert is_admin(FakeUser("dew@6igma.com")) is False
    assert is_admin(FakeUser("someone.else@example.com")) is True
