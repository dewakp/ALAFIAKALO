#!/usr/bin/env python3
"""Build app/data/loinc_core.tsv.gz from the official LOINC release.

WHY THIS EXISTS. `docparse/dictionaries.py` carries a hand-typed
`ANALYTE_NAMES` of 136 entries. Measured against production on 2026-09-30 it
recognises **136 of 411 distinct stored test names — 33.1%**. It cannot name
`ALT`, `AST`, `BILIRUBIN, TOTAL`, `Anion Gap`, `ALBUMIN/GLOBULIN RATIO` or
`BUN/CREATININE RATIO`: ordinary chemistry. A hand-written vocabulary is a list
of the spellings somebody happened to meet, which is §3ad's "never type a code
from memory" and §3aj's 23-row seed table that was wrong in both directions.

LOINC is the published authority for laboratory observations. Three of the
defects found by hand on 2026-09-30 fall out of it rather than needing
special-case code:

  * SCALE_TYP tells us urine occult blood is **Ord**, so `2+` is the value and
    storing a bare `2` is provably wrong — no hand-written result vocabulary.
  * SYSTEM separates serum glucose from urine glucose, which currently land as
    two rows both named "Glucose", indistinguishable on any chart.
  * PROPERTY and EXAMPLE_UCUM_UNITS make a haematocrit of 338.4 % impossible by
    definition, replacing the PERCENT_CEILING constant invented for it.

WHY YOU MUST DOWNLOAD THE FILE YOURSELF
---------------------------------------
LOINC is free and the licence explicitly permits redistribution (with the
copyright notice and version), BUT the download sits behind a free account at
https://loinc.org/downloads — there is no unauthenticated URL, unlike WHO's
ICD-11 Simple Tabulation which `build_icd11_catalog.py` fetches directly. No
PyPI package redistributes the table either (checked). So this script takes the
zip you downloaded; it never tries to work around the account gate.

    1. create a free account at https://loinc.org/downloads
    2. download "LOINC Table File (CSV)"  ->  Loinc_2.80.zip  (~76 MB)
    3. python scripts/build_loinc_catalog.py --zip ~/Downloads/Loinc_2.80.zip

The generated file is ~1-2 MB gzipped and ships in the image beside
`icd11_mms.tsv.gz`. Do not hand-edit it; edit this script and re-run.

WHAT IS KEPT, AND WHY NOT EVERYTHING
------------------------------------
LoincTableCore.csv carries ~100k terms and a dozen columns. We keep the six
axes plus units and status. Deactivated and discouraged terms are kept but
flagged — a report from 2016 may legitimately use a term LOINC has since
retired, and dropping it would make an old document unreadable (§3ab: an error
is not an empty state).

⚠️ LOINC does NOT own everything in this corpus. Of 411 stored names, only 150
carry a printed reference range; `BLDFLOW`, `AMPUTATE FACTOR`, `DAYS/WEEK` and
`Dialyzer KOA` are dialysis machine and prescription parameters that no lab
vocabulary covers. This catalog is the authority for OBSERVATIONS, and the
resolver must fall through gracefully for the rest rather than discarding them.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import io
import sys
import zipfile
from pathlib import Path

OUT_PATH = Path(__file__).resolve().parent.parent / "app" / "data" / "loinc_core.tsv.gz"

#: Read from `LoincTable/Loinc.csv`, NOT `LoincTableCore.csv`.
#:
#: Measured on the real 2.83 release: the core table has only 15 columns and
#: carries **no EXAMPLE_UCUM_UNITS**, so building from it would leave the units
#: half of the job undone — and units are what make a 338.4 % haematocrit
#: impossible by definition instead of by a PERCENT_CEILING somebody invented.
#: The full table has 40 columns and is the one with units, synonyms and rank.
_KEEP = (
    "LOINC_NUM",
    "COMPONENT",          # the analyte: "Hemoglobin"
    "PROPERTY",           # kind of quantity: MCnc, MFr, NFr …
    "TIME_ASPCT",         # Pt, 24H …
    "SYSTEM",             # Ser/Plas, Urine, Bld — separates the two "Glucose"
    "SCALE_TYP",          # Qn | Ord | Nom | Nar | SemiQn — "2+" legal, "2" wrong
    "METHOD_TYP",
    "CLASS",              # CHEM, HEM/BC, UA … replaces CATEGORY_RULES
    "CLASSTYPE",          # 1=lab 2=clinical 3=claims 4=survey. 69,651 are lab;
                          # this is what keeps survey instruments out, and it
                          # also sidesteps redistribution (of 7,355 terms with a
                          # third-party copyright notice, only 10 are lab).
    "SHORTNAME",
    "LONG_COMMON_NAME",
    "RELATEDNAMES2",      # the synonyms ANALYTE_NAMES was hand-rolling
    "COMMON_TEST_RANK",   # how ordinary a test is — the tiebreak that stops
                          # "Hemoglobin" resolving to one of 330 terms by luck
    "FORMULA",            # LOINC's own record of derived values
    "UNITSREQUIRED",
    "EXAMPLE_UCUM_UNITS",
    "EXTERNAL_COPYRIGHT_NOTICE",   # kept so redistribution stays auditable
    "STATUS",             # ACTIVE | TRIAL | DISCOURAGED | DEPRECATED
)


def _find_core(zf: zipfile.ZipFile) -> str:
    """The FULL table, not LoincTableCore.csv.

    Measured on 2.83: `LoincTableCore/LoincTableCore.csv` has 15 columns and
    carries no EXAMPLE_UCUM_UNITS, RELATEDNAMES2 or COMMON_TEST_RANK — the three
    fields that do the actual work (units catch an impossible percentage,
    synonyms reach "Magnessium", rank stops "Hemoglobin" resolving to a newborn
    screen). `LoincTable/Loinc.csv` has 40 columns and is the real source.

    Preferring the core file was the first version of this function and it made
    the builder refuse its own column list.
    """
    names = zf.namelist()
    for name in names:
        if name.lower().endswith("loinctable/loinc.csv"):
            return name
    for name in names:
        if name.lower().endswith("/loinc.csv") or name.lower() == "loinc.csv":
            return name
    raise SystemExit(
        "No LoincTable/Loinc.csv inside the zip.\n"
        "Expected the official 'LOINC Table File (CSV)' download — note the\n"
        "CORE file is not enough: it lacks units, synonyms and test rank."
    )


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument(
        "--zip", type=Path, required=True,
        help="the Loinc_N.NN.zip you downloaded from loinc.org/downloads "
             "(a free account is required; there is no direct URL)")
    args = ap.parse_args()

    if not args.zip.is_file():
        raise SystemExit(f"no such file: {args.zip}")

    with zipfile.ZipFile(args.zip) as zf:
        member = _find_core(zf)
        raw = zf.read(member).decode("utf-8-sig")
        version = next(
            (n.split("_")[1].rstrip(".zip") for n in [args.zip.name] if "_" in n),
            "unknown")

    reader = csv.DictReader(io.StringIO(raw))
    missing = [c for c in _KEEP if c not in (reader.fieldnames or [])]
    if missing:
        raise SystemExit(
            f"{member} is missing expected columns: {missing}\n"
            f"present: {reader.fieldnames}")

    # FILTERED to ACTIVE laboratory terms. Measured on 2.83:
    #
    #   everything                     112,405 terms   5.95 MB gz
    #   ACTIVE only                     99,737 terms   5.34 MB
    #   ACTIVE + CLASSTYPE 1 (lab)      62,148 terms   3.64 MB   <- what we ship
    #
    # CLASSTYPE 2/3/4 are clinical documents, claims attachments and survey
    # instruments (PROMIS, FACIT, InterRAI). None of them is a lab observation,
    # so none can ever match a row off a lab report — they would only add weight
    # and extra chances to mis-resolve.
    #
    # It also all but removes the redistribution question: of the 7,355 terms
    # carrying a third-party EXTERNAL_COPYRIGHT_NOTICE, only 10 are CLASSTYPE 1.
    #
    # DEPRECATED/DISCOURAGED terms are dropped too — but note the cost: a report
    # from 2016 may legitimately name a term LOINC has since retired, and such a
    # row will now fall through to its printed wording rather than resolve. That
    # is the right failure (the name is preserved either way, §3ax) but it is a
    # failure, not a no-op.
    rows = []
    skipped_status = skipped_class = 0
    for rec in reader:
        if not (rec.get("LOINC_NUM") or "").strip():
            continue
        if (rec.get("STATUS") or "").strip().upper() != "ACTIVE":
            skipped_status += 1
            continue
        if (rec.get("CLASSTYPE") or "").strip() != "1":
            skipped_class += 1
            continue
        rows.append(tuple((rec.get(c) or "").strip() for c in _KEEP))

    # LOINC ships ~100k terms. Anything far below that means a partial file, and
    # a half-sized vocabulary that silently resolves 40% of names is worse than
    # none — it looks authoritative. Same guard as build_icd11_catalog.py.
    # 62,148 active lab terms in 2.83. Well below that means a partial file, and
    # a half-sized vocabulary that silently resolves a fraction of names is
    # worse than none — it looks authoritative. Same guard as the ICD-11 builder.
    if len(rows) < 40_000:
        raise SystemExit(
            f"refusing to write a suspiciously small catalog ({len(rows)} terms). "
            "Did the zip contain only an accessory file?")

    buf = io.StringIO()
    buf.write(f"# LOINC {version} — generated by scripts/build_loinc_catalog.py\n")
    buf.write("# This material contains content from LOINC (https://loinc.org).\n")
    buf.write("# LOINC is copyright (c) 1995-2025, Regenstrief Institute, Inc. and\n")
    buf.write("# the LOINC Committee, and is available at no cost under the\n")
    buf.write("# LOINC license: https://loinc.org/license\n")
    buf.write("# DO NOT HAND-EDIT — edit the builder and re-run.\n")
    writer = csv.writer(buf, delimiter="\t", lineterminator="\n")
    writer.writerow([c.lower() for c in _KEEP])
    writer.writerows(rows)

    payload = buf.getvalue().encode("utf-8")
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    # mtime=0 so rebuilding an unchanged release produces an identical file.
    with gzip.GzipFile(OUT_PATH, "wb", compresslevel=9, mtime=0) as fh:
        fh.write(payload)

    print(f"wrote {OUT_PATH.name}: {len(rows)} terms, "
          f"{OUT_PATH.stat().st_size / 1024:.0f} KB gz (LOINC {version})",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
