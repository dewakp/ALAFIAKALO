# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""Label→value pairs from a form, with no vocabulary of labels.

`metadata.py` reads six fields using ~40 hand-typed label literals.
`fields.py` discovers them structurally, because a list of six cannot read a
form with forty — the operator's point about grounding hundreds of variations in
a handful of hard-coded entries, applied to field names instead of doc types.

The oracle is `metadata.py` itself: whatever the tuned reader finds on a real
document, discovery must also find, or this is a regression dressed as a
generalisation. Measured over the 13-document corpus, 2026-10-11:

    collection date   12 of 12
    lab               12 of 12
    ordering provider 13 of 13
    fields discovered 165 total — ~12.7 per document against a ceiling of 6

Two bugs were found by that measurement rather than by reading the code, and
both are pinned below: a colon inside a CLOCK read as a label boundary, and
inline matching run per LINE letting the unlabelled patient name bleed into the
next field's label.

⚠️ Scope, stated so it is not overclaimed: there is NO form-shaped clinical PDF
on this machine (304 PDFs, 13 clinical, all table-shaped lab reports), so the
geometry is validated against those reports' header block and the no-colon
treatment-form case is UNVALIDATED until a real PDF exists. §3ab — the corpus
cannot see what it does not contain.
"""

import pathlib

import pytest

from app.services.docparse.extract import Page, Word
from app.services.docparse.fields import (
    discover_fields,
    fields_in_document,
    header_fields,
    inline_fields,
)
from app.services.docparse.layout import group_lines


def _words(cells: list[str], top: float = 10.0, gap: float = 40.0) -> list[Word]:
    """Lay out CELLS on one visual line with realistic spacing.

    Each string is one cell; words inside it sit 3pt apart (a word space) and
    cells sit `gap` apart. This matters: the first version of these fixtures
    placed every word 60pt from the last, which makes each WORD its own cell, so
    `Ordered Target Weight:` arrived as three cells and the label came back as
    just `Weight`. Seven tests failed against an implementation that was working
    correctly on real documents — the fixture was wrong, not the code.

    `layout.py` measures a word space at ~2pt and a column gap at ~29pt on this
    PDF family, so 3 and 40 sit cleanly either side of `_CELL_GAP`.
    """
    words: list[Word] = []
    x = 0.0
    for position, cell in enumerate(cells):
        if position:
            x += gap
        for token in cell.split():
            width = max(len(token) * 6.0, 6.0)
            words.append(Word(text=token, x0=x, x1=x + width, top=top,
                              bottom=top + 9.0))
            x += width + 3.0
    return words


def _line(cells: list[str], top: float = 10.0, gap: float = 40.0):
    return group_lines(_words(cells, top, gap))[0]


def _page(rows: list[list[str]], gap: float = 40.0) -> Page:
    words: list[Word] = []
    for index, row in enumerate(rows):
        words.extend(_words(row, top=10.0 + index * 20.0, gap=gap))
    return Page(number=1, width=612.0, height=792.0, words=words,
                text="\n".join(" ".join(row) for row in rows))


def _at(rows: list[list[tuple[str, float]]]) -> Page:
    """A page whose cells sit at EXPLICIT x positions, words 3pt apart inside.

    `_page` lays every row out from x=0, so a two-cell value row does not line
    up under a two-cell header row — which made the bleed test fail against
    correct code, because `R-4471` began 15pt to the LEFT of the `Requisition`
    header it belongs under. Real reports align a value column with its header,
    so a test about column bounds has to place the columns.
    """
    words: list[Word] = []
    for index, row in enumerate(rows):
        top = 10.0 + index * 20.0
        for cell, x0 in row:
            x = x0
            for token in cell.split():
                width = max(len(token) * 6.0, 6.0)
                words.append(Word(text=token, x0=x, x1=x + width, top=top,
                                  bottom=top + 9.0))
                x += width + 3.0
    return Page(number=1, width=612.0, height=792.0, words=words,
                text="\n".join(" ".join(c for c, _ in row) for row in rows))


# ── A colon is also a time separator ────────────────────────────────────────

def test_a_clock_is_not_a_label():
    """Measured: a naive `([A-Z]…)\\s*:` over the corpus returns
    `DaVita Inc. 01/12/2026 14` seven times and `EDT 23` twenty-four — footer
    timestamps, matched right up to the colon in `14:23`. §3av's
    `parseInt("7:27") == 7`, in a different reader."""
    assert inline_fields(
        _line(["DaVita Inc. 01/12/2026 14:23:45 EST"]), 1) == []


def test_a_real_label_beside_a_clock_still_resolves():
    """The exclusion must not throw the baby out: a labelled field on a line
    that also carries a time is still a field."""
    found = inline_fields(_line(["MPI:", "1934716", "Printed 14:23"]), 1)
    assert [(f.label, f.value) for f in found] == [("MPI", "1934716")]


# ── Inline matching is per CELL, not per line ───────────────────────────────

def test_an_unlabelled_name_does_not_bleed_into_the_next_label():
    """Run over the whole LINE, `Akpose, Adewole C.  DOB: 03/15/1974` yields the
    label `Adewole C. DOB`. Measured on the real corpus — one document — and
    fixed by matching within the cell the label sits in."""
    found = inline_fields(_line(["Akpose, Adewole C.", "DOB:", "03/15/1974"]), 1)
    assert [f.label for f in found] == ["DOB"]
    assert found[0].value == "03/15/1974"


def test_a_previous_fields_VALUE_does_not_become_the_next_fields_label():
    """`DOB: 03/15/1974 MPI: 1934716` packed into ONE cell.

    Found by re-measuring the corpus after an implementation change, not by any
    unit test: the label came back as `03/15/1974 | MPI` on all 13 documents.
    The backward walk stopped when the previous WORD was a label, which the date
    is not — it is the previous label's VALUE. The walk is now floored at the
    previous colon.

    The spacing is the whole point of this fixture: one cell, so the words sit
    3pt apart. Separate cells (the earlier fixtures) hide the bug entirely.
    """
    found = inline_fields(_line(["DOB: 03/15/1974 MPI: 1934716"]), 1)
    assert [(f.label, f.value) for f in found] == [
        ("DOB", "03/15/1974"), ("MPI", "1934716")]


def test_a_label_never_begins_with_a_date_or_a_number():
    """A value-shaped word ends the label — it does not sink the field.

    This assertion was originally written as `== []`, expecting the date-start
    guard in `_looks_like_label` to reject the whole thing. That was the wrong
    expectation: the walk now stops AT the date, so the label is simply `MPI`
    and the field is read correctly. Discarding it would have lost a real field
    to protect against a bug that no longer exists — `_looks_like_label`'s
    date-start check remains as a backstop, not as the mechanism.
    """
    found = inline_fields(_line(["03/15/1974 MPI: 1934716"]), 1)
    assert [(f.label, f.value) for f in found] == [("MPI", "1934716")]


def test_several_fields_on_one_line_each_keep_their_own_value():
    found = inline_fields(
        _line(["MPI: 1934716", "Age: 52", "DOB: 03/15/1974"]), 1)
    assert [(f.label, f.value) for f in found] == [
        ("MPI", "1934716"), ("Age", "52"), ("DOB", "03/15/1974")]


# ── Header over value ───────────────────────────────────────────────────────

def test_a_value_is_bounded_by_the_NEXT_header():
    """`metadata.py` records what a fixed slack cost instead: "Ordering
    Provider(s)" sits beside "Requisition Number", and the provider came back
    with a requisition number stuck to their name."""
    page = _at([
        [("Ordering Provider", 0.0), ("Requisition Number", 220.0)],
        [("Desai, Anand MD", 0.0), ("R-4471", 220.0)],
    ])
    lines = group_lines(page.words)
    found = header_fields(lines, 0, 1)
    by_label = {f.label: f.value for f in found}
    assert by_label["Ordering Provider"] == "Desai, Anand MD"
    assert "R-4471" not in by_label["Ordering Provider"]
    assert by_label["Requisition Number"] == "R-4471"


def test_a_single_cell_line_is_not_a_header_row():
    """One stray phrase above some text is a wrapped title, not a header."""
    page = _page([["Laboratory Report"], ["continued"]])
    assert header_fields(group_lines(page.words), 0, 1) == []


def test_a_row_of_numbers_is_not_a_header_row():
    """A table BODY row must not be read as labels for the row beneath it."""
    page = _page([["4.2", "3.5", "5.0"], ["5.1", "3.5", "5.5"]])
    assert header_fields(group_lines(page.words), 0, 1) == []


# ── Document level ──────────────────────────────────────────────────────────

def test_the_FIRST_occurrence_wins():
    """§3ba measured what last-wins costs on a repeating header: a dict keyed by
    label let the LAST column win and 234 of 609 statements were aimed at the
    wrong instant. The header block repeats on every page here."""
    first = _page([["MPI: 1934716"]])
    second = Page(number=2, width=612.0, height=792.0,
                  words=_words(["MPI: 9999999"]),
                  text="MPI: 9999999")
    found = fields_in_document([first, second])
    assert found["mpi"].value == "1934716"
    assert found["mpi"].page == 1


def test_a_line_read_as_inline_is_not_also_read_as_a_header():
    page = _page([["MPI: 1934716", "Age: 52"], ["something beneath"]])
    kinds = {f.kind for f in discover_fields(page)}
    assert kinds == {"inline"}


def test_discovery_holds_no_opinion_about_which_fields_matter():
    """The whole difference from `metadata.py`: no vocabulary. An invented label
    nobody has ever seen is discovered just the same, which is what lets a
    document type nobody enumerated be read."""
    found = inline_fields(_line(["Ordered Target Weight:", "50.0 kg"]), 1)
    assert [(f.label, f.value) for f in found] == [
        ("Ordered Target Weight", "50.0 kg")]


# ── The oracle, against real documents ──────────────────────────────────────

def _corpus() -> pathlib.Path | None:
    for parent in pathlib.Path(__file__).resolve().parents:
        candidate = parent / "ML" / "data" / "raw" / "pdf"
        if candidate.is_dir() and any(candidate.glob("*.pdf")):
            return candidate
    return None


@pytest.mark.skipif(_corpus() is None,
                    reason="the real PHI corpus is not mounted here — it is "
                           "deliberately not in CI (§3ab)")
def test_discovery_recovers_every_field_the_hand_typed_reader_finds():
    """Vocabulary-free must not mean worse. `metadata.py` is the oracle.

    Dates are compared by their DIGITS: the oracle is ISO (`2025-10-03`) and the
    document prints US (`10/03/2025`), and comparing the strings reported 0 of
    12 on a reader that was working perfectly — my measurement bug, not the
    code's, and worth pinning so the next reader does not repeat it.

    `patient_name` is deliberately NOT asserted: these reports print the name
    with no label at all, so it belongs to `metadata._guess_patient_name`'s
    name-shape regex. A form extractor cannot find an unlabelled field, and
    pretending otherwise would be the wrong fix.
    """
    import re

    from app.services.docparse.extract import extract
    from app.services.docparse.metadata import extract_metadata

    corpus = _corpus()
    assert corpus is not None
    missed: list[str] = []
    discovered = 0

    for path in sorted(corpus.glob("*.pdf")):
        document = extract(path.read_bytes(), path.name)
        meta = extract_metadata(document)
        found = fields_in_document(document.pages)
        discovered += len(found)
        blob = " | ".join(f"{f.label}={f.value}" for f in found.values())

        if meta.report_date:
            wanted = set(re.findall(r"\d+", str(meta.report_date)))
            if not wanted <= set(re.findall(r"\d+", blob)):
                missed.append(f"{path.name}: collection date {meta.report_date}")
        for name, oracle in (("lab", meta.lab_name),
                             ("provider", meta.ordering_provider)):
            if oracle and oracle.lower()[:18] not in blob.lower():
                missed.append(f"{path.name}: {name} {oracle!r}")

    assert not missed, (
        "discovery lost a field the hand-typed reader finds:\n  "
        + "\n  ".join(missed))
    assert discovered > 100, (
        f"only {discovered} fields discovered across the corpus — the gates "
        "have become too strict")
