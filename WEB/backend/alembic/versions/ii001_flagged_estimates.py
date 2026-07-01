"""flagged_estimates — believability review/learning queue

Revision ID: ii001_flagged_estimates
Revises: hh001_facilities
Create Date: 2026-07-01
"""
import sqlalchemy as sa
from alembic import op

revision = "ii001_flagged_estimates"
down_revision = "hh001_facilities"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "flagged_estimates",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("food_name", sa.String(512), nullable=False),
        sa.Column("food_name_normalized", sa.String(512), nullable=False),
        sa.Column("nutrients", sa.JSON(), nullable=False),
        sa.Column("kcal_per_100g", sa.Float(), nullable=True),
        sa.Column("category", sa.String(64), nullable=True),
        sa.Column("expected_kcal_low", sa.Float(), nullable=True),
        sa.Column("expected_kcal_high", sa.Float(), nullable=True),
        sa.Column("reason", sa.String(64), nullable=False, server_default="out_of_band"),
        sa.Column("source", sa.String(40), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("reviewed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("occurrences", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_flagged_estimates_food_name",
                    "flagged_estimates", ["food_name"])
    op.create_index("ix_flagged_estimates_food_name_normalized",
                    "flagged_estimates", ["food_name_normalized"])
    op.create_index("ix_flagged_estimates_reviewed",
                    "flagged_estimates", ["reviewed"])


def downgrade():
    op.drop_index("ix_flagged_estimates_reviewed", table_name="flagged_estimates")
    op.drop_index("ix_flagged_estimates_food_name_normalized", table_name="flagged_estimates")
    op.drop_index("ix_flagged_estimates_food_name", table_name="flagged_estimates")
    op.drop_table("flagged_estimates")
