"""Medication and condition records, read from the same reconstructed tables.

A medication list and a problem list are the same geometry as a lab report — a
subject column plus attributes — so the layout engine needs no changes; only the
meaning of the columns differs.

Enum values are emitted as plain strings so this module keeps no dependency on
the app's models, the same property that lets `extract` and `layout` be
exercised against a corpus of PDFs with no database. The mapper converts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from .layout import Table
from .normalize import parse_date

# ── Medications ──────────────────────────────────────────────────────────────

#: "500 mg", "0.25mcg", "1,000 IU"
_DOSE_RE = re.compile(
    r"(\d[\d,]*\.?\d*)\s*(mcg|µg|ug|mg|g|kg|ml|l|iu|units?|meq|mmol|%)\b",
    re.I,
)

_ROUTES = {
    "oral", "po", "by mouth", "iv", "intravenous", "im", "intramuscular",
    "subcutaneous", "sc", "subq", "topical", "inhaled", "inhalation",
    "sublingual", "rectal", "transdermal", "ophthalmic", "otic", "nasal",
    "intraperitoneal", "ip",
}

#: Frequency shorthand a prescription actually uses.
_FREQUENCY_HINTS = (
    "daily", "once", "twice", "three times", "four times", "every", "hourly",
    "weekly", "monthly", "bid", "tid", "qid", "qd", "hs", "prn", "as needed",
    "with meals", "before meals", "after meals", "at bedtime", "morning",
    "evening", "night", "am", "pm", "q4h", "q6h", "q8h", "q12h", "qhs",
)

_INACTIVE_HINTS = ("stopped", "discontinued", "completed", "inactive", "held", "cancelled")


@dataclass
class MedicationRecord:
    name: str
    raw_name: str
    dosage: str | None = None
    dosage_unit: str | None = None
    frequency: str | None = None
    route: str | None = None
    start_date: date | None = None
    prescribing_doctor: str | None = None
    is_active: bool = True
    notes: str | None = None
    confidence: float = 0.0
    parse_notes: list[str] = field(default_factory=list)


def split_dose(text: str) -> tuple[str | None, str | None]:
    """`500 mg` -> ("500", "mg"). Returns (None, None) when there is no dose."""
    match = _DOSE_RE.search(text or "")
    if not match:
        return None, None
    amount = match.group(1).replace(",", "")
    unit = match.group(2).lower()
    # Normalize the two ways microgram is written; mcg is what the app stores.
    unit = {"µg": "mcg", "ug": "mcg", "iu": "IU", "unit": "units"}.get(unit, unit)
    return amount, unit


def looks_like_frequency(text: str) -> bool:
    lowered = (text or "").lower()
    return any(hint in lowered for hint in _FREQUENCY_HINTS)


def looks_like_route(text: str) -> bool:
    return (text or "").strip().lower() in _ROUTES


def records_from_medication_table(table: Table) -> list[MedicationRecord]:
    """Read a medication list. Columns are used when present, inferred when not."""
    records: list[MedicationRecord] = []
    for row in table.rows:
        raw_name = row.get("name").strip()
        if not raw_name:
            continue

        dose_text = row.get("dose") or row.get("value")
        dosage, unit = split_dose(dose_text or raw_name)

        frequency = row.get("frequency") or None
        route = row.get("route") or None
        remainder = " ".join(
            filter(None, [row.get("comments"), row.get("status"), dose_text])
        )

        # Many lists put dose, frequency and route in one free-text column.
        if not frequency and looks_like_frequency(remainder):
            frequency = remainder.strip()
        if not route:
            for token in re.split(r"[,;/]| by ", remainder):
                if looks_like_route(token):
                    route = token.strip().lower()
                    break

        status_text = (row.get("status") or "").lower()
        is_active = not any(hint in status_text for hint in _INACTIVE_HINTS)

        name = re.sub(_DOSE_RE, "", raw_name).strip(" ,-") or raw_name

        record = MedicationRecord(
            name=name,
            raw_name=raw_name,
            dosage=dosage,
            dosage_unit=unit,
            frequency=(frequency or None),
            route=route,
            start_date=parse_date(row.get("date")),
            is_active=is_active,
            notes=(row.get("comments") or None),
        )
        score = 0.4 + (0.2 if dosage else 0.0) + (0.2 if record.frequency else 0.0)
        score += 0.1 if route else 0.0
        score += 0.1 if record.start_date else 0.0
        record.confidence = round(min(score, 1.0), 2)
        if not dosage:
            record.parse_notes.append("No dose found — confirm before importing.")
        records.append(record)
    return records


# ── Conditions ───────────────────────────────────────────────────────────────

#: ChronicCondition.category is a NOT NULL enum, so every imported condition
#: must resolve to one of these. Order matters: first match wins.
_CATEGORY_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("renal", ("kidney", "renal", "ckd", "esrd", "nephro", "dialysis", "glomerul")),
    ("cancer", ("cancer", "carcinoma", "tumor", "tumour", "lymphoma", "leukemia",
                "melanoma", "sarcoma", "myeloma", "malignan")),
    ("diabetes", ("diabet",)),
    ("blood_disorder", ("anemia", "anaemia", "sickle", "thalassemia", "hemophilia",
                        "clotting", "thrombocyt", "g6pd")),
    ("cardiovascular", ("heart", "cardiac", "coronary", "hypertension", "arrhythm",
                        "atrial", "stroke", "vascular", "cardiomyopathy")),
    ("respiratory", ("asthma", "copd", "emphysema", "bronchit", "pulmonary", "apnea")),
    ("autoimmune", ("lupus", "rheumatoid", "psoriasis", "crohn", "colitis",
                    "multiple sclerosis", "autoimmun", "celiac")),
    ("neurological", ("epilep", "seizure", "parkinson", "alzheimer", "dementia",
                      "neuropath", "migraine")),
    ("endocrine", ("thyroid", "hypothyroid", "hyperthyroid", "adrenal", "pituitary",
                   "cushing", "addison")),
]

_SEVERITY_WORDS = {
    "mild": "mild", "moderate": "moderate", "severe": "severe",
    "critical": "critical", "remission": "remission", "end stage": "severe",
    "end-stage": "severe", "advanced": "severe",
}

_ICD10_RE = re.compile(r"\b([A-TV-Z]\d{2}(?:\.\d{1,4})?)\b")
_RESOLVED_HINTS = ("resolved", "inactive", "history of", "past", "remission", "cured")


@dataclass
class ConditionRecord:
    condition_name: str
    raw_name: str
    category: str = "other"
    severity: str = "moderate"
    icd10_code: str | None = None
    diagnosis_date: date | None = None
    is_active: bool = True
    stage: str | None = None
    confidence: float = 0.0
    parse_notes: list[str] = field(default_factory=list)


def condition_category(name: str) -> tuple[str, bool]:
    """(category, recognised). Falls back to "other" rather than dropping the row."""
    lowered = (name or "").lower()
    for category, needles in _CATEGORY_RULES:
        if any(needle in lowered for needle in needles):
            return category, True
    return "other", False


def condition_severity(text: str) -> tuple[str, bool]:
    """(severity, stated). `moderate` is the default because the column is NOT NULL."""
    lowered = (text or "").lower()
    for word, severity in _SEVERITY_WORDS.items():
        if word in lowered:
            return severity, True
    return "moderate", False


def records_from_condition_table(table: Table) -> list[ConditionRecord]:
    records: list[ConditionRecord] = []
    for row in table.rows:
        raw_name = row.get("name").strip()
        if not raw_name:
            continue

        blob = " ".join(filter(None, [raw_name, row.get("status"), row.get("comments")]))
        category, category_known = condition_category(blob)
        severity, severity_stated = condition_severity(blob)

        code_text = " ".join(filter(None, [row.get("code"), row.get("comments")]))
        icd_match = _ICD10_RE.search(code_text)

        status_text = (row.get("status") or "").lower()
        is_active = not any(hint in status_text for hint in _RESOLVED_HINTS)

        record = ConditionRecord(
            condition_name=raw_name,
            raw_name=raw_name,
            category=category,
            severity=severity,
            icd10_code=icd_match.group(1) if icd_match else None,
            diagnosis_date=parse_date(row.get("date")),
            is_active=is_active,
        )

        score = 0.4 + (0.2 if category_known else 0.0) + (0.2 if record.icd10_code else 0.0)
        score += 0.1 if severity_stated else 0.0
        score += 0.1 if record.diagnosis_date else 0.0
        record.confidence = round(min(score, 1.0), 2)

        # Both of these are stored as fact but were never stated in the document.
        # Say so, so a reviewer can correct them rather than inherit a guess.
        if not category_known:
            record.parse_notes.append(
                'Category could not be determined from the text — filed as "other".'
            )
        if not severity_stated:
            record.parse_notes.append(
                'Severity was not stated in the document — defaulted to "moderate".'
            )
        records.append(record)
    return records
