"""Which external identities belong to which account.

Social sign-in used to be brokered by Firebase, and the link was a single
`users.firebase_uid`. Two things are wrong with carrying that forward now that
the provider's own token is verified directly:

  * the column names a vendor we no longer use, and
  * it holds ONE value, while a person may sign in with Google today and Apple
    tomorrow and expect the same account. One column cannot hold both, so the
    second provider would either overwrite the first or create a duplicate
    account for the same human.

So the link is its own row: one per (provider, subject). `subject` is the
provider's stable `sub` claim — not the email, which people change, and which
Apple may hand over as a per-app private relay address that differs from the one
they use anywhere else.

`(provider, subject)` is UNIQUE: one external identity resolves to exactly one
account, or the lookup that authenticates people is ambiguous.
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

GOOGLE = "google"
APPLE = "apple"


class UserIdentity(Base):
    """One external identity (a provider's `sub`) linked to one local account."""

    __tablename__ = "user_identities"
    __table_args__ = (
        UniqueConstraint("provider", "subject", name="uq_user_identity_provider_subject"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True,
    )

    #: "google" | "apple". Stored as given rather than an enum: a new provider
    #: must not require a migration before anyone can sign in with it.
    provider: Mapped[str] = mapped_column(String(32), nullable=False)

    #: The provider's stable subject (`sub`). Opaque, and the only identifier
    #: here that is guaranteed not to change under the person's feet.
    subject: Mapped[str] = mapped_column(String(255), nullable=False)

    #: The address the provider asserted AT LINK TIME — kept for support
    #: questions ("which account is this?"), never for matching. Apple's private
    #: relay means this can differ from the address the user knows themselves by.
    email: Mapped[str | None] = mapped_column(String(320))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    #: Answers "is this link still in use, or can it be revoked?"
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
