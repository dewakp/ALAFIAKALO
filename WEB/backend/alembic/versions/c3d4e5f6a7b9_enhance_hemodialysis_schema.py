"""enhance hemodialysis schema with flowsheet fields and intradialytic readings

Revision ID: c3d4e5f6a7b9
Revises: b2c3d4e5f6a8
Create Date: 2025-02-20 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b9'
down_revision: Union[str, None] = 'b2c3d4e5f6a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Enhanced Dialysis Fields on therapy_sessions ---
    op.add_column('therapy_sessions', sa.Column('dry_weight_kg', sa.Float(), nullable=True))
    op.add_column('therapy_sessions', sa.Column('previous_post_weight_kg', sa.Float(), nullable=True))
    op.add_column('therapy_sessions', sa.Column('fluid_to_remove_kg', sa.Float(), nullable=True))
    op.add_column('therapy_sessions', sa.Column('flow_fraction', sa.Float(), nullable=True))
    op.add_column('therapy_sessions', sa.Column('filtration_fraction', sa.String(50), nullable=True))
    op.add_column('therapy_sessions', sa.Column('day_of_week', sa.String(20), nullable=True))
    op.add_column('therapy_sessions', sa.Column('rn_reviewer', sa.String(200), nullable=True))

    # Dialysate Prescription
    op.add_column('therapy_sessions', sa.Column('dialysate_volume_liters', sa.Float(), nullable=True))
    op.add_column('therapy_sessions', sa.Column('dialysate_lactate_meq', sa.Float(), nullable=True))
    op.add_column('therapy_sessions', sa.Column('dialysate_potassium_meq', sa.Float(), nullable=True))
    op.add_column('therapy_sessions', sa.Column('sak_number', sa.Integer(), nullable=True))
    op.add_column('therapy_sessions', sa.Column('needle_gauge', sa.String(20), nullable=True))
    op.add_column('therapy_sessions', sa.Column('needle_length', sa.Float(), nullable=True))
    op.add_column('therapy_sessions', sa.Column('buttonhole_technique', sa.Boolean(), nullable=True))

    # Standing BP (Pre & Post)
    op.add_column('therapy_sessions', sa.Column('pre_standing_systolic_bp', sa.Integer(), nullable=True))
    op.add_column('therapy_sessions', sa.Column('pre_standing_diastolic_bp', sa.Integer(), nullable=True))
    op.add_column('therapy_sessions', sa.Column('pre_standing_heart_rate', sa.Integer(), nullable=True))
    op.add_column('therapy_sessions', sa.Column('post_standing_systolic_bp', sa.Integer(), nullable=True))
    op.add_column('therapy_sessions', sa.Column('post_standing_diastolic_bp', sa.Integer(), nullable=True))
    op.add_column('therapy_sessions', sa.Column('post_standing_heart_rate', sa.Integer(), nullable=True))

    # Equipment Tracking
    op.add_column('therapy_sessions', sa.Column('cartridge_lot', sa.String(50), nullable=True))
    op.add_column('therapy_sessions', sa.Column('sak_lot', sa.String(50), nullable=True))
    op.add_column('therapy_sessions', sa.Column('cycler_number', sa.String(50), nullable=True))
    op.add_column('therapy_sessions', sa.Column('warmer_serial', sa.String(50), nullable=True))
    op.add_column('therapy_sessions', sa.Column('control_panel_serial', sa.String(50), nullable=True))

    # Pre-Treatment Symptom Checklist
    op.add_column('therapy_sessions', sa.Column('pre_shortness_of_breath', sa.Boolean(), nullable=True))
    op.add_column('therapy_sessions', sa.Column('pre_swelling', sa.Boolean(), nullable=True))
    op.add_column('therapy_sessions', sa.Column('pre_change_in_mobility', sa.Boolean(), nullable=True))
    op.add_column('therapy_sessions', sa.Column('pre_digestion_problems', sa.Boolean(), nullable=True))
    op.add_column('therapy_sessions', sa.Column('pre_hosp_er_since_last', sa.Boolean(), nullable=True))

    # Access Assessment
    op.add_column('therapy_sessions', sa.Column('access_thrill_bruit', sa.Boolean(), nullable=True))
    op.add_column('therapy_sessions', sa.Column('access_redness_drainage', sa.Boolean(), nullable=True))

    # Post-Treatment Totals
    op.add_column('therapy_sessions', sa.Column('total_dialysate_liters', sa.Float(), nullable=True))
    op.add_column('therapy_sessions', sa.Column('total_uf_liters', sa.Float(), nullable=True))
    op.add_column('therapy_sessions', sa.Column('total_blood_volume_processed', sa.Float(), nullable=True))
    op.add_column('therapy_sessions', sa.Column('dialyzer_appearance', sa.String(100), nullable=True))
    op.add_column('therapy_sessions', sa.Column('post_bleeding_stop_time', sa.String(50), nullable=True))
    op.add_column('therapy_sessions', sa.Column('post_bruising', sa.Boolean(), nullable=True))
    op.add_column('therapy_sessions', sa.Column('post_infiltration', sa.Boolean(), nullable=True))
    op.add_column('therapy_sessions', sa.Column('post_shortness_of_breath', sa.Boolean(), nullable=True))
    op.add_column('therapy_sessions', sa.Column('post_swelling', sa.Boolean(), nullable=True))
    op.add_column('therapy_sessions', sa.Column('post_digestion_problems', sa.Boolean(), nullable=True))
    op.add_column('therapy_sessions', sa.Column('post_access_thrill_bruit', sa.Boolean(), nullable=True))

    # Machine Maintenance
    op.add_column('therapy_sessions', sa.Column('purification_pak_change', sa.Boolean(), nullable=True))
    op.add_column('therapy_sessions', sa.Column('air_filter_cleaned', sa.Boolean(), nullable=True))
    op.add_column('therapy_sessions', sa.Column('waste_line_bleach_disinfection', sa.Boolean(), nullable=True))
    op.add_column('therapy_sessions', sa.Column('sak_use_number', sa.Integer(), nullable=True))
    op.add_column('therapy_sessions', sa.Column('total_chloramine_level', sa.Float(), nullable=True))
    op.add_column('therapy_sessions', sa.Column('alarm_test_completed', sa.Boolean(), nullable=True))

    # Lab Tubes
    op.add_column('therapy_sessions', sa.Column('lab_tubes_drawn', sa.Text(), nullable=True))

    # --- Create intradialytic_readings table ---
    op.create_table(
        'intradialytic_readings',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('session_id', sa.Integer(), sa.ForeignKey('therapy_sessions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('reading_time', sa.Time(), nullable=False),
        sa.Column('reading_number', sa.Integer(), nullable=True),
        sa.Column('systolic_bp', sa.Integer(), nullable=True),
        sa.Column('diastolic_bp', sa.Integer(), nullable=True),
        sa.Column('pulse', sa.Integer(), nullable=True),
        sa.Column('mean_arterial_pressure', sa.Float(), nullable=True),
        sa.Column('dialysate_rate', sa.Float(), nullable=True),
        sa.Column('dialysate_volume_remaining', sa.Float(), nullable=True),
        sa.Column('uf_rate', sa.Float(), nullable=True),
        sa.Column('uf_volume_removed', sa.Float(), nullable=True),
        sa.Column('blood_flow_rate', sa.Float(), nullable=True),
        sa.Column('arterial_pressure', sa.Float(), nullable=True),
        sa.Column('venous_pressure', sa.Float(), nullable=True),
        sa.Column('effluent_pressure', sa.Float(), nullable=True),
        sa.Column('access_state', sa.String(50), nullable=True),
        sa.Column('saline_amount', sa.String(50), nullable=True),
        sa.Column('remarks', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_intradialytic_readings_session_id', 'intradialytic_readings', ['session_id'])
    op.create_index('ix_intradialytic_readings_user_id', 'intradialytic_readings', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_intradialytic_readings_user_id', table_name='intradialytic_readings')
    op.drop_index('ix_intradialytic_readings_session_id', table_name='intradialytic_readings')
    op.drop_table('intradialytic_readings')

    # Drop all added columns from therapy_sessions
    columns_to_drop = [
        'dry_weight_kg', 'previous_post_weight_kg', 'fluid_to_remove_kg',
        'flow_fraction', 'filtration_fraction', 'day_of_week', 'rn_reviewer',
        'dialysate_volume_liters', 'dialysate_lactate_meq', 'dialysate_potassium_meq',
        'sak_number', 'needle_gauge', 'needle_length', 'buttonhole_technique',
        'pre_standing_systolic_bp', 'pre_standing_diastolic_bp', 'pre_standing_heart_rate',
        'post_standing_systolic_bp', 'post_standing_diastolic_bp', 'post_standing_heart_rate',
        'cartridge_lot', 'sak_lot', 'cycler_number', 'warmer_serial', 'control_panel_serial',
        'pre_shortness_of_breath', 'pre_swelling', 'pre_change_in_mobility',
        'pre_digestion_problems', 'pre_hosp_er_since_last',
        'access_thrill_bruit', 'access_redness_drainage',
        'total_dialysate_liters', 'total_uf_liters', 'total_blood_volume_processed',
        'dialyzer_appearance', 'post_bleeding_stop_time', 'post_bruising',
        'post_infiltration', 'post_shortness_of_breath', 'post_swelling',
        'post_digestion_problems', 'post_access_thrill_bruit',
        'purification_pak_change', 'air_filter_cleaned', 'waste_line_bleach_disinfection',
        'sak_use_number', 'total_chloramine_level', 'alarm_test_completed',
        'lab_tubes_drawn',
    ]
    for col in columns_to_drop:
        op.drop_column('therapy_sessions', col)
