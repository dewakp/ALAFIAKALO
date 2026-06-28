"""learned_food_nutrients — nutrition learning model (user corrections)

Revision ID: dd001_learned_food_nutrients
Revises: cc001_user_identity_uid
Create Date: 2026-06-28
"""
import sqlalchemy as sa
from alembic import op

revision = "dd001_learned_food_nutrients"
down_revision = "cc001_user_identity_uid"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "learned_food_nutrients",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("food_name_normalized", sa.String(512), nullable=False),
        sa.Column("food_name_original", sa.String(512), nullable=False),
        sa.Column("nutrients", sa.JSON(), nullable=False),
        sa.Column("serving_weight_g", sa.Float(), nullable=True),
        sa.Column("source", sa.String(40), nullable=False, server_default="user_correction"),
        sa.Column("sample_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.95"),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_learned_food_nutrients_food_name_normalized",
        "learned_food_nutrients", ["food_name_normalized"], unique=True,
    )


def downgrade():
    op.drop_index("ix_learned_food_nutrients_food_name_normalized",
                  table_name="learned_food_nutrients")
    op.drop_table("learned_food_nutrients")
