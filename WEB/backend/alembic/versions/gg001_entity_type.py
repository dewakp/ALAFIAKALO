"""directory — entity_type (clinician vs facility); facilities are not clinicians

Revision ID: gg001_entity_type
Revises: ff001_loc_precision
Create Date: 2026-06-29
"""
import sqlalchemy as sa
from alembic import op

revision = "gg001_entity_type"
down_revision = "ff001_loc_precision"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("physicians", sa.Column(
        "entity_type", sa.String(20), nullable=False, server_default="clinician"))
    op.create_index("ix_physicians_entity_type", "physicians", ["entity_type"])
    # Existing rows are all individual clinicians (CMS NPI-1).
    op.execute("UPDATE physicians SET entity_type = 'clinician'")
    # OSM-sourced records that slipped in as 'facilities' are places, not clinicians.
    op.execute("UPDATE physicians SET entity_type = 'facility', clinician_role = NULL, "
               "credential_verified = FALSE WHERE primary_source = 'osm'")


def downgrade():
    op.drop_index("ix_physicians_entity_type", table_name="physicians")
    op.drop_column("physicians", "entity_type")
