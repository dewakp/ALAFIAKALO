"""Record that a dose was overridden, and why.

`acknowledge_unusual` was a request flag only — nothing persisted. A clinician
reading the chart could not tell a force-logged dose from a routine one, on
exactly the rows where that distinction matters most: the guard fires only on
provable contradictions (a unit the drug is not measured in, a dose above the
largest marketed strength RxNorm lists, a name RxNorm does not recognise).

The findings are stored verbatim rather than recomputed later. RxNorm's answer
changes over time; what belongs in the record is what the patient was shown at
the moment they pressed "log it anyway".

Revision ID: qq001_dose_override
Revises: pp001_record_access
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "qq001_dose_override"
down_revision: Union[str, None] = "pp001_record_access"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # server_default so the NOT NULL applies to the rows already there. Existing
    # doses were not overridden — none of them could have been, the flag did not
    # persist — so false is the truthful backfill, not merely a convenient one.
    op.add_column(
        "medication_dose_logs",
        sa.Column("override_acknowledged", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
    )
    op.add_column(
        "medication_dose_logs",
        sa.Column("override_reason", sa.Text(), nullable=True),
    )
    # Partial index: overridden doses are the rare ones, and they are what a
    # clinician reviewing a record actually searches for.
    op.create_index(
        "ix_dose_logs_overridden",
        "medication_dose_logs",
        ["user_id", "log_date"],
        postgresql_where=sa.text("override_acknowledged"),
    )


def downgrade() -> None:
    op.drop_index("ix_dose_logs_overridden", table_name="medication_dose_logs")
    op.drop_column("medication_dose_logs", "override_reason")
    op.drop_column("medication_dose_logs", "override_acknowledged")
