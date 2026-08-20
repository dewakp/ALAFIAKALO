"""Document parsing: geometry, not reflowed text.

Fixtures are synthesised here rather than committed, because the corpus this was
built against is real patient records (`ML/data/raw/` is gitignored for that
reason). The synthetic PDFs reproduce the *geometry* that broke the old parser,
which is the part that matters:

    1.00 -
    1051 A/G RATIO 1.8 Calc Final
    2.50

`page.extract_text()` emits those three lines in reading order, so a
line-oriented regex sees a row with no reference range and two stray numbers
belonging to nothing. Across the real corpus that lost 489 of 853 ranges, and
three of thirteen documents lost every single one.
"""

import io

import pytest

from app.services.docparse import layout, layout_matrix
from app.services.docparse.extract import extract
from app.services.docparse.metadata import extract_metadata
from app.services.docparse.normalize import (
    compute_abnormal,
    parse_reference,
    parse_value,
    records_from_table,
    split_trailing_unit,
)
from app.services.docparse.pipeline import parse

PAGE_HEIGHT = 792.0


def _pdf(draw) -> bytes:
    """Build a one-page PDF by placing strings at exact coordinates.

    `draw(put)` receives `put(x, top, text)` using top-down coordinates so the
    fixtures read like the document they imitate.
    """
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    pdf.setFont("Helvetica", 8)
    draw(lambda x, top, text: pdf.drawString(x, PAGE_HEIGHT - top, text))
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def _lab_header(put, result_x=198.0, unit_x=331.0, ref_x=386.0, status_x=445.0):
    put(27.0, 199.3, "CODE")
    put(68.0, 199.3, "LAB TEST NAME")
    put(result_x, 199.3, "RESULT")
    put(unit_x, 199.3, "UNIT")
    put(ref_x, 195.0, "REFERENCE")
    put(ref_x, 203.5, "RANGE")
    put(status_x, 199.3, "STATUS")


def wrapped_range_pdf() -> bytes:
    """The layout that defeated the old parser: range above and below the row."""

    def draw(put):
        put(27.0, 120.0, "Lab Draw Report")
        put(27.0, 140.0, "Rivera, Dana K. Female | Age: 44 | DOB: 02/02/1982 | MPI: 5550001")
        put(27.0, 160.0, "Collection Date/Time")
        put(180.0, 160.0, "Ordering Provider(s)")
        put(27.0, 172.0, "03/14/2026")
        put(180.0, 172.0, "Okafor, N MD")
        _lab_header(put)

        # A/G RATIO — range wraps around the anchor row.
        put(386.0, 224.0, "1.00 -")
        put(27.0, 232.0, "1051")
        put(68.0, 232.0, "A/G RATIO")
        put(198.0, 232.0, "1.8")
        put(331.0, 232.0, "Calc")
        put(445.0, 232.0, "Final")
        put(386.0, 240.0, "2.50")

        # ALBUMIN — same wrap, with a unit.
        put(386.0, 256.0, "3.40 -")
        put(27.0, 264.0, "1002")
        put(68.0, 264.0, "ALBUMIN")
        put(198.0, 264.0, "4.6")
        put(331.0, 264.0, "g/dL")
        put(445.0, 264.0, "Final")
        put(386.0, 272.0, "4.80")

        # ALK PHOS — abnormal high, flagged by the lab.
        put(386.0, 288.0, "46.00 -")
        put(27.0, 296.0, "1001")
        put(68.0, 296.0, "ALK PHOS")
        put(198.0, 296.0, "637 H")
        put(331.0, 296.0, "U/L")
        put(445.0, 296.0, "Final")
        put(386.0, 304.0, "116.00")

        # A test name that itself wraps over three lines.
        put(68.0, 320.0, "ACTUAL DAYS/WEEK")
        put(27.0, 328.0, "1959")
        put(198.0, 328.0, "6")
        put(445.0, 328.0, "Final")
        put(68.0, 336.0, "TREATED")

    return _pdf(draw)


def inline_range_pdf() -> bytes:
    """The other variant: ranges inline, and different column positions."""

    def draw(put):
        put(27.0, 120.0, "Lab Draw Report")
        put(27.0, 140.0, "Rivera, Dana K. Female | Age: 44 | DOB: 02/02/1982")
        put(27.0, 160.0, "Collection Date/Time")
        put(27.0, 172.0, "01/27/2026")
        _lab_header(put, result_x=170.0, unit_x=243.0, ref_x=298.0, status_x=387.0)

        put(27.0, 232.0, "1002")
        put(68.0, 232.0, "ALB")
        put(170.0, 232.0, "4.1")
        put(243.0, 232.0, "g/dL")
        put(298.0, 232.0, "3.4 - 4.8")
        put(387.0, 232.0, "Final")

        # A bounded result and a wrapped unit.
        put(27.0, 248.0, "1012")
        put(68.0, 248.0, "ALT/SGPT")
        put(170.0, 248.0, "< 9 L")
        put(243.0, 244.0, "x 10^6")
        put(243.0, 252.0, "cells/uL")
        put(298.0, 248.0, "10.0 - 49.0")
        put(387.0, 248.0, "Final")

    return _pdf(draw)


def trend_matrix_pdf() -> bytes:
    """Analyte × period grid, two blocks side by side, dates under the values."""

    def draw(put):
        put(18.0, 23.0, "IDT Patient Profile Worksheet")
        put(18.0, 48.0, "Rivera, Dana K. DOB: 02/02/1982 | MPI: 5550001")
        put(26.0, 156.0, "MONTHLY LABS")

        put(26.0, 174.7, "ANEMIA")
        put(111.0, 174.7, "SEP 2025")
        put(180.0, 174.7, "AUG 2025")
        put(248.0, 174.7, "JUL 2025")
        put(317.0, 174.7, "ADEQUACY")
        put(406.0, 174.7, "SEP 2025")
        put(475.0, 174.7, "AUG 2025")
        put(544.0, 174.7, "JUL 2025")

        put(26.0, 185.9, "HEMOGLOBIN (g/dL)")
        put(109.0, 185.9, "13.2")
        put(178.0, 185.9, "12.4")
        put(247.0, 185.9, "12.8")
        put(317.0, 185.9, "SPKT/V")
        put(405.0, 185.9, "1.65")
        put(474.0, 185.9, "1.61")
        put(542.0, 185.9, "N/A")

        put(149.0, 195.7, "(09/03)")
        put(217.0, 195.7, "(08/13)")
        put(287.0, 195.7, "(07/17)")

        put(26.0, 206.9, "FERRITIN (ng/mL)")
        put(109.0, 206.9, "182")
        put(178.0, 206.9, "186")
        put(247.0, 206.9, "178")

    return _pdf(draw)


# ── Value parsing ────────────────────────────────────────────────────────────

class TestValueParsing:
    def test_plain_number(self):
        assert parse_value("4.6") == (4.6, None, None)

    def test_high_flag_is_kept_and_stripped(self):
        value, text, abnormal = parse_value("637 H")
        assert (value, text, abnormal) == (637.0, None, True)

    def test_bounded_result_keeps_both_forms(self):
        """"< 9" is not the number 9 — the bound has to survive."""
        value, text, _ = parse_value("< 9")
        assert value == 9.0
        assert text == "< 9"

    def test_error_is_a_result_not_a_blank(self):
        """A failed draw is a clinical fact; dropping it hides that."""
        assert parse_value("Error") == (None, "Error", None)

    def test_placeholder_is_not_a_result(self):
        assert parse_value("-") == (None, None, None)

    def test_reactive_is_abnormal(self):
        assert parse_value("Reactive")[2] is True


class TestReferenceParsing:
    def test_two_sided_range(self):
        assert parse_reference("3.40 - 4.80") == (3.4, 4.8, "3.40 - 4.80")

    def test_reassembled_wrapped_range(self):
        """This is the string the layout engine rebuilds from two fragments."""
        assert parse_reference("1.00 - 2.50")[:2] == (1.0, 2.5)

    def test_upper_bound_only(self):
        assert parse_reference("< 5.6")[:2] == (None, 5.6)

    def test_en_dash_is_a_range(self):
        assert parse_reference("46.00 – 116.00")[:2] == (46.0, 116.0)


class TestAbnormal:
    def test_lab_flag_wins_over_range(self):
        assert compute_abnormal(5.0, 1.0, 10.0, True) is True

    def test_derived_from_range_when_unflagged(self):
        assert compute_abnormal(637.0, 46.0, 116.0, None) is True
        assert compute_abnormal(4.6, 3.4, 4.8, None) is False

    def test_unknown_without_a_range(self):
        assert compute_abnormal(4.6, None, None, None) is None


class TestUnitSplitting:
    def test_unit_is_split_off_the_name(self):
        assert split_trailing_unit("HEMOGLOBIN (g/dL)") == ("HEMOGLOBIN", "g/dL")

    def test_compound_unit_is_still_a_unit(self):
        assert split_trailing_unit("WBC (x 10^3 cells/uL)") == ("WBC", "x 10^3 cells/uL")

    def test_qualifier_stays_part_of_the_name(self):
        assert split_trailing_unit("VITAMIN D (25-OH)") == ("VITAMIN D (25-OH)", None)
        assert split_trailing_unit("STDKT/V (DIAL)") == ("STDKT/V (DIAL)", None)


# ── Layout ───────────────────────────────────────────────────────────────────

class TestWrappedColumnLayout:
    @pytest.fixture(scope="class")
    def rows(self):
        document = extract(wrapped_range_pdf(), "wrapped.pdf")
        tables = layout.parse_document(document)
        assert tables, "no table was reconstructed"
        return {r.get("name"): r for r in tables[0].rows}

    def test_range_printed_above_and_below_rejoins(self, rows):
        assert rows["A/G RATIO"].get("ref_range") == "1.00 - 2.50"

    def test_every_row_keeps_its_own_range(self, rows):
        assert rows["ALBUMIN"].get("ref_range") == "3.40 - 4.80"
        assert rows["ALK PHOS"].get("ref_range") == "46.00 - 116.00"

    def test_a_wrapped_test_name_is_reassembled(self, rows):
        assert "ACTUAL DAYS/WEEK TREATED" in rows

    def test_values_land_in_the_value_column(self, rows):
        assert rows["ALBUMIN"].get("value") == "4.6"
        assert rows["ALK PHOS"].get("value") == "637 H"

    def test_no_phantom_row_from_the_wrapped_header(self, rows):
        assert not any("RANGE" == name for name in rows)


class TestInlineColumnLayout:
    """Same code, different column positions — nothing may be hardcoded."""

    @pytest.fixture(scope="class")
    def rows(self):
        document = extract(inline_range_pdf(), "inline.pdf")
        tables = layout.parse_document(document)
        assert tables
        return {r.get("name"): r for r in tables[0].rows}

    def test_inline_range_is_read(self, rows):
        assert rows["ALB"].get("ref_range") == "3.4 - 4.8"

    def test_wrapped_unit_is_reassembled(self, rows):
        assert rows["ALT/SGPT"].get("unit") == "x 10^6 cells/uL"

    def test_bounded_value_survives_the_columns(self, rows):
        assert rows["ALT/SGPT"].get("value") == "< 9 L"


class TestNoTableIsNotAnEmptyTable:
    def test_a_document_without_a_header_yields_no_table(self):
        """Better nothing than a fabricated table.

        Scoring alone found three "roles" in ordinary prose — "Full Code",
        "Modality Status", "Start Date" — and invented rows beneath them.
        """
        def draw(put):
            put(27.0, 100.0, "Advance Care Plan Status: Full Code")
            put(27.0, 112.0, "Modality Status: Home Hemodialysis")
            put(27.0, 124.0, "Actual Start Date: 03/30/2017")

        assert layout.parse_document(extract(_pdf(draw), "prose.pdf")) == []


class TestTrendMatrix:
    @pytest.fixture(scope="class")
    def cells(self):
        document = extract(trend_matrix_pdf(), "matrix.pdf")
        table = layout_matrix.parse_page(document.pages[0])
        assert table is not None, "no matrix was reconstructed"
        return table.cells

    def test_each_period_becomes_its_own_cell(self, cells):
        hgb = {c.period: c.value for c in cells if c.analyte.startswith("HEMOGLOBIN")}
        assert hgb == {"SEP 2025": "13.2", "AUG 2025": "12.4", "JUL 2025": "12.8"}

    def test_the_right_shifted_date_belongs_to_its_own_value(self, cells):
        september = next(
            c for c in cells
            if c.analyte.startswith("HEMOGLOBIN") and c.period == "SEP 2025"
        )
        assert september.cell_date == "09/03"

    def test_side_by_side_blocks_stay_separate(self, cells):
        """A visual line spans both grids; it is not one row."""
        spkt = [c for c in cells if c.analyte == "SPKT/V"]
        assert {c.value for c in spkt} == {"1.65", "1.61", "N/A"}


# ── Metadata ─────────────────────────────────────────────────────────────────

class TestMetadata:
    def test_collection_date_is_not_the_date_of_birth(self):
        """The old parser took the first date in the file — always the DOB."""
        meta = extract_metadata(extract(wrapped_range_pdf(), "wrapped.pdf"))
        assert str(meta.report_date) == "2026-03-14"
        assert str(meta.report_date) != "1982-02-02"

    def test_provider_does_not_absorb_the_next_column(self):
        meta = extract_metadata(extract(wrapped_range_pdf(), "wrapped.pdf"))
        assert meta.ordering_provider == "Okafor, N MD"


# ── Normalization + pipeline ─────────────────────────────────────────────────

class TestRecords:
    def test_records_carry_range_value_and_abnormality(self):
        document = extract(wrapped_range_pdf(), "wrapped.pdf")
        table = layout.parse_document(document)[0]
        records = {r.test_name: r for r in records_from_table(table)}

        albumin = records["Albumin"]
        assert (albumin.value, albumin.unit) == (4.6, "g/dL")
        assert (albumin.reference_low, albumin.reference_high) == (3.4, 4.8)
        assert albumin.is_abnormal is False

        alk = records["Alk Phos"]
        assert alk.value == 637.0
        assert alk.is_abnormal is True
        assert alk.category == "Liver & Protein"


@pytest.mark.asyncio
class TestPipeline:
    async def test_a_lab_report_is_classified_and_read(self):
        result = await parse(wrapped_range_pdf(), "wrapped.pdf", use_model=False)
        assert result.doc_type == "lab_report"
        assert result.layout_kind == "columns"
        assert result.ok
        assert result.error_detail is None

    async def test_a_trend_grid_falls_through_to_the_matrix_reader(self):
        result = await parse(trend_matrix_pdf(), "matrix.pdf", use_model=False)
        assert result.layout_kind == "matrix"
        assert result.ok

    async def test_an_unreadable_file_explains_itself(self):
        """Never an empty success — that reads as "nothing was in the document"."""
        result = await parse(b"%PDF-1.7\nbroken", "broken.pdf", use_model=False)
        assert not result.ok
        assert result.error_detail

    async def test_a_scan_says_it_needs_ocr(self):
        blank = _pdf(lambda put: None)
        result = await parse(blank, "scan.pdf", use_model=False)
        assert result.extraction_method == "needs_ocr"
        assert "text recognition" in (result.error_detail or "").lower()

    async def test_the_same_file_hashes_the_same_under_any_name(self):
        """The hash is what makes re-uploading a file idempotent.

        It is taken over the bytes, so two *generations* of an equivalent PDF
        differ (reportlab stamps a creation time) while the same file uploaded
        twice does not. The filename must not enter into it.
        """
        content = wrapped_range_pdf()
        first = await parse(content, "labs.pdf", use_model=False)
        second = await parse(content, "labs-copy.pdf", use_model=False)
        assert first.content_hash == second.content_hash
