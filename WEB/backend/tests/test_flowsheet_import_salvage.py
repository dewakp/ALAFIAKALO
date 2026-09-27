"""The importer's two salvage rules, pinned.

Both exist because a clinical cell held something that was ALMOST a value, and
in both cases storing it verbatim put a wrong fact in front of a clinician:

  '1;47'  a real administration time typed with `;` — which on a US keyboard is
          the UNSHIFTED `:`. Read as 1:47, because a misspelled SEPARATOR is not
          an unknown value. Operator decision, 2026-09-26; the repaired row is
          session_drugs id 2184 (Doxercalcif, 2 mcg, 2023-02-09 01:47).

  'Oct'   a MONTH sitting in the Dose column. Not a dose at all. Stored
          verbatim it reached production as `Epogene / Oct / SC`
          (session_drugs id 2018), where it is indistinguishable from a real
          dose. NULL reads as "given, amount not recorded", which is true.

Neither rule may widen, and that is what these tests are really guarding.
`repair_typed_time` interprets ONLY the separator and takes the digits exactly
as typed; anything whose digits would have to be invented, completed or
reordered is refused. `_MONTH_ONLY` refuses month names and nothing else —
every real dose in this corpus carries a digit, and a guard that swallowed
those would destroy clinical data to fix a typo.

WHY THE MODULE IS LOADED BY PATH
--------------------------------
`scripts/import_flowsheets.py` is a script, not part of the `app` package, and
it imports `openpyxl` at module scope — which the backend image does not carry
(the app never reads .xlsx; document import uses pdfplumber). Rather than add an
xlsx dependency to the production image to satisfy a test, openpyxl is stubbed
for the load.

That is honest rather than merely convenient: NEITHER function under test
touches openpyxl, so nothing under test is faked. If either ever does, this stub
becomes a lie and the test must change with it.
"""

import importlib.util
import sys
import types
from datetime import date, datetime, time
from pathlib import Path

import pytest


def _load_importer():
    # tests/ -> WEB/backend -> scripts/import_flowsheets.py.
    #
    # parents[1], deliberately not a deeper index: a path computed from a deeper
    # ancestor breaks the moment this tree is mounted somewhere else, which has
    # already produced a false "test failure" on this repo once.
    path = Path(__file__).resolve().parents[1] / "scripts" / "import_flowsheets.py"
    assert path.is_file(), f"importer not found at {path}"
    sys.modules.setdefault("openpyxl", types.ModuleType("openpyxl"))
    spec = importlib.util.spec_from_file_location("_import_flowsheets_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


F = _load_importer()


# ── '1;47' — a time typed with the wrong separator ────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("1;47", time(1, 47)),      # the actual cell, on sheet 02-09-2023
    ("1.47", time(1, 47)),
    ("1,47", time(1, 47)),
    ("23;59", time(23, 59)),
    (" 9;05 ", time(9, 5)),     # single-digit hour, padded; surrounding space
])
def test_a_mistyped_separator_is_read_through(raw, expected):
    assert F.repair_typed_time(raw) == expected


@pytest.mark.parametrize("raw", [
    "147",       # no separator at all — which digits are the hour?
    "1;4",       # a second minute digit would have to be INVENTED
    "24;00",     # not an hour
    "12;60",     # not a minute
    "1;47;30",   # not a time in this format
    "NONE",      # the explicit "not recorded" marker, handled elsewhere
    "",
])
def test_anything_needing_invented_digits_is_refused(raw):
    assert F.repair_typed_time(raw) is None


@pytest.mark.parametrize("value", [time(1, 47), date(2023, 2, 9), datetime(2023, 2, 9, 1, 47)])
def test_a_value_that_is_already_a_time_is_not_this_functions_business(value):
    # parse_time_value handles those. Returning a "repair" here would mask a
    # cell that needed no repairing.
    assert F.repair_typed_time(value) is None


# ── 'Oct' — a month in the Dose column ────────────────────────────────────────

@pytest.mark.parametrize("raw", [
    "Oct", "oct", "OCT", "October", " Oct ", "Dec", "September", "Jan", "may",
])
def test_a_month_name_is_not_a_dose(raw):
    assert F._MONTH_ONLY.match(raw)


@pytest.mark.parametrize("raw", [
    "2 mcg",        # doxercalciferol, as recorded
    "3,000 SQ",     # epogene
    "100 mg",       # venofer
    "2.5 ml x 2",   # sodium citrate
    "20,000 SQ",
    "0.5 mcg",
    "10 mg",
    "1 g",
    "Marcaine 0.5%",   # begins with "Mar" — must NOT be eaten by the month rule
    "Augmentin 625",   # begins with "Aug" — same
])
def test_a_real_dose_is_left_alone(raw):
    assert F._MONTH_ONLY.match(raw) is None


def test_the_month_rule_is_anchored_at_both_ends():
    """A month name is refused only when it is the WHOLE cell.

    This is the property that keeps the guard narrow. Without the trailing
    anchor, "Marcaine 0.5%" and "Augmentin 625" are month-prefixed strings and
    a real dose would be discarded — turning a fix for one wrong value into
    silent loss of correct ones.
    """
    assert F._MONTH_ONLY.match("Oct")
    assert F._MONTH_ONLY.match("Octreotide 50 mcg") is None
