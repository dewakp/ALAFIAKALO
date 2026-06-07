"""add diagnostics engine tables

Revision ID: d4e5f6a7b8c0
Revises: c3d4e5f6a7b9
Create Date: 2025-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c0'
down_revision: Union[str, None] = 'c3d4e5f6a7b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -- Diagnostic Assessments --
    op.create_table(
        'diagnostic_assessments',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False, index=True),
        sa.Column('assessment_code', sa.String(50), unique=True, nullable=False, index=True),
        sa.Column('status', sa.Enum('pending', 'completed', 'reviewed', 'superseded', name='assessmentstatus', create_type=True), nullable=False, server_default='completed'),
        sa.Column('urgency_level', sa.Enum('emergency', 'urgent', 'soon', 'routine', 'monitoring', name='urgencylevel', create_type=True), nullable=False, server_default='routine'),
        sa.Column('urgency_trigger', sa.String(255), nullable=True),
        sa.Column('reported_symptoms', postgresql.JSON(), nullable=True),
        sa.Column('additional_context', sa.Text(), nullable=True),
        sa.Column('primary_impression', sa.Text(), nullable=True),
        sa.Column('supporting_evidence', postgresql.JSON(), nullable=True),
        sa.Column('contradicting_factors', postgresql.JSON(), nullable=True),
        sa.Column('recommended_actions', postgresql.JSON(), nullable=True),
        sa.Column('recommended_tests', postgresql.JSON(), nullable=True),
        sa.Column('red_flags', postgresql.JSON(), nullable=True),
        sa.Column('risk_factors_identified', postgresql.JSON(), nullable=True),
        sa.Column('follow_up_timeline', sa.String(255), nullable=True),
        sa.Column('patient_education', postgresql.JSON(), nullable=True),
        sa.Column('reviewed_by_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('reviewer_notes', sa.Text(), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )

    # -- Differential Diagnoses --
    op.create_table(
        'differential_diagnoses',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('assessment_id', sa.Integer(), sa.ForeignKey('diagnostic_assessments.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('icd10_code', sa.String(20), nullable=False, index=True),
        sa.Column('condition_name', sa.String(500), nullable=False),
        sa.Column('body_system', sa.String(100), nullable=True),
        sa.Column('confidence', sa.Float(), server_default='0.0'),
        sa.Column('rank', sa.Integer(), server_default='0'),
        sa.Column('matched_symptoms', postgresql.JSON(), nullable=True),
        sa.Column('risk_factor_match', postgresql.JSON(), nullable=True),
        sa.Column('reasoning', sa.Text(), nullable=True),
        sa.Column('source', sa.Enum('rule_based', 'ai_enhanced', 'provider_confirmed', name='diagnosticsource', create_type=True), nullable=False, server_default='ai_enhanced'),
        sa.Column('provider_confirmed', sa.Boolean(), nullable=True),
        sa.Column('provider_notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )

    # -- Screening Recommendations --
    op.create_table(
        'screening_recommendations',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False, index=True),
        sa.Column('screening_name', sa.String(500), nullable=False),
        sa.Column('icd10_code', sa.String(20), nullable=True),
        sa.Column('rationale', sa.Text(), nullable=True),
        sa.Column('frequency', sa.String(255), nullable=True),
        sa.Column('priority', sa.String(50), nullable=True),
        sa.Column('status', sa.Enum('recommended', 'scheduled', 'completed', 'declined', 'overdue', name='screeningstatus', create_type=True), nullable=False, server_default='recommended'),
        sa.Column('risk_level', sa.String(50), nullable=True),
        sa.Column('risk_rationale', sa.Text(), nullable=True),
        sa.Column('associated_risks', postgresql.JSON(), nullable=True),
        sa.Column('recommended_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )

    # -- Lab Correlation Reports --
    op.create_table(
        'lab_correlation_reports',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False, index=True),
        sa.Column('correlation_code', sa.String(50), unique=True, nullable=False, index=True),
        sa.Column('labs_analyzed', sa.Integer(), server_default='0'),
        sa.Column('abnormal_count', sa.Integer(), server_default='0'),
        sa.Column('abnormal_labs', postgresql.JSON(), nullable=True),
        sa.Column('diagnostic_correlations', postgresql.JSON(), nullable=True),
        sa.Column('possible_conditions', postgresql.JSON(), nullable=True),
        sa.Column('recommended_follow_up_tests', postgresql.JSON(), nullable=True),
        sa.Column('clinical_significance', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )


def downgrade() -> None:
    op.drop_table('lab_correlation_reports')
    op.drop_table('screening_recommendations')
    op.drop_table('differential_diagnoses')
    op.drop_table('diagnostic_assessments')

    # Drop enum types
    sa.Enum(name='assessmentstatus').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='urgencylevel').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='screeningstatus').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='diagnosticsource').drop(op.get_bind(), checkfirst=True)
