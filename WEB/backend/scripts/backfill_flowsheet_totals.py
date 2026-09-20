"""Restore the post-treatment totals the flowsheet import dropped.

WHAT WAS LOST
-------------
`ML/data/raw/excel/all_flowsheet_sessions.csv` is the flowsheet parser's own
output. It carries, per session:

    total_bvp          1,605 of 1,792 rows   -> total_blood_volume_processed
    total_dialysate_L  1,626                 -> total_dialysate_liters
    total_uf_kg        1,610                 -> total_uf_liters

The database holds 34, 40 and 25. The whole post-treatment totals block was
extracted and then never written, while `dialysate_volume_liters` — the
PRESCRIPTION field immediately above it — landed on 1,980 sessions. Two
importers exist with different coordinate schemes for that block
(`parse_flowsheets.py` reads `iloc[totals_data_row, 10]`;
`WEB/backend/scripts/import_flowsheets.py` reads fixed cells `52/'L'`), and
whichever populated this database missed the row.

The cost was not cosmetic. `dialysis_balance` models protein loss as a flat
9 g per session scaled only by dialysate volume, because blood volume was
believed unavailable — so an 18-minute session that processed 3.6 L of blood
and a 170-minute session that processed 62.5 L are both credited with exactly
9.0 g. Across 1,725 real sessions the protein figure takes three distinct
values. Restoring throughput is what makes a real model possible.

JOINING SAFELY
--------------
The CSV carries `session_date` and NOTHING else identifying — no session id, no
user id. So:

  * a date matching exactly ONE session is written;
  * a date matching several is SKIPPED and reported. 74 days in range carry
    more than one session, and writing one sheet's blood volume onto the wrong
    treatment is a clinical error, not a rounding one;
  * rows are attributed to the session's own user, never assumed. User 63 owns
    2,015 of 2,094 sessions and is the only one predating 2026-03, but that is
    a fact to read off the row, not to hardcode.

Existing values are never overwritten — a figure someone entered by hand
outranks one recovered from an export.

Dry run by default. `--apply` writes.

    docker compose --profile test run --rm \
      -e DATABASE_URL=postgresql+asyncpg://alafia:alafia@db:5432/alafia \
      backend-test python scripts/backfill_flowsheet_totals.py
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import logging
import os
import sys
from collections import defaultdict
from datetime import date, datetime

from sqlalchemy import select

from app.core.database import async_session
from app.models.chronic_conditions import TherapySession
# Imported rather than re-typed: one band, and the transfer model refuses the
# same values this refuses to store.
from app.services.dialysis_balance import DIALYSATE_VOLUME_PLAUSIBLE_L

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("backfill_flowsheet_totals")

#: Where the parser's own output lives. `docker-compose.yml` mounts the repo's
#: `ML/` at `/ml` read-only for every backend container, so that is the path
#: that works in the place this actually runs. The repo-relative fallback is for
#: a host checkout; relative-to-__file__ walks off the container root, which is
#: how the first run reported `/ML/data/...` not found.
_CANDIDATES = (
    os.environ.get("FLOWSHEET_CSV"),
    "/ml/data/raw/excel/all_flowsheet_sessions.csv",
    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 "..", "..", "..", "ML", "data", "raw", "excel",
                 "all_flowsheet_sessions.csv"),
)


def _csv_path() -> str | None:
    for candidate in _CANDIDATES:
        if candidate and os.path.exists(os.path.normpath(candidate)):
            return os.path.normpath(candidate)
    return None

#: CSV column -> (model attribute, plausible range).
#:
#: The bands are NOT decoration. The first run of this script transcribed the
#: parser's output verbatim and wrote a 1.5 L blood volume, a 519 L blood
#: volume, and 23 dialysate values outside 5-120 L against a 30 L prescription
#: — on 11 rows the dialysate column holds the UF figure exactly, which is a
#: cell the extractor read from the wrong place.
#:
#: `dialysis_balance` already refuses a dialysate volume outside this band, and
#: refuses a potassium bath outside 0-4 mEq/L for the same reason: 11 sessions
#: carry 45 mEq/L, the LACTATE value written into the potassium column. A
#: backfill that passes such a value through is §3ab's stolen-value failure
#: moved one layer upstream — and at 1,551 rows it is worse than the empty
#: column it replaced, because an implausible number reads as a measurement.
#:
#: Blood volume: Qb 150-480 mL/min over 120-300 min spans roughly 18-144 L.
#: The band is deliberately wider than that so a genuine outlier survives; it
#: exists to reject a value that cannot be a treatment at all.
FIELDS = {
    "total_bvp": ("total_blood_volume_processed", (10.0, 200.0)),
    "total_dialysate_L": ("total_dialysate_liters", DIALYSATE_VOLUME_PLAUSIBLE_L),
    "total_uf_kg": ("total_uf_liters", (0.05, 10.0)),
}


def _num(raw: str | None) -> float | None:
    """A value, or None. Never 0.0 for a blank — that reads as measured."""
    text = (raw or "").strip()
    if text in ("", "nan", "None", "NaN"):
        return None
    try:
        value = float(text.replace(",", ""))
    except ValueError:
        return None
    # A recorded zero is not plausible for any of these three and is how a
    # blank cell arrives from some sheets.
    return value if value > 0 else None


def _day(raw: str | None) -> date | None:
    text = (raw or "").strip()[:10]
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


async def run(apply: bool) -> int:
    path = _csv_path()
    if path is None:
        logger.error("CSV not found. Looked in:")
        for candidate in _CANDIDATES:
            if candidate:
                logger.error("  %s", os.path.normpath(candidate))
        logger.error("Set FLOWSHEET_CSV to override.")
        return 1

    with open(path, newline="", errors="replace") as fh:
        rows = list(csv.DictReader(fh))
    logger.info("read %d rows from %s", len(rows), path)

    by_day: dict[date, dict[str, float]] = {}
    rejected: list[str] = []
    for row in rows:
        day = _day(row.get("session_date"))
        if day is None:
            continue
        values: dict[str, float] = {}
        for col, (_attr, (lo, hi)) in FIELDS.items():
            value = _num(row.get(col))
            if value is None:
                continue
            if not (lo <= value <= hi):
                rejected.append(f"{day} {col}={value:g} (outside {lo:g}-{hi:g})")
                continue
            values[col] = value
        if values:
            by_day[day] = values
    logger.info("%d dates carry at least one of the three totals", len(by_day))

    written = skipped_ambiguous = skipped_absent = already = 0
    ambiguous_days: list[str] = []

    async with async_session() as db:
        sessions = (await db.execute(
            select(TherapySession).where(
                TherapySession.scheduled_date.isnot(None))
        )).scalars().all()

        per_day: dict[date, list[TherapySession]] = defaultdict(list)
        for s in sessions:
            per_day[s.scheduled_date.date()].append(s)

        for day, values in sorted(by_day.items()):
            candidates = per_day.get(day, [])
            if not candidates:
                skipped_absent += 1
                continue
            if len(candidates) > 1:
                # Two treatments that day; the sheet says which date, not which
                # session. Guessing here writes one treatment's throughput onto
                # another's record.
                skipped_ambiguous += 1
                if len(ambiguous_days) < 12:
                    ambiguous_days.append(str(day))
                continue

            target = candidates[0]
            changed = False
            for col, (attr, _band) in FIELDS.items():
                value = values.get(col)
                if value is None:
                    continue
                if getattr(target, attr, None) is not None:
                    already += 1
                    continue        # a hand-entered figure outranks an export
                if apply:
                    setattr(target, attr, value)
                changed = True
            if changed:
                written += 1

        if apply:
            await db.commit()

    logger.info("")
    logger.info("sessions %s: %d", "UPDATED" if apply else "that WOULD be updated", written)
    logger.info("  skipped, date matches >1 session: %d %s",
                skipped_ambiguous, ambiguous_days[:12])
    logger.info("  skipped, no session on that date: %d", skipped_absent)
    logger.info("  fields left alone (already set):  %d", already)
    # Named, never silent. A value the extractor got wrong is a finding about
    # the source sheets, and hiding the count would make this look cleaner than
    # the data is.
    logger.info("  values REJECTED as implausible:   %d", len(rejected))
    for line in rejected[:15]:
        logger.info("      %s", line)
    if len(rejected) > 15:
        logger.info("      ... and %d more", len(rejected) - 15)
    if not apply:
        logger.info("")
        logger.info("DRY RUN — nothing written. Re-run with --apply to persist.")
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true",
                    help="persist (default is a dry run that writes nothing)")
    args = ap.parse_args()
    sys.exit(asyncio.run(run(args.apply)))


if __name__ == "__main__":
    main()
