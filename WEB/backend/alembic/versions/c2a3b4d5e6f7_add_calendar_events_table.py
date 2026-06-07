"""add calendar events table

Revision ID: c2a3b4d5e6f7
Revises: a1b2c3d4e5f6
Create Date: 2026-02-15 18:00:00.000000

"""
from typing import Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c2a3b4d5e6f7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, tuple[str, ...], None] = None
depends_on: Union[str, tuple[str, ...], None] = None


def upgrade() -> None:
    op.create_table(
        'calendar_events',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False, index=True),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('category', sa.String(50), nullable=False, index=True),
        sa.Column('event_date', sa.Date(), nullable=False, index=True),
        sa.Column('start_time', sa.Time(), nullable=True),
        sa.Column('end_time', sa.Time(), nullable=True),
        sa.Column('all_day', sa.Boolean(), server_default='false'),
        sa.Column('recurrence', sa.String(20), nullable=True),
        sa.Column('recurrence_end_date', sa.Date(), nullable=True),
        sa.Column('recurrence_days', sa.String(100), nullable=True),
        sa.Column('status', sa.String(20), server_default='scheduled'),
        sa.Column('location', sa.String(500), nullable=True),
        sa.Column('reminder_minutes', sa.Integer(), nullable=True),
        sa.Column('metadata_json', sa.Text(), nullable=True),
        sa.Column('linked_medication_id', sa.Integer(), nullable=True),
        sa.Column('linked_condition_id', sa.Integer(), nullable=True),
        sa.Column('linked_fitness_id', sa.Integer(), nullable=True),
        sa.Column('color', sa.String(20), nullable=True),
        sa.Column('priority', sa.String(10), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('calendar_events')
