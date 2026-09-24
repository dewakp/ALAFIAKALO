"""user_identities — external sign-in identities, one row per (provider, subject)

Social sign-in no longer goes through Firebase, so the link can no longer be a
single `users.firebase_uid`: that column names a vendor we do not use and holds
only ONE value, while a person may sign in with Google today and Apple tomorrow
and expect the same account.

`users.firebase_uid` is deliberately LEFT IN PLACE. Accounts created through the
old Firebase path still carry it, and dropping a populated column to tidy up is
how history is lost — canon §3ao. Nothing new writes it.

Hand-written and additive. `--autogenerate` on this schema emits ~200 lines that
drop five live tables and a `users` column.

Revision ID: aj001_user_identities
Revises: ai001_email_events
Create Date: 2026-09-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "aj001_user_identities"
down_revision: Union[str, None] = "ai001_email_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_identities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        # Not an enum: a new provider must not need a migration before anyone
        # can sign in with it.
        sa.Column("provider", sa.String(length=32), nullable=False),
        # The provider's stable `sub`. Never the email — people change those,
        # and Apple may supply a per-app private relay address.
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        # One external identity resolves to exactly one account, or the lookup
        # that authenticates people is ambiguous.
        sa.UniqueConstraint("provider", "subject",
                            name="uq_user_identity_provider_subject"),
    )
    op.create_index(op.f("ix_user_identities_id"), "user_identities", ["id"], unique=False)
    op.create_index(op.f("ix_user_identities_user_id"), "user_identities",
                    ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_user_identities_user_id"), table_name="user_identities")
    op.drop_index(op.f("ix_user_identities_id"), table_name="user_identities")
    op.drop_table("user_identities")
