"""Drugs given during dialysis, parsed out of the flowsheet free-text field.

CLAUDE.md §3aa names two medication tables. There is a third —
`therapy_sessions.drugs_administered` — and on a real record it holds a decade
of ESA and IV iron that appears in neither of the other two:

    Epogene 1,962 sessions · Venofer 1,248 · Doxercalciferol 788
    ...and 0 rows in medication_dose_logs.

Every parsing case below is taken from that corpus, not invented.
"""

import pytest

from app.services.flowsheet_drugs import (
    parse_drugs_administered,
    summarize_flowsheet_drugs,
)


def names(text):
    return [d.name for d in parse_drugs_administered(text)]


# ── The trap in the real data ─────────────────────────────────────────


def test_semicolon_inside_parentheses_is_not_a_separator():
    """`text.split(";")` invents a drug called "3ml Arterial)".

    This exact record appears in the corpus. Splitting naively turns one
    catheter-lock entry into two, one of which is not a drug at all.
    """
    drugs = parse_drugs_administered(
        "Sodium Citrate (12 ml  Venous; 3ml Arterial); Epogene (3,000 SQ); Venofer (100 mg)"
    )
    assert [d.name for d in drugs] == ["Sodium citrate", "Epoetin alfa", "Iron sucrose"]
    assert drugs[0].dose == "12 ml  Venous; 3ml Arterial"


# ── Grouping ──────────────────────────────────────────────────────────


def test_case_and_truncation_group_to_one_drug():
    """`venofer`/`Venofer` and `Doxercalcif`/`Doxercalciferol` are each ONE drug.

    The same case-sensitivity trap §3aa documents for dose logs: two spellings
    of one drug misstate the regimen.
    """
    assert names("venofer (100 mg)") == names("Venofer (100 mg)") == ["Iron sucrose"]
    assert names("Doxercalcif (4mcg)") == names("Doxercalciferol (4 mcg)") == ["Doxercalciferol"]


@pytest.mark.parametrize(
    "written,canonical,klass",
    [
        ("Epogene (20,000 SQ)", "Epoetin alfa", "ESA"),
        ("Aranesp (60 mcg)", "Darbepoetin alfa", "ESA"),
        ("Venofer (100 mg)", "Iron sucrose", "IV iron"),
        ("Doxercalcif (2 mcg)", "Doxercalciferol", "vitamin D analogue"),
        ("Heparin (5000 units)", "Heparin", "anticoagulant"),
    ],
)
def test_drug_class_is_available_for_driver_analysis(written, canonical, klass):
    """An ESA on board means an anaemia is being TREATED.

    That is the difference between "eat more iron" and "the ESA is working",
    so the class has to survive parsing, not just the name.
    """
    d = parse_drugs_administered(written)[0]
    assert (d.name, d.drug_class) == (canonical, klass)
    assert d.is_esa == (klass == "ESA")


# ── Doses ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text,dose",
    [
        ("Epogene (20,000 SQ)", "20,000 SQ"),
        ("Venofer (100mg)", "100mg"),
        ("Sodium Citrate (1.8 ml x 2)", "1.8 ml x 2"),
    ],
)
def test_dose_is_kept_verbatim(text, dose):
    # Never normalised into a number: "20,000 SQ" is subcutaneous units and
    # "100 mg" is milligrams. Inventing a unit is worse than keeping the text.
    assert parse_drugs_administered(text)[0].dose == dose


@pytest.mark.parametrize("text", ["Epogene (NONE)", "Epogene (Oct)", "Epogene"])
def test_non_doses_are_not_recorded_as_doses(text):
    """`(NONE)` and `(Oct)` both occur in the corpus. Neither is a dose."""
    d = parse_drugs_administered(text)[0]
    assert d.name == "Epoetin alfa"
    assert d.dose is None


# ── Unknown drugs ─────────────────────────────────────────────────────


def test_unrecognised_drug_is_kept_verbatim_not_guessed():
    """A wrong drug name on a medication list is worse than an unmapped one.

    "Flucel Vax" (a flu vaccine) is in the corpus and maps to nothing.
    """
    d = parse_drugs_administered("Flucel Vax (5 ml)")[0]
    assert d.name == "Flucel Vax"
    assert d.recognised is False
    assert d.drug_class is None


@pytest.mark.parametrize("text", [None, "", "   "])
def test_empty_input_is_empty_not_an_error(text):
    # A flowsheet with no drugs must not break the screen that shows it.
    assert parse_drugs_administered(text) == []


# ── Rollup ────────────────────────────────────────────────────────────


class _Session:
    def __init__(self, drugs, when):
        self.drugs_administered = drugs
        self.scheduled_date = when


def test_summary_counts_sessions_and_tracks_the_period():
    sessions = [
        _Session("Epogene (3,000 SQ); Venofer (100 mg)", "2024-01-01"),
        _Session("Epogene (20,000 SQ)", "2024-06-01"),
        _Session("epogene", "2025-01-01"),
    ]
    by_name = {e.name: e for e in summarize_flowsheet_drugs(sessions)}
    esa = by_name["Epoetin alfa"]
    assert esa.sessions == 3
    assert (esa.first_seen, esa.last_seen) == ("2024-01-01", "2025-01-01")
    # Latest dose is the most recent one that HAD a dose, not the last row.
    assert esa.latest_dose == "20,000 SQ"
    assert by_name["Iron sucrose"].sessions == 1


def test_summary_is_ordered_by_how_often_the_drug_was_given():
    sessions = [_Session("Epogene", "2024-01-01")] * 3 + [_Session("Venofer", "2024-02-01")]
    assert [e.name for e in summarize_flowsheet_drugs(sessions)][0] == "Epoetin alfa"
