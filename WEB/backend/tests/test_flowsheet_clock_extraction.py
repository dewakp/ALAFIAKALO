"""Pin the flowsheet clock rules. Every one was a SILENT wrong answer.

`scripts/extract_flowsheet_clocks.py` and `scripts/backfill_session_clock.py`
fill `actual_start_time`, `actual_end_time`, `machine_total_time_minutes` and
the treatment totals from the Excel flowsheets — 3,748 values on a table that
held the clock on 49 of 2,032 rows and machine time on 4.

None of the faults these tests pin ever raised. Each produced a plausible wrong
number that was written, or a real sheet that was dropped without being counted,
and each was found only by making the extractor report what it refused. A dry
run against production is evidence today; this file is evidence next month.

Run:
    docker compose --profile test run --rm backend-test \\
        python -m pytest tests/test_flowsheet_clock_extraction.py -v
"""

from __future__ import annotations

import datetime
import importlib.util
import pathlib
import sys
import types

import pytest

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader, f"cannot load {name}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# The BACKFILL's gates need no openpyxl and must always run in the backend
# image — they are the rules that decide what reaches a clinical column. But
# the module imports `app.core.database`, so it cannot load under
# ML/.venv-health-ml, which is the only interpreter that HAS openpyxl. Guard
# each import symmetrically: either set of tests must be runnable without the
# other's dependency, or one of the two can never be executed anywhere.
try:
    backfill = _load("backfill_session_clock")
    _NO_APP = None
except Exception as exc:  # pragma: no cover - environment
    backfill = None
    _NO_APP = f"backfill_session_clock needs the app package ({exc})"

needs_app = pytest.mark.skipif(_NO_APP is not None, reason=_NO_APP or "")

# openpyxl is STUBBED for the load, following the pattern in
# `tests/test_flowsheet_import_salvage.py`. The backend image deliberately
# carries no xlsx dependency — the app never reads .xlsx, and document import
# uses pdfplumber — so adding one to the production image to satisfy a test
# would be the wrong trade.
#
# The stub is honest only under a condition this file has to keep: NONE of the
# functions tested here touches openpyxl. `classify_sheet`, `read_time`,
# `read_duration_minutes`, `read_number` and `value_cells` take cell VALUES and
# plain integers, never a worksheet; only `extract_sheet` and `main` reach into
# the library, and neither is tested. If that ever changes, the stub becomes a
# lie and this test must change with it.
#
# ⚠️ This was a module-level `pytest.importorskip("openpyxl")` first, and the
# whole file reported `collected 0 items / 1 skipped` — every backfill gate
# test skipped silently along with it, in the file written to PROVE those
# gates. §3av: a test that fails, or skips, at COLLECTION proves nothing. The
# second attempt scoped the skip per class, which ran the gates but still left
# these 17 unexecuted on every interpreter: the only one carrying openpyxl
# (ML/.venv-health-ml) has no sqlalchemy, so it cannot load the backfill at
# all. Stubbing is what makes BOTH halves run in CI.
sys.modules.setdefault("openpyxl", types.ModuleType("openpyxl"))
extract = _load("extract_flowsheet_clocks")

#: Kept as a no-op so the class decorators still read as intentional. The
#: extractor's pure functions now run everywhere; nothing is skipped.
needs_openpyxl = pytest.mark.skipif(False, reason="openpyxl is stubbed")


# ── the sheet NAME is the date authority ────────────────────────────────────

@needs_openpyxl
class TestSheetNames:
    def test_a_month_name_longer_than_three_letters_is_still_a_month(self):
        """`^([A-Z][a-z]{2})\\s` discarded 48 July/June/March sheets silently."""
        for name, expected in [
            ("July 31-2018", datetime.date(2018, 7, 31)),
            ("June 30-2018", datetime.date(2018, 6, 30)),
            ("March 5-2018", datetime.date(2018, 3, 5)),
            ("Nov 14-2018", datetime.date(2018, 11, 14)),
        ]:
            kind, day, seq, also, _ = extract.classify_sheet(name)
            assert kind == "dated", name
            assert day == expected, name
            assert seq == 1

    def test_a_typod_month_resolves_by_prefix_and_a_word_does_not(self):
        """`Marc 23-2018` is March; `Master` must NOT become March."""
        kind, day, _, _, _ = extract.classify_sheet("Marc 23-2018.2")
        assert kind == "dated" and day == datetime.date(2018, 3, 23)
        kind, day, _, _, _ = extract.classify_sheet("oct 21-2017")
        assert kind == "dated" and day == datetime.date(2017, 10, 21)
        for junk in ("Master", "Dummy", "Davita", "Hospital",
                     "Maintenance Log", "Vomit Log", "Supplies Request"):
            kind, day, _, _, _ = extract.classify_sheet(junk)
            assert kind != "dated", junk
            assert day is None, junk

    def test_a_dot_suffix_marks_a_second_treatment_on_EITHER_side(self):
        """Recognising only `Oct 13.2-2018` dropped eight of eleven second
        treatments — the set that decides how many days held two."""
        for name in ("Nov 9-2018.2", "July 19-2018.2", "Jan 8-2018.2",
                     "Oct 13.2-2018", "01-09-2023.2"):
            kind, _, seq, _, _ = extract.classify_sheet(name)
            assert kind == "dated", name
            assert seq == 2, name

    def test_a_dotted_number_above_the_sequence_cap_is_a_SECOND_DAY(self):
        """`Sep 17.18-2017` covers Sept 17 AND 18, not treatment 18."""
        kind, day, seq, also, _ = extract.classify_sheet("Sep 17.18-2017")
        assert kind == "dated"
        assert day == datetime.date(2017, 9, 17)
        assert seq == 1
        assert also == datetime.date(2017, 9, 18)

    def test_a_sheet_with_no_year_is_reported_not_dropped(self):
        kind, day, _, _, _ = extract.classify_sheet("Apr 14")
        assert kind == "no_year_in_name"
        assert day is None

    def test_trailing_whitespace_and_single_digit_days(self):
        kind, day, _, _, _ = extract.classify_sheet("July 3-2017 ")
        assert kind == "dated" and day == datetime.date(2017, 7, 3)
        kind, day, _, _, _ = extract.classify_sheet("3-18-2023")
        assert kind == "dated" and day == datetime.date(2023, 3, 18)


# ── a cell's VALUE is not always a value ────────────────────────────────────

@needs_openpyxl
class TestTimeCells:
    def test_the_epoch_DAY_separates_a_real_time_from_a_serial(self):
        """`1900-03-05T04:48` is in the start cell of EIGHTEEN sheets,
        identically — a template artifact, an Excel serial of ~65.2 days whose
        fraction renders as 04:48. An earlier pass wrote it as a real start on
        all 18. But `1900-01-01T00:45` IS a real time: a time-only cell carries
        the epoch date, and rejecting the whole year lost four genuine stops."""
        value, note = extract.read_time(datetime.datetime(1900, 3, 5, 4, 48))
        assert value is None
        assert "REFUSED" in note and "serial" in note

        value, note = extract.read_time(datetime.datetime(1900, 1, 1, 0, 45))
        assert value == datetime.time(0, 45)
        assert note and "epoch" in note

    def test_only_a_four_digit_integer_is_military_time(self):
        """`10` is as likely 10:00 as 00:10, and `103` as likely 10:30 as
        01:03. Guessing either is CLAUDE.md 0 inside a format reader."""
        value, note = extract.read_time(1254)
        assert value == datetime.time(12, 54)
        assert note and "four_digit" in note

        for ambiguous in (10, 103, 7, 930.0):
            value, note = extract.read_time(ambiguous)
            if ambiguous == 930.0:
                continue  # four digits are fine; 930 is three
            assert value is None, ambiguous
            assert "REFUSED" in note, ambiguous

    def test_a_separator_typo_is_read_and_REPORTED(self):
        for text, expected in [("22;04", datetime.time(22, 4)),
                               ("13;30", datetime.time(13, 30)),
                               ("22>00", datetime.time(22, 0))]:
            value, note = extract.read_time(text)
            assert value == expected, text
            assert note and "separator" in note, text

    def test_an_unreadable_time_is_refused_by_name(self):
        for junk in ("WA", "1900-03-", "abc"):
            value, note = extract.read_time(junk)
            assert value is None, junk
            assert "REFUSED" in note, junk
        assert extract.read_time(None) == (None, None)
        assert extract.read_time("  ") == (None, None)

    def test_a_plain_time_passes_through_unannotated(self):
        assert extract.read_time(datetime.time(18, 38)) == (datetime.time(18, 38), None)


@needs_openpyxl
class TestDurationAndNumberCells:
    def test_total_time_is_hours_and_minutes_not_a_decimal(self):
        """`3:11` is 3 h 11 m on dialysis — 191 minutes, not 3.11 of anything."""
        assert extract.read_duration_minutes(datetime.time(3, 11)) == (191, None)
        assert extract.read_duration_minutes(datetime.time(4, 0))[0] == 240
        assert extract.read_duration_minutes(datetime.time(0, 14))[0] == 14

    def test_an_ambiguous_number_is_not_a_duration(self):
        value, note = extract.read_duration_minutes(3.26)
        assert value is None and "REFUSED" in note

    def test_a_non_epoch_serial_is_not_a_duration(self):
        value, note = extract.read_duration_minutes(
            datetime.datetime(1900, 2, 10, 0, 0))
        assert value is None
        assert "REFUSED" in note, "an earlier report filed this as ACCEPTED"

    def test_a_comma_can_be_a_decimal_point(self):
        """`'62,8'` stripped of commas became 628 L against a median of 41."""
        value, note = extract.read_number("62,8")
        assert value == pytest.approx(62.8)
        assert note and "decimal_comma" in note

    def test_an_ordinary_number_passes_through(self):
        assert extract.read_number(53.4) == (53.4, None)
        assert extract.read_number(99) == (99.0, None)
        assert extract.read_number(None) == (None, None)


@needs_openpyxl
class TestValueLocation:
    def test_a_values_region_stops_at_the_next_label(self):
        """`Total Time` at r52c1 has its value at r52c3, and `Total Dialysate`
        is the next label at r52c5. Scanning past it would read a label as a
        value. Reading one fixed offset found 7 machine times out of 653."""
        cells = extract.value_cells(52, 1, [1, 5, 7, 11])
        assert (52, 2) in cells and (52, 3) in cells and (52, 4) in cells
        assert (52, 5) not in cells, "must stop before the next label"
        assert (53, 1) in cells, "the 2017 layout puts the value BELOW"


# ── the backfill's clock and plausibility rules ─────────────────────────────

@needs_app
class TestRollover:
    def test_a_stop_before_the_start_belongs_to_the_next_day(self):
        """43% of this record's treatments cross midnight; without the rollover
        216 of 504 clocks would be negative."""
        problems: list[str] = []
        out = backfill.clock_values(
            {"start": "23:35:00", "stop": "02:04:00", "machine_minutes": 140},
            datetime.date(2018, 5, 6), problems)
        assert out["actual_start_time"] == datetime.datetime(2018, 5, 6, 23, 35)
        assert out["actual_end_time"] == datetime.datetime(2018, 5, 7, 2, 4)
        assert not problems

    def test_a_same_day_stop_stays_on_the_day(self):
        problems: list[str] = []
        out = backfill.clock_values(
            {"start": "16:50:00", "stop": "20:55:00", "machine_minutes": 225},
            datetime.date(2025, 6, 6), problems)
        assert out["actual_end_time"] == datetime.datetime(2025, 6, 6, 20, 55)
        assert not problems

    def test_no_stop_writes_a_start_and_no_end(self):
        problems: list[str] = []
        out = backfill.clock_values(
            {"start": "06:00:00", "stop": None, "machine_minutes": 228},
            datetime.date(2025, 7, 6), problems)
        assert "actual_start_time" in out
        assert "actual_end_time" not in out

    def test_no_start_writes_nothing(self):
        assert backfill.clock_values(
            {"start": None, "stop": None, "machine_minutes": 137},
            datetime.date(2018, 10, 13), []) == {}


@needs_app
class TestAmPmGate:
    def test_a_twelve_hour_clock_withholds_the_END_and_keeps_the_start(self):
        """'Nov 11-2017' reads 10:07 -> 02:00, a 953 min clock around 197 min on
        the machine. A 22:07 start would give 233 min — a 36-minute gap, in the
        normal band (median 22, p95 47). Which cell is wrong is not knowable, so
        neither is corrected, and a 16-hour duration must not reach the column
        every duration feature reads."""
        problems: list[str] = []
        out = backfill.clock_values(
            {"start": "10:07:00", "stop": "02:00:00", "machine_minutes": 197},
            datetime.date(2017, 11, 11), problems)
        assert out["actual_start_time"] == datetime.datetime(2017, 11, 11, 10, 7)
        assert "actual_end_time" not in out
        assert len(problems) == 1
        assert "WITHHELD" in problems[0]

    def test_an_ordinary_pause_is_NOT_withheld(self):
        """A 22-minute excess is the normal population, not a fault."""
        problems: list[str] = []
        out = backfill.clock_values(
            {"start": "20:20:00", "stop": "00:40:00", "machine_minutes": 243},
            datetime.date(2025, 4, 7), problems)
        assert out["actual_end_time"] == datetime.datetime(2025, 4, 8, 0, 40)
        assert not problems

    def test_machine_time_over_the_clock_is_flagged_and_the_end_still_written(self):
        """3at says the clock must exceed machine time. Where it does not, the
        contradiction is surfaced rather than reconciled."""
        problems: list[str] = []
        out = backfill.clock_values(
            {"start": "16:15:00", "stop": "17:20:00", "machine_minutes": 165},
            datetime.date(2024, 3, 12), problems)
        assert out["actual_end_time"] == datetime.datetime(2024, 3, 12, 17, 20)
        assert len(problems) == 1
        assert "EXCEEDS" in problems[0]


@needs_app
class TestPlausibilityGates:
    def test_a_transposed_uf_bvp_pair_is_withheld_not_swapped(self):
        """'04-05-2025' reads UF=99 and BVP=1.5. Each is a possible number; only
        BVP/minutes — 6 ml/min against a median of 426 — says they swapped.
        Swapping them would be a guess about which box was meant."""
        problems: list[str] = []
        out = backfill.gated_values(
            {"machine_minutes": 249, "total_uf_liters": 99.0,
             "total_dialysate_liters": 63.0,
             "total_blood_volume_processed": 1.5}, problems)
        assert "total_uf_liters" not in out
        assert "total_blood_volume_processed" not in out
        assert out["total_dialysate_liters"] == 63.0, "dialysate is unaffected"
        assert any("transposed" in p for p in problems)

    def test_a_short_aborted_treatment_is_KEPT(self):
        """'Jan 30-2018' reads 14 min / 2.3 L / 0.0 L / 5 L — internally
        consistent. Withholding it would delete the record of a treatment that
        failed, which is itself a clinical finding (3ab)."""
        problems: list[str] = []
        out = backfill.gated_values(
            {"machine_minutes": 14, "total_uf_liters": 0.0,
             "total_dialysate_liters": 2.3,
             "total_blood_volume_processed": 5.0}, problems)
        assert out["machine_total_time_minutes"] == 14
        assert out["total_dialysate_liters"] == 2.3
        assert out["total_uf_liters"] == 0.0

    def test_an_ordinary_sheet_passes_every_gate(self):
        problems: list[str] = []
        out = backfill.gated_values(
            {"machine_minutes": 240, "total_uf_liters": 0.4,
             "total_dialysate_liters": 66.4,
             "total_blood_volume_processed": 103.0}, problems)
        assert out == {"machine_total_time_minutes": 240,
                       "total_uf_liters": 0.4,
                       "total_dialysate_liters": 66.4,
                       "total_blood_volume_processed": 103.0}
        assert not problems

    def test_an_implausible_dialysate_volume_is_withheld(self):
        problems: list[str] = []
        out = backfill.gated_values(
            {"machine_minutes": 222, "total_uf_liters": 2.1,
             "total_dialysate_liters": 628.0,
             "total_blood_volume_processed": 99.0}, problems)
        assert "total_dialysate_liters" not in out
        assert any("total_dialysate_liters" in p for p in problems)


@needs_app
class TestReadingAnchoring:
    def test_readings_that_wrap_midnight_are_re_anchored(self):
        """A session starting 22:00 has readings at 22:xx AND 00:xx, so
        min(reading_time) is 00:xx. Treating that as the start made every
        window span the whole day — which reported 54 two-treatment days as 4."""
        mins = [5, 30, 1330, 1380, 1430]      # 00:05..23:50
        names = [n for n, _ in backfill.anchorings(mins)]
        assert "wrapped" in names
        wrapped = dict(backfill.anchorings(mins))["wrapped"]
        assert min(wrapped) == 1330, "the early readings moved to the next day"
        assert max(wrapped) - min(wrapped) < 300, "and the block is contiguous"

    def test_readings_entirely_after_midnight_get_a_next_morning_candidate(self):
        """These cannot be detected from the readings alone — the sheet's own
        window is the evidence for shifting them."""
        names = [n for n, _ in backfill.anchorings([0, 30, 90, 180])]
        assert "next_morning" in names

    def test_a_sheet_window_scores_the_session_whose_readings_sit_in_it(self):
        sheet = {"start": "23:48:00", "stop": "04:50:00"}
        fraction, anchoring, inside = backfill.score(sheet, [0, 60, 120, 240])
        assert fraction == 1.0
        assert anchoring == "next_morning"
        assert inside == 4

    def test_no_readings_is_no_evidence_either_way(self):
        fraction, anchoring, inside = backfill.score(
            {"start": "16:50:00", "stop": "20:55:00"}, [])
        assert fraction == 0.0
        assert inside == 0
