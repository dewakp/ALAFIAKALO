"""add mental health tables

Revision ID: b7d4e2f1a9c3
Revises: 9c5e7b8c3d2a
Create Date: 2026-02-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b7d4e2f1a9c3"
down_revision: Union[str, None] = "9c5e7b8c3d2a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "mental_health_assessments",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("assessment_date", sa.Date(), nullable=False),
        sa.Column("assessment_type", sa.String(50), nullable=False, index=True),
        sa.Column("phq_interest", sa.Integer(), nullable=True),
        sa.Column("phq_feeling_down", sa.Integer(), nullable=True),
        sa.Column("phq_sleep", sa.Integer(), nullable=True),
        sa.Column("phq_energy", sa.Integer(), nullable=True),
        sa.Column("phq_appetite", sa.Integer(), nullable=True),
        sa.Column("phq_self_esteem", sa.Integer(), nullable=True),
        sa.Column("phq_concentration", sa.Integer(), nullable=True),
        sa.Column("phq_psychomotor", sa.Integer(), nullable=True),
        sa.Column("phq_suicidal_ideation", sa.Integer(), nullable=True),
        sa.Column("gad_nervous", sa.Integer(), nullable=True),
        sa.Column("gad_uncontrollable_worry", sa.Integer(), nullable=True),
        sa.Column("gad_excessive_worry", sa.Integer(), nullable=True),
        sa.Column("gad_trouble_relaxing", sa.Integer(), nullable=True),
        sa.Column("gad_restless", sa.Integer(), nullable=True),
        sa.Column("gad_irritable", sa.Integer(), nullable=True),
        sa.Column("gad_afraid", sa.Integer(), nullable=True),
        sa.Column("who5_cheerful", sa.Integer(), nullable=True),
        sa.Column("who5_calm", sa.Integer(), nullable=True),
        sa.Column("who5_active", sa.Integer(), nullable=True),
        sa.Column("who5_rested", sa.Integer(), nullable=True),
        sa.Column("who5_interesting", sa.Integer(), nullable=True),
        sa.Column("total_score", sa.Integer(), nullable=True),
        sa.Column("severity", sa.String(50), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "breathing_sessions",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("session_date", sa.Date(), nullable=False),
        sa.Column("exercise_type", sa.String(50), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=False),
        sa.Column("mood_before", sa.Integer(), nullable=True),
        sa.Column("mood_after", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "gratitude_entries",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("item_1", sa.Text(), nullable=False),
        sa.Column("item_2", sa.Text(), nullable=True),
        sa.Column("item_3", sa.Text(), nullable=True),
        sa.Column("reflection", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("gratitude_entries")
    op.drop_table("breathing_sessions")
    op.drop_table("mental_health_assessments")
