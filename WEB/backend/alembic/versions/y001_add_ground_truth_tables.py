"""Add ground-truth tables: genetic_markers + env_social_logs (Basis req #3)."""

from alembic import op
import sqlalchemy as sa

revision = 'y001_add_ground_truth_tables'
down_revision = 'x001_add_device_tokens'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'genetic_markers',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('gene', sa.String(100), nullable=False),
        sa.Column('variant', sa.String(100), nullable=True),
        sa.Column('genotype', sa.String(50), nullable=True),
        sa.Column('risk_allele', sa.String(50), nullable=True),
        sa.Column('associated_condition', sa.String(255), nullable=True),
        sa.Column('risk_level', sa.String(50), nullable=True),
        sa.Column('source', sa.String(100), nullable=True),
        sa.Column('interpretation', sa.Text(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_genetic_markers_id', 'genetic_markers', ['id'])
    op.create_index('ix_genetic_markers_user_id', 'genetic_markers', ['user_id'])

    op.create_table(
        'env_social_logs',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('log_date', sa.Date(), nullable=False),
        sa.Column('location', sa.String(255), nullable=True),
        sa.Column('air_quality_index', sa.Integer(), nullable=True),
        sa.Column('ambient_temp_c', sa.Float(), nullable=True),
        sa.Column('humidity_pct', sa.Float(), nullable=True),
        sa.Column('noise_level', sa.String(50), nullable=True),
        sa.Column('pollen_level', sa.String(50), nullable=True),
        sa.Column('household_size', sa.Integer(), nullable=True),
        sa.Column('occupation', sa.String(255), nullable=True),
        sa.Column('work_stress_level', sa.Integer(), nullable=True),
        sa.Column('financial_stress_level', sa.Integer(), nullable=True),
        sa.Column('social_support_level', sa.Integer(), nullable=True),
        sa.Column('major_life_event', sa.Text(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_env_social_logs_id', 'env_social_logs', ['id'])
    op.create_index('ix_env_social_logs_user_id', 'env_social_logs', ['user_id'])


def downgrade():
    op.drop_table('env_social_logs')
    op.drop_table('genetic_markers')
