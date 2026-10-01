"""A lab's address is not a lab result — and "NONE SEEN" is.

THE INCIDENT. A real 3-page Quest report (`results - Jan 2022.pdf`) imported a
street address, the lab director's name, a section heading and four lines of LDL
footnote as clinical results. The worst reached the record as a flagged-abnormal
measurement:

    01: Quest Diagnostics-Houston = 5850        <- Rogerdale Road, the lab's address

`looks_like_prose` did not catch any of it and could not: it judges the NAME
cell, and every one of those names is short, capitalised and free of connective
words. The prose sat in the cells the guard never looked at.

WHAT THE DOCUMENT ITSELF SAYS, measured rather than assumed. Every real finding
on that report carries a flag AND a reference range, including the wordless ones:

    COLOR        YELLOW      flag=NORMAL    ref='YELLOW 01'
    WBC          NONE SEEN   flag=NORMAL    ref='< OR = 5 /HPF 01'
    OCCULT BLOOD 2+          flag=ABNORMAL  ref='NEGATIVE 01'

while the furniture carries neither:

    Performing Laboratory    Information:        (name and value, nothing else)
    Director: Dr Robert L    Breckenridge        (name and value, nothing else)

THE TRAP THIS FILE EXISTS TO HOLD SHUT. The obvious fix — "a real row has a
number in its value column" — is wrong, and the 13-document PHI corpus CANNOT
see that it is wrong, because every corpus document is a DaVita report with no
microscopy panel. Measured on the Quest report that rule deletes 49 of 106 rows,
taking an entire urinalysis microscopy panel and half a differential with it.

So the half of this file that matters is `test_real_findings_survive`. If a later
change gets better at removing footnotes and quietly starts eating "NONE SEEN",
the corpus harness will still report 100% and these tests are the only thing
between that change and a clinician.
"""

import pytest

from app.services.docparse.layout import Column, Row, Table
from app.services.docparse.normalize import records_from_table, row_is_prose


# ── Furniture: rows that must never reach a clinical table ───────────────────
#
# Cells are given exactly as the parser reconstructed them from the real PDF.

@pytest.mark.parametrize("cells", [
    # The lab's postal address, spread across four cells. Twelve words rejoined.
    {"name": "01: Quest Diagnostics-Houston", "value": "Lab, 5850 Rogerdale",
     "flag": "Road, Houston", "ref_range": "TX, 77072-1602, phone: ,"},
    # Name and value only — no flag, no unit, no range.
    {"name": "Director: Dr Robert L", "value": "Breckenridge"},
    {"name": "Performing Laboratory", "value": "Information:"},
    {"name": "Fasting reference", "value": "interval"},
    {"name": "SED RATE BY MODIFIED", "value": "WESTERGREN"},
    # LDL footnote, wrapped across lines.
    {"name": "LDL-C is now calculated", "value": "using the Martin-Hopkins"},
    {"name": "calculation, which is", "value": "a validated novel method"},
    {"name": "Desirable range <100", "value": "mg/dL for primary prevention;"},
    {"name": "FASTING:YES AN UPDATE OR CORRECTION TO DOB", "value": "HAS BEEN MADE"},
])
def test_document_furniture_is_rejected(cells):
    assert row_is_prose(cells) is True, f"{cells} reached the record"


# ── The half that matters: real findings that must SURVIVE ───────────────────

@pytest.mark.parametrize("cells", [
    # Urinalysis microscopy — not a number in sight, every one a real finding.
    {"name": "WBC", "value": "NONE SEEN", "flag": "NORMAL", "ref_range": "< OR = 5 /HPF 01"},
    {"name": "RBC", "value": "0-2", "flag": "NORMAL", "ref_range": "< OR = 2 /HPF 01"},
    {"name": "BACTERIA", "value": "NONE SEEN", "flag": "NORMAL", "ref_range": "NONE SEEN 01"},
    {"name": "HYALINE CAST", "value": "NONE SEEN", "flag": "NORMAL", "ref_range": "NONE SEEN /LPF 01"},
    {"name": "CASTS", "value": "DNR", "flag": "NORMAL", "ref_range": "NONE SEEN /LPF 01"},
    # "did not report" — a lab statement, not a blank. Even with no structure.
    {"name": "ABSOLUTE BAND NEUTROPHILS", "value": "DNR"},
    {"name": "CALCIUM OXALATE CRYSTALS", "value": "DNR"},
    {"name": "BUN/CREATININE RATIO", "value": "NOT APPLICABLE",
     "flag": "NORMAL", "ref_range": "6-22 (calc) 01"},
    # Qualitative chemistry, including the wordless colour/appearance rows that
    # a vocabulary-based guard would have eaten.
    {"name": "COLOR", "value": "YELLOW", "flag": "NORMAL", "ref_range": "YELLOW 01"},
    {"name": "APPEARANCE", "value": "CLEAR", "flag": "NORMAL", "ref_range": "CLEAR 01"},
    {"name": "PROTEIN", "value": "NEGATIVE", "flag": "NORMAL", "ref_range": "NEGATIVE 01"},
    {"name": "OCCULT BLOOD", "value": "2+", "flag": "ABNORMAL", "ref_range": "NEGATIVE 01"},
    {"name": "Hep B Ag", "value": "NEG"},
    # Numeric rows, with structure and without.
    {"name": "GLUCOSE", "value": "84", "unit": "mg/dL", "ref_range": "65-99"},
    {"name": "GLUCOSE", "value": "84"},
    {"name": "HEMOGLOBIN", "value": "9.4", "unit": "g/dL", "ref_range": "11.7-15.5"},
])
def test_real_findings_survive(cells):
    assert row_is_prose(cells) is False, (
        f"{cells} is a real clinical finding and was discarded"
    )


def test_a_bare_number_is_never_furniture():
    """A value with a digit survives even with no structure at all.

    Some reports print a unitless count. Losing it because the lab was terse
    would be the §3aa failure this guard exists to prevent, inverted.
    """
    assert row_is_prose({"name": "ANYTHING", "value": "84"}) is False


# ── Rows an earlier version of this guard DESTROYED ──────────────────────────
#
# Caught by measurement before shipping, never in production. The rejoined-row
# prose test counted words against `looks_like_prose`'s ceiling of 10 — a figure
# calibrated for NAMES — so an ordinary row with a long name plus flag, range and
# unit read as a sentence. It deleted a neutropenic white-cell count.
#
# Every case here is a real row from a real document. They are the reason
# `_is_plain_measurement` short-circuits ahead of the prose test.

@pytest.mark.parametrize("cells", [
    # 11 words rejoined. The value is the patient's WBC count — 2.4, LOW.
    {"name": "CBC (INCLUDES DIFF/PLT) WHITE BLOOD CELL COUNT", "value": "2.4",
     "flag": "LOW", "ref_range": "3.8-10.8", "unit": "Thousand/uL"},
    # Both eGFRs, reported separately by race on this lab's panel.
    {"name": "eGFR NON-AFR. AMERICAN", "value": "92"},
    {"name": "eGFR AFRICAN AMERICAN", "value": "106"},
    # The sed rate itself, under a name long enough to trip the ceiling.
    {"name": "SED RATE BY MODIFIED WESTERGREN", "value": "2"},
    # Corpus casualties: 6 rows per document were being removed from PDFs that
    # had previously lost nothing at all.
    {"name": "GRAN%", "value": "64.4", "unit": "%Final"},
    {"name": "HCT%", "value": "37.2 L", "unit": "%", "ref_range": "41.0 - 53.0"},
])
def test_a_long_row_with_a_real_value_is_not_prose(cells):
    assert row_is_prose(cells) is False, (
        f"{cells} is a real measurement and an earlier guard deleted it"
    )


def test_an_empty_value_is_not_this_guards_business():
    """`records_from_table` drops valueless rows itself; this must not pre-empt it."""
    assert row_is_prose({"name": "SODIUM", "value": ""}) is False


# ── Known residue — deliberately NOT claimed as handled ──────────────────────

def test_a_citation_with_digits_still_survives_this_layer():
    """Recorded so the limit is visible rather than discovered later.

    `Martin SS et al. JAMA. = 2013;310(19): 2061-2068` carries digits, so the
    name+value clause spares it, and rejoined it is six words — under the prose
    ceiling. Shape cannot separate it from a terse real row, and inventing a
    threshold that could would start eating real ones. It belongs to the review
    and learning layer, not here. This test asserts the CURRENT behaviour so a
    change that fixes it fails loudly and gets its own measurement.
    """
    cells = {"name": "Martin SS et al. JAMA.", "value": "2013;310(19): 2061-2068"}
    assert row_is_prose(cells) is False


# ── The guard has to actually run ────────────────────────────────────────────

def _table(rows: list[dict]) -> Table:
    return Table(
        columns=[Column(role=r, x_start=0.0, x_end=1.0)
                 for r in ("name", "value", "unit", "ref_range")],
        rows=[Row(cells=cells, top=float(i), page=1) for i, cells in enumerate(rows)],
        page=1,
    )


def test_the_guard_is_wired_into_record_building():
    """Defined but never called is the §3ar dead control, in a parser.

    This failed the first time it ran, for exactly that reason: the function
    existed and nothing invoked it.
    """
    table = _table([
        {"name": "GLUCOSE", "value": "84", "unit": "mg/dL", "ref_range": "65-99"},
        {"name": "01: Quest Diagnostics-Houston", "value": "Lab, 5850 Rogerdale",
         "flag": "Road, Houston", "ref_range": "TX, 77072-1602, phone: ,"},
        {"name": "WBC", "value": "NONE SEEN", "unit": "/HPF"},
        {"name": "Director: Dr Robert L", "value": "Breckenridge"},
    ])
    names = [r.raw_name for r in records_from_table(table)]
    assert "GLUCOSE" in names
    assert "WBC" in names, "a real microscopy finding was discarded"
    assert not any("Quest Diagnostics" in n for n in names), "the lab's address was imported"
    assert not any("Breckenridge" in n for n in names), "the lab director was imported"
