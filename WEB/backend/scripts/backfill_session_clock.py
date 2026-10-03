#!/usr/bin/env python3
# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""Fill the treatment clock and machine totals from the flowsheet workbooks.

Consumes the JSON written by `extract_flowsheet_clocks.py`, matches each sheet
to a `therapy_sessions` row, and fills ONLY columns that are currently NULL.

    # 1. on the host, read the workbooks
    ML/.venv-health-ml/bin/python WEB/backend/scripts/extract_flowsheet_clocks.py \
        --out /tmp/flowsheet_clocks.json

    # 2. against prod, through the proxy (see the invocation note at the end)
    python scripts/backfill_session_clock.py --sheets /tmp/flowsheet_clocks.json
    python scripts/backfill_session_clock.py --sheets /tmp/flowsheet_clocks.json --apply

WHY THIS IS WORTH DOING
=======================
Measured on production 2026-10-02:

    therapy_sessions                     2,032 rows
      actual_start_time                     49
      machine_total_time_minutes             4
      total_uf_liters                       31

The workbooks carry a start on 653 sheets and a machine total time on 653.
Per CLAUDE.md 3at the machine's total time is time actually ON dialysis — the
figure Kt/V is computed from, always less than the wall clock — and it is NOT
derivable from anything else on the row. Neither is the clock: `scheduled_date`
is stored at midnight, and 3an warns that measuring dialysis recency from it
invents up to a day of error on the one number that decides whether potassium
is at its trough.

HOW A SHEET IS MATCHED TO A SESSION
===================================
**The sheet NAME is the date authority, not the sheet's own date cell.** `r4c8`
disagrees with the name on 41 of 689 sheets, and where it does the record
settles it: on all 14 large disagreements the NAME's date has a session and the
cell's date has none. `'May 21-2013'` carries `r4c8 = 2018-05-21`, and the
database holds exactly one 2013 session — 2013-05-21, its earliest row — and
nothing at all on 2018-05-21. Three July 2017 sheets all carry the same stale
`2021-09-15`. So the cell is recorded as a disagreement and never preferred.

Date alone is NOT enough, because **54 of 77 multi-session days are genuinely
two treatments** — a daytime one and an overnight one. (That was established
from the reading times after an earlier pass reported 4: it had used
`min(reading_time)` as a session's start, which is `00:xx` on a session that
began at 22:00 and whose readings wrapped past midnight, so every window
spanned the whole day and overlapped everything.) Matching therefore goes:

1. **A candidate whose EXISTING clock equals the sheet's is the match.** It is
   already timed, so nothing is written — but claiming it stops the sheet being
   mis-assigned to the other session on that day. This is what resolves
   2018-10-13, 2025-06-06 and 2025-06-16.
2. **One sheet and one session on a day is a match.** Evidence exists to
   disambiguate; it must not gate a match with nothing to confuse it with.
3. **Otherwise, score by readings inside the sheet's window.** Each session's
   reading times are tried under three anchorings — as stored, wrapped (early
   readings shifted to the following morning when the set spans both ends of the
   day), and wholly next-morning — and the best is kept. A session whose
   readings are ENTIRELY post-midnight cannot be detected from the readings
   alone; the sheet's own window is the evidence for shifting them.
4. Anything still unresolved is reported, never assigned on a guess.

WHAT THE READINGS CANNOT CORROBORATE
====================================
On 14 matched sheets no reading falls inside the window under any anchoring —
because on those rows `reading_time` is **not a time of day**. 2018-05-12 holds
`00:00, 00:03, 00:06, 00:09, 00:14, 00:48, 01:09, 01:44, 02:31, 02:59`: an
elapsed-time schedule from the start of treatment. 2024-07-22 holds nine
readings all at `00:00`. That is a separate, pre-existing question about how
those rows were imported and is NOT repaired here. The sheet is the primary
document for the clock, so the clock is written and the row is REPORTED as
uncorroborated — rather than silently trusting or silently discarding it.

PLAUSIBILITY: ONLY THE IMPOSSIBLE IS WITHHELD
=============================================
Following 3ab — "plausibility is impossible, never abnormal" — a questionable
value arrives flagged, not deleted, and only arithmetic impossibilities are
held back:

* `total_uf_liters = 99` with `total_blood_volume_processed = 1.5` on
  '04-05-2025' are **transposed** at the cell: BVP is ~99 L and UF ~1.5 L on
  every other sheet. Both are withheld for that sheet rather than swapped,
  because swapping them would be a guess about which box the operator meant.
* 'Oct 29-2017' reads `BVP = 4.7` where ~40 is expected; `BVP ÷ machine
  minutes` implies 47 ml/min against a median of 426 and a delivered median of
  397 (3ac). Withheld.
* **A short treatment is NOT withheld.** Machine times of 14, 18, 53, 58 and 59
  minutes are aborted sessions, and their dialysate, UF and BVP all scale down
  together — 'Jan 30-2018' reads 14 min / 2.3 L / 0.0 L / 5 L, internally
  consistent. Withholding those would delete the record of a treatment that
  failed, which is a clinical finding.
* **Machine time exceeding the wall clock is flagged, not fixed.** 10 sheets do
  it: '03-12-2024' reads `16:15 -> 17:20` (65 min) against `Total Time 2:45`
  (165). Every one of those machine values passes the BVP check, so the stop
  time is the unreliable half — but which is wrong is not knowable from here,
  and 3at requires a gap between the two clocks to be surfaced rather than
  reconciled.
* **A wall clock twelve hours too long is an AM/PM error, and its end is
  withheld.** The gap between the clock and the machine's time on dialysis is
  tight across the 486 sheets carrying both — median 22 min, p95 47 — and then
  EMPTY from 60 to 600 before 12 sheets appear at 612-858 min. Those 12 are a
  separate population, not a tail: `'Nov 11-2017' 10:07 -> 02:00` rolls to 953
  min against 197 on the machine, and a `22:07` start would give 233 min, a
  36-minute gap. `'10-23-2025' 20:30 -> 12:30` against 221 min becomes 240 min
  with a `00:30` stop. The START is written (internally consistent) and the end
  is not, because a 16-hour duration would corrupt every duration-based feature
  reading this column. Which of the two cells is wrong is not inferable, so
  neither is altered — see `MAX_CLOCK_MINUS_MACHINE`.

ONLY NULLS ARE FILLED
=====================
Every write is `if getattr(row, field) is None`. Nothing stored is ever
overwritten, including the 49 existing clocks and the 4 existing machine times
— so a disagreement between a stored value and a sheet is reported and left for
a person. This matters: 2 of the 14 comparable stored clocks differ from their
sheet (id 4 by 4 minutes, id 18 by 1 h 39 m), and deciding those is not a
backfill's job.

Running against production needs BOTH host networking and the proxy:

    docker run --rm --network host \\
      -v "$PWD/WEB/backend:/app" -v "$PWD/ML/src:/ml/src" -w /app \\
      -v /tmp/flowsheet_clocks.json:/tmp/flowsheet_clocks.json \\
      -e PYTHONPATH=/ml/src:/app \\
      -e DATABASE_URL="postgresql+asyncpg://${DB_USER}:${PROD_DB_PASS}@127.0.0.1:${PROXY_PORT}/${DB_NAME}" \\
      web-backend-test python scripts/backfill_session_clock.py \\
          --sheets /tmp/flowsheet_clocks.json
"""

from __future__ import annotations

import argparse
import asyncio
import collections
import datetime
import json
import pathlib
import sys

from sqlalchemy import select, text

sys.path.insert(0, "/app")

from app.core.database import async_session               # noqa: E402
from app.models.chronic_conditions import TherapySession  # noqa: E402

#: Commit every N sessions, so a failure part-way leaves completed work on disk.
BATCH = 100

#: Minutes either side of a sheet's window that still count as "inside" it.
#: A reading is taken on the half hour by hand; the clock is read off a machine.
TOLERANCE_MINUTES = 45

#: Plausibility bands. Only values OUTSIDE these are withheld, and every one is
#: reported. See the module docstring for why a 14-minute treatment is kept.
MACHINE_MINUTES_RANGE = (5, 600)
UF_LITERS_RANGE = (0.0, 8.0)
DIALYSATE_LITERS_RANGE = (0.5, 120.0)
BVP_LITERS_RANGE = (1.0, 200.0)
#: Blood volume processed divided by minutes on dialysis, in ml/min. The
#: delivered rate's median is 397 (3ac); this band is deliberately wide and
#: exists only to catch a transposed cell, not to judge a treatment.
BVP_RATE_ML_MIN = (150.0, 600.0)

#: How far the wall clock may exceed the machine's time on dialysis before the
#: PAIR is judged inconsistent and `actual_end_time` is withheld.
#:
#: Not invented — read off the distribution of (clock - machine) over the 486
#: sheets that carry both. Genuine pauses and alarms are tight: p25=16,
#: median=22, p75=29, p95=47 minutes. Then the distribution is EMPTY from 60 to
#: 600, and 12 sheets sit at 612-858 with a mean near 735 — twelve hours, an
#: AM/PM error in one of the two cells. Any value in that empty region works;
#: 360 sits in the middle of it.
MAX_CLOCK_MINUS_MACHINE = 360


def parse_time(text_value: str | None) -> datetime.time | None:
    return datetime.time.fromisoformat(text_value) if text_value else None


def minutes_of(value: datetime.time) -> int:
    return value.hour * 60 + value.minute


def sheet_window(sheet: dict) -> tuple[int, int, bool]:
    """(start, end, crosses_midnight) in minutes from midnight of the sheet date.

    A stop earlier than the start belongs to the following day. Corroborated
    independently: session 2755 computes 295 minutes once rolled against a
    stored `machine_total_time_minutes` of 263, and 3at requires the wall clock
    to exceed the machine's time on dialysis.
    """
    start = parse_time(sheet["start"])
    stop = parse_time(sheet["stop"])
    begin = minutes_of(start)
    if stop is None:
        # No stop recorded. A 6 h envelope is used for SCORING only; no
        # actual_end_time is written without a stop on the sheet.
        return begin, begin + 360, False
    end = minutes_of(stop)
    return begin, (end + 1440 if end < begin else end), end < begin


def anchorings(mins: list[int]) -> list[tuple[str, list[int]]]:
    """Every reading of one reading set. The sheet decides which one is right."""
    if not mins:
        return []
    out = [("as_stored", mins)]
    if any(m < 360 for m in mins) and any(m >= 1080 for m in mins):
        out.append(("wrapped",
                    sorted((m + 1440) if m < 720 else m for m in mins)))
    out.append(("next_morning", [m + 1440 for m in mins]))
    return out


def score(sheet: dict, reading_minutes: list[int]) -> tuple[float, str, int]:
    """(fraction inside, which anchoring, how many) — 0.0 when there is no
    evidence either way, which is NOT the same as evidence against."""
    if not reading_minutes:
        return 0.0, "no readings", 0
    begin, end, _ = sheet_window(sheet)
    best = (0.0, "none", 0)
    for name, candidate in anchorings(reading_minutes):
        inside = sum(1 for m in candidate
                     if begin - TOLERANCE_MINUTES <= m <= end + TOLERANCE_MINUTES)
        fraction = inside / len(candidate)
        if fraction > best[0]:
            best = (fraction, name, inside)
    return best


def in_band(value, band: tuple[float, float]) -> bool:
    return value is not None and band[0] <= value <= band[1]


def gated_values(sheet: dict, problems: list[str]) -> dict:
    """The sheet's measurements, with the impossible ones withheld and named."""
    out: dict[str, object] = {}
    machine = sheet.get("machine_minutes")
    if machine is not None:
        if in_band(machine, MACHINE_MINUTES_RANGE):
            out["machine_total_time_minutes"] = int(machine)
        else:
            problems.append(f"machine_total_time_minutes={machine} outside "
                            f"{MACHINE_MINUTES_RANGE}")

    bvp = sheet.get("total_blood_volume_processed")
    uf = sheet.get("total_uf_liters")
    dialysate = sheet.get("total_dialysate_liters")

    # A transposed UF/BVP pair is caught by the implied blood-flow rate, not by
    # either value alone: 99 L of UF and 1.5 L of BVP are each a possible
    # NUMBER, and only their relationship to the minutes says they swapped.
    rate = None
    if bvp and machine:
        rate = bvp * 1000.0 / machine

    if in_band(uf, UF_LITERS_RANGE):
        out["total_uf_liters"] = float(uf)
    elif uf is not None:
        problems.append(f"total_uf_liters={uf} outside {UF_LITERS_RANGE}")

    if in_band(dialysate, DIALYSATE_LITERS_RANGE):
        out["total_dialysate_liters"] = float(dialysate)
    elif dialysate is not None:
        problems.append(f"total_dialysate_liters={dialysate} outside "
                        f"{DIALYSATE_LITERS_RANGE}")

    if bvp is not None:
        if not in_band(bvp, BVP_LITERS_RANGE):
            problems.append(f"total_blood_volume_processed={bvp} outside "
                            f"{BVP_LITERS_RANGE}")
        elif rate is not None and not (BVP_RATE_ML_MIN[0] <= rate
                                       <= BVP_RATE_ML_MIN[1]):
            problems.append(
                f"total_blood_volume_processed={bvp} implies {rate:.0f} ml/min "
                f"over {machine} min, outside {BVP_RATE_ML_MIN} — a transposed "
                f"cell (UF={uf})")
            out.pop("total_uf_liters", None)
            problems.append("total_uf_liters withheld as well: the pair is "
                            "unreliable, and swapping them would be a guess")
        else:
            out["total_blood_volume_processed"] = float(bvp)
    return out


def clock_values(sheet: dict, day: datetime.date,
                 problems: list[str]) -> dict:
    """actual_start_time and actual_end_time, with the midnight rollover."""
    start = parse_time(sheet["start"])
    stop = parse_time(sheet["stop"])
    if start is None:
        return {}
    out = {"actual_start_time": datetime.datetime.combine(day, start)}
    if stop is None:
        return out
    rolled = stop < start
    end_day = day + datetime.timedelta(days=1) if rolled else day
    out["actual_end_time"] = datetime.datetime.combine(end_day, stop)
    clock = int((out["actual_end_time"] - out["actual_start_time"])
                .total_seconds() // 60)
    machine = sheet.get("machine_minutes")
    if machine is not None and machine > clock:
        # 3at: the machine's time on dialysis must be LESS than the wall clock.
        # Flagged, not reconciled — the machine value is corroborated by BVP,
        # so the stop time is the unreliable half, but which is wrong is not
        # knowable from here.
        problems.append(f"machine_total_time_minutes={machine} EXCEEDS the "
                        f"wall clock of {clock} min ({sheet['start']} -> "
                        f"{sheet['stop']}{' next day' if rolled else ''}) — "
                        f"3at says it must be smaller")
    elif machine is not None and clock - machine > MAX_CLOCK_MINUS_MACHINE:
        # A ~12 h excess is an AM/PM error in one of the two cells, not a long
        # pause: 'Nov 11-2017' reads 10:07 -> 02:00 (953 min) against 197 min
        # on the machine, and a 22:07 start would give 233 min — a 36-minute
        # gap, squarely in the normal band. WHICH cell is wrong differs per
        # sheet and is not knowable from here, so neither is corrected. The
        # start is kept (it is internally consistent) and the end withheld,
        # because a 16-hour duration in this column would corrupt every
        # duration-based feature and any Kt/V comparison built on it.
        shifted = clock - machine - 720
        out.pop("actual_end_time")
        problems.append(
            f"actual_end_time WITHHELD: {sheet['start']} -> {sheet['stop']}"
            f"{' next day' if rolled else ''} is a {clock} min clock around "
            f"{machine} min on the machine, a gap of {clock - machine} min "
            f"(~12 h out by {shifted:+d} min). One of the two times has the "
            f"wrong AM/PM; the start is kept and the stop needs fixing at "
            f"source. Typical gap on this record is 22 min (p95 47).")
    return out


async def load_sessions(db) -> tuple[dict, dict]:
    """(sessions by id, session ids by date) with the reading times attached."""
    rows = (await db.execute(
        select(TherapySession.id, TherapySession.scheduled_date,
               TherapySession.actual_start_time, TherapySession.actual_end_time,
               TherapySession.machine_total_time_minutes)
    )).all()
    sessions = {}
    by_day = collections.defaultdict(list)
    for sid, scheduled, start, end, machine in rows:
        day = scheduled.date() if scheduled else None
        sessions[sid] = {"id": sid, "day": day, "start": start, "end": end,
                         "machine": machine, "readings": []}
        if day:
            by_day[day].append(sid)

    # Raw SQL for the readings: this script needs only (session_id, time), and
    # naming a model it does not otherwise use would be inventing an import.
    for sid, reading in (await db.execute(text(
        "SELECT session_id, reading_time FROM intradialytic_readings "
        "WHERE reading_time IS NOT NULL"
    ))).all():
        if sid in sessions:
            sessions[sid]["readings"].append(minutes_of(reading))
    for s in sessions.values():
        s["readings"].sort()
    return sessions, by_day


def choose(sheets: list[dict], candidates: list[dict]) -> tuple[list[tuple], list]:
    """[(sheet, session, basis, fraction, anchoring)], [unmatched sheets]."""
    matched, taken_sheets, taken_sessions = [], set(), set()

    # 1. an existing clock that equals the sheet's claims that sheet outright.
    for sheet in sheets:
        if not sheet["start"]:
            continue
        start = parse_time(sheet["start"])
        for session in candidates:
            if session["id"] in taken_sessions or not session["start"]:
                continue
            if session["start"].time() == start:
                matched.append((sheet, session, "stored clock matches the sheet",
                                None, "existing clock"))
                taken_sheets.add(sheet["sheet"])
                taken_sessions.add(session["id"])
                break

    live_sheets = [s for s in sheets if s["sheet"] not in taken_sheets]
    live_sessions = [s for s in candidates if s["id"] not in taken_sessions]

    # 2. nothing to confuse it with.
    if len(live_sheets) == 1 and len(live_sessions) == 1:
        fraction, anchoring, _ = score(live_sheets[0], live_sessions[0]["readings"]) \
            if live_sheets[0]["start"] else (None, "no start", 0)
        matched.append((live_sheets[0], live_sessions[0], "only candidate",
                        fraction, anchoring))
        return matched, []

    # 3. let the readings decide.
    pairs = []
    for sheet in live_sheets:
        for session in live_sessions:
            if not sheet["start"]:
                pairs.append((-1.0, "no start", sheet, session))
                continue
            fraction, anchoring, _ = score(sheet, session["readings"])
            pairs.append((fraction, anchoring, sheet, session))
    pairs.sort(key=lambda p: -p[0])
    for fraction, anchoring, sheet, session in pairs:
        if sheet["sheet"] in taken_sheets or session["id"] in taken_sessions:
            continue
        if fraction <= 0.0:
            continue
        matched.append((sheet, session, "best of "
                        f"{len(live_sheets)} sheets x {len(live_sessions)} sessions",
                        fraction, anchoring))
        taken_sheets.add(sheet["sheet"])
        taken_sessions.add(session["id"])

    rest_sheets = [s for s in live_sheets if s["sheet"] not in taken_sheets]
    rest_sessions = [s for s in live_sessions if s["id"] not in taken_sessions]

    # 4. one of each left over: pair them, and say there was no evidence.
    if len(rest_sheets) == 1 and len(rest_sessions) == 1:
        matched.append((rest_sheets[0], rest_sessions[0], "last remaining pair",
                        None, "no evidence"))
        return matched, []
    return matched, rest_sheets


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sheets", required=True,
                    help="JSON from extract_flowsheet_clocks.py")
    ap.add_argument("--apply", action="store_true",
                    help="write the values (default: dry run)")
    ap.add_argument("--clock-only", action="store_true",
                    help="write actual_start_time/actual_end_time only, leaving "
                         "machine time and the treatment totals alone")
    ap.add_argument("--show", type=int, default=25,
                    help="how many matches to print (default 25)")
    args = ap.parse_args()

    payload = json.loads(pathlib.Path(args.sheets).read_text())
    sheets = payload["sheets"]
    print(f"sheets read: {len(sheets)}  (extracted {payload['generated_at']})")

    by_day_sheets = collections.defaultdict(list)
    for sheet in sheets:
        by_day_sheets[sheet["date"]].append(sheet)

    async with async_session() as db:
        sessions, by_day_sessions = await load_sessions(db)
        print(f"sessions: {len(sessions)}   "
              f"already clocked: {sum(1 for s in sessions.values() if s['start'])}   "
              f"with machine time: "
              f"{sum(1 for s in sessions.values() if s['machine'] is not None)}")

        filled = collections.Counter()
        touched = unmatched = no_session = pending = 0
        problems: list[str] = []
        uncorroborated: list[str] = []
        disagreements: list[str] = []
        shown = 0

        for day_text in sorted(by_day_sheets):
            day = datetime.date.fromisoformat(day_text)
            candidate_ids = by_day_sessions.get(day, [])
            day_sheets = by_day_sheets[day_text]
            if not candidate_ids:
                no_session += 1
                problems.append(f"{day_text}: no session for "
                                f"{[s['sheet'] for s in day_sheets]}")
                continue
            candidates = [sessions[i] for i in candidate_ids]
            matched, leftover = choose(day_sheets, candidates)
            unmatched += len(leftover)
            for sheet in leftover:
                problems.append(
                    f"{day_text}: sheet {sheet['sheet']!r} "
                    f"({sheet['start']}->{sheet['stop']}) matched no session; "
                    f"candidates {[(c['id'], len(c['readings'])) for c in candidates]}")

            for sheet, session, basis, fraction, anchoring in matched:
                row = await db.get(TherapySession, session["id"])
                if row is None:
                    continue
                proposed: dict[str, object] = {}
                sheet_problems: list[str] = []
                proposed.update(clock_values(sheet, day, sheet_problems))
                if not args.clock_only:
                    proposed.update(gated_values(sheet, sheet_problems))
                for note in sheet_problems:
                    problems.append(f"{day_text} {sheet['sheet']!r}: {note}")

                wrote = []
                for field, value in proposed.items():
                    current = getattr(row, field)
                    if current is None:
                        setattr(row, field, value)
                        wrote.append(field)
                        filled[field] += 1
                    elif current != value:
                        disagreements.append(
                            f"{day_text} {sheet['sheet']!r} id={session['id']} "
                            f"{field}: stored {current!r} kept, sheet says "
                            f"{value!r}")
                if wrote:
                    touched += 1
                    pending += 1
                if (fraction == 0.0 and session["readings"]
                        and sheet["start"]):
                    uncorroborated.append(
                        f"{day_text} {sheet['sheet']!r} -> id {session['id']}: "
                        f"none of {len(session['readings'])} readings fall in "
                        f"{sheet['start']}->{sheet['stop']}")
                if shown < args.show:
                    shown += 1
                    frac = "-" if fraction is None else f"{fraction:.2f}"
                    print(f"  {day_text} {sheet['sheet']!r:18} -> id "
                          f"{session['id']:<5} [{basis}, {anchoring}, {frac}] "
                          f"{'+'.join(wrote) or 'nothing to fill'}")
                # `touched % BATCH` would re-fire on every later sheet while
                # `touched` sat on a multiple of 100, because it only advances
                # when something is written. Count what is actually pending.
                if args.apply and pending >= BATCH:
                    await db.commit()
                    pending = 0

        print(f"\nsheet-days with no session : {no_session}")
        print(f"sheets matching no session : {unmatched}")
        print(f"sessions touched           : {touched}")
        print(f"columns filled:")
        for field, count in filled.most_common():
            print(f"    {field:<34} {count}")

        print(f"\nstored values KEPT where the sheet disagrees "
              f"({len(disagreements)}):")
        for line in disagreements[:40]:
            print(f"    {line}")

        print(f"\nclocks written that the readings do NOT corroborate "
              f"({len(uncorroborated)}) — the readings on these rows are elapsed "
              f"times, not times of day:")
        for line in uncorroborated:
            print(f"    {line}")

        print(f"\nproblems and withheld values ({len(problems)}):")
        for line in problems:
            print(f"    {line}")

        if args.apply:
            await db.commit()
            print(f"\napplied: {sum(filled.values())} value(s) across "
                  f"{touched} session(s).")
        else:
            await db.rollback()
            print(f"\ndry run: {sum(filled.values())} value(s) across "
                  f"{touched} session(s) would be written. Nothing changed. "
                  f"Use --apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
