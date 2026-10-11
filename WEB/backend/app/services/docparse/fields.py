# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""Layer 1c — label→value pairs from a FORM, with no vocabulary of labels.

`layout.py` reconstructs tables and `layout_matrix.py` reconstructs trend grids.
Neither reads a FORM: labelled values scattered across a page. That is most of
what a treatment record is — `Ordered Target Weight 50.0 kg`, `BFR 300 mL/min`,
`Close Treatment Reason …` — and it is why the 10/09 DaVita Treatment Details
Report scores 1 point out of a possible 41 against the signature table and had
to be imported as hand-written SQL (production session 2776, 2026-10-10).

`metadata.py` ALREADY does this, for six hand-typed label tuples — about 40
literals across `_COLLECTION_LABELS`, `_PROVIDER_LABELS`, `_LAB_LABELS` and the
rest. Its three primitives are the right ones and are deliberately mirrored
here; what changes is that the labels are DISCOVERED rather than listed, because
a list of six fields cannot read a form with forty (§3ab, and the operator's
own point about grounding hundreds of variations in five hard-coded types).

TWO FORMS, AND THE CORPUS SAYS WHICH MATTERS
--------------------------------------------
Measured over the 13 real documents, 2026-10-11:

  * INLINE  `Label: value` — present in all 13, but only about six of the 47
    candidates are real (`MPI`, `DOB`, `Age`, `DISCLAIMER`, `NOTE`,
    `METHODOLOGY`).
  * BELOW   a header with its value underneath — the dominant form in this
    family, and the reason `metadata.py` needs `_value_below` at all.

⚠️ **A COLON IS ALSO A TIME SEPARATOR.** A naive `([A-Z]…)\\s*:` over these
documents returns `DaVita Inc. 01/12/2026 14` (7×), `EDT 23` (24×), `EST 20`,
`EST 22` — footer timestamps, where the match ends just before the colon in
`14:23`. That is §3av's `parseInt("7:27") == 7` in a different reader. A colon
flanked by digits is never a label boundary here.

WHAT IS NOT VALIDATED, STATED PLAINLY
-------------------------------------
There is **no form-shaped clinical PDF on this machine** — measured: 304 PDFs on
disk, 13 of them clinical, and all 13 are table-shaped lab reports. The
treatment report exists only as photographs, which cannot be parsed at all
because there is no OCR path (TASKS 14e).

So the geometry below is validated against the lab reports' own header block —
including a cross-check that it recovers every field `metadata.py`'s hand-typed
extractor finds — and the no-colon treatment-form case is **unvalidated until a
real PDF exists**. §3ab: the corpus cannot see what it does not contain, and
saying so beats a synthetic fixture that proves the fixture.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .extract import Page
from .layout import Line, group_lines

_CLEAN = re.compile(r"^[:\s\-–|,]+|[\s|,]+$")

#: A label is a short phrase. Longer than this and the line is prose — the same
#: judgement `layout._MAX_WORDS_IN_ONE_CELL` makes about a table cell, and the
#: shape test §3ab's `looks_like_prose` makes about a row.
_MAX_LABEL_WORDS = 6

#: A header cell must not be the value itself. A purely numeric or unit-only
#: cell is data, whatever row it sits on.
_PURE_NUMBER = re.compile(r"^[<>]?\s*-?[\d,]+(?:\.\d+)?\s*%?$")

#: Gap (in points) that separates two cells on one line. `layout.py` measures a
#: word space at ~2pt and a column gap at ~29pt on this PDF family, so a
#: threshold anywhere between is equivalent; 8 is taken from that measured gap
#: rather than chosen.
_CELL_GAP = 8.0


@dataclass
class Field:
    """One label→value pair, with where it was found and how."""

    label: str
    value: str
    page: int
    kind: str                 # "inline" | "below"
    x0: float = 0.0
    x1: float = 0.0

    @property
    def key(self) -> str:
        """Normalised label, for a consumer that wants to look one up."""
        return re.sub(r"[^a-z0-9]+", "_", self.label.lower()).strip("_")


def _cells(line: Line) -> list[tuple[str, float, float]]:
    """Split a visual line into cells on the measured column gap."""
    words = sorted(line.words, key=lambda w: w.x0)
    if not words:
        return []
    out: list[tuple[str, float, float]] = []
    run = [words[0]]
    for word in words[1:]:
        if word.x0 - run[-1].x1 > _CELL_GAP:
            out.append((" ".join(w.text for w in run), run[0].x0, run[-1].x1))
            run = [word]
        else:
            run.append(word)
    out.append((" ".join(w.text for w in run), run[0].x0, run[-1].x1))
    return out


def _is_label_token(text: str) -> bool:
    """Could this single word be part of a label, rather than a value?

    Letters, optionally with punctuation a label carries (`Provider(s)`,
    `CLIA#`, `Date/Time`). A date, a number, a number with a unit, or a bare
    comparator is a VALUE and ends the label.
    """
    stripped = text.strip().strip("|")
    if not stripped:
        return False
    if re.match(r"^[<>]?\s*[\d.,/\-:%]+$", stripped):
        return False                       # 03/15/1974, 4.2, 3.5-5.0, 52%
    return bool(re.search(r"[A-Za-z]", stripped))


def _looks_like_label(text: str) -> bool:
    stripped = text.strip()
    if not stripped or _PURE_NUMBER.match(stripped):
        return False
    words = stripped.split()
    if len(words) > _MAX_LABEL_WORDS:
        return False
    # A label does not BEGIN with a date or a number. Belt-and-braces beside the
    # backward-walk floor above: `03/15/1974 | MPI` passed the letters test
    # because "MPI" is letters, and a reader seeing that label in a payload
    # would have no idea a previous field's value was inside it.
    if re.match(r"^[<>]?\s*[\d./\-]+$", words[0]):
        return False
    # A label contains letters. "10/09/2026" and "---" do not qualify.
    return bool(re.search(r"[A-Za-z]{2,}", stripped))


def _colon_split(text: str) -> tuple[str, str] | None:
    """Split a token at a colon that is NOT part of a clock.

    `MPI:` -> ("MPI", ""), `Weight:50` -> ("Weight", "50"), `14:23` -> None.
    """
    for index, char in enumerate(text):
        if char != ":":
            continue
        before, after = text[:index], text[index + 1:]
        if before[-1:].isdigit() and after[:1].isdigit():
            continue                      # a clock, not a label boundary
        return before, after
    return None


def inline_fields(line: Line, page: int) -> list[Field]:
    """`MPI: 1934716   DOB: 03/15/1974` — several pairs on one line.

    The bounds are DELIBERATELY ASYMMETRIC, and each side was measured:

    * The LABEL may not reach backwards across a cell gap. Allowed to, the line
      `Akpose, Adewole C.   DOB: 03/15/1974` yields the label
      **`Adewole C. DOB`** — the unlabelled patient name swallowed into the next
      field's label. Found on a real corpus document, not imagined.
    * The VALUE is the remainder of the label's OWN cell, or — when the colon
      ends that cell — the single next cell, and never more.

    That second rule is tighter than it first looks, because geometry alone
    cannot separate these two lines:

        MPI: 1934716              Printed 14:23      <- 'Printed 14:23' is NOT the value
        Ordered Target Weight:    50.0 kg            <- '50.0 kg' IS the value

    Both are `label:` then a cell gap then more text. Letting a value run
    forward to the next label swallows the footer in the first; bounding it to
    the label's own cell loses the value in the second, which on a form is most
    of them. Taking exactly ONE following cell reads both correctly.

    Working in WORDS rather than on the joined string is what makes the gap
    measurable at all — `layout.py` reads geometry the same way.
    """
    words = sorted(line.words, key=lambda w: w.x0)
    marks = [i for i, w in enumerate(words) if _colon_split(w.text) is not None]

    # PASS 1 — where does each label BEGIN? Needed before any value can be
    # bounded: a value must stop at the next label's first word, not at its
    # colon. Stopping at the colon makes `MPI: 1934716  Ordered Target Weight:`
    # read as `MPI = "1934716 Ordered Target"`, swallowing the next label.
    spans: list[tuple[int, int, str]] = []        # (start, colon index, label)
    for position, index in enumerate(marks):
        head, _ = _colon_split(words[index].text)  # type: ignore[misc]
        pieces = [head] if head else []
        cursor = index
        # The walk stops at a cell boundary, at another label's colon, or at a
        # word that is VALUE-shaped.
        #
        # ⚠️ That last condition is the one the real documents forced, while the
        # unit tests passed. `DOB: 03/15/1974  MPI: 1934716` packs the date and
        # `MPI:` 3pt apart — one cell — so a purely geometric walk swallowed the
        # date and the label came back as `03/15/1974 | MPI`, on all 13 corpus
        # documents. Geometry CANNOT separate those: the date is equidistant
        # from the label it follows and the label it precedes.
        #
        # Token shape can. A label is made of words; `03/15/1974` is a
        # measurement. `metadata._NEXT_LABEL` already assumes exactly this by
        # matching `[A-Z][A-Za-z]*` and nothing numeric.
        #
        # A floor at the previous colon was tried first and was WORSE than the
        # bug: it made `MPI`'s span start at the date, which truncated `DOB`'s
        # value to empty, and BOTH fields were then lost.
        while cursor > 0:
            previous = words[cursor - 1]
            if words[cursor].x0 - previous.x1 > _CELL_GAP:
                break                              # a cell boundary
            if cursor - 1 in marks:
                break                              # another field's label
            if not _is_label_token(previous.text):
                break                              # a previous field's value
            pieces.insert(0, previous.text)
            cursor -= 1
        spans.append((cursor, index, " ".join(p for p in pieces if p).strip()))

    # Word index -> which cell it belongs to, so "the rest of this cell" and
    # "the next cell" are answerable.
    cell_of: list[int] = [0] * len(words)
    cell = 0
    for i in range(1, len(words)):
        if words[i].x0 - words[i - 1].x1 > _CELL_GAP:
            cell += 1
        cell_of[i] = cell

    # PASS 2 — the remainder of the label's cell, else exactly one cell on.
    out: list[Field] = []
    for position, (start, index, label) in enumerate(spans):
        if not _looks_like_label(label):
            continue
        hard_stop = spans[position + 1][0] if position + 1 < len(spans) else len(words)
        _, tail = _colon_split(words[index].text)  # type: ignore[misc]

        own = [w.text for i, w in enumerate(words)
               if index < i < hard_stop and cell_of[i] == cell_of[index]]
        pieces = [tail, *own]

        if not any(p.strip() for p in pieces):
            # The colon ended its cell: take the NEXT cell, whole and alone.
            following = cell_of[index] + 1
            pieces = [w.text for i, w in enumerate(words)
                      if index < i < hard_stop and cell_of[i] == following]

        value = _CLEAN.sub("", " ".join(p for p in pieces if p.strip()))
        if value:
            out.append(Field(label=label, value=value, page=page, kind="inline",
                             x0=words[start].x0, x1=words[index].x1))
    return out


def header_fields(lines: list[Line], index: int, page: int) -> list[Field]:
    """A row of short headers with their values on the line beneath.

    Gated so an ordinary line of prose or a table body row cannot pass:

      * at least TWO cells, so a single stray phrase is not a header row;
      * every cell label-shaped (letters, <= 6 words, not a bare number);
      * the line below carries text in at least two of the same x-spans.

    The right bound for each value is the NEXT header's `x0` — `metadata.py`
    records what a fixed slack cost instead: "Ordering Provider(s)" sits beside
    "Requisition Number", and the provider came back with a requisition number
    stuck to their name.
    """
    if index + 1 >= len(lines):
        return []
    header = _cells(lines[index])
    if len(header) < 2 or not all(_looks_like_label(t) for t, _, _ in header):
        return []

    below = lines[index + 1]
    out: list[Field] = []
    for position, (label, x0, x1) in enumerate(header):
        right = header[position + 1][1] if position + 1 < len(header) else float("inf")
        tokens = [w for w in below.words if w.x1 > x0 - 2 and w.x0 < right - 2]
        value = _CLEAN.sub("", " ".join(
            w.text for w in sorted(tokens, key=lambda w: w.x0)))
        # Any non-empty value is kept. Deliberately NOT filtered on shape: a
        # real value is often itself wordy ("Desai, Anand MD", "Patient Choice
        # (AMA, feels unwell/cramping)"), so testing it for label-likeness
        # would discard exactly the fields worth having.
        if value:
            out.append(Field(label=label, value=value, page=page,
                             kind="below", x0=x0, x1=x1))
    # Require that the row below actually populated more than one column,
    # otherwise this was a wrapped title rather than a header row.
    return out if len(out) >= 2 else []


def discover_fields(page: Page) -> list[Field]:
    """Every label→value pair on a page, inline first then header-over-value.

    Returns them in reading order. A consumer maps the ones it recognises onto
    its own columns; discovery holds NO opinion about which fields matter, which
    is the whole difference from `metadata.py`'s six hand-typed tuples.
    """
    lines = group_lines(page.words)
    out: list[Field] = []
    for index, line in enumerate(lines):
        inline = inline_fields(line, page.number)
        out.extend(inline)
        # A line already read as `Label: value` is not also a header row.
        if not inline:
            out.extend(header_fields(lines, index, page.number))
    return out


def fields_in_document(pages: list[Page]) -> dict[str, Field]:
    """First occurrence of each discovered field, keyed by normalised label.

    FIRST, not last: `metadata.py` reads the header block off page 1 because it
    repeats on every page, and §3ba measured what last-wins costs on a repeating
    header — a dict keyed by label let the LAST column win and 234 of 609
    statements were aimed at the wrong instant.
    """
    found: dict[str, Field] = {}
    for page in pages:
        for field in discover_fields(page):
            found.setdefault(field.key, field)
    return found
