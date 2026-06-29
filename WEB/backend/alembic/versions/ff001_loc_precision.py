"""clinician directory — location_precision (exact vs approximate map coords)

Revision ID: ff001_loc_precision
Revises: ee001_clinician_directory
Create Date: 2026-06-29
"""
import sqlalchemy as sa
from alembic import op

revision = "ff001_loc_precision"
down_revision = "ee001_clinician_directory"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("physicians", sa.Column("location_precision", sa.String(20), nullable=True))


def downgrade():
    op.drop_column("physicians", "location_precision")
