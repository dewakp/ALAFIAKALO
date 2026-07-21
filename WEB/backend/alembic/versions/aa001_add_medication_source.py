"""Add `source` to medications: distinguish user-entered from portal-imported.

FHIR/portal-synced medications (see ehr.py) were written unlabeled, so imported
sandbox test data looked like the patient's own prescriptions. `source` holds the
importing portal/org name; NULL means the patient entered it manually.
"""

from alembic import op
import sqlalchemy as sa

revision = 'aa001_add_medication_source'
# Was branched off z001 (a stale head) in commit 05fd81c, creating a second head.
# Re-parented onto the mainline tip (ll001) to linearize the migration graph.
down_revision = 'll001_labeled_food_images'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('medications', sa.Column('source', sa.String(length=100), nullable=True))
    # Backfill: existing FHIR-imported rows are tagged by notes = "FHIR:<id>".
    op.execute("UPDATE medications SET source = 'Imported (portal)' "
               "WHERE notes LIKE 'FHIR:%' AND source IS NULL")


def downgrade():
    op.drop_column('medications', 'source')
