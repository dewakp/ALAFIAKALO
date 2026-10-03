# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""session_drugs — the flowsheet's drug table, with the route and time it recorded

`therapy_sessions.drugs_administered` flattens four drugs into one string, so
route and time had nowhere to go. The source sheet is a table — drug, dose,
route, time, initials — and the importer read only the first two columns.

MEASURED across the 694 session sheets in the four workbooks that are present
(FlowsheetGermantown.xlsx is not synced):

    1,769 drug rows · route on 1,763 (99.7%) · a time on 268 (15.1%)

    Epogene         673 rows, 218 timed   Access 363 · SC 309 · SCT 1
    Venofer         364 rows,  19 timed   Access 362 · IV 1
    Sodium Citrate  363 rows,   0 timed   Access 363
    Doxercalcif     363 rows,  30 timed   Access 363
    Flucel Vax        1 row,    1 timed   IV 1

An earlier set of figures here — 520 tabs, 1,148 rows, 363 timed, "Sodium
Citrate 209 (137 timed)" — was WRONG, and wrong in one specific way: it counted
NON-EMPTY Time cells rather than times. 140 of those cells hold the text "NONE"
(spelled seven ways). Sodium Citrate turns out never to be timed on any sheet;
all 137 of its supposed times were that text.

`drugs_administered` is deliberately LEFT IN PLACE. It is what every current
reader uses — `clinical_sources.medications_administered`, the clinician board,
the parser in `flowsheet_drugs` — and dropping a populated column to tidy up is
how history is lost (§3ao). These rows are additive; readers move over when
they are ready.

The unique index on (session_id, row_index) makes a re-import CONVERGE rather
than duplicate: §3ab records that a parser fix does not repair what it already
imported, and that re-importing without a dedupe key lands corrected rows
BESIDE the wrong ones.

Hand-written and additive. `--autogenerate` on this schema emits ~200 lines
that drop five live tables and a `users` column.

Revision ID: ak001_session_drugs
Revises: aj001_user_identities
Create Date: 2026-09-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "ak001_session_drugs"
down_revision: Union[str, None] = "aj001_user_identities"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "session_drugs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        # Which of the sheet's five drug rows (24-28 -> 0-4).
        sa.Column("row_index", sa.Integer(), nullable=False),
        # Verbatim as written; canonicalisation stays in flowsheet_drugs (§3ax).
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("dose_text", sa.String(length=120), nullable=True),
        sa.Column("route", sa.String(length=60), nullable=True),
        # What the sheet said…
        sa.Column("administered_time", sa.Time(), nullable=True),
        # …and the same instant against the session date, midnight rollover
        # applied. NULL when the sheet gave no time — never the session start.
        #
        # `timestamp WITHOUT time zone`, matching therapy_sessions.actual_start_time
        # which it is derived from. An aware column beside a naive one is the
        # §3aa bug: the comparison raises asyncpg DataError and the screen shows
        # "no sessions found" for a patient who has hundreds.
        sa.Column("administered_at", sa.DateTime(), nullable=True),
        sa.Column("initials", sa.String(length=20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["session_id"], ["therapy_sessions.id"],
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_session_drugs_id"), "session_drugs", ["id"], unique=False)
    op.create_index(op.f("ix_session_drugs_session_id"), "session_drugs",
                    ["session_id"], unique=False)
    op.create_index(op.f("ix_session_drugs_user_id"), "session_drugs",
                    ["user_id"], unique=False)
    # The dedupe key: a re-import converges on the row it already wrote.
    op.create_index("ix_session_drugs_session_row", "session_drugs",
                    ["session_id", "row_index"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_session_drugs_session_row", table_name="session_drugs")
    op.drop_index(op.f("ix_session_drugs_user_id"), table_name="session_drugs")
    op.drop_index(op.f("ix_session_drugs_session_id"), table_name="session_drugs")
    op.drop_index(op.f("ix_session_drugs_id"), table_name="session_drugs")
    op.drop_table("session_drugs")
