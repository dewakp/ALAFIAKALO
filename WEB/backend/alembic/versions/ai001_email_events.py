"""email_events — what happened to a message AFTER we handed it to the provider

The application could not answer "did it arrive?" for any message it has ever
sent. `send_email` returns True the moment Resend answers 200, and Resend
answers 200 with a message id for a send it will never transmit: an address on
its suppression list, added automatically after an earlier hard bounce. On
2026-09-23 that produced three "Email sent via Resend to …" log lines for one
bounce and two sends that never left the building, and those lines were then
reported as proof of delivery.

The send RESPONSE cannot tell us; only the delivery EVENT can. These rows are
that evidence — §3d's "the row is the receipt", applied to outbound mail rather
than to the contact form.

Hand-written. `--autogenerate` on this schema emits ~200 lines that drop five
live tables and a `users` column — canon §3ao. Additive only.

Revision ID: ai001_email_events
Revises: ah001_nutrient_effects
Create Date: 2026-09-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "ai001_email_events"
down_revision: Union[str, None] = "ah001_nutrient_effects"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "email_events",
        sa.Column("id", sa.Integer(), nullable=False),
        # "resend" today. Named rather than assumed: SMTP is still the fallback
        # path and reports nothing at all, so an ABSENCE of rows for a message
        # is not evidence of delivery.
        sa.Column("provider", sa.String(length=32), nullable=False,
                  server_default="resend"),
        # The provider's message id — the same value the send path logs, so a
        # send in the application log can be joined to what became of it.
        sa.Column("message_id", sa.String(length=128), nullable=True),
        # Verbatim provider event name ("email.bounced"). Not an enum of our
        # own: a provider that adds an event type must not make a row
        # unwritable, and the raw name is what the dashboard shows.
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("recipient", sa.String(length=320), nullable=True),
        sa.Column("subject", sa.String(length=500), nullable=True),
        sa.Column("bounce_type", sa.String(length=32), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        # When the provider says it happened, versus when we were told. They
        # differ, and a webhook retried for hours would otherwise look current.
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        # The whole callback, as sent. The columns above are a guess about
        # which fields matter, made before the first real incident.
        sa.Column("payload", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_email_events_id"), "email_events", ["id"], unique=False)
    op.create_index(op.f("ix_email_events_message_id"), "email_events",
                    ["message_id"], unique=False)
    op.create_index(op.f("ix_email_events_event_type"), "email_events",
                    ["event_type"], unique=False)
    # The useful question is usually about an ADDRESS — has this one bounced
    # before, is it suppressed — not about one message.
    op.create_index(op.f("ix_email_events_recipient"), "email_events",
                    ["recipient"], unique=False)
    op.create_index("idx_email_events_recipient_received", "email_events",
                    ["recipient", "received_at"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_email_events_recipient_received", table_name="email_events")
    op.drop_index(op.f("ix_email_events_recipient"), table_name="email_events")
    op.drop_index(op.f("ix_email_events_event_type"), table_name="email_events")
    op.drop_index(op.f("ix_email_events_message_id"), table_name="email_events")
    op.drop_index(op.f("ix_email_events_id"), table_name="email_events")
    op.drop_table("email_events")
