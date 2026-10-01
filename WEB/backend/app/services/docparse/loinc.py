"""LOINC — the published authority for what a lab analyte IS.

`ANALYTE_NAMES` in `dictionaries.py` is 136 hand-typed entries. Measured against
production on 2026-09-30 it names **136 of 411 stored test names — 33.1%**. It
cannot name ALT, AST, `BILIRUBIN, TOTAL`, `Anion Gap`, `ALBUMIN/GLOBULIN RATIO`
or `BUN/CREATININE RATIO`: ordinary chemistry. §3ad forbids typing codes from
memory and §3aj proved a 23-row seed wrong in both directions; neither rule had
reached this parser.

The catalog is generated, never typed: `scripts/build_loinc_catalog.py` reads
the official release and writes `app/data/loinc_core.tsv.gz` — 62,148 ACTIVE
CLASSTYPE-1 laboratory terms from LOINC 2.83.

WHY COMPONENT IS NOT THE KEY — the mistake this module exists to avoid
----------------------------------------------------------------------
`718-7` (haemoglobin), `785-6` (MCH) and `786-4` (MCHC) all carry
`COMPONENT = 'Hemoglobin'`. They differ only by SYSTEM (Bld vs RBC) and
PROPERTY. An index keyed on component collapses all three onto one key, and the
best-ranked wins: a first attempt resolved plain "Hemoglobin" to **MCHC**,
because MCHC ranks 13 and true haemoglobin ranks 17.

That is §3c's confidently-wrong match with a clinical code attached — worse than
the 33% dict, because every row would carry an authoritative-looking identifier.
The six axes exist precisely because the component alone does not identify a
test. SHORTNAME is the discriminating field: `Hgb Bld-mCnc`, `MCH RBC Qn Auto`,
`MCHC RBC Auto-EntMCnc`.

...AND THE FIRST FIX FOR THAT WAS STILL WRONG (2026-10-01)
----------------------------------------------------------
The paragraph above was written, and the resolver shipped resolving plain
"Hemoglobin" to **786-4 — MCHC** anyway. Tier 0 misses (`hemoglobin` is not a
shortname), so it fell to the COMPONENT tier, which keeps the best-RANKED term
sharing a component: MCHC ranks 13, true haemoglobin 17. Documenting a trap is
not avoiding it.

Worse, the word a report actually PRINTS is often in no indexed axis at all.
LOINC 2.83 gives hematocrit the component `Erythrocyte/Blood` — correct (it is
the volume fraction of erythrocytes in blood) and unreachable from a report that
says "HEMATOCRIT". Zero terms in the release normalise to `hematocrit` on the
component axis.

The printed word lives in **LONG_COMMON_NAME**, ahead of the first bracket:

    Hemoglobin [Mass/volume] in Blood                     -> Hemoglobin
    Hematocrit [Volume Fraction] of Blood by Auto count   -> Hematocrit
    MCHC [Entitic Mass/volume] in Red Blood Cells         -> MCHC

So the analyte HEAD of the long name is indexed as a tier of its own, between
shortname and component. It is derived from the authority, not typed: no alias
table, nothing to go stale, and `_SYSTEM_HINTS` stays the only literal here.

Measured over all 136 `ANALYTE_NAMES` entries — 3 gained, 2 corrected, **0 lost**:

    HEMATOCRIT   (none)                          -> 4544-3  Hct VFr Bld Auto
    MCH          (none)                          -> 785-6   MCH RBC Qn Auto
    MCHC         (none)                          -> 786-4   MCHC RBC Auto-EntMCnc
    HEMOGLOBIN   786-4  MCHC RBC Auto-EntMCnc    -> 718-7   Hgb Bld-mCnc
    MCV          54022-9 Mut cit vimentin Ab     -> 787-2   MCV RBC Auto

⚠️ Read that MCV row. "MCV" was resolving to **mutated citrullinated vimentin
antibody** — a rheumatoid-arthritis autoantibody — for a routine red-cell index.
It was found only by diffing all 136 names; a ten-name spot check missed it,
exactly as a ten-name spot check is what made COMPONENT look like a usable key.
**Measure the whole vocabulary when you change the index, or the wrong answers
you keep are the ones you did not think to probe.**

Measured consequences of getting this right:

    Hemoglobin + Bld   -> 718-7   Qn  g/dL
    Glucose + Ser/Plas -> 2345-7  Qn  mg/dL      two rows both named "Glucose"
    Glucose + Urine    -> 5792-7  SemiQn mg/dL   stop being indistinguishable

RANK IS NOT A SORT KEY, IT IS A TIEBREAK — and 0 means UNRANKED
--------------------------------------------------------------
`COMMON_TEST_RANK` is 0 on 43,956 of 62,148 terms. Sorting ascending therefore
puts every obscure term FIRST: an early version ranked
`Hematocrit^30M post dose glucose` above everything. Unranked sorts LAST here.

The ranked 18,192 run 1→20,000 in the order a clinician would expect —
Creatinine 4, Sodium 5, Glucose 6, Potassium 7 — so within a tier it is a good
tiebreak and nothing more.

WHAT THIS DOES NOT OWN
----------------------
Of 411 stored names only 150 carry a printed reference range. `BLDFLOW`,
`AMPUTATE FACTOR`, `DAYS/WEEK`, `Dialyzer KOA` are dialysis machine and
prescription parameters that no laboratory vocabulary covers. `resolve()`
returns None for those and the caller KEEPS THE DOCUMENT'S OWN WORDING (§3ax) —
an unresolved name is never dropped.

This module reads one gzipped file and imports nothing from the app, so
`docparse` stays runnable without a database or settings — the property that
lets the corpus harness run at all.
"""

from __future__ import annotations

import gzip
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_DATA_FILE = Path(__file__).resolve().parents[2] / "data" / "loinc_core.tsv.gz"

_TOKEN_RE = re.compile(r"[a-z0-9]+")

#: Unranked terms sort after every ranked one.
_UNRANKED = 10**9

#: Specimen words a report prints, mapped to LOINC SYSTEM values. This is the
#: ONE place a literal is unavoidable: LOINC's SYSTEM axis is its own
#: vocabulary ("Ser/Plas", "Bld", "RBC") and a lab report says "serum" or
#: "urine". It maps presentation to the authority's own terms; it states no
#: clinical fact and adds no analyte.
_SYSTEM_HINTS = {
    "serum": "Ser/Plas", "plasma": "Ser/Plas", "ser": "Ser/Plas",
    "blood": "Bld", "whole blood": "Bld", "bld": "Bld",
    "urine": "Urine", "ua": "Urine", "urinalysis": "Urine",
    "stool": "Stool", "feces": "Stool",
    "rbc": "RBC", "csf": "CSF",
}


@dataclass(frozen=True)
class LoincTerm:
    loinc_num: str
    component: str
    system: str
    scale: str          # Qn | Ord | SemiQn | Nom | OrdQn | Nar
    property: str
    units: str
    long_name: str
    short_name: str
    rank: int

    @property
    def is_quantitative(self) -> bool:
        return self.scale == "Qn"

    @property
    def is_ordinal(self) -> bool:
        """`2+`, `NEGATIVE`, `TRACE` — a number alone is the WRONG shape here."""
        return self.scale in ("Ord", "OrdQn", "SemiQn")

    @property
    def is_percentage(self) -> bool:
        return self.units.strip() == "%"


def _norm(text: str) -> str:
    return " ".join(_TOKEN_RE.findall((text or "").lower()))


class _Catalog:
    """The generated table plus the indexes that make a lookup cheap."""

    def __init__(self) -> None:
        self.terms: list[LoincTerm] = []
        self.by_code: dict[str, LoincTerm] = {}
        self._by_short: dict[str, LoincTerm] = {}
        self._by_long_head: dict[str, LoincTerm] = {}
        self._by_comp_sys: dict[tuple[str, str], LoincTerm] = {}
        self._by_comp: dict[str, LoincTerm] = {}
        self._by_synonym: dict[str, LoincTerm] = {}
        self.version = "unknown"

    def load(self) -> "_Catalog":
        if not _DATA_FILE.exists():
            # Absent catalog is not fatal: the caller falls back to the
            # hand-written vocabulary. A missing data file must never stop a
            # patient importing a document.
            return self

        with gzip.open(_DATA_FILE, "rt", encoding="utf-8") as fh:
            header: list[str] | None = None
            for line in fh:
                line = line.rstrip("\n")
                if line.startswith("#"):
                    if self.version == "unknown" and "LOINC" in line:
                        self.version = line.lstrip("# ").split("—")[0].strip()
                    continue
                parts = line.split("\t")
                if header is None:
                    header = parts
                    continue
                row = dict(zip(header, parts))
                try:
                    rank = int(row.get("common_test_rank") or 0)
                except ValueError:
                    rank = 0
                term = LoincTerm(
                    loinc_num=row.get("loinc_num", ""),
                    component=row.get("component", ""),
                    system=row.get("system", ""),
                    scale=row.get("scale_typ", ""),
                    property=row.get("property", ""),
                    units=row.get("example_ucum_units", ""),
                    long_name=row.get("long_common_name", ""),
                    short_name=row.get("shortname", ""),
                    rank=rank or _UNRANKED,
                )
                if not term.loinc_num:
                    continue
                self.terms.append(term)
                self.by_code[term.loinc_num] = term

                def better(existing: LoincTerm | None) -> bool:
                    return existing is None or term.rank < existing.rank

                short = _norm(term.short_name)
                if short and better(self._by_short.get(short)):
                    self._by_short[short] = term

                # The analyte as LOINC itself writes it in prose, ahead of the
                # first bracket — which is the word a lab report prints:
                #   "Hemoglobin [Mass/volume] in Blood"  ->  "Hemoglobin"
                # 26,314 of 62,148 terms yield a head. This is what reaches
                # "Hematocrit", whose COMPONENT is `Erythrocyte/Blood` and is
                # therefore unreachable from the printed word on any axis.
                head = _norm((term.long_name or "").split("[")[0])
                if head and better(self._by_long_head.get(head)):
                    self._by_long_head[head] = term

                comp = _norm(term.component)
                if comp:
                    key = (comp, term.system)
                    if better(self._by_comp_sys.get(key)):
                        self._by_comp_sys[key] = term
                    if better(self._by_comp.get(comp)):
                        self._by_comp[comp] = term

                for synonym in (row.get("relatednames2") or "").split(";"):
                    key_s = _norm(synonym)
                    # Synonyms are the weakest signal and the noisiest: MCHC's
                    # related names contain the bare word "hemoglobin". They are
                    # consulted only after component and shortname have failed.
                    if key_s and better(self._by_synonym.get(key_s)):
                        self._by_synonym[key_s] = term
        return self


@lru_cache(maxsize=1)
def _catalog() -> _Catalog:
    return _Catalog().load()


def available() -> bool:
    """Whether the generated catalog is present in this image."""
    return bool(_catalog().terms)


def catalog_version() -> str:
    return _catalog().version


def system_for(hint: str | None) -> str | None:
    """Map a specimen word off the report to a LOINC SYSTEM."""
    return _SYSTEM_HINTS.get(_norm(hint)) if hint else None


def resolve(name: str, specimen: str | None = None) -> LoincTerm | None:
    """Resolve a printed analyte name to one LOINC term, or None.

    Tiers, strongest first. A weaker tier is consulted only when every stronger
    one misses, so a synonym can never outrank a component or shortname match:

      0. SHORTNAME exact      — the only field that separates Hgb/MCH/MCHC
      1. LONG_COMMON_NAME head — the analyte as LOINC writes it in prose, which
                                is the word a report actually prints. Ahead of
                                COMPONENT because it is what corrects HEMOGLOBIN
                                (was MCHC) and MCV (was an RA autoantibody).
      2. (COMPONENT, SYSTEM)  — when the document told us the specimen
      3. COMPONENT exact      — best-ranked; ambiguous across systems, so last
                                among the strong tiers
      4. synonym              — noisy, consulted last

    Returns None rather than a guess. The caller keeps the document's wording.
    """
    key = _norm(name)
    if not key:
        return None
    cat = _catalog()
    if not cat.terms:
        return None

    hit = cat._by_short.get(key)
    if hit is not None:
        return hit

    hit = cat._by_long_head.get(key)
    if hit is not None:
        return hit

    system = system_for(specimen)
    if system:
        hit = cat._by_comp_sys.get((key, system))
        if hit is not None:
            return hit

    hit = cat._by_comp.get(key)
    if hit is not None:
        return hit

    return cat._by_synonym.get(key)


def value_shape_disagrees(term: LoincTerm, value: float | None,
                          value_text: str | None) -> str | None:
    """Does the stored value contradict the term's own SCALE_TYP?

    This is the check that makes `OCCULT BLOOD = 2` provably wrong rather than a
    matter of taste: urine haemoglobin is an ORDINAL observation, so the value is
    `2+` and a bare 2 has lost the grade. Returns a sentence for the reviewer, or
    None when the shape is consistent.
    """
    if term.is_ordinal and value is not None and not (value_text or "").strip():
        return (
            f"{term.long_name or term.component} is reported on an ordinal scale "
            f"({term.scale}) — values look like '1+', '2+', 'NEGATIVE'. A bare "
            f"number here usually means a grade lost its '+'."
        )
    if term.is_percentage and value is not None and value > 100:
        return (
            f"{value:g}% exceeds 100% — {term.loinc_num} is a proportion "
            f"({term.property}), so this cannot be a real measurement."
        )
    return None
