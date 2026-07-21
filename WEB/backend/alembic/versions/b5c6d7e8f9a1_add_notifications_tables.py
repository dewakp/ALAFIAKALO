"""add notifications tables

Revision ID: b5c6d7e8f9a1
Revises: 2940057c9079
Create Date: 2026-02-16 14:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "b5c6d7e8f9a1"
down_revision: Union[str, None] = "2940057c9079"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Enum values matching the Python enums
CATEGORY_VALUES = (
    "therapy_session", "calendar", "lab_anomaly",
    "treatment_anomaly", "medication_conflict", "nutrition_alert", "system",
)
PRIORITY_VALUES = ("low", "medium", "high", "urgent")
CHANNEL_VALUES = ("in_app", "push", "email", "sms")


def upgrade() -> None:
    # Create enum types using raw SQL with DO block to handle IF NOT EXISTS
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE notificationcategory AS ENUM ('therapy_session', 'calendar', 'lab_anomaly', 'treatment_anomaly', 'medication_conflict', 'nutrition_alert', 'system');
        EXCEPTION WHEN duplicate_object THEN null;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE notificationpriority AS ENUM ('low', 'medium', 'high', 'urgent');
        EXCEPTION WHEN duplicate_object THEN null;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE notificationchannel AS ENUM ('in_app', 'push', 'email', 'sms');
        EXCEPTION WHEN duplicate_object THEN null;
        END $$;
    """)

    # Reference the existing PG enums without re-creating them. postgresql.ENUM
    # with create_type=False reliably suppresses the CREATE TYPE that create_table's
    # before_create hook would otherwise emit (generic sa.Enum still emitted it here,
    # colliding with the DO-block types above → "type already exists" on a fresh DB).
    cat_col = postgresql.ENUM(*CATEGORY_VALUES, name="notificationcategory", create_type=False)
    pri_col = postgresql.ENUM(*PRIORITY_VALUES, name="notificationpriority", create_type=False)

    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("category", cat_col, nullable=False, index=True),
        sa.Column("priority", pri_col, nullable=False, server_default="medium"),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("action_url", sa.String(512), nullable=True),
        sa.Column("metadata", sa.Text(), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.text("false"), index=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "notification_preferences",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("category", cat_col, nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("in_app", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("push", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("email", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("sms", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )

    op.create_index(
        "ix_notification_preferences_user_category",
        "notification_preferences",
        ["user_id", "category"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_notification_preferences_user_category", table_name="notification_preferences")
    op.drop_table("notification_preferences")
    op.drop_table("notifications")
    sa.Enum(name="notificationcategory").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="notificationpriority").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="notificationchannel").drop(op.get_bind(), checkfirst=True)
