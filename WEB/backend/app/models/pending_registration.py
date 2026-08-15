"""A signup in progress — deliberately NOT a user account.

Robot signups were creating real `users` rows: 55 of 77 accounts in this
database were `*@example.com` / `*@x.com` automation leftovers. The fix is to
stop handing out user rows for free.

An account is now materialised only when BOTH gates are passed:

    1. the email address is verified (proves a reachable mailbox)
    2. a subscription is paid for

Until then the signup lives here. A robot that never reads mail and never pays
leaves one expiring row in this table and nothing else — no `users` row, no
identity credential, no place in any user count.

Nothing here is a credential store: `password_hash` is held only so the account
can be created at the end without asking again, and the row is deleted the
moment the real account exists.
"""

from datetime import datetime, timezone

from sqlalchemy import String, DateTime, Text, Integer, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PendingRegistration(Base):
    __tablename__ = "pending_registrations"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Hashed on arrival — a pending signup is never a place for a plaintext secret.
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    # ── Gate 1: email verification ───────────────────────────────────────
    # Only the SHA-256 of the token is stored. A leaked database row must not
    # let anyone verify an address they do not control.
    verification_token_hash: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    verification_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verification_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # ── Gate 2: payment ──────────────────────────────────────────────────
    payment_provider: Mapped[str | None] = mapped_column(String(20), nullable=True)
    payment_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # ── Gate 0: age ──────────────────────────────────────────────────────
    # Captured at /signup/start and validated there, BEFORE the verification
    # email is sent or any payment is taken — refusing someone after they have
    # paid is both a bad experience and a refund to process. Carried through to
    # the user row by materialise(), because the date of birth is the evidence
    # the age check was performed against.
    date_of_birth: Mapped[str | None] = mapped_column(String(10), nullable=True)
    country: Mapped[str | None] = mapped_column(String(2), nullable=True)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    # Abandoned signups are swept, so this table cannot grow without bound and a
    # squatted email address frees itself.
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)

    @property
    def email_verified(self) -> bool:
        return self.email_verified_at is not None

    @property
    def paid(self) -> bool:
        return self.paid_at is not None

    @property
    def ready_to_create(self) -> bool:
        """Both gates passed. The ONLY condition under which an account is made."""
        return self.email_verified and self.paid

    def is_expired(self, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        expires = self.expires_at
        if expires is not None and expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        return expires is not None and expires <= now


Index("ix_pending_registrations_state", PendingRegistration.email_verified_at,
      PendingRegistration.paid_at)
