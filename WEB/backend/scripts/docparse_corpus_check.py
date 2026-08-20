#!/usr/bin/env python3
"""Regression harness: run the geometry parser over a corpus of real PDFs.

Not part of CI. It reads `ML/data/raw/pdf/`, which is gitignored because it
holds real patient records (named individual, DOB, MPI). Run it locally when
touching `docparse.layout` or `docparse.normalize`.

The number that matters is *reference-range recovery*. The previous
regex-over-reflowed-text extractor lost 489 of 853 ranges (43%), and three of
the thirteen PDFs lost every single one, because a range printed beside a row
lands on a different line once the text is reflowed.

    python3 scripts/docparse_corpus_check.py
    python3 scripts/docparse_corpus_check.py --baseline ../../ML/data/raw/pdf/pdf_labs_extracted.csv
"""

from __future__ import annotations

import argparse
import csv
import pathlib
import sys
from collections import defaultdict

BACKEND = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from app.services.docparse.extract import extract          # noqa: E402
from app.services.docparse.layout import parse_document    # noqa: E402
from app.services.docparse import layout_matrix            # noqa: E402

DEFAULT_CORPUS = BACKEND.parent.parent / "ML" / "data" / "raw" / "pdf"


RANGE_RE = __import__("re").compile(r"\d+\.?\d*\s*[-–]\s*\d+\.?\d*")


class _EMPTY:
    """Stand-in so a page with no matrix contributes no cells."""

    cells: list = []


def analyse(pdf: pathlib.Path) -> dict:
    doc = extract(pdf.read_bytes(), pdf.name)
    if not doc.usable:
        return {
            "file": pdf.name,
            "status": doc.extraction_method,
            "detail": doc.error_detail,
            "rows": 0,
            "ranged": set(),
        }

    rows = [row for table in parse_document(doc) for row in table.rows]

    if not rows:
        # No labelled-column table. Try the trend-matrix shape (analyte × period)
        # before calling the document unparseable.
        cells = [c for page in doc.pages for c in (layout_matrix.parse_page(page) or _EMPTY).cells]
        if cells:
            return {
                "file": pdf.name,
                "status": "matrix",
                "detail": f"{len({c.analyte for c in cells})} analytes × "
                          f"{len({c.period for c in cells})} periods",
                "rows": len(cells),
                "ranged": set(),
            }

    return {
        "file": pdf.name,
        "status": doc.extraction_method,
        "detail": None,
        "rows": len(rows),
        # Keyed on the report's own test code so the two extractors can be
        # compared row-for-row without hand-labelling anything.
        "ranged": {
            (pdf.name, r.get("code"))
            for r in rows
            if r.get("code") and RANGE_RE.search(r.get("ref_range"))
        },
    }


def load_baseline(path: pathlib.Path) -> tuple[dict[str, int], set[tuple[str, str]]]:
    """Old extractor's (rows per file, {(file, code) that carried a range})."""
    if not path.exists():
        return {}, set()
    totals: dict[str, int] = defaultdict(int)
    ranged: set[tuple[str, str]] = set()
    with path.open() as fh:
        for record in csv.DictReader(fh):
            name = record["source_file"]
            totals[name] += 1
            code = (record.get("code") or "").strip()
            # The old CSV wrote codes as floats ("1051.0").
            code = code[:-2] if code.endswith(".0") else code
            if (record.get("ref_low") or "").strip() and code:
                ranged.add((name, code))
    return dict(totals), ranged


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=pathlib.Path, default=DEFAULT_CORPUS)
    parser.add_argument("--baseline", type=pathlib.Path, default=DEFAULT_CORPUS / "pdf_labs_extracted.csv")
    parser.add_argument("--min-range-pct", type=float, default=95.0)
    parser.add_argument("--min-file-pct", type=float, default=90.0)
    args = parser.parse_args()

    pdfs = sorted(args.corpus.glob("*.pdf"))
    if not pdfs:
        print(f"No PDFs in {args.corpus}", file=sys.stderr)
        return 2

    base_rows, base_ranged = load_baseline(args.baseline)
    results = [analyse(p) for p in pdfs]

    # Fair denominator without hand-labelling: every (file, code) for which
    # *either* extractor recovered a range is a range the document really has.
    new_ranged: set[tuple[str, str]] = set()
    for r in results:
        new_ranged |= r["ranged"]
    union = base_ranged | new_ranged

    print(f"{'file':32s} {'rows':>5s} {'ranges':>7s}   {'old rows':>8s} {'old rng':>8s}  {'lost':>5s}")
    print("-" * 78)

    worst = 100.0
    for r in results:
        if r["status"] not in ("pdf_text", "plain_text"):
            print(f"{r['file'][:32]:32s} {'--':>5s} {'--':>7s}   {r['status']}")
            continue
        per_file_union = {k for k in union if k[0] == r["file"]}
        lost = {k for k in per_file_union if k in base_ranged and k not in r["ranged"]}
        covered = len(r["ranged"] & per_file_union)
        pct = 100.0 * covered / len(per_file_union) if per_file_union else 100.0
        old = base_rows.get(r["file"], 0)
        old_rng = len({k for k in base_ranged if k[0] == r["file"]})
        flag = f"{len(lost)}" if lost else "-"
        print(
            f"{r['file'][:32]:32s} {r['rows']:5d} {len(r['ranged']):7d}   "
            f"{old:8d} {old_rng:8d}  {flag:>5s}   {pct:5.1f}%"
        )
        worst = min(worst, pct)

    total_rows = sum(r["rows"] for r in results)
    new_cov = 100.0 * len(new_ranged & union) / len(union) if union else 0.0
    old_cov = 100.0 * len(base_ranged & union) / len(union) if union else 0.0
    regressions = base_ranged - new_ranged

    print("-" * 78)
    print(f"{'TOTAL':32s} {total_rows:5d} {len(new_ranged):7d}   "
          f"{sum(base_rows.values()):8d} {len(base_ranged):8d}")
    print()
    print(f"Ranges the document actually contains (union of both extractors): {len(union)}")
    print(f"  new parser recovers: {len(new_ranged & union):4d}  ({new_cov:.1f}%)")
    print(f"  old parser recovered:{len(base_ranged & union):4d}  ({old_cov:.1f}%)")
    print(f"  regressions (old had, new lost): {len(regressions)}")
    if regressions:
        for key in sorted(regressions)[:15]:
            print(f"    - {key[0]} code {key[1]}")

    ok = new_cov >= args.min_range_pct and not regressions
    print()
    print(
        f"{'PASS' if ok else 'FAIL'}: recovery {new_cov:.1f}% "
        f"(need {args.min_range_pct}%), regressions {len(regressions)} (need 0)"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
