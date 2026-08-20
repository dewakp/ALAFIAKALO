"""Layer 2a — pull report-level context out of a document.

Who the report is about, when the specimen was taken, which lab ran it, who
ordered it. Labels are matched by synonym and the value is taken from the same
line or from directly beneath — clinical headers are usually a small grid:

    Collection Date/Time    Result Release Date    Ordering Provider(s)
    10/03/2025              10/06/2025             Desai, Anand MD

Dates are the trap here. Every one of these documents prints a date of birth
above the collection date, and the previous parser returned "the first date in
the file", so every lab report in the system was stamped 03/15/1974. Birth dates
are therefore identified and excluded before any fallback runs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from .extract import Document
from .layout import Line, group_lines
from .normalize import parse_date

_DATE_TOKEN = re.compile(r"\b(\d{1,2}/\d{1,2}/\d{2,4}|\d{4}-\d{2}-\d{2})\b")

#: Labels whose value we want, in priority order.
_COLLECTION_LABELS = (
    "collection date/time", "collection date", "date collected", "collected",
    "specimen collected", "draw date", "date drawn", "collected on",
)
_REPORTED_LABELS = ("result release date", "date reported", "reported", "released")
_PROVIDER_LABELS = (
    "ordering provider(s)", "ordering provider", "ordering physician",
    "primary nephrologist", "nephrologist", "ordered by", "referring physician",
    "requested by", "attending", "provider", "physician",
)
_LAB_LABELS = (
    "lab location (clia#)", "lab location", "performing lab", "laboratory",
    "performed at", "lab name", "facility",
)
# Bare "name" is deliberately absent — it matches the *table* header
# "LAB TEST NAME", and the value beneath it is the first analyte, so the patient
# came out as "RATIO".
_PATIENT_LABELS = ("patient name", "patient")
_MRN_LABELS = ("mpi", "mrn", "medical record number", "patient id", "account")

#: Anything on a line with these words is a birth date, never a collection date.
_BIRTH_MARKERS = ("dob", "date of birth", "birth date", "born")

#: Dates that are real but are not this specimen's — a therapy start date is
#: eight years off, and stamping labs with it would be worse than having none.
_NON_COLLECTION_MARKERS = (
    "start date", "began", "admitted", "printed", "schedule", "next appointment",
    "ver.", "plan status", "expires",
)

#: "Akpose, Adewole C." — surname, given names, optional initial.
_NAME_RE = re.compile(r"^([A-Z][A-Za-z'\-]+),\s+([A-Z][A-Za-z'\-]+(?:\s+[A-Z]\.?)?)")

_CLEAN_VALUE = re.compile(r"^[:\s\-–|]+|[\s|]+$")

#: The start of the next "Label:" field on a line that packs several together.
_NEXT_LABEL = re.compile(r"\s+[A-Z][A-Za-z]*(?:\s+[A-Za-z]+){0,4}\s*:")


@dataclass
class ReportMetadata:
    patient_name: str | None = None
    report_date: date | None = None
    reported_date: date | None = None
    lab_name: str | None = None
    ordering_provider: str | None = None
    identifiers: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _label_at(line: Line, labels: tuple[str, ...]) -> tuple[float, float, float] | None:
    """If the line carries one of `labels`, return (x0, x1, right_bound).

    `right_bound` is where the *next* header label starts. Values below a header
    are read within that bound, otherwise a neighbouring column bleeds in —
    "Ordering Provider(s)" sits beside "Requisition Number", and a fixed slack
    returned the provider with a requisition number stuck to their name.
    """
    lowered = _normalise(line.text)
    for label in labels:
        if not (lowered.startswith(label) or f" {label}" in f" {lowered}"):
            continue
        words = sorted(line.words, key=lambda w: w.x0)
        target = label.split()
        for start in range(len(words)):
            run = words[start : start + len(target)]
            if len(run) == len(target) and _normalise(" ".join(w.text for w in run)) == label:
                after = words[start + len(target) :]
                return run[0].x0, run[-1].x1, (after[0].x0 if after else float("inf"))
        return words[0].x0, words[-1].x1, float("inf")
    return None


def _value_after_colon(line: Line, labels: tuple[str, ...]) -> str | None:
    """`Ordering Provider: Desai, Anand MD` — value on the same line."""
    lowered = _normalise(line.text)
    for label in labels:
        marker = f"{label}:"
        index = lowered.find(marker)
        if index >= 0:
            rest = line.text[index + len(marker):]
            # These header lines pack several fields onto one row
            # ("Primary Nephrologist: X   Actual DaVita Start Date: Y"), so the
            # value ends where the next label begins.
            next_label = _NEXT_LABEL.search(rest)
            if next_label:
                rest = rest[: next_label.start()]
            return _CLEAN_VALUE.sub("", rest) or None
    return None


def _value_below(lines: list[Line], index: int, span: tuple[float, float, float]) -> str | None:
    """Value printed under its own column header, bounded by the next column."""
    x0, _, right_bound = span
    for line in lines[index + 1 : index + 4]:
        tokens = [w for w in line.words if w.x1 > x0 - 2 and w.x0 < right_bound - 2]
        text = " ".join(w.text for w in sorted(tokens, key=lambda w: w.x0)).strip()
        if text:
            return _CLEAN_VALUE.sub("", text) or None
    return None


def _find_field(lines: list[Line], labels: tuple[str, ...]) -> str | None:
    for index, line in enumerate(lines):
        inline = _value_after_colon(line, labels)
        if inline:
            return inline
        span = _label_at(line, labels)
        if span:
            below = _value_below(lines, index, span)
            if below:
                return below
    return None


def _dates_on(line: Line) -> list[str]:
    return _DATE_TOKEN.findall(line.text)


def extract_metadata(document: Document) -> ReportMetadata:
    meta = ReportMetadata()
    if not document.pages:
        return meta

    # The header block repeats on every page; the first page is enough.
    lines = group_lines(document.pages[0].words)

    # The "Surname, Given M." line is a stronger signal than a "Patient" label,
    # which also matches document titles like "IDT Patient Profile Worksheet".
    meta.patient_name = _guess_patient_name(lines) or _find_field(lines, _PATIENT_LABELS)
    meta.lab_name = _find_field(lines, _LAB_LABELS)
    meta.ordering_provider = _find_field(lines, _PROVIDER_LABELS)

    identifier = _find_field(lines, _MRN_LABELS)
    if identifier:
        meta.identifiers.append(identifier)

    collected = _find_field(lines, _COLLECTION_LABELS)
    meta.report_date = parse_date(_first_date(collected)) if collected else None

    reported = _find_field(lines, _REPORTED_LABELS)
    meta.reported_date = parse_date(_first_date(reported)) if reported else None

    if meta.report_date is None:
        meta.report_date = _fallback_date(lines, meta)

    return meta


def _first_date(text: str | None) -> str | None:
    if not text:
        return None
    found = _DATE_TOKEN.search(text)
    return found.group(1) if found else None


def _fallback_date(lines: list[Line], meta: ReportMetadata) -> date | None:
    """Earliest plausible non-birth date in the header.

    Never returns a date that shares a line with a birth-date label, and never
    one that equals a date already recognised as the patient's DOB.
    """
    birth_dates: set[str] = set()
    candidates: list[str] = []

    for line in lines:
        lowered = _normalise(line.text)
        found = _dates_on(line)
        if not found:
            continue
        if any(marker in lowered for marker in _BIRTH_MARKERS):
            birth_dates.update(found)
            continue
        if any(marker in lowered for marker in _NON_COLLECTION_MARKERS):
            continue
        candidates.extend(found)

    for raw in candidates:
        if raw in birth_dates:
            continue
        parsed = parse_date(raw)
        if parsed:
            meta.notes.append(
                "Collection date was not labelled; used the first non-birth date in the header."
            )
            return parsed

    if birth_dates and not candidates:
        meta.notes.append(
            "No collection date found — the only dates in the header are birth dates."
        )
    return None


def _guess_patient_name(lines: list[Line]) -> str | None:
    """`Surname, Given M.` near the top, usually beside DOB/MRN."""
    for line in lines[:8]:
        match = _NAME_RE.match(line.text.strip())
        if match:
            return f"{match.group(2)} {match.group(1)}".strip()
    return None


def redact(text: str, meta: ReportMetadata) -> str:
    """Strip direct identifiers before any text is handed to a model.

    The model runs locally, so this is defence in depth rather than the control
    itself — but a prompt is also logged, and a log is a second copy.
    """
    redacted = text
    if meta.patient_name:
        for part in meta.patient_name.split():
            if len(part) > 2:
                redacted = re.sub(rf"\b{re.escape(part)}\b", "[NAME]", redacted, flags=re.I)
    for identifier in meta.identifiers:
        redacted = redacted.replace(identifier, "[ID]")

    redacted = re.sub(
        rf"((?:{'|'.join(_BIRTH_MARKERS)})\s*:?\s*)({_DATE_TOKEN.pattern})",
        r"\1[DATE]",
        redacted,
        flags=re.I,
    )
    return redacted
