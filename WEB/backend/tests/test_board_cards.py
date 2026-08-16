"""Category cards: the domain layer between a trend line and a raw table.

Neither a line nor a table answers "is this patient's potassium safe this week".
These tests pin the two judgements that make the cards trustworthy rather than
decorative:

  - a meal whose nutrients were never estimated must not be averaged in as a
    zero-calorie meal, and
  - every category that has data must produce a card, so the board is not "two
    rich screens and eleven bare tables".
"""

from datetime import date, timedelta

import pytest

from app.services import patient_board as board


def _series(label, unit, values, start=date(2026, 8, 1)):
    return {"label": label, "unit": unit,
            "points": [{"date": str(start + timedelta(days=i)), "value": v}
                       for i, v in enumerate(values)]}


def test_default_cards_report_latest_and_range():
    detail = board.Detail(series=[_series("Weight", "kg", [55.1, 54.0, 56.2])])
    cards = board.default_cards(detail, 90)
    labels = [c["label"] for c in cards]
    assert labels == ["Most recent", "Range over 90 days"]

    latest = cards[0]["items"][0]
    assert latest["value"] == 56.2, "the most recent point must be the last one"
    assert "2026-08-03" in latest["note"]

    rng = cards[1]["items"][0]
    assert rng["value"] == "54 – 56.2"
    assert "3 readings" in rng["note"]


def test_a_measure_with_no_points_contributes_nothing():
    """No card may invent a value for a measure that was never recorded."""
    detail = board.Detail(series=[_series("Weight", "kg", []),
                                  _series("Pulse", "bpm", [70, 72])])
    cards = board.default_cards(detail, 30)
    for card in cards:
        assert [i["label"] for i in card["items"]] == ["Pulse"]


def test_a_single_reading_is_not_described_as_a_range():
    detail = board.Detail(series=[_series("Weight", "kg", [55.1])])
    rng = board.default_cards(detail, 30)[1]["items"][0]
    assert rng["note"].endswith("1 reading"), rng["note"]


def test_categories_without_series_still_get_a_card():
    """Conditions, journal and connected records are lists, not measurements."""
    detail = board.Detail(
        columns=[{"key": "date", "label": "Date"}, {"key": "name", "label": "Condition"},
                 {"key": "severity", "label": "Severity"}],
        rows=[{"date": "2026-08-01", "name": "ESRD", "severity": "severe"},
              {"date": "2026-07-01", "name": "Anaemia", "severity": "moderate"}],
    )
    cards = board.default_cards(detail, 90)
    assert len(cards) == 1
    assert [i["label"] for i in cards[0]["items"]] == ["ESRD", "Anaemia"]
    assert "2 records" in cards[0]["note"]


def test_a_truly_empty_category_gets_no_card():
    """An empty category must stay empty rather than grow a card saying nothing."""
    assert board.default_cards(board.Detail(), 90) == []


def test_row_cards_say_how_many_are_not_shown():
    detail = board.Detail(
        columns=[{"key": "date", "label": "Date"}, {"key": "name", "label": "Name"}],
        rows=[{"date": "2026-08-01", "name": f"row {i}"} for i in range(10)],
    )
    note = board.default_cards(detail, 90)[0]["note"]
    assert "10 records" in note and "4 more below" in note


class _Lab:
    """Just the fields lab_is_abnormal reads."""

    def __init__(self, value=None, low=None, high=None, is_abnormal=None):
        self.value = value
        self.reference_range_low = low
        self.reference_range_high = high
        self.is_abnormal = is_abnormal


def test_the_labs_own_flag_always_wins():
    """Deriving is a fallback. A lab that says 'normal' is not overruled."""
    assert board.lab_is_abnormal(_Lab(618, 46, 116, is_abnormal=False)) is False
    assert board.lab_is_abnormal(_Lab(4.2, 3.4, 4.8, is_abnormal=True)) is True


def test_out_of_range_is_derived_when_the_lab_did_not_flag_it():
    """is_abnormal is NULL on all 422 results in the reference record, and 136
    of them sit outside their own reference range."""
    assert board.lab_is_abnormal(_Lab(618, 46, 116)) is True      # Alk Phos
    assert board.lab_is_abnormal(_Lab(6.0, 3.5, 5.5)) is True     # K+, hyperkalaemia
    assert board.lab_is_abnormal(_Lab(85, 140, 450)) is True      # platelets, low
    assert board.lab_is_abnormal(_Lab(4.2, 3.4, 4.8)) is False    # albumin, normal


def test_a_one_sided_range_still_flags():
    assert board.lab_is_abnormal(_Lab(50, None, 33)) is True
    assert board.lab_is_abnormal(_Lab(20, None, 33)) is False
    assert board.lab_is_abnormal(_Lab(1, 4.6, None)) is True


def test_unknowable_stays_unknown_rather_than_normal():
    """No range or no value must not read as 'fine' — that is a false negative
    on a screen a clinician scans for exactly these."""
    assert board.lab_is_abnormal(_Lab(1.62, None, None)) is None   # BSA Dubois
    assert board.lab_is_abnormal(_Lab(None, 3.4, 4.8)) is None
