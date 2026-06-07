"""add_pantry_items

Revision ID: c5ffe803fcf5
Revises: c6d7e8f9a0b1
Create Date: 2026-02-17 08:12:20.730816
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "c5ffe803fcf5"
down_revision: Union[str, None] = "c6d7e8f9a0b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pantry_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(length=50), nullable=False),
        sa.Column("location", sa.String(length=50), nullable=False),
        sa.Column("expiration_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("auto_replenish", sa.Boolean(), nullable=False),
        sa.Column("low_threshold", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_pantry_items_id"), "pantry_items", ["id"], unique=False)
    op.create_index(op.f("ix_pantry_items_user_id"), "pantry_items", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_pantry_items_user_id"), table_name="pantry_items")
    op.drop_index(op.f("ix_pantry_items_id"), table_name="pantry_items")
    op.drop_table("pantry_items")
