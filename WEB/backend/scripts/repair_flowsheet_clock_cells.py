#!/usr/bin/env python3
"""Correct eight clock cells the flowsheets themselves prove wrong, and
withdraw two stored ends the flowsheets prove impossible.

    python scripts/repair_flowsheet_clock_cells.py            # dry run
    python scripts/repair_flowsheet_clock_cells.py --apply

WHERE THE EVIDENCE COMES FROM
=============================
`backfill_session_clock.py` withheld `actual_end_time` on 12 sheets because the
wall clock exceeded the machine's time on dialysis by about twelve hours — an
AM/PM error in one of the two cells. It recorded that WHICH cell was wrong "is
not knowable from here". **That was false.** The sheet carries its own
per-reading times: the readings table header is row 29 with `Time` in column 1,
and those times bracket the treatment independently of the Start/Stop cells.

So the readings choose the cell. `'Nov 11-2017'` reads `10:07 -> 02:00`; its own
readings run `10:14 .. 12:25`, which agrees with the START to seven minutes, so
the STOP is the wrong cell and `14:00` is the value that reconciles it with the
machine's 197 minutes. `'Marc 23-2018.2'` reads `11:23 -> 01:43` with readings
`23:25 .. 01:42` — 718 minutes from the start cell and agreeing with the stop —
so there the START is wrong.

This matters because the arithmetic ALONE can never choose: shifting either cell
by twelve hours changes the clock by the same ±720 and yields an identical gap.
Only the readings break the tie.

FOUR ATTEMPTS, AND WHAT EACH GOT WRONG
======================================
Recorded because the failures are the reusable part.

1. Flagged 121 sheets. No midnight normalisation between the start CELL and the
   first READING (every overnight sheet showed a spurious ~1,400-minute
   offset — and 43% of this record crosses midnight), plus a 120-minute ceiling
   on how long after its last reading a treatment may end. Readings stop early
   by habit: `'01-05-2025'` logs two readings in the first 11 minutes of a
   166-minute session, and CLAUDE.md 3ac records the cadence falling from 9.5
   per session to 3.2. Nearly all 121 were artifacts of the rule.
2. Used machine time as the trigger — correct, and its blame table was right —
   but classified reading-column wraps with `prev >= 22:00 and cur <= 02:00`.
   An ordinary crossing with two readings hours apart looks like
   `21:49 -> 01:06` and fails both bounds, so 46 benign sheets were filed as
   "unclassified".
3. Chose the smallest wrap step whose span stayed plausible, but never required
   the step to RESTORE ORDER. For `21:49 -> 01:06`, `+720` gives `13:06` —
   still behind — yet the test passed vacuously, so `+720` always won and 172
   sheets were mislabelled 12-hour. `'May 10-2018'` printing a `21:53..12:17`
   window is that bug on its face.
4. This one. A step must restore order AND keep the span plausible, which gives
   **181 midnight / 5 twelve-hour / 9 mistyped** — and 181 corroborates the
   independently measured 43% of treatments crossing midnight.

WHAT IS DELIBERATELY NOT REPAIRED
=================================
Nine sheets are reported and left alone, because naming the fault is honest and
guessing the keystroke is not:

* **No reading carries a time** — `05-18-2024`, `10-16-2025`, `12-11-2025`.
  A twelve-hour shift of either cell would fit `05-18-2024` and `12-13-2025`
  equally well; with no readings there is nothing to break the tie.
* **The slip is not twelve hours.** `'July 11-2018'` reads `08:05` against
  readings beginning `18:08` — a ten-hour difference, one digit in the tens
  place. The readings name the cell; they do not name the keystroke, so the
  replacement is not derivable and `±720` correctly refuses to invent it.
* **The start sits 55-85 minutes from the first reading** — `May 10-2018`,
  `Jan 3-2018`, `05-17-2025`, `12-13-2025`. Neither agreeing nor twelve hours
  out, so the readings cannot adjudicate.
* `'03-27-2025'` leans the other way entirely: its last reading carries a
  **systolic of 44**, and a session cut short after a pressure like that makes
  the clock right and the machine's 221 minutes the odd value.

TWO ENDS ARE WITHDRAWN, NOT CORRECTED
=====================================
`'07-06-2024'` stores a stop of `17:05` while its own last reading is `18:53`,
and `'03-12-2024'` stores `17:20` against a last reading of `18:26`. A treatment
cannot end before a reading taken during it. Those two ends were written by the
flowsheet backfill — flagged at the time only as "machine exceeds clock", which
is weaker evidence than this — and 3ab says the impossible is withheld while the
merely abnormal is kept. So they return to NULL and are reported. The STARTS
stay: both agree with their first reading to within five minutes.

Every row below verifies the stored value still matches what this script was
written against. A row someone has already corrected is skipped and reported,
so a second run cannot shift a cell twice.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import sys

from sqlalchemy import select

sys.path.insert(0, "/app")

from app.core.database import async_session               # noqa: E402
from app.models.chronic_conditions import TherapySession  # noqa: E402

D = datetime.datetime

#: (session, sheet, expected_start, expected_end, new_start, new_end, evidence)
#:
#: `expected_end` is None on the eight corrections because the backfill
#: WITHHELD those ends — they are NULL, and the repair fills them. On the two
#: withdrawals the end is present and becomes NULL.
CORRECTIONS: list[tuple] = [
    (1070, "July 18-2017",
     D(2017, 7, 18, 11, 30), None,
     None, D(2017, 7, 18, 14, 5),
     "readings 11:30..13:40 agree with the START (align 0), so the stop 02:05 "
     "is 12 h out; 14:05 gives a 155 min clock over 143 min machine (gap 12). "
     "This sheet is one of the 5 writing its readings on a 12-hour clock: the "
     "raw column reads ...12:33, 01:08, 01:40, i.e. 13:08 and 13:40"),
    (995, "Nov 11-2017",
     D(2017, 11, 11, 10, 7), None,
     None, D(2017, 11, 11, 14, 0),
     "readings 10:14..12:25 agree with the START (align 7); 14:00 gives 233 min "
     "over 197 min machine (gap 36)"),
    (969, "Dec 25-2017",
     D(2017, 12, 25, 11, 0), None,
     None, D(2017, 12, 25, 13, 40),
     "readings 11:00..11:23 agree with the START (align 0); 13:40 gives 160 min "
     "over 137 min machine (gap 23)"),
    (908, "Marc 23-2018.2",
     D(2018, 3, 23, 11, 23), None,
     D(2018, 3, 23, 23, 23), D(2018, 3, 24, 1, 43),
     "readings 23:25..01:42 are 718 min from the START and agree with the stop, "
     "so the START is 12 h out; 23:23 gives 140 min over 124 min machine "
     "(gap 16). The second treatment that day — the base sheet 'Mar 23-2018' is "
     "session 909"),
    (890, "Apr 21-2018",
     D(2018, 4, 21, 18, 58), None,
     None, D(2018, 4, 21, 21, 29),
     "readings 18:59..21:26 agree with the START (align 1); 21:29 gives 151 min "
     "over 143 min machine (gap 8)"),
    (887, "Apr 25-2018",
     D(2018, 4, 25, 11, 58), None,
     D(2018, 4, 25, 23, 58), D(2018, 4, 26, 3, 17),
     "readings 00:34..03:05 are 684 min from the START and agree with the stop, "
     "so the START is 12 h out; 23:58 gives 199 min over 142 min machine "
     "(gap 57 — the loosest of the eight, still inside the observed p95 of 47 "
     "plus one reading interval)"),
    (1152, "06-21-2024",
     D(2024, 6, 21, 10, 44), None,
     None, D(2024, 6, 21, 14, 15),
     "readings 10:49..13:47 agree with the START (align 5); 14:15 gives 211 min "
     "over 190 min machine (gap 21)"),
    (1268, "10-23-2025",
     D(2025, 10, 23, 20, 30), None,
     None, D(2025, 10, 24, 0, 30),
     "readings 20:38..20:43 agree with the START (align 8); 00:30 next day "
     "gives 240 min over 221 min machine (gap 19)"),
]

#: (session, sheet, expected_start, expected_end, reason)
WITHDRAW_END: list[tuple] = [
    (1145, "07-06-2024", D(2024, 7, 6, 14, 59), D(2024, 7, 6, 17, 5),
     "the stored stop 17:05 precedes this sheet's own last reading at 18:53 — "
     "a treatment cannot end before a reading taken during it. The start agrees "
     "with the first reading (15:04, align 5) and is kept. Machine time is 224 "
     "min against a 126 min clock, so the stop is the unreliable half, but its "
     "true value is not derivable: the slip is not 12 hours"),
    (1200, "03-12-2024", D(2024, 3, 12, 16, 15), D(2024, 3, 12, 17, 20),
     "the stored stop 17:20 precedes this sheet's own last reading at 18:26. "
     "The start agrees with the first reading (16:26, align 11) and is kept. "
     "Machine time 165 min against a 65 min clock"),
]


def _fmt(value) -> str:
    return "NULL" if value is None else str(value)


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true",
                    help="write the corrections (default: dry run)")
    args = ap.parse_args()

    ids = [r[0] for r in CORRECTIONS] + [r[0] for r in WITHDRAW_END]
    fixed = withdrawn = skipped = 0

    async with async_session() as db:
        rows = {s.id: s for s in (await db.execute(
            select(TherapySession).where(TherapySession.id.in_(ids))
        )).scalars().all()}
        print(f"sessions requested: {len(ids)}   found: {len(rows)}\n")

        print("=" * 76)
        print("CORRECT a clock cell the sheet's own readings prove wrong")
        print("=" * 76)
        for sid, sheet, exp_start, exp_end, new_start, new_end, why in CORRECTIONS:
            row = rows.get(sid)
            if row is None:
                print(f"\n  id {sid:<5} {sheet!r}: NOT FOUND"); skipped += 1; continue
            if row.actual_start_time != exp_start or row.actual_end_time != exp_end:
                print(f"\n  id {sid:<5} {sheet!r}: STATE CHANGED — skipped")
                print(f"        expected {_fmt(exp_start)} -> {_fmt(exp_end)}")
                print(f"        found    {_fmt(row.actual_start_time)} -> "
                      f"{_fmt(row.actual_end_time)}")
                skipped += 1
                continue
            final_start = new_start or exp_start
            clock = int((new_end - final_start).total_seconds() // 60)
            mach = row.machine_total_time_minutes
            if not 60 <= clock <= 480:
                print(f"\n  id {sid:<5} {sheet!r}: REFUSED — the repair gives a "
                      f"{clock} min clock"); skipped += 1; continue
            if mach is not None and clock <= mach:
                print(f"\n  id {sid:<5} {sheet!r}: REFUSED — {clock} min clock "
                      f"would not exceed {mach} min of machine time (3at)")
                skipped += 1
                continue
            print(f"\n  id {sid:<5} {sheet!r}")
            if new_start:
                print(f"        start {exp_start}  ->  {new_start}")
            print(f"        end   {_fmt(exp_end)}  ->  {new_end}")
            print(f"        clock {clock} min, machine {mach} min, "
                  f"gap {clock - mach if mach else '?'}")
            print(f"        {why}")
            if args.apply:
                if new_start:
                    row.actual_start_time = new_start
                row.actual_end_time = new_end
            fixed += 1

        print("\n" + "=" * 76)
        print("WITHDRAW an end the sheet proves impossible")
        print("=" * 76)
        for sid, sheet, exp_start, exp_end, why in WITHDRAW_END:
            row = rows.get(sid)
            if row is None:
                print(f"\n  id {sid:<5} {sheet!r}: NOT FOUND"); skipped += 1; continue
            if row.actual_start_time != exp_start or row.actual_end_time != exp_end:
                print(f"\n  id {sid:<5} {sheet!r}: STATE CHANGED — skipped")
                print(f"        expected {_fmt(exp_start)} -> {_fmt(exp_end)}")
                print(f"        found    {_fmt(row.actual_start_time)} -> "
                      f"{_fmt(row.actual_end_time)}")
                skipped += 1
                continue
            print(f"\n  id {sid:<5} {sheet!r}")
            print(f"        end   {exp_end}  ->  NULL   (start {exp_start} kept)")
            print(f"        {why}")
            if args.apply:
                row.actual_end_time = None
            withdrawn += 1

        if args.apply:
            await db.commit()
            print(f"\napplied: {fixed} corrected, {withdrawn} end(s) withdrawn, "
                  f"{skipped} skipped.")
        else:
            await db.rollback()
            print(f"\ndry run: {fixed} would be corrected, {withdrawn} end(s) "
                  f"withdrawn, {skipped} skipped. Nothing written. Use --apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
