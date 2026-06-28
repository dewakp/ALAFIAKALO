"""Add log_time + pre/post vitals to medication_dose_logs.

Matches the "Log New Medication Intake" form (time + pre/post-medication BP & HR)
and lets the UI show clean structured data instead of packing it into notes.
"""

from alembic import op
import sqlalchemy as sa

revision = 'aa001_dose_log_time_vitals'
down_revision = 'z001_elimination_weights_image'
branch_labels = None
depends_on = None

_COLS = [
    ('log_time', sa.Time()),
    ('pre_systolic_bp', sa.Integer()),
    ('pre_diastolic_bp', sa.Integer()),
    ('pre_heart_rate', sa.Integer()),
    ('post_systolic_bp', sa.Integer()),
    ('post_diastolic_bp', sa.Integer()),
    ('post_heart_rate', sa.Integer()),
]


def upgrade():
    for name, col_type in _COLS:
        op.add_column('medication_dose_logs', sa.Column(name, col_type, nullable=True))


def downgrade():
    for name, _ in reversed(_COLS):
        op.drop_column('medication_dose_logs', name)
