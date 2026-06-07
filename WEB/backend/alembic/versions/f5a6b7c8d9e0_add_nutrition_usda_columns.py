"""Add fdc_id and extended_nutrients columns to nutrition_logs

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2025-01-01 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "f5a6b7c8d9e0"
down_revision = "e4f5a6b7c8d9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("nutrition_logs", sa.Column("fdc_id", sa.Integer(), nullable=True))
    op.add_column("nutrition_logs", sa.Column("extended_nutrients", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("nutrition_logs", "extended_nutrients")
    op.drop_column("nutrition_logs", "fdc_id")
