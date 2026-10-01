"""Layer 3 — turn reconstructed cells into canonical clinical records.

Both layout engines converge here, so a labelled-column lab report and a trend
matrix produce the same `LabRecord` shape and the mappers downstream need to
know nothing about how the document was drawn.

Value parsing is deliberately conservative. `Error`, `Recollect`, `N/A` and `-`
are all real things a lab prints, and each means something different from "no
result". They are preserved as text rather than dropped — one month in the
sample corpus is almost entirely `Error`, and silently discarding those rows
would show a clinician a blank where a failed draw belongs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime

from .dictionaries import canonical_name, category_for
from .layout import Table
from .layout_matrix import MatrixTable

#: Results that are text, not numbers. Kept, never coerced to 0 — "Error" means
#: the draw failed, which is a clinical fact and not the same as no row.
NON_NUMERIC_RESULTS = {
    "ERROR", "N/A", "NA", "TNP", "CANC", "CANCELLED", "QNS", "PENDING", "SENT",
    "RECEIVED", "NOT DETECTED", "DETECTED", "NEGATIVE", "POSITIVE", "NONREACTIVE",
    "NON-REACTIVE", "REACTIVE", "NORMAL", "ABNORMAL", "SEE NOTE",
}

#: Placeholders meaning "this test was not performed in this period". A trend
#: grid is mostly these; recording them would invent hundreds of empty results.
NO_RESULT_MARKERS = {"-", "--", "---", "—", "–", ".", "N/D"}

#: Text results that themselves indicate an abnormal finding.
_ABNORMAL_TEXT = {"DETECTED", "POSITIVE", "REACTIVE", "ABNORMAL"}

_FLAG_RE = re.compile(r"(?:^|\s)([HL])(?:\s|$)")
_COMPARATOR_RE = re.compile(r"^\s*([<>]=?)\s*")
_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")
_RANGE_RE = re.compile(r"(-?\d+(?:\.\d+)?)\s*[-–—]\s*(-?\d+(?:\.\d+)?)")
_OPEN_RANGE_RE = re.compile(r"^\s*([<>]=?)\s*(-?\d+(?:\.\d+)?)\s*$")
_UNIT_SUFFIX_RE = re.compile(r"\s*\(([^()]*)\)\s*$")

_DATE_FORMATS = ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%d/%m/%Y", "%b %Y", "%B %Y")
_PERIOD_RE = re.compile(r"^([A-Za-z]{3,9})\s+((?:19|20)\d{2})$")


@dataclass
class LabRecord:
    """One measurement, ready to be mapped onto a clinical table."""

    test_name: str                 # canonical where known, else the document's wording
    raw_name: str
    value: float | None = None
    value_text: str | None = None  # non-numeric result, or one carrying a comparator
    unit: str | None = None
    reference_low: float | None = None
    reference_high: float | None = None
    reference_text: str | None = None
    is_abnormal: bool | None = None
    status: str | None = None
    code: str | None = None
    category: str | None = None
    test_date: date | None = None
    recognised: bool = False
    confidence: float = 0.0
    notes: list[str] = field(default_factory=list)

    @property
    def has_result(self) -> bool:
        return self.value is not None or bool(self.value_text)


def split_trailing_unit(name: str) -> tuple[str, str | None]:
    """`HEMOGLOBIN (g/dL)` -> (`HEMOGLOBIN`, `g/dL`).

    Matrix documents carry the unit inside the analyte label because there is no
    unit column. Only strip it when the parenthetical looks like a unit — the
    corpus also contains `VITAMIN D (25-OH)` and `STDKT/V (DIAL)`, where the
    parenthetical is part of the name.
    """
    match = _UNIT_SUFFIX_RE.search(name)
    if not match:
        return name.strip(), None

    inner = match.group(1).strip()
    if not inner or _looks_like_qualifier(inner):
        return name.strip(), None
    return name[: match.start()].strip(), inner


def _looks_like_qualifier(text: str) -> bool:
    """True when a parenthetical qualifies the name rather than giving a unit.

    Decided by shape, not length: a unit is a rate or a proportion and so
    carries "/" or "%". That keeps "x 10^3 cells/uL" a unit — a length rule read
    it as a qualifier and welded it onto the analyte name — while "25-OH",
    "DIAL" and "Calc" stay part of the name they disambiguate.
    """
    upper = text.upper()
    if upper in {"DIAL", "CALC", "TOTAL", "INTACT", "25-OH", "FREE", "POST", "PRE"}:
        return True
    return "/" not in text and "%" not in text


def parse_value(raw: str) -> tuple[float | None, str | None, bool | None]:
    """Parse a result cell into (number, text, explicit_abnormal_flag).

    Returns the number when the cell is numeric, the original text when it is
    not, and the H/L flag as a tri-state — None means the report said nothing.
    """
    text = (raw or "").strip()
    if not text or text.upper() in NO_RESULT_MARKERS:
        return None, None, None

    flag_match = _FLAG_RE.search(text)
    explicit_abnormal: bool | None = None
    if flag_match:
        explicit_abnormal = True
        text = (text[: flag_match.start()] + " " + text[flag_match.end():]).strip()

    upper = text.upper()
    if upper in NON_NUMERIC_RESULTS:
        if explicit_abnormal is None and upper in _ABNORMAL_TEXT:
            explicit_abnormal = True
        return None, text, explicit_abnormal

    comparator = ""
    comparator_match = _COMPARATOR_RE.match(text)
    if comparator_match:
        comparator = comparator_match.group(1)
        text = text[comparator_match.end():].strip()

    number_match = _NUMBER_RE.search(text)
    if not number_match:
        return None, raw.strip() or None, explicit_abnormal

    number = float(number_match.group())
    if comparator:
        # "< 9" is a bounded result, not the number 9. Keep both.
        return number, f"{comparator} {number_match.group()}", explicit_abnormal
    return number, None, explicit_abnormal


def parse_reference(raw: str) -> tuple[float | None, float | None, str | None]:
    """Parse a reference cell into (low, high, original_text)."""
    text = (raw or "").strip()
    if not text:
        return None, None, None

    match = _RANGE_RE.search(text)
    if match:
        return float(match.group(1)), float(match.group(2)), text

    open_match = _OPEN_RANGE_RE.match(text)
    if open_match:
        operator, number = open_match.group(1), float(open_match.group(2))
        return (None, number, text) if operator.startswith("<") else (number, None, text)

    return None, None, text


def compute_abnormal(
    value: float | None,
    low: float | None,
    high: float | None,
    explicit: bool | None,
) -> bool | None:
    """Prefer what the report said; fall back to the range it printed."""
    if explicit is not None:
        return explicit
    if value is None:
        return None
    if low is not None and value < low:
        return True
    if high is not None and value > high:
        return True
    if low is not None or high is not None:
        return False
    return None


def parse_date(raw: str | None, fallback_year: int | None = None) -> date | None:
    text = (raw or "").strip()
    if not text:
        return None

    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue

    # "09/03" with the year implied by the column header ("SEP 2025").
    if fallback_year and re.fullmatch(r"\d{1,2}/\d{1,2}", text):
        month, day = (int(part) for part in text.split("/"))
        try:
            return date(fallback_year, month, day)
        except ValueError:
            return None
    return None


def period_to_date(period: str) -> tuple[date | None, int | None]:
    """`SEP 2025` -> (2025-09-01, 2025). Used when a cell has no own date."""
    match = _PERIOD_RE.match(period.strip())
    if not match:
        return None, None
    for fmt in ("%b %Y", "%B %Y"):
        try:
            parsed = datetime.strptime(f"{match.group(1)[:3]} {match.group(2)}", fmt).date()
            return parsed, parsed.year
        except ValueError:
            continue
    return None, int(match.group(2))



# Words that only appear in prose, never in an analyte name. A lab report is a
# clinical document wrapped in legal boilerplate, and the boilerplate parses
# just as happily as the results do.
_PROSE_WORDS = frozenset("""
and or the of to with including up down for from that this which shall will
may must employment termination disciplinary action policy confidential
please note refer contact page report printed signature authorized
""".split())


def looks_like_prose(name: str) -> bool:
    """True when a candidate analyte name is really a sentence fragment.

    Production carries a lab result named "up to and including termination of"
    whose value is "employment with DaVita." — DaVita's disciplinary-policy
    footer, parsed as a test and a result and shown to a clinician among real
    labs.

    Decided by shape, not a blocklist of phrases: an analyte name is a short
    noun phrase, so it does not run to many words, does not begin lowercase,
    and does not contain the connective words prose is built from. That catches
    the next document's boilerplate too, which a phrase list would not.
    """
    text = (name or "").strip()
    if not text:
        return True
    words = text.split()
    # Real names are short. "Erythrocyte distribution width [Entitic volume] by
    # Automated count" is 8 words, so the bar has to sit above that.
    if len(words) > 10:
        return True
    lowered = [w.strip(".,;:()").lower() for w in words]
    connectives = sum(1 for w in lowered if w in _PROSE_WORDS)
    # A name starting lowercase is already suspect; combined with connectives it
    # is prose. "up to and including termination of" -> 5 of 6.
    starts_lower = text[:1].islower()
    if starts_lower and connectives >= 2:
        return True
    # Even capitalised, a majority of connectives means a sentence.
    return len(words) >= 4 and connectives >= len(words) / 2


#: Results a lab prints as words on rows that carry no unit and no range —
#: microscopy and differential findings, and the two ways a lab says "we did not
#: report this". Same kind of set as NON_NUMERIC_RESULTS above, and it exists for
#: the same reason: each of these is a clinical fact, not a blank.
_RESULT_WORDS = {"DNR", "NONE SEEN", "NOT APPLICABLE", "NOT APPL", "TRACE",
                 "NOT DONE", "NEG", "POS", "NONE"}

#: Roles rejoined to judge a row as the document drew it.
_ROW_ROLES = ("name", "value", "flag", "unit", "ref_range", "status", "comments")

#: A bare number, optionally bounded ("< 9") or graded ("2+").
_PLAIN_VALUE = re.compile(r"^[<>]?=?\s*-?\d+(?:\.\d+)?\+?$")


def _is_plain_measurement(value: str) -> bool:
    """True when the value cell is a bare number, give or take the lab's flag.

    `2.4`, `92`, `37.2 L`, `< 9`, `2+`. This is the short-circuit that keeps a
    legitimately LONG row out of the prose test below, whose word ceiling was
    calibrated for NAMES and not for whole rows. Without it,

        CBC (INCLUDES DIFF/PLT) WHITE BLOOD CELL COUNT 2.4 LOW 3.8-10.8 Thousand/uL 01

    is 11 words and reads as prose — and the guard deleted that patient's WBC
    count of 2.4 (the neutropenia), both eGFRs, the sed rate, and six real rows
    per document across the PHI corpus. Measured, on the way to being shipped.

    A range is deliberately NOT plain: `0.55-2.73` is the tail of a pregnancy
    reference footnote, and `0-2` is a real microscopy count that the row's own
    flag and range already spare.
    """
    text = _FLAG_RE.sub(" ", f" {value} ").strip()
    return bool(_PLAIN_VALUE.match(text))

_HAS_DIGIT = re.compile(r"\d")


def row_is_prose(cells: dict) -> bool:
    """True when a whole ROW is the document's furniture rather than a result.

    `looks_like_prose` judges the NAME alone, and that is not enough. On a real
    3-page Quest report every one of these was imported as a lab result, because
    each has a short, capitalised, connective-free name:

        01: Quest Diagnostics-Houston = Lab, 5850 Rogerdale   <- a street address
        Martin SS et al. JAMA.        = 2013;310(19): 2061-2068 <- a citation
        Desirable range <100          = mg/dL for primary prev  <- a footnote
        Director: Dr Robert L         = Breckenridge            <- the lab director
        Performing Laboratory         = Information:            <- a section heading

    The prose was in the cells the name-only guard never inspected.

    WHY NOT "a real row has a number in its value column"
    ----------------------------------------------------
    Because it is wrong, and measurably so: on that same report it removes 49 of
    106 rows, and most are REAL findings —

        WBC = NONE SEEN · RBC = 0-2 · BACTERIA = NONE SEEN
        HYALINE CAST = NONE SEEN · ABSOLUTE BLASTS = DNR
        BUN/CREATININE RATIO = NOT APPLICABLE

    an entire urinalysis microscopy panel and half a differential, deleted to
    remove an address. This module already makes that argument about `Error` and
    `N/A`: they are things a lab really prints and each means something other
    than "no result".

    The 13-document PHI corpus scores that rule as FREE — 0 rows lost — because
    every corpus document is a DaVita report with no microscopy. A green corpus
    run is not evidence about precision (§3ab); this is the second time that has
    had to be said.

    WHAT ACTUALLY SEPARATES THEM
    ----------------------------
    Measured on that report, every real finding carries a FLAG and a RANGE, even
    the wordless ones — `COLOR YELLOW NORMAL YELLOW 01` — while the furniture
    carries neither: `Performing Laboratory = Information:` and
    `Director: Dr Robert L = Breckenridge` occupy name and value and nothing
    else. So the signals are the document's own structure, not a vocabulary we
    have to maintain:

      1. a closed-vocabulary result ("DNR", "NEG") is always a finding;
      2. the row REJOINED is judged as prose — the lab's address is 12 words
         across four cells, which the name alone never revealed;
      3. a row occupying only name and value, with no digit, is furniture.

    Sparing any row with a non-empty range was the earlier rule, and it is what
    let the address through: that row's range cell reads
    `TX, 77072-1602, phone: ,`. A non-empty cell is not structure.
    """
    populated = {role: (text or "").strip()
                 for role, text in (cells or {}).items() if (text or "").strip()}
    value = populated.get("value", "")
    if not value:
        # A valueless row is discarded downstream on its own terms.
        return False

    # A closed-vocabulary result is a clinical fact whatever structure it has.
    upper = value.upper()
    if upper in _RESULT_WORDS or upper in NON_NUMERIC_RESULTS:
        return False

    # A bare number is a measurement, however long the row reads. This must come
    # BEFORE the prose test: that test counts words against a ceiling meant for
    # names, and a real row with a long name plus flag, range and unit sails
    # past it. See `_is_plain_measurement` for what this cost when it was missing.
    if _is_plain_measurement(value):
        return False

    # Judge the row REJOINED. A footnote is one sentence split across the
    # columns, so it is only visible as a sentence once they are put back
    # together — the lab's address runs to 12 words across four cells and trips
    # the word ceiling that the name alone never reached.
    whole = " ".join(populated.get(role, "") for role in _ROW_ROLES).strip()
    if looks_like_prose(whole):
        return True

    # A row occupying ONLY name and value has none of the structure a lab gives
    # a measurement — no flag, no unit, no range. Measured on the Quest report,
    # every real finding carries a flag AND a range (even the wordless ones:
    # `COLOR YELLOW NORMAL YELLOW 01`), while `Director: Dr Robert L =
    # Breckenridge` and `Performing Laboratory = Information:` carry neither.
    # A number is still a number, so a bare `GLUCOSE 84` survives.
    if set(populated) <= {"name", "value"} and not _HAS_DIGIT.search(value):
        return True

    return False


def _finish(record: LabRecord) -> LabRecord:
    """Assign category and a confidence the reviewer can sort on."""
    record.category = category_for(record.test_name)

    score = 0.4
    if record.recognised:
        score += 0.3
    if record.value is not None:
        score += 0.15
    if record.unit:
        score += 0.05
    if record.reference_low is not None or record.reference_high is not None:
        score += 0.05
    if record.test_date:
        score += 0.05
    record.confidence = round(min(score, 1.0), 2)
    return record


def records_from_table(table: Table, report_date: date | None = None) -> list[LabRecord]:
    """Normalize a labelled-column table."""
    records: list[LabRecord] = []
    for row in table.rows:
        raw_name = row.get("name").strip()
        if not raw_name:
            continue
        # Boilerplate is not a lab result. Prod shows a clinician a row named
        # "up to and including termination of" with the value "employment with
        # DaVita." among real results.
        if looks_like_prose(raw_name):
            continue
        # …and the NAME alone is not enough. A lab's street address, its
        # director and a journal citation all have short, capitalised,
        # connective-free names; the prose sits in the cells this guard never
        # inspected. `row_is_prose` judges the row as the document drew it.
        if row_is_prose(row.cells):
            continue

        name, unit_from_name = split_trailing_unit(raw_name)
        canonical, recognised = canonical_name(name)

        value, value_text, explicit = parse_value(row.get("value"))
        low, high, ref_text = parse_reference(row.get("ref_range"))
        unit = row.get("unit").strip() or unit_from_name or None

        record = LabRecord(
            test_name=canonical,
            raw_name=raw_name,
            value=value,
            value_text=value_text,
            unit=unit,
            reference_low=low,
            reference_high=high,
            reference_text=ref_text,
            is_abnormal=compute_abnormal(value, low, high, explicit),
            status=(row.get("status").strip() or None),
            code=(row.get("code").strip() or None),
            test_date=parse_date(row.get("date")) or report_date,
            recognised=recognised,
        )
        if not record.has_result:
            continue
        if not recognised:
            record.notes.append("Test name not in the reference vocabulary — please confirm.")
        records.append(_finish(record))
    return records


def records_from_matrix(matrix: MatrixTable) -> list[LabRecord]:
    """Normalize a trend matrix — one record per (analyte, period) cell."""
    records: list[LabRecord] = []
    for cell in matrix.cells:
        name, unit = split_trailing_unit(cell.analyte)
        canonical, recognised = canonical_name(name)

        value, value_text, explicit = parse_value(cell.value)
        period_date, year = period_to_date(cell.period)
        test_date = parse_date(cell.cell_date, fallback_year=year) or period_date

        record = LabRecord(
            test_name=canonical,
            raw_name=cell.analyte,
            value=value,
            value_text=value_text,
            unit=unit,
            is_abnormal=compute_abnormal(value, None, None, explicit),
            test_date=test_date,
            recognised=recognised,
        )
        if not record.has_result:
            continue
        if cell.block:
            record.notes.append(f"Section: {cell.block}")
        if not recognised:
            record.notes.append("Test name not in the reference vocabulary — please confirm.")
        records.append(_finish(record))
    return records
