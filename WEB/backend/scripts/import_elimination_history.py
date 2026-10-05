#!/usr/bin/env python3
# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""Stool and vomiting history from the workbooks, measured before it is written.

Two DIFFERENT operations, and getting them the wrong way round is the §3ab
failure that produces contradictory duplicate rows:

    bowel_movements   INSERT    1,777 rows, 2022-06-01 .. 2024-11-17
                                The table's earliest row is 2025-06-01, so the
                                workbook's range does not touch it. Overlap
                                measured as ZERO.

    vomiting_logs     ENRICH    607 rows across three Vomit Log tabs, and
                                measured overlap is 607 of 607 — every one is
                                ALREADY in the table. Nothing is inserted;
                                the structured columns are filled in on rows
                                that exist, from the sheet they came from.

**Why this exists at all.** `bowel_movements` has five writers and two of them
— `import_firestore.py:346` and `migrate_all_firebase.py:508` — insert only
`(user_id, log_date, log_time, notes, created_at)` and name no structured
column. So everything they migrated arrived as prose. Measured on the reference
record: 134 of 648 rows say "Bloody" in `notes` while `blood_present` is NULL on
all 648, and every consumer that reads the flag scores them as no blood at all.
The workbook has a dedicated `Blood?` column that was never carried across.

Likewise `vomiting_logs.time_since_last_meal_hours` is populated on 0 of 1,991
rows while `Last Meal Date`/`Last Meal Time` sit in columns H and G of the
sheet the rows came from.

**Source selection is NOT the path someone hardcoded.** `Records.xlsx` exists in
five places and they are strict supersets of each other, all starting
2022-06-01:

    Developer/data   2024-11-18   1,777 rows   415 YES   <- used
    iCloud           2024-02-14   1,155 rows   206 YES   <- import_food_bowel.py
    RecordsData      2024-08-12   1,155 rows   206 YES
    Documents        2023-03-23     493 rows    93 YES
    WellnessScore    2022-08-27     133 rows    41 YES

Taking the path the old script names would import 206 blood-positive events
instead of 417, losing more than half the finding. `--records` defaults to the
newest and prints which file it read.

**It writes no rows itself.** It reads the workbooks (which live on the host,
outside any container mount) and emits SQL. Applying is a separate, visible
step — not a flag inside a script that holds clinical data:

    python3 scripts/import_elimination_history.py --user-email you@example.com
    # read the report, then:
    docker compose exec -T db psql -U alafia -d alafia -f - < <the .sql it wrote>

Every rejected row is counted and characterised. A parser that drops what it
cannot read without saying so hides its own failure (§3av) — that is how an
earlier pass reported a confident 618 sheets having silently discarded 76.
"""

from __future__ import annotations

import argparse
import datetime
import sys
from collections import Counter
from pathlib import Path

try:
    import openpyxl
except ImportError:  # pragma: no cover - the host runs this, not the image
    raise SystemExit("openpyxl is required: pip3 install openpyxl")

#: A time-only cell legitimately carries the Excel epoch DATE. Any other 1900
#: date is the copy-paste artifact §3av documents (eighteen sheets sharing
#: 1900-03-05T04:48 to the second), so the epoch DAY is the test, not the year.
EPOCH = datetime.date(1900, 1, 1)

RECORDS_DEFAULT = "/Users/woleakpose/Developer/data/Records.xlsx"
VOMIT_BOOKS_DEFAULT = [
    "/Users/woleakpose/Documents/2023FlowSheets-ex.xlsx",
    "/Users/woleakpose/Developer/data/2024FlowSheets.xlsx",
    # The CloudStorage copy of the 2025 book is TCC-blocked (PermissionError
    # [Errno 1]); this path is the same bytes and is readable.
    "/Users/woleakpose/Library/Group Containers/UBF8T346G9.OneDriveStandaloneSuite"
    "/OneDrive.noindex/OneDrive/2025FlowSheets.xlsx",
]


def sql_str(value) -> str:
    if value is None:
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


def as_date(v):
    if isinstance(v, datetime.datetime):
        return v.date()
    return v if isinstance(v, datetime.date) else None


def as_time(v):
    if isinstance(v, datetime.time):
        return v
    if isinstance(v, datetime.datetime):
        return v.time() if v.date() == EPOCH else None
    return None


def header_map(ws, header_row: int) -> dict[str, int]:
    """Column index by header LABEL — FIRST occurrence wins.

    A fixed coordinate is an assumption, not a location (§3av), so columns are
    found by label. But on these sheets the labels REPEAT, and taking the last
    occurrence silently aimed the whole import at the wrong column:

        row 1  ('Vomit', None, 'Weight in Kg', None, None,
                'Visual Content', 'Last Meal', None, 'Last Dialyss')
        row 2  ('Date',  'Time', 'Pre', 'Post', 'Delta',
                 None,   'Time',  'Date', 'Time')

    `Date` appears at index 0 (the episode) and again at index 7 (the last
    meal); `Time` appears three times. A plain dict assignment let index 7 and
    8 win, so the generated UPDATE matched on the LAST MEAL date and the LAST
    DIALYSIS time instead of when the patient was actually sick — caught by
    reading the emitted SQL, where a row whose episode is 2023-01-01 08:00 was
    keyed `2022-12-31 04:55`.

    Only the 2024 book names its columns `VomitDate`/`VomitTime`; 2023 and 2025
    use the generic labels, so 234 of 609 statements were affected.
    """
    out: dict[str, int] = {}
    for row in ws.iter_rows(min_row=header_row, max_row=header_row, values_only=True):
        for idx, cell in enumerate(row):
            if cell is None:
                continue
            out.setdefault(str(cell).strip().lower(), idx)
    return out


def grouped_header(ws) -> dict[str, int]:
    """`{"<group> <field>": index}` for a TWO-ROW header.

    Row 1 names a group and spans several columns; row 2 names the field. The
    group is forward-filled across its span, so `Last Meal`+`Date` becomes
    "last meal date" and is reachable without colliding with the episode's own
    `Date`. This is what disambiguates a sheet that uses one word three times.
    """
    rows = [r for i, r in enumerate(ws.iter_rows(values_only=True)) if i < 2]
    if len(rows) < 2:
        return {}
    groups, current = [], ""
    for cell in rows[0]:
        if cell is not None and str(cell).strip():
            current = str(cell).strip().lower()
        groups.append(current)
    out: dict[str, int] = {}
    for idx, field in enumerate(rows[1]):
        if field is None or not str(field).strip():
            continue
        grp = groups[idx] if idx < len(groups) else ""
        out.setdefault(f"{grp} {str(field).strip().lower()}".strip(), idx)
    return out


def pick(cols: dict[str, int], *names: str) -> int | None:
    for n in names:
        if n in cols:
            return cols[n]
    return None


# ── Stool: rows that are genuinely absent ────────────────────────────────────

def read_poop(path: str) -> tuple[list[dict], Counter]:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb["Poop Log"]
    cols = header_map(ws, 1)
    c_date = pick(cols, "date") or 0
    c_time = pick(cols, "time") or 1
    c_meal = pick(cols, "last meal")
    c_blood = pick(cols, "blood?", "blood")
    c_notes = pick(cols, "notes")

    kept: list[dict] = []
    rej: Counter = Counter()
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not any(x is not None for x in row):
            rej["blank row"] += 1
            continue
        d = as_date(row[c_date] if c_date < len(row) else None)
        if d is None:
            rej[f"date unreadable ({type(row[c_date]).__name__})"] += 1
            continue
        # A missing time stays MISSING. Defaulting it to 00:00 writes a real
        # instant the sheet never recorded — §3av measured exactly this on
        # `intradialytic_readings`, where 3,662 rows read 00:00 because an
        # import defaulted a lost timestamp and every window built on them was
        # wrong. Worse here, it also collapses the dedupe key: the first run
        # found three dates carrying two untimed rows each, and on 2024-03-12
        # those were one blood-positive and one blood-negative event. The
        # positive survived only because it came first in the sheet.
        t = as_time(row[c_time] if c_time < len(row) else None)

        raw_blood = row[c_blood] if c_blood is not None and c_blood < len(row) else None
        blood_txt = (str(raw_blood).strip().upper() if raw_blood is not None else "")
        # YES and TRACE are both blood. A BLANK cell is NOT a negative finding —
        # it is no finding, and recording it as False would assert something the
        # sheet never said.
        if blood_txt in ("YES", "Y", "TRUE", "1", "TRACE"):
            blood = True
        elif blood_txt in ("NO", "N", "FALSE", "0"):
            blood = False
        else:
            blood = None

        note_parts = []
        meal = as_time(row[c_meal]) if c_meal is not None and c_meal < len(row) else None
        if meal:
            note_parts.append(f"Last meal: {meal.strftime('%H:%M')}")
        raw_note = row[c_notes] if c_notes is not None and c_notes < len(row) else None
        if raw_note not in (None, ""):
            note_parts.append(str(raw_note).strip())
        if blood_txt == "TRACE":
            note_parts.append("Blood: trace")

        kept.append({
            "date": d, "time": t, "blood": blood,
            "notes": "; ".join(note_parts) or None,
        })
    wb.close()
    return kept, rej


# ── Vomiting: rows that already exist and are missing their columns ──────────

def read_vomit(path: str) -> tuple[list[dict], Counter]:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    tab = next((s for s in wb.sheetnames if "vomit" in s.lower()), None)
    if tab is None:
        wb.close()
        return [], Counter({"no vomit tab in this book": 1})
    ws = wb[tab]
    # Two sources, deliberately. `grouped` joins the group row to the field row
    # ("last meal date"), which is the ONLY thing that separates the episode's
    # own Date from the last meal's on the 2023 and 2025 sheets — both of which
    # label three different columns `Time` and two of them `Date`. `flat` is
    # first-wins and serves the 2024 sheet, which names its fields outright.
    grouped = grouped_header(ws)
    flat = header_map(ws, 2)

    def col(*names, default=None):
        for n in names:
            if n in grouped:
                return grouped[n]
            if n in flat:
                return flat[n]
        return default

    c_date = col("vomit date", "vomitdate", "date", default=0)
    c_time = col("vomit time", "vomittime", "time", default=1)
    c_pre = col("weight in kg pre", "preweight", "pre")
    c_post = col("weight in kg post", "postweight", "post")
    c_meal_t = col("last meal time", "lastmealtime")
    c_meal_d = col("last meal date", "lastmealdate")
    c_visual = col("visual content")
    if c_visual is None:
        c_visual = pick(header_map(ws, 1), "visual content")

    # Printed so the mapping is auditable. The first version of this reader
    # resolved c_date to 7 and c_time to 8 — the last meal's date and the last
    # dialysis time — and said nothing, so every statement it produced was
    # keyed on the wrong instant. A scan is evidence only once it is shown to
    # see what it claims to (§3av).
    print(f"      columns: date={c_date} time={c_time} pre={c_pre} post={c_post} "
          f"meal_time={c_meal_t} meal_date={c_meal_d} visual={c_visual}")
    if c_date != 0 or c_time != 1:
        print(f"      ⚠ REFUSING this sheet: the episode date/time resolved to "
              f"({c_date}, {c_time}), not (0, 1). Mapping the wrong column is "
              "how an import writes one episode's values onto another.")
        wb.close()
        return [], Counter({"header mapping refused": 1})

    kept: list[dict] = []
    rej: Counter = Counter()
    for row in ws.iter_rows(min_row=3, values_only=True):
        if not any(x is not None for x in row):
            rej["blank row"] += 1
            continue
        raw_d = row[c_date] if c_date < len(row) else None
        if isinstance(raw_d, str):
            # 'Maximum', 'Minimum', 'Mean', 'STD Deviation' — summary rows the
            # sheet appends under the data.
            rej["summary row"] += 1
            continue
        d = as_date(raw_d)
        if d is None:
            rej[f"date unreadable ({type(raw_d).__name__})"] += 1
            continue
        t = as_time(row[c_time] if c_time < len(row) else None)
        if t is None:
            rej[f"time unreadable ({type(row[c_time]).__name__})"] += 1
            continue

        def num(idx):
            if idx is None or idx >= len(row):
                return None
            v = row[idx]
            return float(v) if isinstance(v, (int, float)) else None

        visual = None
        if c_visual is not None and c_visual < len(row) and row[c_visual] not in (None, ""):
            visual = str(row[c_visual]).strip()

        # Hours between the last meal and the episode. The sheet carries both
        # halves; the column has been NULL on every one of 1,991 rows.
        gap = None
        mt = as_time(row[c_meal_t]) if c_meal_t is not None and c_meal_t < len(row) else None
        md = as_date(row[c_meal_d]) if c_meal_d is not None and c_meal_d < len(row) else None
        if mt is not None:
            meal_day = md or d
            delta = (datetime.datetime.combine(d, t)
                     - datetime.datetime.combine(meal_day, mt))
            hours = delta.total_seconds() / 3600.0
            # A meal recorded AFTER the episode means the sheet's date column
            # disagrees with its time column; reporting a negative gap would be
            # inventing precision. Withheld rather than repaired (§3ab).
            if 0 <= hours <= 48:
                gap = round(hours, 2)

        kept.append({
            "date": d, "time": t, "pre": num(c_pre), "post": num(c_post),
            "visual": visual, "gap": gap,
        })
    wb.close()
    return kept, rej


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--user-email", required=True,
                    help="the patient these rows belong to, resolved by EMAIL "
                         "because row ids shift with every restore")
    ap.add_argument("--records", default=RECORDS_DEFAULT)
    ap.add_argument("--vomit-book", action="append", default=None)
    ap.add_argument("--out", default="/tmp/elimination_history.sql")
    args = ap.parse_args()
    books = args.vomit_book or VOMIT_BOOKS_DEFAULT

    print("=" * 72)
    print("ELIMINATION HISTORY — report first, SQL second, nothing written here")
    print("=" * 72)

    poop, poop_rej = read_poop(args.records)
    blood_yes = sum(1 for r in poop if r["blood"] is True)
    blood_no = sum(1 for r in poop if r["blood"] is False)
    blood_unk = sum(1 for r in poop if r["blood"] is None)
    print(f"\nSTOOL  {args.records}")
    print(f"  parsed {len(poop)} rows, rejected {sum(poop_rej.values())}")
    for k, v in poop_rej.most_common():
        print(f"      {v:5}  {k}")
    if poop:
        print(f"  span {min(r['date'] for r in poop)} .. {max(r['date'] for r in poop)}")
    print(f"  blood: yes {blood_yes} | no {blood_no} | not stated {blood_unk}")

    vomit: list[dict] = []
    print("\nVOMITING  (enrichment only — every measured row already exists)")
    for book in books:
        if not Path(book).exists():
            print(f"  MISSING {book}")
            continue
        rows, rej = read_vomit(book)
        vomit.extend(rows)
        print(f"  {Path(book).name:26} parsed {len(rows):5} rejected {sum(rej.values()):5}")
        for k, v in rej.most_common():
            print(f"      {v:5}  {k}")
    with_gap = sum(1 for r in vomit if r["gap"] is not None)
    with_wt = sum(1 for r in vomit if r["pre"] is not None or r["post"] is not None)
    print(f"  total {len(vomit)} | meal-gap computable {with_gap} | weights {with_wt}")

    # ── SQL ──────────────────────────────────────────────────────────────
    out = Path(args.out)
    lines: list[str] = [
        "-- Generated by scripts/import_elimination_history.py — review before applying.",
        "BEGIN;",
        "\\set ON_ERROR_STOP on",
        f"CREATE TEMP TABLE _target AS SELECT id FROM users WHERE lower(email)=lower({sql_str(args.user_email)});",
        "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM _target) THEN "
        "RAISE EXCEPTION 'no user with that email in this database'; END IF; END $$;",
        "",
        "-- STOOL: insert only where (log_date, log_time) is absent for this user.",
    ]
    # Two untimed events on one day are two events. A `(date, time)` key cannot
    # express that once the time is NULL, so untimed rows are counted per date
    # and the guard admits the Nth only while fewer than N exist. That is
    # idempotent on a re-run AND keeps both rows — which the first version did
    # not: it silently dropped the second of three such pairs.
    untimed_seen: Counter = Counter()
    for r in poop:
        blood = "NULL" if r["blood"] is None else ("true" if r["blood"] else "false")
        if r["time"] is None:
            untimed_seen[r["date"]] += 1
            nth = untimed_seen[r["date"]]
            guard = (
                "WHERE (SELECT count(*) FROM bowel_movements b "
                "WHERE b.user_id=(SELECT id FROM _target) "
                f"AND b.log_date='{r['date']}'::date AND b.log_time IS NULL) < {nth}"
            )
            time_sql = "NULL"
        else:
            guard = (
                "WHERE NOT EXISTS (SELECT 1 FROM bowel_movements b "
                "WHERE b.user_id=(SELECT id FROM _target) "
                f"AND b.log_date='{r['date']}'::date AND b.log_time='{r['time']}'::time)"
            )
            time_sql = f"'{r['time']}'::time"
        lines.append(
            "INSERT INTO bowel_movements (user_id, log_date, log_time, blood_present, notes, created_at) "
            f"SELECT (SELECT id FROM _target), '{r['date']}'::date, {time_sql}, "
            f"{blood}, {sql_str(r['notes'])}, NOW() " + guard + ";"
        )

    lines += ["", "-- VOMITING: fill gaps on rows that already exist. COALESCE everywhere,",
              "-- so a value already recorded is never replaced by one from a sheet."]
    for r in vomit:
        sets = [
            f"time_since_last_meal_hours = COALESCE(time_since_last_meal_hours, {r['gap'] if r['gap'] is not None else 'NULL'})",
            f"pre_event_weight_kg = COALESCE(pre_event_weight_kg, {r['pre'] if r['pre'] is not None else 'NULL'})",
            f"post_event_weight_kg = COALESCE(post_event_weight_kg, {r['post'] if r['post'] is not None else 'NULL'})",
        ]
        if r["visual"]:
            low = r["visual"].lower()
            if "blood" in low and "no blood" not in low:
                sets.append("contains_blood = COALESCE(contains_blood, true)")
            if "bile" in low:
                sets.append("contains_bile = COALESCE(contains_bile, true)")
            sets.append(f"notes = COALESCE(NULLIF(notes,''), {sql_str(r['visual'])})")
        lines.append(
            "UPDATE vomiting_logs SET " + ", ".join(sets) +
            " WHERE user_id=(SELECT id FROM _target) "
            f"AND log_date='{r['date']}'::date AND log_time='{r['time']}'::time;"
        )

    lines += ["", "COMMIT;"]
    out.write_text("\n".join(lines) + "\n")
    print(f"\nSQL written to {out}  ({len(lines)} statements incl. preamble)")
    print("NOTHING HAS BEEN WRITTEN. To apply, review the file then run:")
    print(f"  docker compose exec -T db psql -U alafia -d alafia -v ON_ERROR_STOP=1 -f - < {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
