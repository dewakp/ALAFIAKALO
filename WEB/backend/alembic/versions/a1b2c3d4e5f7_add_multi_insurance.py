"""Add multi-insurance table

Revision ID: a1b2c3d4e5f7
Revises: f5a6b7c8d9e0
Create Date: 2026-02-15 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5f7"
down_revision = "f5a6b7c8d9e0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "insurances",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("region", sa.String(length=50), nullable=False),
        sa.Column("country_code", sa.String(length=10), nullable=False),
        sa.Column("country_name", sa.String(length=100), nullable=False),
        sa.Column("provider_code", sa.String(length=100), nullable=False),
        sa.Column("provider_name", sa.String(length=255), nullable=False),
        sa.Column("policy_number", sa.String(length=100), nullable=True),
        sa.Column("group_number", sa.String(length=100), nullable=True),
        sa.Column("member_id", sa.String(length=100), nullable=True),
        sa.Column("plan_name", sa.String(length=255), nullable=True),
        sa.Column("plan_type", sa.String(length=100), nullable=True),
        sa.Column("coverage_start", sa.Date(), nullable=True),
        sa.Column("coverage_end", sa.Date(), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("subscriber_name", sa.String(length=255), nullable=True),
        sa.Column("subscriber_relationship", sa.String(length=50), nullable=True),
        sa.Column("insurance_phone", sa.String(length=50), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_insurances_id"), "insurances", ["id"], unique=False)
    op.create_index(op.f("ix_insurances_user_id"), "insurances", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_insurances_user_id"), table_name="insurances")
    op.drop_index(op.f("ix_insurances_id"), table_name="insurances")
    op.drop_table("insurances")
