"""Add device_tokens table for APNs / FCM push registration."""

from alembic import op
import sqlalchemy as sa

revision = 'x001_add_device_tokens'
down_revision = 'w001_add_med_nutrient_tables'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'device_tokens',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            'user_id', sa.Integer(),
            sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False,
        ),
        sa.Column('token', sa.String(512), nullable=False),
        sa.Column('platform', sa.String(20), nullable=False, server_default='ios'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_seen', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_device_tokens_id', 'device_tokens', ['id'])
    op.create_index('ix_device_tokens_user_id', 'device_tokens', ['user_id'])
    op.create_index('ix_device_tokens_token', 'device_tokens', ['token'], unique=True)


def downgrade():
    op.drop_table('device_tokens')
