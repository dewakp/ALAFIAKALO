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
