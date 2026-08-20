"""Layer 1 — reconstruct a table from word geometry.

The whole point of this module is that it never assumes a vendor. Column
positions are read off the document's own header row, so a report whose RESULT
column sits at x=197 parses by the same code as one where it sits at x=169.

The failure this exists to fix: `page.extract_text()` returns words in reading
order, and a reference range printed to the *left* of a row is emitted on the
line above it:

    1.00 -
    1051 A/G RATIO 1.8 Calc Final
    2.50

Any line-oriented regex loses that range. Working from coordinates, the "1.00 -"
and "2.50" fragments are simply two more pieces of the same row's REFERENCE
column, and rejoin in vertical order.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field

from .extract import Document, Page, Word

# Vertical tolerance, in points, for calling two words part of the same visual
# line. Rows in the sample corpus are ~6.4pt apart, so this is comfortable.
_LINE_TOLERANCE = 2.5

# A header must resolve at least this many distinct roles to be believed.
_MIN_HEADER_ROLES = 3

#: A column table is *about* something measured, so its header has to name either
#: the thing or its result. Without this gate a document with no table at all
#: still scores three roles off incidental prose — "Full Code", "Modality
#: Status", "Start Date" — and every row after it is fabricated.
_REQUIRED_HEADER_ROLES = ("name", "value")

# A header can wrap over this many visual lines ("REFERENCE" / "RANGE").
_MAX_HEADER_LINES = 3

# Header lines sit tight against each other. Without this bound a window happily
# reaches up into the patient block and matches stray labels — "Order Comments"
# and "Lab Location" both name column roles, and dragging them in produces
# columns that span the whole page.
_MAX_HEADER_LINE_GAP = 12.0

# Columns may abut but must not genuinely overlap; allow a hair for rounding.
_COLUMN_OVERLAP_TOLERANCE = 1.0

# Prose guards — a real table row is short and spread across columns.
_MAX_WORDS_IN_ONE_CELL = 8
_MAX_WORDS_IN_ROW = 22

#: Column role → header keywords. Deliberately generic: these are the words labs
#: actually print, not DaVita's in particular.
ROLE_KEYWORDS: dict[str, set[str]] = {
    "code": {"code", "id", "loinc", "icd", "rxnorm"},
    # "lab" is deliberately absent: reports print "Lab Location" and "Lab
    # Medical Director" in the patient block, and matching those pollutes the
    # name column's x-span. "test"/"name" already catch "LAB TEST NAME".
    "name": {
        "test", "tests", "analyte", "component", "description", "name", "procedure",
        # medication lists and problem lists are the same shape with a different
        # subject column
        "medication", "medications", "drug", "drugs", "prescription",
        "condition", "conditions", "problem", "problems", "diagnosis", "diagnoses",
    },
    "value": {"result", "results", "value", "observation", "reading", "finding"},
    "unit": {"unit", "units", "uom"},
    "ref_range": {"reference", "range", "ranges", "normal", "expected", "interval", "limits"},
    "flag": {"flag", "flags", "abnormal"},
    "status": {"status", "state", "active"},
    "comments": {"interpretation", "comment", "comments", "note", "notes", "remark", "remarks"},
    "date": {"date", "collected", "drawn", "observed", "resulted", "onset", "diagnosed", "since"},
    "dose": {"dose", "dosage", "strength", "amount", "quantity"},
    "frequency": {"frequency", "freq", "sig", "schedule", "directions", "instructions"},
    "route": {"route"},
}

_WORD_RE = re.compile(r"[a-z]+")


@dataclass
class Line:
    top: float
    words: list[Word] = field(default_factory=list)

    @property
    def text(self) -> str:
        return " ".join(w.text for w in sorted(self.words, key=lambda w: w.x0))


@dataclass
class Column:
    role: str
    x_start: float
    x_end: float


@dataclass
class Row:
    """One reconstructed record: role → cell text, already de-wrapped."""

    cells: dict[str, str]
    top: float
    page: int

    def get(self, role: str, default: str = "") -> str:
        return self.cells.get(role, default) or default


@dataclass
class Table:
    columns: list[Column]
    rows: list[Row]
    page: int

    @property
    def roles(self) -> set[str]:
        return {c.role for c in self.columns}


def group_lines(words: list[Word], tolerance: float = _LINE_TOLERANCE) -> list[Line]:
    """Cluster words into visual lines by their `top` coordinate."""
    if not words:
        return []

    lines: list[Line] = []
    for word in sorted(words, key=lambda w: (w.top, w.x0)):
        if lines and abs(word.top - lines[-1].top) <= tolerance:
            lines[-1].words.append(word)
        else:
            lines.append(Line(top=word.top, words=[word]))
    return lines


def _role_of(token: str) -> str | None:
    """Map a single header token to a column role, if it names one."""
    letters = "".join(_WORD_RE.findall(token.lower()))
    if not letters:
        return None
    for role, keywords in ROLE_KEYWORDS.items():
        if letters in keywords:
            return role
    return None


def find_header(lines: list[Line]) -> tuple[int, int, list[Column]] | None:
    """Locate the table header and derive column x-boundaries from it.

    Returns (first_line_index, last_line_index, columns), or None if this page
    has no recognisable table header.

    A header may wrap ("REFERENCE" above "RANGE"), so consecutive lines are
    considered together and the best-scoring window wins.
    """
    best: tuple[int, int, list[Column]] | None = None
    best_score = 0

    gap_limit = max(_MAX_HEADER_LINE_GAP, 1.8 * _median_spacing([ln.top for ln in lines]))

    for start in range(len(lines)):
        for span in range(1, _MAX_HEADER_LINES + 1):
            end = start + span - 1
            if end >= len(lines):
                break

            window = lines[start : end + 1]
            # Reject a window that reaches across a visual break — that is the
            # patient block, not a wrapped header.
            if any(b.top - a.top > gap_limit for a, b in zip(window, window[1:])):
                break

            header_words: list[Word] = []
            for line in window:
                header_words.extend(line.words)

            spans: dict[str, list[float]] = {}
            for word in header_words:
                role = _role_of(word.text)
                if role is None:
                    continue
                bounds = spans.setdefault(role, [word.x0, word.x1])
                bounds[0] = min(bounds[0], word.x0)
                bounds[1] = max(bounds[1], word.x1)

            score = len(spans)
            # Prefer the earliest, richest header; require a real improvement so
            # a trailing line of prose cannot extend a good header.
            if (
                score > best_score
                and score >= _MIN_HEADER_ROLES
                and any(role in spans for role in _REQUIRED_HEADER_ROLES)
            ):
                columns = _columns_from_spans(spans)
                if columns:
                    best = (start, end, columns)
                    best_score = score

    if best is None:
        return None

    return _absorb_wrapped_header_lines(lines, best, gap_limit)


def _absorb_wrapped_header_lines(
    lines: list[Line],
    best: tuple[int, int, list[Column]],
    gap_limit: float,
) -> tuple[int, int, list[Column]]:
    """Pull a wrapped header tail ("RANGE" under "REFERENCE") into the header.

    Scoring counts *distinct* roles, so a line that only re-states roles already
    present cannot raise the score and the window stops short of it. Left in the
    body, those words become a phantom first row.

    A line is absorbed only if every token on it already names a known role —
    which "RANGE"/"COMMENTS" satisfy and a real data row never does.
    """
    start, end, _ = best
    known = {
        role
        for line in lines[start : end + 1]
        for role in (_role_of(w.text) for w in line.words)
        if role is not None
    }

    while end + 1 < len(lines):
        candidate = lines[end + 1]
        if candidate.top - lines[end].top > gap_limit:
            break
        tokens = [w for w in candidate.words if _WORD_RE.search(w.text.lower()) or w.text.isalnum()]
        if not tokens or not all(_role_of(w.text) in known for w in tokens):
            break
        end += 1

    header_words = [w for line in lines[start : end + 1] for w in line.words]
    spans: dict[str, list[float]] = {}
    for word in header_words:
        role = _role_of(word.text)
        if role is None:
            continue
        bounds = spans.setdefault(role, [word.x0, word.x1])
        bounds[0] = min(bounds[0], word.x0)
        bounds[1] = max(bounds[1], word.x1)

    columns = _columns_from_spans(spans)
    return (start, end, columns) if columns else best


def _columns_from_spans(spans: dict[str, list[float]]) -> list[Column]:
    """Turn role→x-span into contiguous column boundaries.

    Boundaries fall midway between the end of one header label and the start of
    the next. Words are then assigned by their midpoint, which keeps a long test
    name ("ACTUAL DAYS/WEEK", ending past the label above it) in its own column.
    """
    ordered = sorted(spans.items(), key=lambda kv: kv[1][0])
    if len(ordered) < 2:
        return []

    # Real column labels occupy disjoint horizontal bands. If two roles overlap,
    # at least one span was built from tokens that are not column headers at
    # all, and every boundary derived from it would be wrong.
    for (_, (_, prev_x1)), (_, (next_x0, _)) in zip(ordered, ordered[1:]):
        if next_x0 < prev_x1 - _COLUMN_OVERLAP_TOLERANCE:
            return []

    columns: list[Column] = []
    for index, (role, (x0, x1)) in enumerate(ordered):
        if index == 0:
            start = float("-inf")
        else:
            prev_x1 = ordered[index - 1][1][1]
            start = (prev_x1 + x0) / 2

        if index == len(ordered) - 1:
            end = float("inf")
        else:
            next_x0 = ordered[index + 1][1][0]
            end = (x1 + next_x0) / 2

        columns.append(Column(role=role, x_start=start, x_end=end))

    return columns


def _assign(line: Line, columns: list[Column]) -> dict[str, list[Word]]:
    """Bucket a line's words into columns by horizontal midpoint."""
    buckets: dict[str, list[Word]] = {}
    for word in sorted(line.words, key=lambda w: w.x0):
        mid = word.x_mid
        for column in columns:
            if column.x_start <= mid < column.x_end:
                buckets.setdefault(column.role, []).append(word)
                break
    return buckets


def _cell_text(words: list[Word]) -> str:
    return " ".join(w.text for w in sorted(words, key=lambda w: w.x0))


def parse_page(page: Page) -> Table | None:
    """Reconstruct the table on one page, de-wrapping continuation lines."""
    lines = group_lines(page.words)
    header = find_header(lines)
    if header is None:
        return None

    _, header_end, columns = header
    body = lines[header_end + 1 :]

    # Pass 1 — split lines into anchors (real rows) and fragments (wrapped text).
    #
    # The discriminator is generic: a real row puts content in two or more
    # columns; a wrapped fragment, by definition, occupies exactly one.
    anchors: list[tuple[float, dict[str, list[Word]]]] = []
    fragments: list[tuple[float, str, list[Word]]] = []

    for line in body:
        buckets = _assign(line, columns)
        if not buckets:
            continue

        populated = len(buckets)
        widest_cell = max(len(ws) for ws in buckets.values())
        total_words = sum(len(ws) for ws in buckets.values())

        is_prose = widest_cell > _MAX_WORDS_IN_ONE_CELL or total_words > _MAX_WORDS_IN_ROW

        if populated >= 2 and not is_prose:
            anchors.append((line.top, buckets))
        elif populated == 1:
            role, words = next(iter(buckets.items()))
            fragments.append((line.top, role, words))
        # Prose spanning many columns is boilerplate (disclaimers, addresses)
        # and is dropped here rather than becoming a bogus row.

    if not anchors:
        return None

    # Pass 2 — attach each fragment to the vertically nearest anchor.
    #
    # A fragment further than the guard distance belongs to no row (page
    # furniture between the table and the footer) and is discarded.
    spacing = _median_spacing([top for top, _ in anchors])
    max_distance = spacing * 1.5 if spacing else float("inf")

    pieces: list[dict[str, list[tuple[float, str]]]] = [
        {role: [(top, _cell_text(words))] for role, words in buckets.items()}
        for top, buckets in anchors
    ]

    anchor_tops = [top for top, _ in anchors]
    for top, role, words in fragments:
        index = _nearest(anchor_tops, top)
        if index is None or abs(anchor_tops[index] - top) > max_distance:
            continue
        pieces[index].setdefault(role, []).append((top, _cell_text(words)))

    # Pass 3 — join each cell's pieces in vertical order, so a range split as
    # "3.40 -" above and "4.80" below reassembles as "3.40 - 4.80".
    rows: list[Row] = []
    for (top, _), cell_pieces in zip(anchors, pieces):
        cells = {
            role: " ".join(text for _, text in sorted(parts, key=lambda p: p[0])).strip()
            for role, parts in cell_pieces.items()
        }
        rows.append(Row(cells=cells, top=top, page=page.number))

    return Table(columns=columns, rows=rows, page=page.number)


def _median_spacing(tops: list[float]) -> float:
    if len(tops) < 2:
        return 0.0
    ordered = sorted(tops)
    gaps = [b - a for a, b in zip(ordered, ordered[1:]) if b - a > 0]
    return statistics.median(gaps) if gaps else 0.0


def _nearest(tops: list[float], target: float) -> int | None:
    if not tops:
        return None
    return min(range(len(tops)), key=lambda i: abs(tops[i] - target))


def parse_document(document: Document) -> list[Table]:
    """Reconstruct every table in the document, one per page that has one."""
    tables = []
    for page in document.pages:
        table = parse_page(page)
        if table is not None:
            tables.append(table)
    return tables
