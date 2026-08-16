"""Let an intradialytic reading have no recorded time.

`reading_time` was NOT NULL, so a blank cell in a source flowsheet had to be
filled with something. The importer filled it with `start_time + N hours`, and
because the start time was itself being read off the label row it was always
None — so the fallback collapsed to `time(0, 0)`. 3664 readings, 22.6% of the
table, carry 00:00:00, and 1263 groups of readings collide on that value.

That is worse than a gap. A reading stamped 00:00 looks measured: it plots on
the intradialytic curve at midnight, it sorts to the front of the flowsheet, and
it makes two distinct observations look like one row saved twice — which is
very nearly how 1816 rows across 1267 sessions got deduplicated away.

Making the column nullable lets the importer record "not stated" as not stated.
Existing 00:00:00 rows are NOT touched here: some of them are real midnight
readings on a patient who dialyses overnight, and this migration cannot tell
which. Separating them needs the source workbooks, not a guess in a migration.

Revision ID: kk001_reading_time_nullable
Revises: ee001_pending_signup_age
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "kk001_reading_time_nullable"
down_revision: Union[str, None] = "ee001_pending_signup_age"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "intradialytic_readings",
        "reading_time",
        existing_type=sa.Time(),
        nullable=True,
    )


def downgrade() -> None:
    # Reversing this needs a value for every NULL, and there is none to give:
    # midnight is exactly the fabrication the column was made nullable to stop.
    # Rows added after the upgrade would have to be filled in by hand first.
    op.alter_column(
        "intradialytic_readings",
        "reading_time",
        existing_type=sa.Time(),
        nullable=False,
    )
