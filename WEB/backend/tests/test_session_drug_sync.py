# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""Saving a flowsheet structures the drugs it records — without losing timing.

`session_drugs` had exactly one writer: `scripts/import_flowsheets.py`, which
reads Excel workbooks. Measured on production 2026-10-02 the table stopped at
**2025-12-31** while dosing continued, and 1,299 sessions spanning
2018-11-16 → 2026-09-25 held drug text with no structured rows.

The clinical surfaces never showed it, because `clinical_sources` falls back to
parsing the text. Anything reading the table directly did: the ML exposure
series saw a patient who ceased IV iron ten months early, across the window
where ferritin fell 1,033 → 24 and transferrin saturation to 6%, and could not
see the dose change from 100 mg to 200 mg because every 2026 session was in the
unparsed set.

These tests pin the two rules that make filling that gap safe.
"""

from __future__ import annotations

from datetime import date, datetime, time

import pytest

from app.models.chronic_conditions import TherapySession, TherapyStatus, TherapyType
from app.models.session_drug import SessionDrug
from app.models.user import User
from app.services import clinical_sources
from app.services.session_drug_sync import sync_session_drugs, verbatim_name

from sqlalchemy import select

DAY = date(2026, 9, 15)


async def _user(db, email: str) -> User:
    u = User(email=email, hashed_password="x", full_name="Sync Tester")
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
    await db.flush()
    return s


def test_the_stored_name_is_what_the_sheet_wrote_not_the_canonical_form():
    """Production holds `Epogene` 673, `Venofer` 364 — never `Epoetin alfa`.

    `parse_drugs_administered` canonicalises, so persisting its `.name` would
    put `Epoetin alfa` beside 673 rows saying `Epogene` and split one drug into
    two spellings inside the table that exists to stop exactly that (§3ax).
    """
    assert verbatim_name("Epogene (3,000 SQ)") == "Epogene"
    assert verbatim_name("Venofer (200 mg)") == "Venofer"
    assert verbatim_name("Sodium Citrate (2.5 ml x 2)") == "Sodium Citrate"
    assert verbatim_name("Doxercalcif (2 mcg)") == "Doxercalcif"
    assert verbatim_name("Epogene") == "Epogene"


@pytest.mark.asyncio
async def test_a_saved_flowsheet_gets_structured_rows(db):
    """The gap this closes: text in, structured rows out, doses preserved."""
    u = await _user(db, "sds-new@example.com")
    s = await _session(db, u.id, "Epogene (3000); Venofer (200 mg)")

    added = await sync_session_drugs(db, s)
    await db.flush()
    assert added == 2

    rows = (await db.execute(
        select(SessionDrug).where(SessionDrug.session_id == s.id)
        .order_by(SessionDrug.row_index)
    )).scalars().all()
    assert [r.name for r in rows] == ["Epogene", "Venofer"]
    assert [r.dose_text for r in rows] == ["3000", "200 mg"]
    # The 200 mg is the point: the dose doubled in 2026 and the old table could
    # not see it, because it held only `100 mg` rows written from a workbook.
    assert rows[1].dose_text == "200 mg"


@pytest.mark.asyncio
async def test_route_and_time_are_absent_not_invented(db):
    """The flattened text carries neither. An absent value stays absent (§0)."""
    u = await _user(db, "sds-absent@example.com")
    s = await _session(db, u.id, "Sodium Citrate (2.5 ml x 2)")

    await sync_session_drugs(db, s)
    await db.flush()

    row = (await db.execute(
        select(SessionDrug).where(SessionDrug.session_id == s.id)
    )).scalars().one()
    assert row.route is None
    assert row.administered_time is None
    assert row.administered_at is None


@pytest.mark.asyncio
async def test_a_session_that_already_has_rows_is_left_alone(db):
    """Rule 1. The workbook carries route on 1,763 rows and time on 269.

    `parse_drugs_administered` can reproduce neither, so re-parsing to "refresh"
    would destroy the timing §3at says is not cosmetic — an IV iron runs over a
    period, and a drug given at 23:47 belongs to a different calendar day than
    the sheet's date.
    """
    u = await _user(db, "sds-existing@example.com")
    s = await _session(db, u.id, "Venofer (100 mg)")
    db.add(SessionDrug(
        session_id=s.id, user_id=u.id, row_index=0, name="Venofer",
        dose_text="100 mg", route="Access",
        administered_time=time(10, 55),
        administered_at=datetime(DAY.year, DAY.month, DAY.day, 10, 55),
    ))
    await db.flush()

    added = await sync_session_drugs(db, s)
    await db.flush()
    assert added == 0

    rows = (await db.execute(
        select(SessionDrug).where(SessionDrug.session_id == s.id)
    )).scalars().all()
    assert len(rows) == 1
    assert rows[0].route == "Access"
    assert rows[0].administered_time == time(10, 55)


@pytest.mark.asyncio
async def test_structuring_a_session_does_not_change_what_a_reader_sees(db):
    """The readers PREFER structured rows, so the two paths must agree.

    `_flowsheet_items` returns structured rows when present and parses the text
    when not. If syncing changed the answer, every historic session would start
    reading differently the moment it was touched.
    """
    u = await _user(db, "sds-parity@example.com")
    s = await _session(db, u.id, "Epogene (3,000 SQ); Venofer (100 mg)")
    await db.flush()

    before = await clinical_sources.administration_events_on_day(db, u.id, DAY)
    before_names = sorted(e.name for e in before)

    await sync_session_drugs(db, s)
    await db.flush()

    after = await clinical_sources.administration_events_on_day(db, u.id, DAY)
    after_names = sorted(e.name for e in after)

    # Canonicalisation happens at READ time, so both paths still yield the
    # canonical names — and neither path invents a time.
    assert before_names == ["Epoetin alfa", "Iron sucrose"]
    assert after_names == before_names
    assert all(e.time is None for e in after)
    # And no doubling: one administration per drug, not one per source.
    assert len(after) == 2


@pytest.mark.asyncio
async def test_a_nested_semicolon_is_one_drug_not_three(db):
    """`Sodium Citrate (12 ml Venous; 3ml Arterial)` is ONE drug.

    A plain split on `;` invents a drug called "3ml Arterial)".
    """
    u = await _user(db, "sds-nested@example.com")
    s = await _session(
        db, u.id,
        "Sodium Citrate (12 ml  Venous; 3ml Arterial); Epogene (3,000 SQ)")

    added = await sync_session_drugs(db, s)
    await db.flush()
    assert added == 2

    rows = (await db.execute(
        select(SessionDrug).where(SessionDrug.session_id == s.id)
        .order_by(SessionDrug.row_index)
    )).scalars().all()
    assert [r.name for r in rows] == ["Sodium Citrate", "Epogene"]


@pytest.mark.asyncio
async def test_empty_and_unparseable_text_add_nothing(db):
    """A session with no drugs must not gain rows, and must not fail its save."""
    u = await _user(db, "sds-empty@example.com")
    for text in (None, "", "   "):
        s = await _session(db, u.id, text)
        assert await sync_session_drugs(db, s) == 0
