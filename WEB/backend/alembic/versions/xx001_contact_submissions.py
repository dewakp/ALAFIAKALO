"""contact_submissions — the contact form's record of truth

Revision ID: xx001_contact_submissions
Revises: ww001_condition_nutrition
Create Date: 2026-09-02

Hand-written. `--autogenerate` on this schema emits ~200 lines that drop five
live tables and a `users` column — see canon §3ao. Additive only.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "xx001_contact_submissions"
down_revision: Union[str, None] = "ww001_condition_nutrition"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "contact_submissions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("reference", sa.String(length=16), nullable=False),
        sa.Column("topic", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("organization", sa.String(length=160), nullable=True),
        sa.Column("phone", sa.String(length=40), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False,
                  server_default="new"),
        sa.Column("assigned_to", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notify_error", sa.String(length=300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reference", name="uq_contact_reference"),
    )
    op.create_index(op.f("ix_contact_submissions_id"), "contact_submissions",
                    ["id"], unique=False)
    op.create_index(op.f("ix_contact_submissions_reference"), "contact_submissions",
                    ["reference"], unique=False)
    op.create_index(op.f("ix_contact_submissions_topic"), "contact_submissions",
                    ["topic"], unique=False)
    op.create_index(op.f("ix_contact_submissions_email"), "contact_submissions",
                    ["email"], unique=False)
    op.create_index(op.f("ix_contact_submissions_status"), "contact_submissions",
                    ["status"], unique=False)
    op.create_index(op.f("ix_contact_submissions_created_at"), "contact_submissions",
                    ["created_at"], unique=False)
    op.create_index("idx_contact_status_created", "contact_submissions",
                    ["status", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_contact_status_created", table_name="contact_submissions")
    op.drop_index(op.f("ix_contact_submissions_created_at"),
                  table_name="contact_submissions")
    op.drop_index(op.f("ix_contact_submissions_status"),
                  table_name="contact_submissions")
    op.drop_index(op.f("ix_contact_submissions_email"),
                  table_name="contact_submissions")
    op.drop_index(op.f("ix_contact_submissions_topic"),
                  table_name="contact_submissions")
    op.drop_index(op.f("ix_contact_submissions_reference"),
                  table_name="contact_submissions")
    op.drop_index(op.f("ix_contact_submissions_id"),
                  table_name="contact_submissions")
    op.drop_table("contact_submissions")
