"""The flowsheet records WHEN a drug was given — without doubling what it already holds.

`session_drugs` carries one row per flowsheet drug line, with the route and the
time the sheet recorded. `therapy_sessions.drugs_administered` carries the SAME
administrations flattened into text, with no time. Both readers in
`clinical_sources` therefore PREFER the structured rows and parse the text only
for a session that has none.

Measured on the dev copy of production when this landed: 670 sessions carry
structured rows, all 670 also carry the text, and the two agree row for row —
306 sessions with 1 each, 363 with 4 each. A reader emitting both would double
every dose on those sessions exactly and silently, and
`administration_events_on_day` feeds nutrient arithmetic, where a doubled
Venofer is doubled iron.

The fallback cannot be dropped either: 1,297 of 1,967 sessions are text-only,
because the workbooks behind them are not present to re-import.

**What each assertion is worth**, stated because the difference matters:

  * The TIME assertions are regression guards. Both readers previously built
    flowsheet rows with `time=None` hardcoded, so these fail against the old
    code.
  * The NO-DOUBLING assertion is a FORWARD guard only. It also passes against
    the old code, which never read this table at all, so it is evidence about
    the next change rather than about this one.
"""

from __future__ import annotations

from datetime import date, datetime, time

import pytest

from app.models.chronic_conditions import TherapySession, TherapyStatus, TherapyType
from app.models.med_nutrient import MedicationDoseLog
from app.models.session_drug import SessionDrug
from app.models.user import User
from app.services import clinical_sources

DAY = date(2026, 9, 14)


async def _user(db, email: str) -> User:
    u = User(email=email, hashed_password="x", full_name="Timing Tester")
    db.add(u)
    await db.flush()
    return u


async def _session(db, user_id: int, text: str | None) -> TherapySession:
    s = TherapySession(
        user_id=user_id,
        therapy_type=TherapyType.HEMODIALYSIS,
        status=TherapyStatus.COMPLETED,
        scheduled_date=datetime(DAY.year, DAY.month, DAY.day, 6, 0),
        drugs_administered=text,
    )
    db.add(s)
    await db.flush()          # the id is needed for session_drugs rows
    return s


@pytest.mark.asyncio
async def test_the_flowsheet_time_reaches_both_readers(db):
    """A structured row's time surfaces, and the drug is counted ONCE."""
    u = await _user(db, "sd-timing@example.com")
    # The session carries BOTH records of the same two administrations — which
    # is the state every re-imported session is in.
    s = await _session(db, u.id, "Epogene (3,000 SQ); Venofer (100 mg)")
    db.add(SessionDrug(session_id=s.id, user_id=u.id, row_index=0, name="Epogene",
                       dose_text="3,000 SQ", route="SC",
                       administered_time=time(10, 55),
                       administered_at=datetime(DAY.year, DAY.month, DAY.day, 10, 55)))
    db.add(SessionDrug(session_id=s.id, user_id=u.id, row_index=1, name="Venofer",
                       dose_text="100 mg", route="Access",
                       administered_time=time(11, 20),
                       administered_at=datetime(DAY.year, DAY.month, DAY.day, 11, 20)))
    await db.flush()

    merged = await clinical_sources.administrations_on_day(db, u.id, DAY)
    by_name = {r.name: r for r in merged}
    assert sorted(by_name) == ["Epoetin alfa", "Iron sucrose"]
    # REGRESSION: both of these were None before, because the reader could only
    # see the flattened text.
    assert by_name["Epoetin alfa"].time == "10:55"
    assert by_name["Iron sucrose"].time == "11:20"
    # The dose still comes from the sheet verbatim, never parsed into a number.
    assert by_name["Epoetin alfa"].dose == "3,000 SQ"

    events = await clinical_sources.administration_events_on_day(db, u.id, DAY)
    # FORWARD GUARD: two administrations recorded twice are two events, not four.
    # This reader feeds nutrient arithmetic, so a 2x here is a 2x of iron.
    assert len(events) == 2, [f"{e.name} {e.time}" for e in events]
    assert sorted(e.time for e in events) == ["10:55", "11:20"]


@pytest.mark.asyncio
async def test_a_session_with_no_structured_rows_still_reads_its_text(db):
    """The fallback carries 1,297 of 1,967 sessions — it must not regress."""
    u = await _user(db, "sd-textonly@example.com")
    await _session(db, u.id, "Epogene (3,000 SQ); Venofer (100 mg)")
    await db.flush()

    events = await clinical_sources.administration_events_on_day(db, u.id, DAY)
    assert sorted(e.name for e in events) == ["Epoetin alfa", "Iron sucrose"]
    # No time is recorded anywhere for these, and none is invented.
    assert all(e.time is None for e in events)


@pytest.mark.asyncio
async def test_a_dose_logs_own_time_wins_over_the_flowsheets(db):
    """Two records of one administration: the patient's own time is kept."""
    u = await _user(db, "sd-bothsources@example.com")
    db.add(MedicationDoseLog(user_id=u.id, medication_name="venofer",
                             log_date=DAY, dose_amount=100, dose_unit="mg",
                             log_time=time(8, 0)))
    s = await _session(db, u.id, "Venofer (100 mg)")
    db.add(SessionDrug(session_id=s.id, user_id=u.id, row_index=0, name="Venofer",
                       dose_text="100 mg", route="Access",
                       administered_time=time(10, 55),
                       administered_at=datetime(DAY.year, DAY.month, DAY.day, 10, 55)))
    await db.flush()

    merged = await clinical_sources.administrations_on_day(db, u.id, DAY)
    assert len(merged) == 1, [r.name for r in merged]
    row = merged[0]
    assert sorted(row.sources) == ["administered", "logged"]
    # The dose log is what the patient themselves recorded; the flowsheet time
    # fills a gap, it does not overwrite their entry.
    assert row.time == "08:00"


@pytest.mark.asyncio
async def test_an_untimed_structured_row_stays_untimed(db):
    """85% of rows have no time on the sheet. An absent time is absent."""
    u = await _user(db, "sd-untimed@example.com")
    s = await _session(db, u.id, "Sodium Citrate (2.5 ml x 2)")
    # Sodium Citrate is never timed on any sheet measured — 363 rows, 0 times.
    db.add(SessionDrug(session_id=s.id, user_id=u.id, row_index=0,
                       name="Sodium Citrate", dose_text="2.5 ml x 2",
                       route="Access", administered_time=None,
                       administered_at=None))
    await db.flush()

    events = await clinical_sources.administration_events_on_day(db, u.id, DAY)
    assert len(events) == 1
    assert events[0].name == "Sodium citrate"
    assert events[0].time is None
    assert events[0].dose == "2.5 ml x 2"
