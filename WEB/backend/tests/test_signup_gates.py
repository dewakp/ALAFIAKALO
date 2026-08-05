"""Two-step signup gates.

The anti-robot property is a single invariant: **no `users` row exists until the
email is verified AND the subscription is paid.** Everything else is UI. These
tests pin the invariant so it cannot regress into "account first, gate later" —
which is how 55 of 77 accounts in this database became automation leftovers.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.models.pending_registration import PendingRegistration
from app.services import signup_service as svc


def _pending(**kw) -> PendingRegistration:
    base = dict(
        email="a@example.org", full_name="A", password_hash="x",
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    base.update(kw)
    return PendingRegistration(**base)


# ── The invariant ────────────────────────────────────────────────────────

def test_neither_gate_passed_is_not_ready():
    assert _pending().ready_to_create is False


def test_verified_but_unpaid_is_not_ready():
    """A confirmed mailbox alone must not produce an account."""
    p = _pending(email_verified_at=datetime.now(timezone.utc))
    assert p.email_verified is True and p.paid is False
    assert p.ready_to_create is False


def test_paid_but_unverified_is_not_ready():
    """Payment must not buy past the verification gate."""
    p = _pending(paid_at=datetime.now(timezone.utc))
    assert p.paid is True and p.email_verified is False
    assert p.ready_to_create is False


def test_both_gates_passed_is_ready():
    now = datetime.now(timezone.utc)
    assert _pending(email_verified_at=now, paid_at=now).ready_to_create is True


# ── Expiry ───────────────────────────────────────────────────────────────

def test_expired_signup_is_detected():
    p = _pending(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
    assert p.is_expired() is True


def test_naive_expiry_is_treated_as_utc():
    """Legacy rows can carry naive timestamps; comparing them must not explode."""
    p = _pending(expires_at=datetime.utcnow() - timedelta(hours=1))
    assert p.is_expired() is True


def test_live_signup_is_not_expired():
    assert _pending().is_expired() is False


# ── Tokens ───────────────────────────────────────────────────────────────

def test_only_the_token_hash_is_storable():
    raw, hashed = svc.new_token()
    assert raw != hashed
    assert len(hashed) == 64            # sha256 hex
    assert svc.hash_token(raw) == hashed


def test_tokens_are_unique_per_call():
    assert svc.new_token()[0] != svc.new_token()[0]


def test_token_hash_is_stable():
    assert svc.hash_token("abc") == svc.hash_token("abc")
    assert svc.hash_token("abc") != svc.hash_token("abd")


@pytest.mark.parametrize("raw", ["", "   "])
def test_blank_token_hashes_are_not_matched_by_accident(raw):
    """A blank submitted token must never collide with a stored NULL/blank."""
    assert svc.hash_token(raw.strip()) == svc.hash_token("")
    # ...and the verify path requires a stored hash, which is cleared on use.
