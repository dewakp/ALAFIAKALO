"""nutrition_logs.nutrient_status — background nutrient enrichment

Nutrient lookup costs seconds (USDA per item, branded, LLM fallback). It used to
run inside the save, so the user waited for all of it and a 10-item meal exceeded
the web client's 30s timeout — and because the request never committed, the meal
they had typed was lost.

The log is now saved and returned immediately and enrichment runs afterwards.
This column is how the client knows whether values are still coming.

  pending | done | failed | skipped

Existing rows default to 'skipped': they were written under the old inline path,
so whatever nutrients they have are already final.

Revision ID: dd004_nutrient_status
Revises: dd003_pending_registrations
"""

from alembic import op
import sqlalchemy as sa

revision = "dd004_nutrient_status"
down_revision = "dd003_pending_registrations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "nutrition_logs",
        sa.Column("nutrient_status", sa.String(16), nullable=False, server_default="skipped"),
    )
    # "which meals are still waiting / failed" is the query the client and any
    # retry sweep run; without this it is a full scan of every meal ever logged.
    op.create_index("ix_nutrition_logs_nutrient_status", "nutrition_logs", ["nutrient_status"])


def downgrade() -> None:
    op.drop_index("ix_nutrition_logs_nutrient_status", table_name="nutrition_logs")
    op.drop_column("nutrition_logs", "nutrient_status")
