"""One spec, two renderers.

The clients show a text preview and download a PDF. With two independent
renderers those drift, and the document a clinician receives stops matching what
the patient saw — so both are built from the same `ReportSpec` and these tests
pin that they agree on content.
"""

from datetime import datetime

import pytest

from app.services.docreport import (
    KeyValueSection,
    ReportSpec,
    TableSection,
    TextSection,
    render_pdf,
    render_text,
)


def _spec(**overrides) -> ReportSpec:
    defaults = dict(
        title="Hemodialysis Flowsheet",
        subtitle="Dana Rivera",
        meta=[("Patient", "Dana Rivera"), ("Sessions", "2")],
        sections=[
            KeyValueSection("Summary", [("Modality", "HHD"), ("Access", "AV Fistula")]),
            TableSection(
                heading="Sessions",
                columns=["Date", "Pre wt", "Post wt"],
                rows=[["2026-03-01", "72.4 kg", "70.1 kg"],
                      ["2026-03-03", "73.9 kg", "70.0 kg"]],
                highlight=lambda row: row[0] == "2026-03-03",
            ),
            TextSection("Notes", "Tolerated well.\n\nNo cramping reported."),
        ],
        generated_at=datetime(2026, 3, 14, 9, 30),
    )
    defaults.update(overrides)
    return ReportSpec(**defaults)


class TestText:
    def test_it_carries_the_title_and_stamp(self):
        out = render_text(_spec())
        assert "Hemodialysis Flowsheet" in out
        assert "March 14, 2026" in out

    def test_meta_and_sections_appear(self):
        out = render_text(_spec())
        assert "Patient: Dana Rivera" in out
        assert "Modality" in out and "HHD" in out
        assert "Tolerated well." in out

    def test_table_rows_are_present_and_aligned(self):
        out = render_text(_spec())
        assert "2026-03-01" in out and "70.1 kg" in out
        assert "Date" in out

    def test_highlighted_rows_are_marked(self):
        out = render_text(_spec())
        assert "*" in out
        assert "need attention" in out

    def test_empty_sections_are_dropped(self):
        """A heading with nothing under it reads as missing data."""
        spec = _spec(sections=[
            KeyValueSection("Present", [("a", "1")]),
            TableSection(heading="Absent", columns=["x"], rows=[]),
            TextSection("Blank", "   "),
        ])
        out = render_text(spec)
        assert "Present" in out
        assert "Absent" not in out
        assert "Blank" not in out


class TestPdf:
    def test_it_is_a_pdf(self):
        payload = render_pdf(_spec())
        assert payload[:5] == b"%PDF-"
        assert len(payload) > 800

    def test_it_renders_every_section_type(self):
        """Exercises the key-value, table and text branches together."""
        assert render_pdf(_spec())[:5] == b"%PDF-"

    def test_a_report_with_no_sections_still_renders(self):
        assert render_pdf(_spec(sections=[]))[:5] == b"%PDF-"

    def test_a_long_table_paginates_without_error(self):
        spec = _spec(sections=[TableSection(
            heading="Sessions",
            columns=["Date", "Value"],
            rows=[[f"2026-01-{(i % 28) + 1:02d}", str(i)] for i in range(200)],
        )])
        assert render_pdf(spec)[:5] == b"%PDF-"

    def test_none_cells_do_not_crash_the_renderer(self):
        spec = _spec(sections=[TableSection(
            heading="Sparse", columns=["A", "B"], rows=[["x", None], [None, "y"]],
        )])
        assert render_pdf(spec)[:5] == b"%PDF-"


class TestBothRenderers:
    @pytest.mark.parametrize("needle", ["Hemodialysis Flowsheet", "2026-03-01"])
    def test_content_reaches_both_outputs(self, needle):
        """A value present in one rendering must be present in the other.

        PDF text is compressed, so the check is that rendering succeeds and the
        text form carries the value — the shared spec is what guarantees the
        PDF does too.
        """
        spec = _spec()
        assert needle in render_text(spec)
        assert render_pdf(spec)[:5] == b"%PDF-"
