#!/usr/bin/env python3
# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""Extract the treatment clock and machine totals from the flowsheet workbooks.

Reads the Excel workbooks and writes ONE JSON file. It touches no database and
makes no clinical decision: `backfill_session_clock.py` consumes the JSON,
matches each sheet to a session and applies the plausibility gates.

This exists because `therapy_sessions` holds `actual_start_time` on 49 of 2,032
rows and `machine_total_time_minutes` on **4**, while the workbooks carry a
start on 653 sheets and a machine total time on 653. Per CLAUDE.md 3at the
machine's total time is time actually ON dialysis — the figure Kt/V uses — and
is NOT derivable from the wall clock, so those 649 figures cannot be computed
from anything already stored.

    python scripts/extract_flowsheet_clocks.py --out /tmp/flowsheet_clocks.json

Runs on the HOST, not in a container: the workbooks live in the operator's
home directory and OneDrive, and openpyxl is in `ML/.venv-health-ml`.

    ML/.venv-health-ml/bin/python WEB/backend/scripts/extract_flowsheet_clocks.py \
        --out /tmp/flowsheet_clocks.json

WHAT WENT WRONG BEFORE, AND WHY EACH RULE BELOW IS HERE
=======================================================
Every one of these was a silent wrong answer, not a crash. They are recorded
because the shape recurs: a coordinate or a format assumed instead of measured.

1. THE SHEET NAME IS THE DATE AUTHORITY, not `r4c8`. That cell holds
   2026-12-31 on a sheet named `12-31-2025`, and 36 of 689 sheets disagree with
   their own name. Where they disagree it is reported, never silently preferred.

2. A MONTH NAME IS NOT THREE LETTERS. The first version matched
   `^([A-Z][a-z]{2})\\s` and so discarded every `July`, `June` and `March`
   sheet — 48 of them — plus the typo `Marc` and the lowercase `oct`. Months
   are matched on their first three letters, case-folded: prefix matching, not
   typo correction, so `Master` and `Dummy` still fail.

3. `.N` APPEARS ON EITHER SIDE OF THE YEAR. `Oct 13.2-2018` and
   `Nov 9-2018.2` are both "the second treatment that day", and the first
   version recognised only the former — which discarded eight of the eleven
   second-treatment sheets, the exact set that decides how many days held two
   treatments. (Measured in the record: 54 of 77 multi-session days are
   genuinely two treatments, a morning one and an overnight one.)

4. A DOTTED NUMBER ABOVE `MAX_SEQUENCE` IS A SECOND DAY, NOT A SEQUENCE.
   `Sep 17.18-2017` covers Sept 17 AND 18; read as a sequence it became
   "treatment 18".

5. THE VALUE IS NOT AT A FIXED OFFSET FROM ITS LABEL. `Start Time` is at
   r24c19 on the 2018+ sheets and r24c22 on the 2017 ones. `Total Time`'s value
   sits at r52c3 — two columns RIGHT, same row — on 646 sheets and directly
   below the label on 7. Reading one offset found 7 machine times out of 653.
   So the value is sought in the region between a label and the next label in
   its row, plus the cell directly beneath, and when two candidates both parse
   and disagree that is reported rather than resolved.

6. `1900-03-05T04:48:00` IS NOT A TIME. It sits in the start cell of EIGHTEEN
   2017-18 sheets, identically — a template copy-paste artifact, an Excel
   serial of ~65.2 days whose fractional part renders as 04:48. An earlier pass
   wrote it as a real 04:48 start on all 18. But `1900-01-01T00:45` IS a real
   time: a time-only cell legitimately carries the epoch date. So the EPOCH DAY
   is the test, not the year.

7. ONLY A FOUR-DIGIT INTEGER IS MILITARY TIME. `1254` is unambiguously 12:54.
   `10` is not 00:10 — it is as likely 10:00 — and `103` is not 01:03. Both are
   refused (CLAUDE.md 0: never guess).

8. A COMMA CAN BE A DECIMAL POINT. `'62,8'` stripped of commas became 628.0 L
   of dialysate against a median of 41. One comma followed by one or two digits
   is a decimal separator.

9. `Bleeding Stop Time` IS NOT THE END OF TREATMENT. Haemostasis after needle
   removal is a different observation, so that label is deliberately not read.

Nothing is repaired silently: every value that needed interpreting, and every
value refused, is listed in the JSON under `notes` so the backfill and the
operator can both see it.
"""

from __future__ import annotations

import argparse
import collections
import datetime
import json
import pathlib
import re
import sys

try:
    import openpyxl
except ModuleNotFoundError:  # pragma: no cover - environment, not logic
    sys.exit("openpyxl is required: run with ML/.venv-health-ml/bin/python")

#: The operator's workbooks, at the paths the flowsheet importer already uses.
#: `FlowsheetGermantown.xlsx` (2019-2022) is ABSENT from this machine, which is
#: why 43 of the 54 two-treatment days have no sheet at all.
BOOKS: dict[str, str] = {
    "Flowsheets(2017-18)": "/Users/woleakpose/Developer/WellnessScore/Flowsheets.xlsx",
    "2023FlowSheets-ex": "/Users/woleakpose/Documents/2023FlowSheets-ex.xlsx",
    "2024FlowSheets": "/Users/woleakpose/Developer/data/2024FlowSheets.xlsx",
    "2025FlowSheets": (
        "/Users/woleakpose/Library/Group Containers/"
        "UBF8T346G9.OneDriveStandaloneSuite/OneDrive.noindex/"
        "OneDrive/2025FlowSheets.xlsx"
    ),
}

#: Label text (case-folded) -> field name. Order is irrelevant; each is located
#: by searching for its own label.
WANT = {
    "start time": "start",
    "stop time": "stop",
    "total time": "machine",
    "total dialysate": "dialysate",
    "total uf": "total_uf",
    "total bvp": "total_bvp",
}

#: A dotted number this size or smaller is a treatment sequence (`.2` = second
#: treatment that day); larger is a second day-of-month (`Sep 17.18-2017`).
#: Nobody receives five treatments in a day, so the boundary cannot collide.
MAX_SEQUENCE = 4

#: Rows/cols searched for labels. The tallest observed sheet is 93 rows.
SCAN_ROWS, SCAN_COLS = 95, 40

#: Excel renders a time-only cell as a datetime on its epoch day. Anything
#: else in 1900 is a serial that was never a time of day (see rule 6).
EPOCH_DAYS = {
    datetime.date(1900, 1, 1),
    datetime.date(1899, 12, 31),
    datetime.date(1899, 12, 30),
}

_MONTH_BY_PREFIX = {
    m.lower(): i + 1
    for i, m in enumerate(
        ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
         "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    )
}

# 03-18-2023 | 3-18-2023 | 03-18-2023.2
_NUMERIC = re.compile(r"^(\d{1,2})-(\d{1,2})-(\d{4})(?:\.(\d+))?$")
# Nov 9-2018 | Oct 13.2-2018 | Nov 9-2018.2 | Sep 17.18-2017 | July 3-2017
_WORDED = re.compile(
    r"^([A-Za-z]{3,9})\s+(\d{1,2})(?:\.(\d+))?\s*-\s*(\d{4})(?:\.(\d+))?$"
)
# Apr 14 — a real sheet carrying no year at all
_NO_YEAR = re.compile(r"^([A-Za-z]{3,9})\s+(\d{1,2})$")
# 22:04 | 22;04 | 22.04 | 22>00  — a separator typo, reported when used
_TIME_TEXT = re.compile(r"^(\d{1,2})\s*[:;.,>]\s*(\d{2})$")
# 62,8 — a decimal comma, not a thousands separator
_DECIMAL_COMMA = re.compile(r"^(\d+),(\d{1,2})$")


def classify_sheet(name: str) -> tuple[str, datetime.date | None, int,
                                       datetime.date | None, str | None]:
    """(kind, date, sequence, also_date, detail).

    `kind` is "dated" or the reason the tab is not a session sheet. A tab that
    is not a session sheet is never a failure — the books carry `Vomit Log`,
    `Access Maintenance`, `Supplies Request`, `Dummy` and `Master` — but it is
    always reported, because an earlier version dropped 76 REAL sheets through
    this path without counting them.
    """
    text = name.strip()

    m = _NUMERIC.match(text)
    if m:
        seq = int(m.group(4)) if m.group(4) else 1
        try:
            day = datetime.date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
        except ValueError as exc:
            return "impossible_date", None, 1, None, str(exc)
        return "dated", day, seq, None, None

    m = _WORDED.match(text)
    if m:
        month = _MONTH_BY_PREFIX.get(m.group(1)[:3].lower())
        if month is None:
            return "not_a_month", None, 1, None, m.group(1)
        mid, tail = m.group(3), m.group(5)
        if mid and tail:
            return "two_dot_groups", None, 1, None, f"{mid}/{tail}"
        dotted = mid or tail
        seq, also = 1, None
        if dotted:
            value = int(dotted)
            if value <= MAX_SEQUENCE:
                seq = value
            else:
                try:
                    also = datetime.date(int(m.group(4)), month, value)
                except ValueError:
                    return "impossible_second_day", None, 1, None, dotted
        try:
            day = datetime.date(int(m.group(4)), month, int(m.group(2)))
        except ValueError as exc:
            return "impossible_date", None, 1, None, str(exc)
        return "dated", day, seq, also, None

    m = _NO_YEAR.match(text)
    if m and _MONTH_BY_PREFIX.get(m.group(1)[:3].lower()):
        return "no_year_in_name", None, 1, None, text

    return "not_a_session_sheet", None, 1, None, text


def read_time(value) -> tuple[datetime.time | None, str | None]:
    """A time of day, or None. The note records any interpretation applied."""
    if value is None:
        return None, None
    if isinstance(value, datetime.time):
        return value, None
    if isinstance(value, datetime.datetime):
        if value.date() in EPOCH_DAYS:
            return value.time(), f"epoch_cell:{value.time()}"
        if value.year < 1910:
            return None, f"REFUSED_excel_serial_not_a_time:{value.isoformat()}"
        return value.time(), None
    if isinstance(value, (int, float)):
        n = int(value)
        if 1000 <= n <= 2359 and n % 100 < 60:
            return datetime.time(n // 100, n % 100), f"four_digit_integer:{n}"
        return None, f"REFUSED_ambiguous_integer:{value}"
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None, None
        m = _TIME_TEXT.match(text)
        if m and int(m.group(1)) < 24 and int(m.group(2)) < 60:
            return (datetime.time(int(m.group(1)), int(m.group(2))),
                    f"separator_typo:{text!r}")
        return None, f"REFUSED_text:{text!r}"
    return None, f"REFUSED_type:{type(value).__name__}"


def read_duration_minutes(value) -> tuple[int | None, str | None]:
    """`Total Time` as MINUTES. `3:11` is 3 h 11 m on dialysis, not 3.11."""
    if value is None:
        return None, None
    if isinstance(value, datetime.time):
        return value.hour * 60 + value.minute, None
    if isinstance(value, datetime.datetime):
        if value.date() in EPOCH_DAYS:
            return value.hour * 60 + value.minute, None
        return None, f"REFUSED_excel_serial:{value.isoformat()}"
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None, None
        m = _TIME_TEXT.match(text)
        if m:
            return (int(m.group(1)) * 60 + int(m.group(2)),
                    f"duration_from_text:{text!r}")
        return None, f"REFUSED_text:{text!r}"
    if isinstance(value, (int, float)):
        # 3.26 could be 3 h 26 m or 3.26 h. Never guessed.
        return None, f"REFUSED_ambiguous_number:{value}"
    return None, None


def read_number(value) -> tuple[float | None, str | None]:
    """A litre figure. A single comma before one or two digits is a DECIMAL."""
    if value is None:
        return None, None
    if isinstance(value, bool):
        return None, f"REFUSED_boolean:{value}"
    if isinstance(value, (int, float)):
        return float(value), None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None, None
        m = _DECIMAL_COMMA.match(text)
        if m:
            return float(f"{m.group(1)}.{m.group(2)}"), f"decimal_comma:{text!r}"
        try:
            return float(text), f"number_from_text:{text!r}"
        except ValueError:
            return None, f"REFUSED_text:{text!r}"
    return None, None


def value_cells(row: int, col: int, label_cols: list[int]) -> list[tuple[int, int]]:
    """Cells that may hold this label's value: the region to its right in the
    same row, stopping at the next label, plus the cell directly beneath."""
    later = [c for c in label_cols if c > col]
    stop = min(later) if later else col + 5
    cells = [(row, c) for c in range(col + 1, min(stop, col + 5))]
    cells.append((row + 1, col))
    return cells


def extract_sheet(ws, book: str, name: str, day: datetime.date, seq: int,
                  also: datetime.date | None, notes: list[dict]) -> dict | None:
    """One sheet -> one row, or None when it carries no clock labels at all."""
    label_cols: dict[int, list[int]] = {}
    found: dict[str, tuple[int, int]] = {}
    for row in ws.iter_rows(min_row=1, max_row=SCAN_ROWS, max_col=SCAN_COLS):
        for cell in row:
            if not isinstance(cell.value, str):
                continue
            label_cols.setdefault(cell.row, []).append(cell.column)
            key = WANT.get(cell.value.strip().lower())
            if key and key not in found:
                found[key] = (cell.row, cell.column)

    if "start" not in found and "stop" not in found:
        notes.append({"book": book, "sheet": name, "field": "-",
                      "at": "-", "note": "REFUSED_no_start_or_stop_label"})
        return None

    values: dict[str, object] = {}
    for key, (row, col) in found.items():
        reader = (read_time if key in ("start", "stop")
                  else read_duration_minutes if key == "machine"
                  else read_number)
        hits = []
        for (rr, cc) in value_cells(row, col, label_cols.get(row, [])):
            parsed, note = reader(ws.cell(rr, cc).value)
            if parsed is not None:
                hits.append((parsed, note, f"r{rr}c{cc}"))
            elif note:
                notes.append({"book": book, "sheet": name, "field": key,
                              "at": f"r{rr}c{cc}", "note": note})
        if not hits:
            values[key] = None
            continue
        values[key] = hits[0][0]
        if hits[0][1]:
            notes.append({"book": book, "sheet": name, "field": key,
                          "at": hits[0][2], "note": hits[0][1]})
        if len({h[0] for h in hits}) > 1:
            notes.append({
                "book": book, "sheet": name, "field": key, "at": hits[0][2],
                "note": "REFUSED_two_candidates_disagree:"
                        + str([(str(h[0]), h[2]) for h in hits]),
            })

    cell_raw = ws.cell(4, 8).value
    cell_day = (cell_raw.date().isoformat()
                if isinstance(cell_raw, datetime.datetime) else None)
    start = values.get("start")
    stop = values.get("stop")
    return {
        "book": book,
        "sheet": name,
        "date": day.isoformat(),
        "sequence": seq,
        "also_date": also.isoformat() if also else None,
        "start": start.strftime("%H:%M:%S") if start else None,
        "stop": stop.strftime("%H:%M:%S") if stop else None,
        "machine_minutes": values.get("machine"),
        "total_dialysate_liters": values.get("dialysate"),
        "total_uf_liters": values.get("total_uf"),
        "total_blood_volume_processed": values.get("total_bvp"),
        "label_cells": {k: f"r{v[0]}c{v[1]}" for k, v in found.items()},
        "cell_date": cell_day,
        "cell_date_disagrees": bool(cell_day and cell_day != day.isoformat()),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True, help="path for the JSON output")
    ap.add_argument("--book", action="append", default=None,
                    help="limit to one book by label (repeatable)")
    args = ap.parse_args()

    rows: list[dict] = []
    notes: list[dict] = []
    skipped: dict[str, list[str]] = collections.defaultdict(list)
    per_book: dict[str, dict] = {}

    for book, path in BOOKS.items():
        if args.book and book not in args.book:
            continue
        p = pathlib.Path(path)
        if not p.is_file():
            per_book[book] = {"error": "absent", "path": path}
            print(f"  {book:22s} ABSENT at {path}", file=sys.stderr)
            continue
        wb = openpyxl.load_workbook(p, read_only=True, data_only=True)
        dated = 0
        for name in wb.sheetnames:
            kind, day, seq, also, detail = classify_sheet(name)
            if kind != "dated":
                skipped[kind].append(f"{book}:{name!r}"
                                     + (f" ({detail})" if detail else ""))
                continue
            row = extract_sheet(wb[name], book, name, day, seq, also, notes)
            if row is not None:
                rows.append(row)
                dated += 1
        wb.close()
        per_book[book] = {"dated_sheets": dated, "tabs": len(wb.sheetnames)}
        print(f"  {book:22s} {per_book[book]}", file=sys.stderr)

    def have(field: str) -> int:
        return sum(1 for r in rows if r.get(field) is not None)

    print(f"\n  sheets           : {len(rows)}", file=sys.stderr)
    for field in ("start", "stop", "machine_minutes", "total_uf_liters",
                  "total_dialysate_liters", "total_blood_volume_processed"):
        print(f"  with {field:<30}: {have(field)}", file=sys.stderr)
    refused = [n for n in notes if n["note"].startswith("REFUSED")]
    print(f"\n  values REFUSED        : {len(refused)}", file=sys.stderr)
    print(f"  values interpreted    : {len(notes) - len(refused)}", file=sys.stderr)
    print(f"  name/r4c8 disagreement: "
          f"{sum(1 for r in rows if r['cell_date_disagrees'])}", file=sys.stderr)
    print(f"  tabs skipped          : "
          f"{ {k: len(v) for k, v in skipped.items()} }", file=sys.stderr)
    for kind, names in sorted(skipped.items()):
        for nm in names:
            print(f"      {kind}: {nm}", file=sys.stderr)
    for note in refused:
        print(f"      REFUSED {note['sheet']!r:22} {note['field']:<12} "
              f"{note['at']:<8} {note['note']}", file=sys.stderr)

    out = {
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "books": per_book,
        "sheets": rows,
        "notes": notes,
        "skipped_tabs": dict(skipped),
    }
    dest = pathlib.Path(args.out)
    dest.write_text(json.dumps(out, indent=1))
    print(f"\n  wrote {dest} ({len(rows)} sheets, {len(notes)} notes)",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
