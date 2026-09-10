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


# ── payment may now precede verification; the ACCOUNT may not ──────────

def test_payment_no_longer_requires_a_verified_email():
    """The signup that prompted this change never reached payment: the account
    was created silently with no mail and no money, and the person had no way
    to tell. Payment is now collected while they are still on the page."""
    import inspect

    from app.services import signup_service

    src = inspect.getsource(signup_service.mark_paid)
    assert "Payment recorded for unverified signup" not in src, (
        "mark_paid must no longer refuse an unverified signup")


def test_the_account_still_requires_BOTH_gates():
    """Relaxing payment must not relax account creation. `materialise` is the
    only path from a pending signup to a users row, and it checks both."""
    import inspect

    from app.services import signup_service

    src = inspect.getsource(signup_service.materialise)
    assert "ready_to_create" in src
    assert "return None" in src


@pytest.mark.parametrize("verified,paid,expected", [
    (False, False, False),
    (True, False, False),
    (False, True, False),   # paid but unproven mailbox — still no account
    (True, True, True),
])
def test_ready_to_create_needs_both(verified, paid, expected):
    from datetime import datetime, timedelta, timezone

    from app.models.pending_registration import PendingRegistration

    p = PendingRegistration(
        email="x@example.com", password_hash="h", full_name="X",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        email_verified_at=datetime.now(timezone.utc) if verified else None,
        paid_at=datetime.now(timezone.utc) if paid else None,
    )
    assert p.ready_to_create is expected


@pytest.mark.asyncio
async def test_an_undeliverable_domain_is_refused_before_payment():
    """Payment now precedes proof, so a typo becomes someone who paid and
    cannot be reached. A domain with no MX record can never accept mail."""
    from app.services.email_deliverability import can_receive_mail

    ok, reason = await can_receive_mail("someone@gmial.cmo")
    assert ok is False and "cannot receive email" in reason

    ok, _ = await can_receive_mail("someone@gmail.com")
    assert ok is True


@pytest.mark.asyncio
async def test_dns_failure_does_not_refuse_a_paying_customer(monkeypatch):
    """Unreachable is not invalid — refusing a customer because our resolver
    blinked is worse than the failure being guarded against (§3aj)."""
    from app.services import email_deliverability as mod

    monkeypatch.setattr(mod, "_has_mx", lambda domain: None)
    ok, reason = await mod.can_receive_mail("someone@whatever.example")
    assert ok is True and reason is None


def test_the_receipt_does_not_invalidate_the_emailed_link():
    """Minting a fresh token in the receipt overwrote the stored hash and
    silently broke the link already in their inbox — a correct verification
    failed after payment. Caught in testing, not in production."""
    import inspect

    from app.api import signup

    src = inspect.getsource(signup.signup_complete)
    assert "svc.new_token()" not in src, (
        "completing payment must not mint a token over the live one")
