# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""A document is routed by what its DATA is, not by one label.

`TARGET_FOR_DOC_TYPE` allowed exactly ONE destination per document, so the real
10/09 DaVita Treatment Details Report — a session, six timed readings, pre/post
vitals, a prescription and a close reason in one PDF — could not be imported at
all and was written by hand as production session 2776 on 2026-10-10.

The guard that matters here is PRECISION, because the obvious implementation of
"route on the data" is to run every extractor, and that is catastrophic.
Measured over the 13-document lab corpus on 2026-10-11:

    true lab rows        1014
    FALSE medications    1115
    FALSE conditions     1115

`records_from_medication_table` and `records_from_condition_table` append a
record for EVERY row with a non-empty name, so unguarded they file `ALB` as a
drug with no dose and `AGE` as a diagnosis "filed as other, severity moderate".
§3ab: the corpus harness scores RECALL, so a parser can emit a hundred prose
rows and still report 100% — this file scores precision instead.

The unit rules below are measured over those 1,014 real records, not invented:
`mg/dL` 130, `g/dL` 63, `Cells/uL` 60, `mEq/L` 54, `U/L` 39, and BARE mass
units ZERO.
"""

import pathlib

import pytest

from app.services.docparse.claims import (
    CONDITION,
    MEASUREMENT,
    MEDICATION,
    NO_TARGET_YET,
    PANTRY_ITEM,
    TARGET_FOR_KIND,
    classify_table,
    kinds_in_document,
    looks_like_dose_unit,
    looks_like_measured_unit,
)
from app.services.docparse.layout import Column, Row, Table


def _table(rows: list[dict[str, str]]) -> Table:
    return Table(
        columns=[Column(role=r, x_start=0.0, x_end=1.0)
                 for r in (rows[0].keys() if rows else [])],
        rows=[Row(cells=dict(r), top=float(i), page=1) for i, r in enumerate(rows)],
        page=1,
    )


# ── The unit discriminator ───────────────────────────────────────────────────

@pytest.mark.parametrize("unit", ["mg/dL", "g/dL", "Cells/uL", "mEq/L", "U/L",
                                  "ng/mL", "pg/mL", "mL/min", "G/KG/D",
                                  "x 10^3 cells/uL"])
def test_a_unit_with_a_denominator_is_a_measurement(unit):
    """A denominator makes a unit a concentration. These ten are the real
    vocabulary of the corpus, in descending frequency."""
    assert looks_like_measured_unit(unit)
    assert not looks_like_dose_unit(unit)


@pytest.mark.parametrize("unit", ["%", "fL", "pg", "kg", "Years", "Inches",
                                  "hrs", "min", "Calc"])
def test_a_dimension_without_a_denominator_is_still_a_measurement(unit):
    """Read off the corpus: these carry no denominator and are not doses."""
    assert looks_like_measured_unit(unit)


@pytest.mark.parametrize("unit", ["mg", "mcg", "ug", "g", "units", "IU",
                                  "tablet", "capsules"])
def test_a_bare_mass_or_count_unit_is_a_DOSE(unit):
    """The other half of the rule. Zero lab records in the corpus carry one of
    these, which is what makes it safe to read them as doses."""
    assert looks_like_dose_unit(unit)
    assert not looks_like_measured_unit(unit)


def test_mg_and_mg_per_dl_are_not_the_same_claim():
    """The whole discriminator in one assertion: `BUN 84 mg/dL` is a
    measurement, `Calcium carbonate 1000 mg` is a dose."""
    assert looks_like_measured_unit("mg/dL") and not looks_like_dose_unit("mg/dL")
    assert looks_like_dose_unit("mg") and not looks_like_measured_unit("mg")


# ── Routing ──────────────────────────────────────────────────────────────────

def test_a_lab_row_is_a_measurement_and_NOTHING_else():
    """`ALB 4.2 g/dL 3.5 - 5.0` must not also be staged as a drug or a
    diagnosis. This is the 1115+1115 false claims, in one row."""
    kinds = classify_table(_table([
        {"name": "ALB", "value": "4.2", "unit": "g/dL", "ref_range": "3.5 - 5.0"},
    ]))
    assert [e.kind for e in kinds] == [MEASUREMENT]


def test_a_row_with_no_unit_and_no_range_is_carried_by_the_labs_own_code():
    """20.2% of real records have neither — the dialysis machine parameters
    §3ab says no lab vocabulary covers. The code is printed on 92.6% of rows."""
    kinds = classify_table(_table([
        {"code": "2023", "name": "BLOOD FLOW-QWB", "value": "450",
         "unit": "", "ref_range": ""},
    ]))
    assert [e.kind for e in kinds] == [MEASUREMENT]
    assert "2023" in kinds[0].reasons[0]


def test_a_row_with_no_unit_no_range_and_no_code_is_not_claimed():
    """No evidence is not a measurement. It must fall through to UNPLACEABLE
    rather than being filed on a guess (§0)."""
    assert classify_table(_table([
        {"name": "SOME HEADING", "value": "", "unit": "", "ref_range": ""},
    ])) == []


def test_a_dose_row_is_a_medication():
    kinds = classify_table(_table([
        {"name": "Calcium Carbonate", "value": "1000", "unit": "mg",
         "ref_range": ""},
    ]))
    assert [e.kind for e in kinds] == [MEDICATION]
    assert TARGET_FOR_KIND[MEDICATION] == "medications"


def test_a_coded_row_is_a_condition():
    kinds = classify_table(_table([
        {"name": "End stage renal disease", "code": "N18.6", "value": "",
         "unit": "", "ref_range": ""},
    ]))
    assert [e.kind for e in kinds] == [CONDITION]
    assert TARGET_FOR_KIND[CONDITION] == "chronic_conditions"


def test_a_counted_row_is_a_pantry_item():
    """`pantry_items` stores name/category/quantity/unit/location/expiry, so a
    photographed pantry list maps on almost directly."""
    kinds = classify_table(_table([
        {"name": "Canned sardines", "value": "4", "unit": "cans",
         "ref_range": ""},
    ]))
    assert [e.kind for e in kinds] == [PANTRY_ITEM]
    assert TARGET_FOR_KIND[PANTRY_ITEM] == "pantry_items"


def test_ONE_document_can_hold_SEVERAL_kinds():
    """The point of the whole change. A visit summary carries conditions AND
    medications AND measurements, and the old router had to pick one."""
    kinds = kinds_in_document([_table([
        {"name": "POTASSIUM", "code": "1016", "value": "5.1", "unit": "mEq/L",
         "ref_range": "3.5 - 5.5", "comments": ""},
        {"name": "Calcitriol", "code": "", "value": "0.5", "unit": "mcg",
         "ref_range": "", "comments": ""},
        {"name": "Anemia of CKD", "code": "D63.1", "value": "", "unit": "",
         "ref_range": "", "comments": ""},
    ])])
    assert set(kinds) == {MEASUREMENT, MEDICATION, CONDITION}
    assert {k: e.target for k, e in kinds.items()} == {
        MEASUREMENT: "lab_results",
        MEDICATION: "medications",
        CONDITION: "chronic_conditions",
    }


def test_a_kind_with_no_table_is_refused_a_target_rather_than_misfiled():
    """Imaging findings and recipes have NO destination in this schema —
    measured: `facilities.imaging` is a facility TYPE enum and `recipe_url` is
    a column on a meal plan. Saying so beats filing them somewhere plausible."""
    assert set(NO_TARGET_YET) == {"imaging_finding", "recipe"}
    for kind in NO_TARGET_YET:
        assert kind not in TARGET_FOR_KIND


def test_confidence_is_never_certain():
    """§3c: a parser claiming certainty about a clinical row is the
    confidently-wrong match. The reviewer confirms."""
    kinds = classify_table(_table([
        {"name": "ALB", "value": "4.2", "unit": "g/dL", "ref_range": "3.5-5.0"},
    ]))
    assert 0.0 < kinds[0].confidence <= 0.95


# ── The precision guard, against the real corpus ─────────────────────────────

def _corpus() -> pathlib.Path | None:
    for parent in pathlib.Path(__file__).resolve().parents:
        candidate = parent / "ML" / "data" / "raw" / "pdf"
        if candidate.is_dir() and any(candidate.glob("*.pdf")):
            return candidate
    return None


@pytest.mark.asyncio
@pytest.mark.skipif(_corpus() is None,
                    reason="the real PHI corpus is not mounted here — it is "
                           "deliberately not in CI (§3ab)")
async def test_the_lab_corpus_yields_measurements_and_ZERO_drugs_or_diagnoses():
    """The measured failure, pinned.

    Over these 13 documents an unguarded router stages 1115 false medications
    and 1115 false conditions beside 1014 true lab rows. Every one of these
    documents IS a lab report, so any medication or condition claim here is
    false by construction.
    """
    from app.services.docparse.pipeline import parse

    corpus = _corpus()
    assert corpus is not None
    measurements = wrong = 0
    offenders: list[str] = []

    for path in sorted(corpus.glob("*.pdf")):
        parsed = await parse(path.read_bytes(), path.name, use_model=False)
        kinds = kinds_in_document(parsed.tables)
        measurements += kinds[MEASUREMENT].rows if MEASUREMENT in kinds else 0
        for bad in (MEDICATION, CONDITION):
            if bad in kinds:
                wrong += kinds[bad].rows
                offenders.append(f"{path.name}: {kinds[bad].rows} × {bad}")

    assert not offenders, (
        "a lab report was routed to a drug or diagnosis table:\n  "
        + "\n  ".join(offenders))
    assert wrong == 0
    assert measurements > 500, (
        f"only {measurements} measurements recognised across the corpus — the "
        "guard has become too strict and is now dropping real results")
