"""Add pre/post weight + image columns to urination_logs and vomiting_logs.

Brings urine/vomit events to parity with bowel_movements so the unified
Elimination Log (poop/urine/vomit, with weights + image) works for all types.
"""

from alembic import op
import sqlalchemy as sa

revision = 'z001_elimination_weights_image'
down_revision = 'y001_add_ground_truth_tables'
branch_labels = None
depends_on = None


def upgrade():
    for table in ('urination_logs', 'vomiting_logs'):
        op.add_column(table, sa.Column('pre_event_weight_kg', sa.Float(), nullable=True))
        op.add_column(table, sa.Column('post_event_weight_kg', sa.Float(), nullable=True))
        op.add_column(table, sa.Column('image_uri', sa.Text(), nullable=True))


def downgrade():
    for table in ('urination_logs', 'vomiting_logs'):
        op.drop_column(table, 'image_uri')
        op.drop_column(table, 'post_event_weight_kg')
        op.drop_column(table, 'pre_event_weight_kg')
