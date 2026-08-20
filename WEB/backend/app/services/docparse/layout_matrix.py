"""Layer 1b — reconstruct a trend matrix (analyte × period).

The other layout module handles the common shape: one row per measurement, with
labelled columns telling you which cell is the result and which is the range.

Flowsheet and "patient profile" documents use a different shape entirely — the
columns are *time periods* and each cell is a measurement:

    ANEMIA            SEP 2025  AUG 2025  JUL 2025   ADEQUACY   SEP 2025 ...
    HEMOGLOBIN (g/dL)     13.2      12.4      12.8   STDKT/V        4.01 ...
                       (09/03)   (08/13)   (07/17)                (09/03) ...

Three things make this resistant to the column parser:

* there is no RESULT or REFERENCE header to anchor on — the headers are dates;
* several independent grids sit side by side, and they are **vertically offset
  from one another**, so a visual line is not a row;
* a cell's collection date is printed on its own line, right-shifted from the
  value it belongs to.

So each block is located by its period headers and then parsed on its own.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .extract import Page, Word
from .layout import Line, group_lines

_MONTHS = "jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec"

#: Tokens that can head a period column. Kept broad on purpose — the point is to
#: recognise "a column keyed by time", not any one vendor's date style.
_PERIOD_PATTERNS = [
    re.compile(rf"^({_MONTHS})[a-z]*$", re.I),          # SEP  (year follows)
    re.compile(r"^(19|20)\d{2}$"),                       # 2025
    re.compile(r"^\d{1,2}/\d{1,2}/\d{2,4}$"),            # 09/03/2025
    re.compile(r"^\d{1,2}/\d{2,4}$"),                    # 09/25
    re.compile(r"^(19|20)\d{2}-\d{2}-\d{2}$"),           # 2025-09-03
    re.compile(rf"^({_MONTHS})[a-z]*-\d{{2,4}}$", re.I),  # Sep-25
    re.compile(r"^Q[1-4]$", re.I),
]

#: A parenthesised cell like "(09/03)" — a collection date, not a value.
_PAREN_DATE = re.compile(r"^\((\d{1,2}/\d{1,2}(?:/\d{2,4})?)\)$")

#: A label-column fragment that is really a wrapped unit — "(g/dL)", "(%)".
_PAREN_ONLY = re.compile(r"^\(.*\)$")

#: Two period headers next to each other are a grid; one is a coincidence.
_MIN_PERIOD_COLUMNS = 2

#: Horizontal slack when deciding which period column a token sits under.
_COLUMN_PADDING = 4.0

#: Prose guards. A measurement is one or two tokens ("13.2", "< 0.5", "N/A") and
#: an analyte name is short. Page furniture — the DaVita printing disclaimer
#: runs the full width of the page — otherwise arrives as cells.
_MAX_VALUE_TOKENS = 2
_MAX_ANALYTE_TOKENS = 6


@dataclass
class PeriodColumn:
    label: str
    x0: float
    x1: float
    x_start: float = 0.0   # assigned boundary
    x_end: float = 0.0


@dataclass
class Block:
    """One grid: a label column on the left, then N period columns."""

    label: str
    label_x0: float
    label_x1: float
    periods: list[PeriodColumn] = field(default_factory=list)

    @property
    def x0(self) -> float:
        return self.label_x0

    @property
    def x1(self) -> float:
        return self.periods[-1].x_end if self.periods else self.label_x1


@dataclass
class MatrixCell:
    analyte: str
    period: str
    value: str
    cell_date: str | None
    block: str


@dataclass
class MatrixTable:
    blocks: list[Block]
    cells: list[MatrixCell]
    page: int


def _is_period_token(text: str) -> bool:
    return any(p.match(text) for p in _PERIOD_PATTERNS)


def _merge_period_tokens(words: list[Word]) -> list[PeriodColumn]:
    """Join adjacent period tokens — "SEP" + "2025" is one column header."""
    columns: list[PeriodColumn] = []
    for word in sorted(words, key=lambda w: w.x0):
        if not _is_period_token(word.text):
            continue
        if columns and word.x0 - columns[-1].x1 <= 8.0:
            columns[-1].label += f" {word.text}"
            columns[-1].x1 = word.x1
        else:
            columns.append(PeriodColumn(label=word.text, x0=word.x0, x1=word.x1))
    return columns


def find_blocks(line: Line) -> list[Block]:
    """Split a period-header line into independent side-by-side grids.

    A non-period token between period columns (``ADEQUACY``) both ends the
    current grid and names the next one.
    """
    ordered = sorted(line.words, key=lambda w: w.x0)
    blocks: list[Block] = []
    current: Block | None = None
    pending: list[Word] = []

    for word in ordered:
        if _is_period_token(word.text):
            if current is None:
                label_words = pending or []
                current = Block(
                    label=" ".join(w.text for w in label_words),
                    label_x0=label_words[0].x0 if label_words else 0.0,
                    label_x1=label_words[-1].x1 if label_words else word.x0,
                )
                pending = []
            current.periods.append(PeriodColumn(label=word.text, x0=word.x0, x1=word.x1))
        else:
            # A label after at least one period column closes the current grid.
            if current is not None and current.periods:
                blocks.append(current)
                current = None
            pending.append(word)

    if current is not None and current.periods:
        blocks.append(current)

    # Re-merge split period tokens ("SEP" "2025") inside each block.
    for block in blocks:
        merged: list[PeriodColumn] = []
        for column in block.periods:
            if merged and column.x0 - merged[-1].x1 <= 8.0:
                merged[-1].label += f" {column.label}"
                merged[-1].x1 = column.x1
            else:
                merged.append(column)
        block.periods = merged

    blocks = [b for b in blocks if len(b.periods) >= _MIN_PERIOD_COLUMNS]

    # Give every period column a horizontal catchment. The right edge stops
    # short of the next column so a right-shifted date stays with its own value.
    for index, block in enumerate(blocks):
        next_x = blocks[index + 1].label_x0 if index + 1 < len(blocks) else float("inf")
        for position, column in enumerate(block.periods):
            column.x_start = column.x0 - _COLUMN_PADDING
            if position + 1 < len(block.periods):
                column.x_end = block.periods[position + 1].x0 - _COLUMN_PADDING
            else:
                column.x_end = next_x

    return blocks


def find_period_header(lines: list[Line]) -> tuple[int, list[Block]] | None:
    """First line that yields at least one usable grid."""
    for index, line in enumerate(lines):
        blocks = find_blocks(line)
        if blocks:
            return index, blocks
    return None


def _parse_block(block: Block, body: list[Line]) -> list[MatrixCell]:
    """Parse one grid independently of its neighbours."""
    # Restrict to this block's horizontal band, then re-line — neighbouring
    # grids sit at different vertical offsets and must not merge into a row.
    words = [
        w
        for line in body
        for w in line.words
        if block.x0 - _COLUMN_PADDING <= w.x0 < block.x1
    ]
    if not words:
        return []

    label_end = block.periods[0].x_start

    cells: list[MatrixCell] = []
    analyte_parts: list[str] = []
    pending: dict[str, dict[str, str]] = {}

    def flush() -> None:
        name = " ".join(analyte_parts).strip()
        if not name or len(name.split()) > _MAX_ANALYTE_TOKENS:
            pending.clear()
            return
        for period, cell in pending.items():
            value = cell.get("value", "").strip()
            if not value or len(value.split()) > _MAX_VALUE_TOKENS:
                continue
            cells.append(
                MatrixCell(
                    analyte=name,
                    period=period,
                    value=value,
                    cell_date=cell.get("date"),
                    block=section,
                )
            )
        pending.clear()

    section = block.label

    # The grid's rows are evenly spaced; the footer sits after a visible gap
    # (29pt versus a 10pt median in the sample). Break on that gap rather than
    # trying to recognise boilerplate by its wording, which is vendor-specific.
    block_lines = group_lines(words)
    gaps = [b.top - a.top for a, b in zip(block_lines, block_lines[1:]) if b.top > a.top]
    median_gap = sorted(gaps)[len(gaps) // 2] if gaps else 0.0
    gap_limit = max(2.2 * median_gap, 20.0) if median_gap else float("inf")

    previous_top: float | None = None

    for line in block_lines:
        if previous_top is not None and line.top - previous_top > gap_limit and cells:
            break
        previous_top = line.top

        ordered = sorted(line.words, key=lambda w: w.x0)

        # The grid restates its period headers for each new category
        # ("NUTRITION  SEP 2025  AUG 2025 ..."). That is a section break, not a
        # measurement — without this the header itself becomes an analyte whose
        # value is the period label.
        if sum(1 for w in ordered if _is_period_token(w.text)) >= _MIN_PERIOD_COLUMNS:
            flush()
            analyte_parts = []
            heading = " ".join(w.text for w in ordered if not _is_period_token(w.text)).strip()
            if heading:
                section = heading
            continue

        label_tokens = [w for w in ordered if w.x0 < label_end]
        label_text = " ".join(w.text for w in label_tokens).strip()

        # The grid is contiguous. The first run of prose after it is the page
        # footer — DaVita prints a multi-line printing disclaimer across the
        # full width — so stop rather than skip, or its wrapped remains keep
        # landing in value columns as two-word "results".
        if len(label_text.split()) > _MAX_ANALYTE_TOKENS:
            break

        # A parenthesised label is a wrapped unit, not the next analyte.
        starts_row = bool(label_text) and not _PAREN_ONLY.match(label_text)

        if starts_row:
            flush()
            analyte_parts = [label_text]
        elif label_text:
            analyte_parts.append(label_text)

        for word in ordered:
            if word.x0 < label_end:
                continue
            for column in block.periods:
                if column.x_start <= word.x0 < column.x_end:
                    slot = pending.setdefault(column.label, {})
                    date_match = _PAREN_DATE.match(word.text)
                    if date_match:
                        slot["date"] = date_match.group(1)
                    else:
                        slot["value"] = (slot.get("value", "") + " " + word.text).strip()
                    break

    flush()
    return cells


def parse_page(page: Page) -> MatrixTable | None:
    lines = group_lines(page.words)
    header = find_period_header(lines)
    if header is None:
        return None

    header_index, blocks = header
    body = lines[header_index + 1 :]

    cells: list[MatrixCell] = []
    for block in blocks:
        cells.extend(_parse_block(block, body))

    return MatrixTable(blocks=blocks, cells=cells, page=page.number) if cells else None
