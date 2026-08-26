"""Marketing opt-out, so a bulk announcement can carry a real unsubscribe.

The app had no marketing consent surface at all. `NotificationCategory` has
twelve values and every one of them is clinical or system — therapy sessions,
lab anomalies, refill reminders — and `notification_preferences.email` defaults
to False. None of that describes "may we send you product announcements", so
there was nothing to check before a bulk send and nothing for a recipient to
turn off afterwards.

A timestamp rather than a boolean: WHEN someone opted out is the fact that
matters if a recipient later disputes a send, and NULL/NOT NULL carries the
boolean for free. Opt-out (not opt-in) matches the column's purpose — every
existing account predates the consent surface, so a boolean defaulting to False
would have silently read as "everyone consented".

This gates MARKETING only. Transactional mail — password reset, address
verification, payment failure — is not affected and must never consult it: a
user who opts out of announcements still needs to be able to reset a password.

Revision ID: oo001_marketing_opt_out
Revises: nn001_condition_icd11
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "oo001_marketing_opt_out"
down_revision: Union[str, None] = "nn001_condition_icd11"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("marketing_opt_out_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Partial index: the only question ever asked of this column is "who is still
    # eligible", so index the opted-out minority rather than the whole table.
    op.create_index(
        "ix_users_marketing_opt_out_at",
        "users",
        ["marketing_opt_out_at"],
        unique=False,
        postgresql_where=sa.text("marketing_opt_out_at IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_users_marketing_opt_out_at", table_name="users")
    op.drop_column("users", "marketing_opt_out_at")
