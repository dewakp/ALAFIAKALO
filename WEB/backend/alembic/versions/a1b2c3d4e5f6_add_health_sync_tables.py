"""add health sync tables

Revision ID: a1b2c3d4e5f6
Revises: b4499a525cca
Create Date: 2026-02-15 12:00:00.000000

"""
from typing import Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'b4499a525cca'
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.create_table(
        'health_sync_connections',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False, index=True),
        sa.Column('platform', sa.String(50), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('enabled_data_types', sa.Text(), nullable=True),
        sa.Column('last_sync_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_sync_status', sa.String(20), nullable=True),
        sa.Column('last_sync_records', sa.Integer(), nullable=True),
        sa.Column('last_sync_duplicates', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('user_id', 'platform', name='uq_user_platform'),
    )

    op.create_table(
        'synced_records',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('platform', sa.String(50), nullable=False),
        sa.Column('data_type', sa.String(50), nullable=False),
        sa.Column('external_id', sa.String(255), nullable=False),
        sa.Column('target_table', sa.String(100), nullable=False),
        sa.Column('target_record_id', sa.Integer(), nullable=True),
        sa.Column('source_timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('synced_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('user_id', 'platform', 'data_type', 'external_id', name='uq_synced_record'),
    )
    op.create_index('ix_synced_lookup', 'synced_records', ['user_id', 'platform', 'data_type'])


def downgrade() -> None:
    op.drop_index('ix_synced_lookup', table_name='synced_records')
    op.drop_table('synced_records')
    op.drop_table('health_sync_connections')
