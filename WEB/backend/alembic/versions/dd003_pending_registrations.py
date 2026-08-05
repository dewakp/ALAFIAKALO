"""pending_registrations: signups that are not yet accounts

Direct registration created a `users` row for one unauthenticated POST, which is
how 55 of the 77 accounts in this database became `*@example.com` / `*@x.com`
automation leftovers.

A signup now waits here until BOTH gates pass — email verified, subscription
paid — and only then becomes a user. A robot that never reads mail and never
pays leaves one expiring row and nothing else.

Only the SHA-256 of the verification token is stored, so a dump of this table
does not let anyone verify an address they do not control.

Revision ID: dd003_pending_registrations
Revises: dd002_user_last_login
"""

from alembic import op
import sqlalchemy as sa


revision = "dd003_pending_registrations"
down_revision = "dd002_user_last_login"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pending_registrations",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True, index=True),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("verification_token_hash", sa.String(64), nullable=True, index=True),
        sa.Column("verification_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verification_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payment_provider", sa.String(20), nullable=True),
        sa.Column("payment_reference", sa.String(255), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False, index=True),
    )
    op.create_index(
        "ix_pending_registrations_state",
        "pending_registrations", ["email_verified_at", "paid_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_pending_registrations_state", table_name="pending_registrations")
    op.drop_table("pending_registrations")
