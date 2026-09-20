"""What the lab importer refuses, and what it must never invent.

Every case here comes from the real corpus (`ML/data/processed/unified_labs.csv`,
9,660 rows, 2016-2026), not from cases someone imagined. The counts in the
comments are what a dry run against that file actually reports.

The importer is the only dedupe there is: `lab_results` carries a primary key
and two plain indexes and NO unique constraint, so nothing in the database
stops a duplicate row. That is why these tests exist at all.
"""

from datetime import date

import pytest

from scripts.import_unified_labs import Row, resolve_conflicts


def raw(**overrides) -> dict:
    """A CSV line with the columns the real file has."""
    row = {
        "date": "2021-06-08", "test_name": "Ferritin", "value": "",
        "unit": "ng/mL", "clinical_pref": "", "facility": "",
        "value_numeric": "186.0", "value_text": "", "source": "records_xlsx",
        "source_file": "", "code": "", "flag": "", "ref_low": "", "ref_high": "",
        "status": "Final", "panel_name": "", "lab_name": "", "reference_range": "",
    }
    row.update(overrides)
    return row


# ── What becomes a value ──────────────────────────────────────────────


def test_a_number_becomes_a_number():
    row = Row(raw(value_numeric="186.0"))
    assert row.usable
    assert row.value == 186.0
    assert row.value_string is None
    assert row.day == date(2021, 6, 8)
    assert row.key == "ferritin"


def test_a_spreadsheet_error_is_refused_not_stored_as_text():
    """76 rows carry `#DIV/0!`. A failed formula is not a result.

    Storing it as a string would put "#DIV/0!" in front of a clinician as
    though the lab had reported it — §3ab's boilerplate-as-a-lab-result, from a
    spreadsheet instead of a PDF footer.
    """
    row = Row(raw(value_numeric="", value_text="#DIV/0!"))
    assert not row.usable
    assert row.reason == "spreadsheet error"
    assert row.value is None and row.value_string is None


def test_a_qualitative_result_is_kept_as_written():
    """45 rows read NEG, 12 Negative, plus Reactive/Nonreactive. Real results."""
    row = Row(raw(value_numeric="", value_text="Nonreactive"))
    assert row.usable
    assert row.value is None
    assert row.value_string == "Nonreactive"


@pytest.mark.parametrize("written", [">1000", "> 1000", "<10", "< 10", "1+"])
def test_a_censored_value_is_never_coerced_to_a_number(written):
    """">1000" forced to 1000.0 is a measurement nobody made.

    The true value is unknown and greater than the bound; asserting the bound
    as the result understates it and looks measured (§3am).
    """
    row = Row(raw(value_numeric="", value_text=written))
    assert row.value is None, "a censored value must not become a float"
    assert row.value_string == written


def test_a_row_with_no_value_at_all_is_refused():
    """68 rows — nPCR, Kt/V variants, Hep B Ag — carry neither number nor word.

    Written with a NULL value it renders as a test that was run and came back
    blank, which is not what the record says (§3aa).
    """
    row = Row(raw(value_numeric="", value_text=""))
    assert not row.usable
    assert row.reason == "no value"


def test_an_unreadable_date_is_refused():
    assert not Row(raw(date="")).usable
    assert not Row(raw(date="not-a-date")).usable


# ── The lab's own flag ────────────────────────────────────────────────


@pytest.mark.parametrize("flag", ["L", "H", "l", "h"])
def test_a_flagged_result_is_marked_abnormal(flag):
    assert Row(raw(flag=flag)).abnormal is True


def test_no_flag_means_the_lab_said_NOTHING_not_that_it_was_normal():
    """`is_abnormal=False` asserts the lab called it normal. It did not.

    Only 203 of 9,660 rows carry a flag at all, so defaulting the rest to False
    would manufacture 9,457 statements of normality (§3aa).
    """
    assert Row(raw(flag="")).abnormal is None


# ── Dedupe, which is the only dedupe there is ─────────────────────────


def test_the_same_value_twice_on_one_day_is_one_result():
    """2 pairs agree: `pdf_davita` and `firestore` reporting the same A1c."""
    rows = [Row(raw(source="pdf_davita")), Row(raw(source="firestore"))]
    kept, conflicts = resolve_conflicts(rows)
    assert len(kept) == 1
    assert conflicts == []


def test_two_different_values_on_one_day_are_BOTH_dropped():
    """25 pairs disagree, every one `records_xlsx` against itself.

    `hemoglobin 5.3 vs 7.7`, `creatinine 20.2 vs 9.2`, `CO2 22.0 vs 2.0`.
    Choosing the first, the last or the larger would be inventing a fact, and
    writing both leaves the patient holding two contradictory results for one
    date — the §3ab duplicate, which no database constraint here would catch.
    """
    rows = [Row(raw(value_numeric="5.3")), Row(raw(value_numeric="7.7"))]
    kept, conflicts = resolve_conflicts(rows)
    assert kept == []
    assert len(conflicts) == 1
    day, key, stated = conflicts[0]
    assert key == "ferritin"
    assert stated == ["5.3", "7.7"], "the report must name both values"


def test_two_spellings_of_one_analyte_are_one_analyte():
    """Comparing raw names reports 9,064 new rows; comparing the analyte
    reports 8,997. Those 67 are the same test under a second spelling.

    "FERR" and "Ferritin" on one date is one result recorded twice, not two
    results. Compared by name it is written again, beside the row it
    duplicates (§3ax).
    """
    rows = [Row(raw(test_name="FERR")), Row(raw(test_name="Ferritin"))]
    assert rows[0].key == rows[1].key == "ferritin"

    kept, conflicts = resolve_conflicts(rows)
    assert len(kept) == 1 and conflicts == []


def test_the_same_analyte_on_DIFFERENT_days_is_two_results():
    rows = [Row(raw(date="2021-06-08")), Row(raw(date="2021-06-22"))]
    kept, conflicts = resolve_conflicts(rows)
    assert len(kept) == 2 and conflicts == []


# ── Provenance travels with the row ───────────────────────────────────


def test_the_row_records_where_it_came_from():
    """A decade of imported history must be traceable to its source file."""
    row = Row(raw(source="pdf_davita", source_file="Labs.pdf", code="1051.0"))
    assert "unified_labs.csv" in row.provenance
    assert "pdf_davita" in row.provenance
    assert "Labs.pdf" in row.provenance
    # `code` is an internal panel number, NOT a LOINC code. It is recorded as
    # provenance rather than asserted in `loinc_code`, where it would claim to
    # be a standard identifier it is not (§3ad).
    assert "1051.0" in row.provenance


def test_a_missing_code_column_does_not_break_the_row():
    payload = raw()
    payload.pop("code")
    assert Row(payload).usable
