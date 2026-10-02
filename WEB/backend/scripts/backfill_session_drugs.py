#!/usr/bin/env python3
"""Structure the drugs on sessions saved before the parser was wired in.

`services/session_drug_sync.py` parses `drugs_administered` when a session is
SAVED. That is forward-only by design, so sessions written before it landed stay
unstructured until someone touches them — and the ML exposure series, which
reads `session_drugs` directly, stays truncated for that history.

WHY THIS DOES NOT BACKFILL EVERYTHING, AND MUST NOT
---------------------------------------------------
Measured on production 2026-10-02: **1,299 sessions spanning 2018-11-16 →
2026-09-25** carry drug text and no structured rows. Filling all of them would
be a data loss, not a repair.

`session_drugs` has a unique index on `(session_id, row_index)`, and the richer
source for the older sessions is an Excel workbook that has not been imported
yet — `FlowsheetGermantown.xlsx` (2019-2022) is recorded as not synced. Those
workbooks carry a ROUTE on 1,763 of 1,764 imported rows and a TIME on 269, and
the flattened text carries neither. Writing text-derived rows over that date
range now would make a later `import_flowsheets.py` run collide with rows that
already exist, and the route and time would be lost for good.

So the default window starts the day AFTER the newest row the workbook importer
produced. Those sessions have no workbook behind them and never will, which is
exactly why the live gap opened there: the table stopped at 2025-12-31 while
dosing continued through 2026, across the window where ferritin fell 1,033 → 24
and transferrin saturation to 6%.

`--all` exists for the day the remaining workbooks are imported and the
collision risk is gone. It is not the safe default and says so.

    python scripts/backfill_session_drugs.py              # dry run, 2026+
    python scripts/backfill_session_drugs.py --apply
    python scripts/backfill_session_drugs.py --all        # read the warning

Running against production needs BOTH host networking and ML/src on PYTHONPATH:

    docker run --rm --network host \
      -v "$PWD/WEB/backend:/app" -v "$PWD/ML/src:/ml/src" -w /app \
      -e PYTHONPATH=/ml/src:/app \
      -e DATABASE_URL="postgresql+asyncpg://${DB_USER}:${PROD_DB_PASS}@127.0.0.1:${PROXY_PORT}/${DB_NAME}" \
      web-backend-test python scripts/backfill_session_drugs.py
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date, timedelta

from sqlalchemy import func, select

sys.path.insert(0, "/app")

from app.core.database import async_session               # noqa: E402
from app.models.chronic_conditions import TherapySession  # noqa: E402
from app.models.session_drug import SessionDrug           # noqa: E402
from app.services.session_drug_sync import sync_session_drugs  # noqa: E402

#: Commit every N sessions rather than once at the end, so a failure part-way
#: leaves completed work on disk instead of discarding all of it.
BATCH = 100


async def _workbook_boundary(db) -> date | None:
    """The newest session that already has structured rows.

    Everything on or before this came from a workbook import, or from a session
    saved since the parser was wired in. Either way it is already structured and
    out of scope.
    """
    newest = (await db.execute(
        select(func.max(TherapySession.scheduled_date))
        .select_from(SessionDrug)
        .join(TherapySession, TherapySession.id == SessionDrug.session_id)
    )).scalar()
    return newest.date() if newest else None


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true",
                    help="write the rows (default: dry run)")
    ap.add_argument("--all", action="store_true",
                    help="ignore the workbook boundary — see the module docstring; "
                         "this can foreclose route and time for sessions whose "
                         "workbook has not been imported yet")
    args = ap.parse_args()

    async with async_session() as db:
        boundary = await _workbook_boundary(db)
        since = None
        if not args.all and boundary:
            since = boundary + timedelta(days=1)
            print(f"workbook boundary: {boundary} — structuring sessions from {since}")
        elif args.all:
            print("--all: NO boundary. Sessions whose workbook is not yet imported "
                  "will be filled from text, and their route and time cannot be "
                  "recovered later.")
        else:
            print("no structured rows exist at all — structuring every session")

        stmt = (
            select(TherapySession)
            .where(
                TherapySession.drugs_administered.isnot(None),
                func.btrim(TherapySession.drugs_administered) != "",
                ~select(SessionDrug.id)
                .where(SessionDrug.session_id == TherapySession.id)
                .exists(),
            )
            .order_by(TherapySession.scheduled_date)
        )
        if since is not None:
            stmt = stmt.where(TherapySession.scheduled_date >= since)

        sessions = (await db.execute(stmt)).scalars().all()
        print(f"sessions with drug text and no structured rows: {len(sessions)}")

        rows = 0
        touched = 0
        for index, session in enumerate(sessions, start=1):
            added = await sync_session_drugs(db, session)
            if added:
                rows += added
                touched += 1
                day = str(session.scheduled_date)[:10]
                if touched <= 15:
                    print(f"  {day}  {added} row(s)  "
                          f"{(session.drugs_administered or '')[:60]}")
            if args.apply and index % BATCH == 0:
                await db.commit()

        if args.apply:
            await db.commit()
            print(f"\napplied: {rows} row(s) across {touched} session(s).")
        else:
            await db.rollback()
            print(f"\ndry run: {rows} row(s) across {touched} session(s) would be "
                  f"written. Nothing changed. Use --apply.")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
