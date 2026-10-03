#!/usr/bin/env python3
# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""Repair the nine therapy sessions whose stored end precedes their start.

    python scripts/repair_session_clocks.py            # dry run
    python scripts/repair_session_clocks.py --apply

NOT a sweep. Nine specific rows, each with its own evidence recorded below, and
each verified to still look broken in the way expected before anything is
written. A generic "add a day where the end is earlier" rule would silently
half-repair the three rows whose end is dated DAYS early, turning an obviously
corrupt row into a plausible wrong one — which is worse, because nobody would
look at it again.

WHY THESE ROWS EXIST
====================
Two unrelated causes, told apart by `created_at`.

**Six are the client rollover bug.** All three clients compose the stored
timestamp one clock at a time — `${day}T${clock}:00` on web, `iso(day:clock:)`
on iOS, `isoAt(date, endTime)` on Android — so an overnight treatment gets its
end stamped on the START's date. Fixed forward in
`_naive_session_payload` (api/chronic_conditions.py), which covers every path
and every shipped build; these are the rows written before that landed.

**Three are a corrupt import.** ids 4, 11 and 13 (created 2026-06-04) carry an
end dated 7, 3 and 1 days BEFORE their start. No rollover explains that, and
adding 24 hours would leave two of them still negative.

THE EVIDENCE, PER ROW
=====================
Nothing here is inferred from plausibility alone.

* The four live-app rows carry their own answer in the next column.
  `duration_minutes` is computed by the SAME save using the clients'
  rollover-aware helper (`minutesBetween`, `d += 24 * 60`), so it already holds
  the correct wall clock while the timestamp pair is negative — 245, 247, 227
  and 295 minutes, matching the rolled clock EXACTLY. §3ai: two computations of
  one interval must not disagree; here one of them was right all along.

* The flowsheet workbooks independently confirm the end TIME on ids 1, 4 and
  13 — sheet '07-08-2025' stops at 02:30, '07-13-2025' at 11:30, '07-11-2025'
  at 10:43 — and those sheets were written by the unit, not by this codebase.

* ⚠️ `duration_minutes` means something DIFFERENT on the import rows. On all
  five where a comparison is possible it equals the sheet's `Total Time`
  exactly (254, 247, 243, 228, 216) — it is the MACHINE's time on dialysis,
  not the wall clock. So it is used as corroboration for those rows only
  through §3at's relationship: the repaired wall clock must be LARGER, by the
  22-minute median gap this record shows. Every repair below lands 19-28
  minutes above it.

NOT REPAIRED
============
Session 10 (2025-06-11, 08:00 -> 23:30, 930 minutes) is not inverted, so no
rollover applies, and its sheet carries neither a start nor a stop — only a
machine time of 233. A 930-minute wall clock around 233 minutes on dialysis is
implausible, but WHICH of the two times is wrong is not knowable from here, and
guessing would be §0. It is printed for a person to resolve.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timedelta

from sqlalchemy import select

sys.path.insert(0, "/app")

from app.core.database import async_session               # noqa: E402
from app.models.chronic_conditions import TherapySession  # noqa: E402

ROLL_ONE_DAY = "roll the end forward one day"
END_DATE_TO_START_DATE = "move the end onto the start's date"
REPORT_ONLY = "report, do not touch"

#: (id, expected_start, expected_end, action, resulting_minutes, evidence)
#:
#: `expected_*` is the state this script was written against. A row that no
#: longer matches is SKIPPED and reported — so a hand-repair is never
#: clobbered, and a second run can never roll the same end twice.
ROWS: list[tuple] = [
    # ── the client rollover bug, live app ────────────────────────────────
    (2745, datetime(2026, 8, 26, 22, 10), datetime(2026, 8, 26, 2, 15),
     ROLL_ONE_DAY, 245,
     "duration_minutes=245 stored by the same save equals the rolled clock "
     "exactly"),
    (2749, datetime(2026, 9, 3, 20, 43), datetime(2026, 9, 3, 0, 50),
     ROLL_ONE_DAY, 247,
     "duration_minutes=247 equals the rolled clock exactly"),
    (2750, datetime(2026, 9, 5, 21, 3), datetime(2026, 9, 5, 0, 50),
     ROLL_ONE_DAY, 227,
     "duration_minutes=227 equals the rolled clock exactly"),
    (2755, datetime(2026, 9, 15, 22, 45), datetime(2026, 9, 15, 3, 40),
     ROLL_ONE_DAY, 295,
     "duration_minutes=295 equals the rolled clock exactly"),
    # ── the same bug, 2026-06-04 import ─────────────────────────────────
    (1, datetime(2025, 7, 8, 21, 53), datetime(2025, 7, 8, 2, 30),
     ROLL_ONE_DAY, 277,
     "sheet '07-08-2025' stops at 02:30, so the end belongs to 07-09; the "
     "rolled clock of 277 min sits 23 min above the sheet's machine time of "
     "254, matching this record's 22-min median gap (3at)"),
    (6, datetime(2025, 7, 3, 20, 40), datetime(2025, 7, 3, 1, 11),
     ROLL_ONE_DAY, 271,
     "sheet '07-03-2025' records no stop, but the rolled clock of 271 min "
     "sits 28 min above its machine time of 243 — inside the observed gap "
     "distribution (median 22, p95 47)"),
    # ── the corrupt end DATE, 2026-06-04 import ─────────────────────────
    (4, datetime(2025, 7, 13, 7, 3), datetime(2025, 7, 6, 11, 30),
     END_DATE_TO_START_DATE, 267,
     "end dated 7 days early; sheet '07-13-2025' confirms the 11:30 stop, and "
     "267 min sits 20 min above the sheet's machine time of 247"),
    (11, datetime(2025, 7, 6, 6, 0), datetime(2025, 7, 3, 10, 7),
     END_DATE_TO_START_DATE, 247,
     "end dated 3 days early; 247 min sits 19 min above the sheet's machine "
     "time of 228"),
    (13, datetime(2025, 7, 11, 6, 47), datetime(2025, 7, 10, 10, 43),
     END_DATE_TO_START_DATE, 236,
     "end dated 1 day early; sheet '07-11-2025' confirms the 10:43 stop, and "
     "236 min sits 20 min above the sheet's machine time of 216"),
    # ── not repairable from here ─────────────────────────────────────────
    (10, datetime(2025, 6, 11, 8, 0), datetime(2025, 6, 11, 23, 30),
     REPORT_ONLY, 930,
     "930-min wall clock around a sheet machine time of 233, but the sheet "
     "carries NO start and NO stop, so which of the two times is wrong cannot "
     "be determined from the record"),
]


def repaired_end(action: str, start: datetime, end: datetime) -> datetime | None:
    if action == ROLL_ONE_DAY:
        return end + timedelta(days=1)
    if action == END_DATE_TO_START_DATE:
        return datetime.combine(start.date(), end.time())
    return None


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true",
                    help="write the repairs (default: dry run)")
    args = ap.parse_args()

    changed = skipped = reported = mismatched = 0
    async with async_session() as db:
        ids = [r[0] for r in ROWS]
        rows = {s.id: s for s in (await db.execute(
            select(TherapySession).where(TherapySession.id.in_(ids))
        )).scalars().all()}
        print(f"rows requested: {len(ids)}   found: {len(rows)}\n")

        for sid, want_start, want_end, action, expect_minutes, evidence in ROWS:
            row = rows.get(sid)
            if row is None:
                print(f"  id {sid:<5} NOT FOUND — skipped")
                mismatched += 1
                continue

            if action == REPORT_ONLY:
                clock = ((row.actual_end_time - row.actual_start_time)
                         .total_seconds() / 60
                         if row.actual_start_time and row.actual_end_time else None)
                print(f"  id {sid:<5} REPORT ONLY  {row.actual_start_time} -> "
                      f"{row.actual_end_time}  ({clock:.0f} min)" if clock
                      else f"  id {sid:<5} REPORT ONLY")
                print(f"        {evidence}")
                reported += 1
                continue

            # Verify it still looks broken in the expected way. A row someone
            # has already corrected must not be rolled a second time.
            if (row.actual_start_time != want_start
                    or row.actual_end_time != want_end):
                print(f"  id {sid:<5} STATE CHANGED — skipped, nothing written")
                print(f"        expected {want_start} -> {want_end}")
                print(f"        found    {row.actual_start_time} -> "
                      f"{row.actual_end_time}")
                skipped += 1
                continue

            new_end = repaired_end(action, want_start, want_end)
            minutes = int((new_end - want_start).total_seconds() // 60)
            if minutes != expect_minutes:
                print(f"  id {sid:<5} ARITHMETIC MISMATCH — skipped: computed "
                      f"{minutes} min, expected {expect_minutes}")
                mismatched += 1
                continue
            if not 60 <= minutes <= 600:
                print(f"  id {sid:<5} IMPLAUSIBLE RESULT {minutes} min — skipped")
                mismatched += 1
                continue

            print(f"  id {sid:<5} {action}")
            print(f"        {want_end}  ->  {new_end}   ({minutes} min)")
            print(f"        {evidence}")
            if args.apply:
                row.actual_end_time = new_end
            changed += 1

        if args.apply:
            await db.commit()
            print(f"\napplied: {changed} row(s) repaired, {reported} reported, "
                  f"{skipped} unchanged since this script was written, "
                  f"{mismatched} refused.")
        else:
            await db.rollback()
            print(f"\ndry run: {changed} row(s) would be repaired, {reported} "
                  f"reported, {skipped} already changed, {mismatched} refused. "
                  f"Nothing written. Use --apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
