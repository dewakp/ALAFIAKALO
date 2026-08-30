"""A wellness score with nothing to measure must be storable as NULL.

`overall_score` was NOT NULL, which was consistent while the score always
produced a number — it defaulted absent domains to 50, so an account with no
data still got 50. That default was the bug (a score for a patient we know
nothing about), and removing it made `overall_score` legitimately None.

The column did not follow, so `GET /wellness/score` **500s for any user with no
data — including every newly registered one**. Found by calling the deployed
endpoint as a real account, not by a unit test: nothing exercised a zero-data
user through the path that persists.

NULL here means "not scoreable on this date", which is a fact worth keeping in
the history series rather than a number worth inventing.

Revision ID: uu001_wellness_nullable
Revises: tt001_clinical_thresholds
"""

import sqlalchemy as sa
from alembic import op

revision = "uu001_wellness_nullable"
down_revision = "tt001_clinical_thresholds"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("wellness_scores", "overall_score",
                    existing_type=sa.Float(), nullable=True)


def downgrade() -> None:
    # Rows written while nothing could be measured have no number to restore,
    # so they are removed rather than back-filled with a fabricated one.
    op.execute("DELETE FROM wellness_scores WHERE overall_score IS NULL")
    op.alter_column("wellness_scores", "overall_score",
                    existing_type=sa.Float(), nullable=False)
