"""Contact submissions — the row IS the receipt.

Email is a notification, not the record. `alafia.app` publishes DKIM and SPF and
has **no MX records at all**: it can send and cannot receive. So a contact form
that only emailed `contact@alafia.app` would have Resend accept the send, return
success, tell the sender "we have it", and bounce where nobody looks — the §3d
failure exactly, where 17 unsubscribe links rendered "You're unsubscribed" and
recorded nothing.

So the submission is persisted first and the request succeeds on THAT. Mail is
attempted afterwards and its failure is logged, never surfaced as a rejection:
the message is already safe.

Modelled on the CRAM marketing site's `contact_forms` — a ticket reference, a
`status` for triage, and room for an assignee and notes.
"""

from datetime import datetime, timezone

from sqlalchemy import String, Text, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ContactSubmission(Base):
    __tablename__ = "contact_submissions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Short human-quotable handle, given back to the sender so they can refer
    # to it. Not the primary key: a guessable sequential id in a URL is an
    # enumeration handle, and these rows can carry health details.
    reference: Mapped[str] = mapped_column(String(16), nullable=False,
                                           unique=True, index=True)

    # Which desk. A key from TOPIC_DESKS — the server resolves the address, so
    # the form can never be pointed at an arbitrary recipient.
    topic: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    organization: Mapped[str | None] = mapped_column(String(160))
    phone: Mapped[str | None] = mapped_column(String(40))
    message: Mapped[str] = mapped_column(Text, nullable=False)

    # new | read | answered | closed
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="new",
                                        index=True)
    assigned_to: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)

    # Whether the notification email actually went out. Recorded because it is
    # the difference between "nobody has looked yet" and "nobody was told".
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notify_error: Mapped[str | None] = mapped_column(String(300))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_contact_status_created", "status", "created_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<ContactSubmission {self.reference} {self.topic} {self.status}>"
