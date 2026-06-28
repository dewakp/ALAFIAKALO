"""Add pre/post temperature (°C) to medication_dose_logs.

Lets the medication intake form capture temperature alongside BP/HR, stored
canonically in Celsius like every other temperature in the app.
"""

from alembic import op
import sqlalchemy as sa

revision = 'bb001_dose_log_temperature'
down_revision = 'aa001_dose_log_time_vitals'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('medication_dose_logs', sa.Column('pre_temperature_c', sa.Float(), nullable=True))
    op.add_column('medication_dose_logs', sa.Column('post_temperature_c', sa.Float(), nullable=True))


def downgrade():
    op.drop_column('medication_dose_logs', 'post_temperature_c')
    op.drop_column('medication_dose_logs', 'pre_temperature_c')
