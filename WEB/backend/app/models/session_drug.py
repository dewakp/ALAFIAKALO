"""One drug given during one dialysis session — as the flowsheet recorded it.

`therapy_sessions.drugs_administered` is a single text column holding
`"Sodium Citrate (2.5 ml x 2); Epogene (3,000 SQ); Venofer (100 mg)"`. The
source sheet is not shaped like that. It is a TABLE:

    H23='Drugs Administered' | K23='Dose' | M23='Route' | O23='Time' | Q23='Initial'
    H25='Epogene'            | K25='3,000 SQ' | M25='Access' | O25=23:47 | Q25='WA'

The importer read only H and K, so route and time were dropped on every import
— and inspecting the flattened result then made it look as though the source
had never carried them.

MEASURED across the 694 session sheets in the four workbooks that are present
(FlowsheetGermantown.xlsx is not synced): 1,769 drug rows, route on 1,763
(99.7%), a time on 268 (15.1%).

An earlier figure of "a time on 408" was WRONG, and wrong in a way worth
recording: it counted NON-EMPTY Time cells. 140 of those hold the text "NONE",
spelled seven different ways (NONE, NoNE, NonE, NONe, None, NOONE, N"ONE) — an
explicit "not recorded", not a time. One further cell holds '1;47', a semicolon
struck instead of a colon: a real administration time, which the importer
REPORTS rather than repairs, because rewriting a clinical timestamp from a typo
invents a fact (§0).

Timing is not cosmetic. An IV iron runs over a period, so "when" and "for how
long" change what the dose did; and a drug given at 23:47 on a session starting
23:49 belongs to a different calendar day than the sheet's date.

**Both a time and a timestamp are stored, deliberately.** `administered_time`
is exactly what the sheet said, kept so a row can always be checked against the
paper. `administered_at` resolves it against the session, applying the same
midnight rollover the importer already uses for session start/stop (a session
running 23:49 → 03:40 ends on the following day). Where the sheet gave no time,
`administered_at` is NULL rather than guessed at.
"""

from datetime import datetime, time, timezone

from sqlalchemy import (
    DateTime, ForeignKey, Index, Integer, String, Time,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SessionDrug(Base):
    """A single row of the flowsheet's Drugs Administered table."""

    __tablename__ = "session_drugs"
    __table_args__ = (
        # The sheet has five drug rows (24-28); this keeps a re-import
        # converging on the same row instead of inserting beside it (§3ab).
        Index("ix_session_drugs_session_row", "session_id", "row_index", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    session_id: Mapped[int] = mapped_column(
        ForeignKey("therapy_sessions.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    #: Carried alongside the FK exactly as `intradialytic_readings` does, so a
    #: per-patient query needs no join.
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True,
    )

    #: Which of the sheet's drug rows this was (24-28 -> 0-4). The dedupe key.
    row_index: Mapped[int] = mapped_column(Integer, nullable=False)

    #: Verbatim, as written on the sheet: "Epogene", "Doxercalcif". Canonical
    #: resolution belongs to flowsheet_drugs.canonical_drug_name, never here —
    #: the stored name is how the row is found on the paper again (§3ax).
    name: Mapped[str] = mapped_column(String(120), nullable=False)

    #: Verbatim too: "3,000 SQ", "2.5 ml x 2", "100 mg", "2 mcg". Never parsed
    #: into a number here — "3,000 SQ" is a dose AND a route hint, and
    #: parse_dose_text already refuses what it cannot read rather than invent.
    dose_text: Mapped[str | None] = mapped_column(String(120))

    #: FOUR routes, not one: Access 1,451 · SC 309 · IV 2 · SCT 1 · absent 6.
    #: An earlier note here claimed "Access on every row", which would have told
    #: the next reader that route carries no information. It does: SC is
    #: subcutaneous, and whether an ESA went subcutaneously or into the circuit
    #: changes how it was absorbed.
    route: Mapped[str | None] = mapped_column(String(60))

    #: Exactly what the sheet said, or NULL. Present on 268 of 1,769 (15.1%).
    administered_time: Mapped[time | None] = mapped_column(Time)

    #: The same instant resolved against the session date, with the midnight
    #: rollover applied. NULL whenever `administered_time` is NULL — an absent
    #: time is absent, not the session start.
    #:
    #: NAIVE, deliberately, because it is derived from
    #: `therapy_sessions.actual_start_time`, which is `Column(DateTime)` with no
    #: timezone. Declaring this one aware would put a tz-aware value beside a
    #: naive one on the same session: comparing them makes asyncpg raise
    #: DataError, the endpoint 500s, and the page renders it as "no sessions
    #: found" on a patient who has hundreds (§3aa).
    administered_at: Mapped[datetime | None] = mapped_column(DateTime)

    #: Who signed for it ("WA"). Kept because it is part of the record.
    initials: Mapped[str | None] = mapped_column(String(20))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
