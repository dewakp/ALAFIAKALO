"""Add med_nutrient_profiles and medication_dose_logs tables."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'w001_add_med_nutrient_tables'
down_revision = 'v001_add_firebase_field_columns'
branch_labels = None
depends_on = None


def upgrade():
    # ── med_nutrient_profiles (global reference table) ──
    op.create_table(
        'med_nutrient_profiles',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('med_name_normalized', sa.String(255), nullable=False),
        sa.Column('med_name_original', sa.String(255), nullable=False),
        sa.Column('brand_names', sa.Text(), nullable=True),
        sa.Column('rxnorm_code', sa.String(30), nullable=True),
        sa.Column('active_ingredient', sa.String(255), nullable=True),
        sa.Column('dose_unit_canonical', sa.String(50), nullable=False),
        sa.Column('nutrients_per_dose_unit', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('source', sa.String(50), nullable=True, server_default='seeded'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_med_nutrient_profiles_id', 'med_nutrient_profiles', ['id'])
    op.create_index(
        'ix_med_nutrient_profiles_med_name_normalized',
        'med_nutrient_profiles', ['med_name_normalized'], unique=True
    )

    # ── medication_dose_logs (per-user dose events) ──
    op.create_table(
        'medication_dose_logs',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('medication_id', sa.Integer(), sa.ForeignKey('medications.id'), nullable=True),
        sa.Column('med_profile_id', sa.Integer(), sa.ForeignKey('med_nutrient_profiles.id'), nullable=True),
        sa.Column('medication_name', sa.String(255), nullable=False),
        sa.Column('log_date', sa.Date(), nullable=False),
        sa.Column('dose_amount', sa.Float(), nullable=False),
        sa.Column('dose_unit', sa.String(50), nullable=False),
        sa.Column('nutrients_contributed', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('nutrients_resolved', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            'user_id', 'log_date', 'medication_name', 'dose_amount', 'dose_unit',
            name='uq_dose_log_per_user_date_med_dose',
        ),
    )
    op.create_index('ix_medication_dose_logs_id', 'medication_dose_logs', ['id'])
    op.create_index('ix_medication_dose_logs_user_id', 'medication_dose_logs', ['user_id'])
    op.create_index('ix_medication_dose_logs_log_date', 'medication_dose_logs', ['log_date'])
    op.create_index('ix_medication_dose_logs_medication_name', 'medication_dose_logs', ['medication_name'])


def downgrade():
    op.drop_table('medication_dose_logs')
    op.drop_table('med_nutrient_profiles')
