"""What happened to an email AFTER we handed it to the provider.

The application could not answer "did it arrive?" for any message it has ever
sent. `send_email` returns True the moment Resend answers 200, and Resend
answers 200 with a message id for a send it will never transmit — an address on
its suppression list, added automatically after an earlier hard bounce. So the
log line said "Email sent via Resend to …" three times for one bounce and two
sends that never left the building, and the only way anyone found out was by
opening the Resend dashboard by hand.

That is §3d's recurring shape: a success path reporting success without
evidence, the same as the 17 unsubscribe links that rendered "You're
unsubscribed" and recorded nothing. The send RESPONSE cannot tell us; only the
delivery EVENT can.

These rows are that evidence. One per provider callback, keyed on the
provider's own message id so a send can be joined to its fate, and on the
recipient so a habitually bouncing address is visible without a dashboard.

The payload is kept verbatim. A provider adds fields, and a column list written
today is a column list that silently drops whatever it did not anticipate.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

#: Event names Resend sends. Stored as given rather than mapped to an enum of
#: our own: a provider that adds an event type must not make a row unwritable,
#: and the raw name is what the dashboard shows.
BOUNCED = "email.bounced"
COMPLAINED = "email.complained"
DELIVERED = "email.delivered"
DELIVERY_DELAYED = "email.delivery_delayed"
SENT = "email.sent"

#: The ones that mean a person did NOT receive it, and somebody should know.
FAILURE_EVENTS = frozenset({BOUNCED, COMPLAINED})


class EmailEvent(Base):
    """One delivery event for one message, as the provider reported it."""

    __tablename__ = "email_events"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    #: "resend" today. Named rather than assumed, because SMTP is still the
    #: fallback path and would report nothing at all — an absence of rows for a
    #: message is not evidence of delivery.
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="resend")

    #: The provider's message id — the same value `send_email` already logs, so
    #: a send in the application log can be joined to what became of it.
    message_id: Mapped[str | None] = mapped_column(String(128), index=True)

    #: Verbatim provider event name, e.g. "email.bounced".
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    #: Indexed because the useful question is usually about an ADDRESS — has
    #: this one bounced before, is it suppressed — not about one message.
    recipient: Mapped[str | None] = mapped_column(String(320), index=True)
    subject: Mapped[str | None] = mapped_column(String(500))

    #: Why it failed, where the provider says. "hard"/"soft" and the SMTP
    #: response are what separate a wrong address from a full mailbox.
    bounce_type: Mapped[str | None] = mapped_column(String(32))
    reason: Mapped[str | None] = mapped_column(Text)

    #: When the provider says it happened, versus when we were told. They
    #: differ, and a webhook retried for hours would otherwise look current.
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    #: The whole callback, as sent. Kept because the columns above are a guess
    #: about which fields matter, made before the first real incident.
    payload: Mapped[str | None] = mapped_column(Text)

    @property
    def is_failure(self) -> bool:
        return self.event_type in FAILURE_EVENTS
