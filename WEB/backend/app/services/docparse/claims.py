# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""Layer 2b — what KIND of data does this region hold, and where does it go?

A document is not one thing. Measured on the real 10/09 DaVita Treatment
Details Report, one PDF carries a treatment session, six timed BP/UF readings,
pre/post vitals, a dialyser prescription and a close reason — five kinds of
clinical fact. `TARGET_FOR_DOC_TYPE` allowed exactly ONE destination per
document, so no value of `doc_type` could ever have imported it; that report was
imported by hand-written SQL on 2026-10-10 (production session 2776).

So routing moves off the document LABEL and onto the DATA. `classify_table`
reports every kind a table holds, and the stager for each kind runs. The label
from `classify.py` stays as metadata — useful to show a reviewer, useless as a
switch, and demoting it also defuses a live trap: `September labs AA.pdf`
classifies as `dialysis_flowsheet` and yields 75 LAB rows, so anything routing
on that label would have broken a working import.

WHY THIS CANNOT JUST CALL EVERY EXTRACTOR
-----------------------------------------
Measured over the 13-document lab corpus, 2026-10-11:

    true lab rows                1014
    FALSE medications            1115     <- what the med extractor would stage
    FALSE conditions             1115     <- what the condition extractor would

More false claims than true ones. `records_from_medication_table` and
`records_from_condition_table` append a record for EVERY row with a non-empty
name — they are correct GIVEN that the caller settled the type, and carry no
shape guard of their own. Unguarded, `ALB` is staged as a drug with no dose and
as a diagnosis "filed as other, severity moderate", and `AGE` and `A/G` with it.
§3ab's precision lesson exactly: the corpus harness scores recall, so a parser
can emit a hundred prose rows and still report 100%.

WHAT DECIDES, AND WHY IT IS NOT A WORD LIST
-------------------------------------------
The authorities are already in this repo, and the canon already says to use them
rather than type the answer (§3aj "RxNorm is the authority on whether a name is a
drug, not a table"; §3ad "never type an ICD code from memory"):

    concentration units + reference ranges   the row's own shape
    app/data/loinc_core.tsv.gz               62,148 terms, local
    app/data/icd11_mms.tsv.gz                35,339 codes, local
    app/services/rxnorm.py                   keyless, cached — NETWORK
    app/core/nutrition_data.py               116 USDA nutrients, local

Local evidence decides in the hot path. RxNorm is deliberately NOT consulted
here: §3aj records that `canonical_name()` is kept off the clinical write path
because it is an extra HTTP round trip, and staging a 100-row document must not
become 100 network calls. A medication CANDIDATE is routed on shape and the
RxNorm check stays where it already is — `validate_dose` on the write path.

Two shape rules carry most of the weight, and both were measured rather than
assumed over 1,014 real records:

  * A unit with a DENOMINATOR is a concentration, so the row is a measurement:
    `mg/dL` 130, `g/dL` 63, `Cells/uL` 60, `mEq/L` 54, `U/L` 39. A BARE mass
    unit (`mg`, `mcg`) is a dose. Bare mass units among those 1,014 lab
    records: ZERO — so this rule cannot misfire on a real lab report.
  * 205 of 1,014 rows (20.2%) carry NEITHER a unit NOR a range — the dialysis
    machine and prescription parameters §3ab says no lab vocabulary covers
    (`BLDFLOW`, `AMPUTATE FACTOR`, `DAYS/WEEK`, `Dialyzer KOA`). Those are
    measurements on the evidence of the lab's OWN test code, which is printed on
    the row and parsed on 939 of 1,014 records (92.6%) into `LabRecord.code`.

`UNPLACEABLE` is a first-class answer. A region whose kind cannot be established
is reported with its evidence and staged for nothing — §3aa, an error is not an
empty state, and it is not a guess either. Imaging findings and recipes have NO
destination table in this schema (measured: `facilities.imaging` is a facility
TYPE enum and `recipe_url` is a column on a meal plan), so they resolve here and
are deliberately refused a target rather than being filed somewhere plausible.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .layout import Table

# ── Claim kinds, and the table each one feeds ────────────────────────────────
#
# These are names for KINDS OF DATA, not for document types. One document may
# produce several; that is the whole point.

MEASUREMENT = "measurement"
MEDICATION = "medication"
CONDITION = "condition"
TREATMENT = "treatment"
PANTRY_ITEM = "pantry_item"
FOOD_ITEM = "food_item"
UNPLACEABLE = "unplaceable"

#: kind -> clinical table. A kind absent from this map parses and stages
#: nothing; `document_import_items.target_table` is already a per-item column
#: and `confirm()` already dispatches on it, so a document feeding several
#: tables needs no migration — only this routing.
TARGET_FOR_KIND: dict[str, str] = {
    MEASUREMENT: "lab_results",
    MEDICATION: "medications",
    CONDITION: "chronic_conditions",
    TREATMENT: "therapy_sessions",
    PANTRY_ITEM: "pantry_items",
    FOOD_ITEM: "nutrition_logs",
}

#: Kinds this schema can recognise but has nowhere to put. Kept explicit so the
#: reviewer is told "we read this and cannot file it" instead of the row being
#: filed somewhere it does not belong. Adding a target means adding a model and
#: a hand-written migration (§3ao — never `--autogenerate`).
NO_TARGET_YET: dict[str, str] = {
    "imaging_finding": "no imaging table exists in this schema",
    "recipe": "no recipes table exists; meal plans carry only a recipe_url",
}

# A denominator makes a unit a CONCENTRATION — a measured quantity per volume
# or mass. `mg/dL`, `Cells/uL`, `x 10^3 cells/uL`, `mL/min`, `G/KG/D`.
_HAS_DENOMINATOR = re.compile(r"[a-zA-Z0-9\^\s]/\s*[a-zA-Z]")

# Units that are measurements despite carrying no denominator. Read off the
# measured vocabulary of the corpus, not invented: %, fL, pg, kg, Years,
# Inches, hrs, min, Calc. These are dimensions, not drug doses.
_MEASUREMENT_UNITS = {
    "%", "fl", "pg", "kg", "lb", "lbs", "years", "yr", "yrs", "inches", "in",
    "cm", "hrs", "hr", "hours", "min", "mins", "calc", "sq m", "ratio", "ml",
    "l", "meq", "mmol", "mosm", "c", "f", "mmhg", "bpm",
}

# A BARE mass/activity unit is a DOSE. Measured: zero lab records in the corpus
# carry one, so this cannot misfire on a real lab report.
_DOSE_UNITS = {"mg", "mcg", "ug", "g", "gram", "grams", "unit", "units", "iu",
               "tablet", "tablets", "capsule", "capsules", "puff", "puffs",
               "drop", "drops", "patch", "patches"}

# ICD-10 shape. The CATALOG decides what a code MEANS (§3ad); this only
# recognises that the document printed something code-shaped.
_ICD10_SHAPE = re.compile(r"\b([A-TV-Z][0-9][0-9AB](?:\.[0-9A-TV-Z]{1,4})?)\b")

# Units a pantry or grocery list counts in. `pantry_items` stores exactly these
# (name/category/quantity/unit/location/expiration_date), so a photographed
# pantry list maps on almost directly.
_COUNTING_UNITS = {"pieces", "piece", "ea", "each", "oz", "lbs", "lb", "cups",
                   "cup", "tbsp", "tsp", "cans", "can", "bottles", "bottle",
                   "boxes", "box", "bags", "bag", "dozen", "packs", "pack"}


# ── A reported failure is not a result ──────────────────────────────────────
#
# Measured over the 13-document corpus, 2026-10-11 — the COMPLETE vocabulary of
# result texts carrying no digit at all:
#
#     'N/A'     60    the lab states no result exists
#     'Error'   60    the assay failed
#     'NEG'     11    NEGATIVE — a real qualitative finding
#
# The first two are statements that no measurement was obtained. The third is a
# measurement. That distinction is the whole rule, and §3ab paid for getting it
# wrong in the other direction: "a real row has a number in its value column"
# deletes 49 of 106 rows on a Quest report — `WBC = NONE SEEN`, `RBC = 0-2`,
# `ABSOLUTE BLASTS = DNR`, an entire urinalysis microscopy panel. So this is an
# explicit two-item list with a measurement behind each entry, NOT a rule about
# digits, and `NEG` is a recorded exclusion rather than an oversight.
#
# Nothing is ever deleted. A row matching this stages UNTICKED with its reason
# (§3ab), because the failure being guarded against is a reviewer ticking
# through what the system already ticked for them.
REPORTED_FAILURE = {"error", "n/a", "n/a.", "na"}

#: Kept as data so the exclusion is testable rather than a claim in a comment.
NOT_A_FAILURE_EXAMPLES = ("NEG", "NONE SEEN", "0-2", "DNR", "Negative")


def result_is_reported_failure(value_text: str | None) -> bool:
    """Did the lab report that it could NOT produce a result?

    Judged on the exact text, folded for case and surrounding punctuation. A
    substring test would catch "NO ERROR" and any comment mentioning an error.
    """
    text = (value_text or "").strip().lower().strip(".")
    return bool(text) and text in {s.strip(".") for s in REPORTED_FAILURE}


@dataclass
class KindEvidence:
    """Why a region was routed where it was.

    Recorded per kind rather than summed into a score. §3aj's lesson on the dose
    guard: a guard that cannot explain itself gets blamed for the thing it did
    not do, and the reviewer here is deciding whether to write a clinical row.
    """

    kind: str
    rows: int = 0
    reasons: list[str] = field(default_factory=list)
    confidence: float = 0.0

    @property
    def target(self) -> str | None:
        return TARGET_FOR_KIND.get(self.kind)


def _norm_unit(unit: str | None) -> str:
    return (unit or "").strip().lower()


def looks_like_measured_unit(unit: str | None) -> bool:
    """Is this unit a measured quantity rather than a dose?

    A denominator settles it. Otherwise the unit must be a known dimension —
    and a bare mass unit is explicitly NOT one.
    """
    u = _norm_unit(unit)
    if not u:
        return False
    if _HAS_DENOMINATOR.search(u):
        return True
    if u in _DOSE_UNITS:
        return False
    return u in _MEASUREMENT_UNITS


def looks_like_dose_unit(unit: str | None) -> bool:
    u = _norm_unit(unit)
    return bool(u) and "/" not in u and u in _DOSE_UNITS


def row_measurement_evidence(row) -> str | None:
    """Return the reason this row is a measurement, or None.

    Order is deliberate: the cheapest and most specific evidence first.
    """
    value = (row.get("value") or "").strip()
    unit = row.get("unit")
    ref = (row.get("ref_range") or "").strip()
    code = (row.get("code") or "").strip()

    has_number = bool(re.search(r"\d", value))

    if unit and looks_like_measured_unit(unit):
        return f"unit {unit!r} is a measured quantity"
    if ref and re.search(r"\d", ref):
        return "the document printed a reference range for this row"
    # The 20.2% with neither: the lab's own catalog code plus a number. This is
    # the evidence that covers the dialysis machine parameters no lab vocabulary
    # names, and it is printed on 92.6% of real rows.
    if code and re.fullmatch(r"\d{3,5}", code) and has_number:
        return f"the lab's own test code {code} with a numeric result"
    return None


def classify_table(table: Table) -> list[KindEvidence]:
    """Report every kind of data this table holds, with the evidence.

    Returns an empty list when nothing can be established — the caller must
    treat that as UNPLACEABLE and say so, never as "no data".
    """
    counts: dict[str, KindEvidence] = {}

    def note(kind: str, reason: str) -> None:
        ev = counts.setdefault(kind, KindEvidence(kind=kind))
        ev.rows += 1
        if reason not in ev.reasons:
            ev.reasons.append(reason)

    for row in table.rows:
        name = (row.get("name") or "").strip()
        if not name:
            continue

        measured = row_measurement_evidence(row)
        if measured:
            note(MEASUREMENT, measured)
            # A measurement is not also a drug or a diagnosis. This single
            # `continue` is what takes the 1115 false medications and 1115 false
            # conditions to zero on the lab corpus.
            continue

        code_text = " ".join(filter(None, [row.get("code"), row.get("comments")]))
        if _ICD10_SHAPE.search(code_text or ""):
            note(CONDITION, "a code-shaped token in the code column")
            continue

        dose_unit = row.get("unit")
        dose_text = row.get("dose") or ""
        if looks_like_dose_unit(dose_unit) or re.search(
            r"\d+\s*(mg|mcg|ug|g|units?|iu|tablets?|capsules?)\b", dose_text, re.I
        ):
            note(MEDICATION, "a bare dose amount with a mass or count unit")
            continue

        qty = (row.get("value") or "").strip()
        unit = _norm_unit(row.get("unit"))
        if unit in _COUNTING_UNITS and re.search(r"\d", qty):
            note(PANTRY_ITEM, f"a counted quantity in {unit!r}")
            continue

    for ev in counts.values():
        share = ev.rows / max(len(table.rows), 1)
        # Confidence is the share of the table this kind accounts for, floored
        # so a small but unambiguous block is not dismissed. Never 1.0: the
        # reviewer confirms, and a parser claiming certainty about a clinical
        # row is the §3c confidently-wrong match.
        ev.confidence = round(min(0.35 + 0.6 * share, 0.95), 2)

    return sorted(counts.values(), key=lambda e: -e.rows)


def kinds_in_document(
    tables: list[Table],
    *,
    layout_kind: str | None = None,
    record_count: int = 0,
) -> dict[str, KindEvidence]:
    """Merge per-table evidence into one answer for the document.

    `layout_kind` and `record_count` carry the MATRIX case, and leaving them out
    is not a detail. `layout_matrix` reconstructs an analyte × PERIOD grid —
    columns keyed by time, with no RESULT or REFERENCE header to anchor on — so
    `parse_document` returns no `Table` for such a page and a tables-only
    detector sees nothing at all.

    Measured: `September labs AA.pdf` yields 75 real lab records through that
    path and ZERO tables. Gating the lab stager on tables-only evidence would
    have silently dropped all 75 — the §3aa failure this whole module is meant
    to prevent, introduced by the fix for it.

    A time-keyed grid of analytes IS a measurement grid by construction, which
    is why the structure alone is sufficient evidence here.
    """
    merged: dict[str, KindEvidence] = {}

    if layout_kind == "matrix" and record_count:
        merged[MEASUREMENT] = KindEvidence(
            kind=MEASUREMENT,
            rows=record_count,
            reasons=["a trend grid of analytes against time periods"],
            confidence=0.8,
        )

    for table in tables:
        for ev in classify_table(table):
            prior = merged.get(ev.kind)
            if prior is None:
                merged[ev.kind] = ev
                continue
            prior.rows += ev.rows
            for reason in ev.reasons:
                if reason not in prior.reasons:
                    prior.reasons.append(reason)
            prior.confidence = max(prior.confidence, ev.confidence)
    return merged
