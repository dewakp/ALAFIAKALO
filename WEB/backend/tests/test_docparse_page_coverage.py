"""A page that contributes nothing must never disappear in silence.

THE INCIDENT. A 3-page Quest report was imported for a real patient. 46 results
from page 1 landed; pages 2 and 3 were discarded. Lost: the entire CBC —
including Hemoglobin 9.4 LOW, Hematocrit 30.2 LOW, MCV 68.0 LOW and Absolute
Neutrophils 859 LOW, a textbook microcytic anaemia with neutropenia — plus the
whole lipid panel, sed rate and TSH.

The record looked complete. `document_imports` said `page_count = 3`,
`error_detail` was empty and `notes` was null. Nothing anywhere said that two
thirds of the document had been thrown away. It was found only because someone
happened to hand us the source PDF and ask.

TWO FAULTS, both covered here:

  1. `parse_page` returned None for any page without a recognisable column
     header, and `parse_document` skipped it. Labs differ on this and the
     difference is invisible: DaVita repeats its header on all six pages of a
     report, Quest prints it once. Column geometry now carries forward, so a
     continuation page is read with the previous page's columns.

  2. Even with the parse fixed, a page CAN legitimately yield nothing. That
     must be reported rather than assumed. `pipeline.parse` now names the pages
     that produced no results in `ParseResult.notes`, which
     `document_import_service` already persists to `document_imports.notes`.

The fixtures are synthetic on purpose. The real corpus lives in
`ML/data/raw/pdf/` and is gitignored because it holds named patient records, so
a regression guard built on it could not run in CI. These reproduce the exact
geometry — a header on page 1 only — with invented values.
"""

import asyncio
import io

import pytest

from app.services.docparse import layout, pipeline
from app.services.docparse.extract import extract

pytest.importorskip("reportlab")

from reportlab.lib.pagesizes import letter  # noqa: E402
from reportlab.pdfgen import canvas  # noqa: E402

# Same x positions on every page: that is what makes the later pages readable
# from the first page's header, and it is how these reports are actually laid out.
_X_NAME, _X_VALUE, _X_FLAG, _X_RANGE = 60, 300, 380, 440

_PAGE_1 = [
    ("GLUCOSE", "84", "NORMAL", "65-99 mg/dL"),
    ("SODIUM", "140", "NORMAL", "135-146 mmol/L"),
    ("POTASSIUM", "4.2", "NORMAL", "3.5-5.3 mmol/L"),
]
# The analytes the real incident lost.
_PAGE_2 = [
    ("HEMOGLOBIN", "9.4", "LOW", "11.7-15.5 g/dL"),
    ("HEMATOCRIT", "30.2", "LOW", "35.0-45.0 %"),
    ("MCV", "68.0", "LOW", "80.0-100.0 fL"),
]


def _rows(pdf, rows, top=720):
    pdf.setFont("Helvetica", 10)
    y = top
    for name, value, flag, ref in rows:
        pdf.drawString(_X_NAME, y, name)
        pdf.drawString(_X_VALUE, y, value)
        pdf.drawString(_X_FLAG, y, flag)
        pdf.drawString(_X_RANGE, y, ref)
        y -= 18
    return y


def _header(pdf, top=720):
    pdf.setFont("Helvetica", 10)
    pdf.drawString(_X_NAME, top, "Test Name")
    pdf.drawString(_X_VALUE, top, "Result")
    pdf.drawString(_X_FLAG, top, "Flag")
    pdf.drawString(_X_RANGE, top, "Reference Range")
    return top - 20


def _build(second_page_rows, second_page_header=False) -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    _rows(pdf, _PAGE_1, _header(pdf))
    pdf.showPage()
    top = _header(pdf) if second_page_header else 720
    if second_page_rows:
        _rows(pdf, second_page_rows, top)
    else:
        pdf.setFont("Helvetica", 9)
        pdf.drawString(60, 720, "This report is confidential and intended solely")
        pdf.drawString(60, 702, "for the use of the named recipient.")
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def _parse(content: bytes):
    return asyncio.run(pipeline.parse(content, filename="fixture.pdf",
                                      content_type="application/pdf",
                                      use_model=False))


def test_a_continuation_page_without_a_header_is_still_read():
    """The incident, reproduced: page 2 repeats the columns but not the header."""
    document = extract(_build(_PAGE_2), "fixture.pdf")
    assert len(document.pages) == 2

    tables = layout.parse_document(document)
    assert sorted(t.page for t in tables) == [1, 2], (
        "page 2 was dropped — a continuation page must inherit the columns"
    )

    names = [row.get("name") for table in tables for row in table.rows]
    for analyte in ("GLUCOSE", "HEMOGLOBIN", "HEMATOCRIT", "MCV"):
        assert analyte in names, f"{analyte} missing — page 2 content was lost"


def test_the_values_on_the_inherited_page_are_read_correctly():
    """Inheriting geometry must produce right answers, not merely some rows."""
    document = extract(_build(_PAGE_2), "fixture.pdf")
    rows = {r.get("name"): r for t in layout.parse_document(document) for r in t.rows}
    assert rows["HEMOGLOBIN"].get("value") == "9.4"
    assert rows["HEMOGLOBIN"].get("flag") == "LOW"
    assert "11.7" in rows["HEMOGLOBIN"].get("ref_range")
    assert rows["MCV"].get("value") == "68.0"


def test_a_page_with_no_results_is_REPORTED_not_silently_dropped():
    """The half that matters even once parsing is fixed.

    A page really can hold nothing but boilerplate. That is fine — what is not
    fine is the reader being unable to tell. Before this, `notes` was empty and
    the import looked complete.
    """
    result = _parse(_build(None))
    assert result.records, "page 1 should still import"
    assert result.notes, "a page contributed nothing and nothing said so"
    joined = " ".join(result.notes)
    assert "page 2" in joined, f"the note must name the page: {result.notes!r}"


def test_a_fully_parsed_document_is_not_annotated():
    """The note must mean something — it cannot fire when nothing was lost."""
    result = _parse(_build(_PAGE_2, second_page_header=True))
    assert not [n for n in result.notes if "could be read from page" in n]


def test_a_page_with_its_own_header_does_not_inherit():
    """A page that starts a new table is parsed on its own terms.

    Inheritance is a fallback, never an override — otherwise a document whose
    second table has different columns would be read through the first one's
    geometry and every value would land in the wrong field.
    """
    document = extract(_build(_PAGE_2, second_page_header=True), "fixture.pdf")
    tables = {t.page: t for t in layout.parse_document(document)}
    assert set(tables) == {1, 2}
    assert tables[2].roles == tables[1].roles
    names = [row.get("name") for row in tables[2].rows]
    assert "Test Name" not in names, "the header row was parsed as a result"
