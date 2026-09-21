"""Import the ten-year lab corpus the application database has never seen.

`ML/data/processed/unified_labs.csv` holds 9,660 results spanning 2016-2026.
`lab_results` holds 887. Every fitted coefficient this project has -- urea,
phosphorus, potassium, calcium, magnesium -- was produced by reading that CSV
directly, because nothing ever loaded it into the database. So the runtime can
serve a decade of history to a chart, a model or a clinician only for the
handful of analytes somebody exported by hand.

Measured, not assumed: 8,997 of the CSV's (date, analyte) pairs are absent from
the database and 619 are already present.

WHY THE COMPARISON IS ON THE ANALYTE, NOT THE NAME
--------------------------------------------------
Comparing raw `test_name` reports 9,064 new pairs; comparing
`docparse.dictionaries.analyte_key` reports 8,997. The 67-row difference is the
same analyte under two spellings -- "FERR"/"Ferritin", "PTH-I"/"PTH (Intact)" --
which a raw comparison would write a second time, beside the row it duplicates.
That is exactly the contradictory duplicate §3ab describes, and `lab_results`
has NO unique constraint (primary key and two plain indexes only), so the
database will not catch it. Dedupe here is the only dedupe there is.

WHAT IS REFUSED, AND WHY EACH ONE
---------------------------------
- **Spreadsheet errors.** 76 rows carry `#DIV/0!`. A failed formula is not a
  result, and one of them sits on a date where the same analyte also has a real
  value.
- **Rows with no value at all** (68: nPCR, Kt/V variants, Hep B Ag). A row with
  neither a number nor a word is not a measurement, and writing it as NULL
  would render as a test that was run and came back blank.
- **Conflicting same-day duplicates** (26 pairs, 52 rows). The source states two
  different values for one analyte on one date -- `hemoglobin 5.3 vs 7.7`,
  `creatinine 20.2 vs 9.2`, `CO2 22.0 vs 2.0` -- and every one is
  `records_xlsx` disagreeing with itself. Choosing between them would be
  inventing a fact; both are dropped and listed. The 2 pairs that AGREE
  (`pdf_davita` and `firestore` on the same A1c) collapse to one row.

WHAT IS KEPT THAT LOOKS WRONG
-----------------------------
- **Qualitative results** -- "NEG", "Nonreactive", ">1000", "<10", "1+" -- go to
  `value_string`, never coerced to a number. A censored ">1000" forced to 1000
  is a fabricated measurement.
- **Zeros** (57 rows, 38 of them `HCT CALC (HBGX3)`). A calculated haematocrit
  of 0.0 is almost certainly a failed calculation, but a basophil count of 0.0
  is a real result. Telling them apart needs per-analyte plausibility bands,
  and hand-writing those is what §3aj forbids. They are imported and counted in
  the report so a human can look.

One value IS worth a human's attention and the report names it: PTH-I 8,478
pg/mL on 2025-02-11, against 14 the following month.

Usage -- dry run is the default and prints what it WOULD do:

    docker compose --profile test run --rm \
      -e DATABASE_URL=postgresql+asyncpg://alafia:alafia@db:5432/alafia \
      backend-test python scripts/import_unified_labs.py --email <address>

    ... then --apply to write.
"""

from __future__ import annotations

import argparse
import asyncio
import collections
import csv
import datetime
import logging
import pathlib
import sys

from sqlalchemy import select

from app.core.database import async_session
from app.models.labs import LabResult
from app.models.user import User
from app.services.docparse.dictionaries import analyte_key

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("import_unified_labs")

#: Where the corpus lives, in order. The container mounts the ML tree at /ml
#: and the script sits at /app/scripts, so a repo-relative walk has nowhere to
#: go there — computing these eagerly raised IndexError at IMPORT time and took
#: the whole script down before the path that does exist was ever tried.
def _candidate_paths() -> list[pathlib.Path]:
    here = pathlib.Path(__file__).resolve()
    paths = [pathlib.Path("/ml/data/processed/unified_labs.csv")]
    if len(here.parents) > 3:
        paths.append(here.parents[3] / "ML/data/processed/unified_labs.csv")
    return paths

#: A failed formula is not a result. These reach the value column as text.
_SPREADSHEET_ERRORS = {
    "#div/0!", "#value!", "#ref!", "#n/a", "#name?", "#null!", "#num!",
}

#: `flag` carries L or H. Either means the lab marked it out of range; an ABSENT
#: flag means the lab said nothing, which is not the same as "normal" (§3aa).
_ABNORMAL_FLAGS = {"l", "h", "ll", "hh", "a"}

#: Rows per transaction.
#:
#: Committing all 8,853 at once produced a single insertmany of ~233 KB with
#: 13,500+ bound parameters, and the Cloud SQL proxy dropped the connection
#: mid-statement: "connection was closed in the middle of operation". Nothing
#: was written — verified against production afterwards, 887 rows before and
#: 887 after, zero rows carrying this script's provenance marker.
#:
#: Batching trades atomicity for resumability, and that is the right way round
#: here: dedupe is on (date, analyte), so a run that stops halfway can simply
#: be run again and whatever landed is skipped. An all-or-nothing transaction
#: of that size is precisely what failed.
_COMMIT_BATCH = 500


def _find_csv(explicit: pathlib.Path | None) -> pathlib.Path:
    if explicit:
        if not explicit.exists():
            sys.exit(f"No such file: {explicit}")
        return explicit
    for candidate in _candidate_paths():
        if candidate.exists():
            return candidate
    sys.exit("Could not find unified_labs.csv; pass --csv")


def _as_float(raw: str | None) -> float | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


class Row:
    """One CSV line, classified once so the report and the write agree."""

    __slots__ = ("day", "name", "key", "value", "value_string", "unit",
                 "ref_low", "ref_high", "abnormal", "lab", "provenance", "reason")

    def __init__(self, raw: dict):
        self.reason: str | None = None
        self.value: float | None = None
        self.value_string: str | None = None

        stamp = (raw.get("date") or "")[:10]
        try:
            self.day = datetime.date.fromisoformat(stamp)
        except ValueError:
            self.day = None
            self.reason = "unreadable date"

        self.name = (raw.get("test_name") or "").strip()[:255]
        self.key = analyte_key(self.name) if self.name else ""
        if not self.name:
            self.reason = self.reason or "no test name"

        numeric = _as_float(raw.get("value_numeric"))
        text = (raw.get("value_text") or "").strip()
        if numeric is not None:
            self.value = numeric
        elif text and text.lower() in _SPREADSHEET_ERRORS:
            self.reason = self.reason or "spreadsheet error"
        elif text:
            # Qualitative or censored. Kept as written: ">1000" coerced to 1000
            # would be a number nobody measured.
            self.value_string = text[:255]
        else:
            self.reason = self.reason or "no value"

        self.unit = ((raw.get("unit") or "").strip() or None)
        if self.unit:
            self.unit = self.unit[:50]
        self.ref_low = _as_float(raw.get("ref_low"))
        self.ref_high = _as_float(raw.get("ref_high"))

        flag = (raw.get("flag") or "").strip().lower()
        self.abnormal = True if flag in _ABNORMAL_FLAGS else None

        self.lab = ((raw.get("lab_name") or "").strip() or None)
        if self.lab:
            self.lab = self.lab[:255]

        # Where this row came from, so a later reader can trace it. `code` is an
        # internal panel number (1051.0), NOT a LOINC code, so it is recorded
        # here rather than asserted in `loinc_code`.
        bits = [b for b in (
            (raw.get("source") or "").strip(),
            (raw.get("source_file") or "").strip(),
            f"code={raw.get('code').strip()}" if (raw.get("code") or "").strip() else "",
        ) if b]
        self.provenance = "imported from unified_labs.csv" + (
            " (" + "; ".join(bits) + ")" if bits else "")

    @property
    def usable(self) -> bool:
        return self.reason is None and self.day is not None and bool(self.key)

    @property
    def stated(self) -> str:
        return self.value_string if self.value is None else f"{self.value}"


def load_rows(path: pathlib.Path) -> list[Row]:
    with path.open() as handle:
        return [Row(raw) for raw in csv.DictReader(handle)]


def resolve_conflicts(rows: list[Row]) -> tuple[list[Row], list[tuple]]:
    """Collapse same-day duplicates; drop the ones that disagree.

    A source that states two values for one analyte on one date is not asserting
    a fact, and picking the first, the last or the larger would be inventing
    one. Both go, and the caller reports them.
    """
    grouped: dict[tuple, list[Row]] = collections.defaultdict(list)
    for row in rows:
        grouped[(row.day, row.key)].append(row)

    kept: list[Row] = []
    conflicts: list[tuple] = []
    for (day, key), group in grouped.items():
        if len(group) == 1:
            kept.append(group[0])
            continue
        stated = {r.stated for r in group}
        if len(stated) == 1:
            kept.append(group[0])          # the same value twice is one result
        else:
            conflicts.append((day, key, sorted(stated)))
    return kept, conflicts


async def run(email: str, path: pathlib.Path, apply: bool, limit: int | None) -> int:
    rows = load_rows(path)
    logger.info("read %d rows from %s", len(rows), path)

    refused = collections.Counter(r.reason for r in rows if r.reason)
    usable = [r for r in rows if r.usable]
    kept, conflicts = resolve_conflicts(usable)

    logger.info("")
    logger.info("REFUSED before dedupe:")
    for reason, count in refused.most_common():
        logger.info("   %-24s %d", reason, count)
    logger.info("   %-24s %d pair(s), %d row(s)", "conflicting same-day",
                len(conflicts), sum(len(c[2]) for c in conflicts))

    async with async_session() as db:
        # Resolved by email, never a literal id: hardcoding one is how clinical
        # data lands on the wrong person.
        user = (await db.execute(
            select(User).where(User.email == email))).scalar_one_or_none()
        if user is None:
            logger.error("No account for %s", email)
            return 1

        existing = (await db.execute(
            select(LabResult.test_date, LabResult.test_name).where(
                LabResult.user_id == user.id))).all()
        present = {(d, analyte_key(n)) for d, n in existing}
        logger.info("")
        logger.info("patient %s (id=%s) already holds %d lab rows, %d distinct (date, analyte)",
                    email, user.id, len(existing), len(present))

        fresh = [r for r in kept if (r.day, r.key) not in present]
        already = len(kept) - len(fresh)
        if limit is not None:
            fresh = fresh[:limit]

        logger.info("   already present, skipped : %d", already)
        logger.info("   NEW, to import           : %d", len(fresh))

        years = collections.Counter(r.day.year for r in fresh)
        logger.info("   by year: %s", dict(sorted(years.items())))
        qualitative = sum(1 for r in fresh if r.value is None)
        zeros = sum(1 for r in fresh if r.value == 0.0)
        logger.info("   qualitative (value_string): %d | zero values: %d",
                    qualitative, zeros)

        if conflicts:
            logger.info("")
            logger.info("CONFLICTING same-day values, dropped — review these:")
            for day, key, stated in sorted(conflicts)[:30]:
                logger.info("   %s  %-26s %s", day, key[:26], stated)

        # A plausibility band belongs nowhere near this script. The first
        # version flagged PTH above 5,000 pg/mL as implausible and fired on 21
        # rows — every one of them real. That series rises monotonically from a
        # 2016 median of 748 to 6,168 in 2024 across 233 values and two
        # independent sources, `PTH POST` tracks `PTH Intact` on the same dates
        # at about half the value, and Doxercalciferol starts in 2022 exactly as
        # PTH crosses 3,000. It was severe secondary hyperparathyroidism being
        # treated, and a hand-written ceiling called it noise — §3aj's rule that
        # ceilings come from an authority, not from a number someone typed.
        #
        # An importer's job is to move what the record says. Judging whether a
        # value is possible is a clinical question with an owner, and it is not
        # this script.

        if not apply:
            logger.info("")
            logger.info("dry run — nothing written. Re-run with --apply.")
            return 0

        written = 0
        for start in range(0, len(fresh), _COMMIT_BATCH):
            batch = fresh[start:start + _COMMIT_BATCH]
            for row in batch:
                db.add(LabResult(
                    user_id=user.id,
                    test_date=row.day,
                    test_name=row.name,      # as the source printed it (§3ax)
                    value=row.value,
                    value_string=row.value_string,
                    unit=row.unit,
                    reference_range_low=row.ref_low,
                    reference_range_high=row.ref_high,
                    is_abnormal=row.abnormal,
                    status="final",
                    performing_lab=row.lab,
                    notes=row.provenance,
                ))
            await db.commit()
            written += len(batch)
            # Progress is reported per batch so a run that dies partway says
            # how far it got. The previous version logged only a total, which
            # on failure printed nothing at all.
            logger.info("   committed %d/%d", written, len(fresh))

        logger.info("")
        logger.info("imported %d row(s)", written)
    return 0


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True,
                        help="the patient whose record this is")
    parser.add_argument("--csv", type=pathlib.Path, default=None)
    parser.add_argument("--apply", action="store_true",
                        help="actually write; omit for a dry run")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    return await run(args.email, _find_csv(args.csv), args.apply, args.limit)


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except Exception as exc:  # noqa: BLE001
        logger.error("import failed: %s", exc, exc_info=True)
        sys.exit(1)
