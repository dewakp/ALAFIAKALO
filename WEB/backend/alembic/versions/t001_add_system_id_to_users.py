"""add system_id to users

Revision ID: t001_add_system_id
Revises: s512_upgrade_hash
Create Date: 2026-04-15
"""
from alembic import op
import sqlalchemy as sa

revision = "t001_add_system_id"
down_revision = "s512_upgrade_hash"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "system_id",
            sa.String(255),
            nullable=True,
            comment="255-char immutable System Identifier (SID)",
        ),
    )
    op.create_index("ix_users_system_id", "users", ["system_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_system_id", table_name="users")
    op.drop_column("users", "system_id")
