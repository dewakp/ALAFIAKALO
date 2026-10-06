# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""Drift guard for the split-table clinical domains.

Some domains are backed by two tables and reading one is silently wrong (see
app/services/clinical_sources.py). Comments do not stop that from happening
again; this test does.

It is a source scan, not a behavioural test, and that is deliberate: the failure
mode is "somebody adds a new reader of the legacy table", which no amount of
end-to-end testing of *existing* endpoints would catch.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parent.parent / "app"

# Models that must only be read through clinical_sources.
GUARDED = {
    "HealthCondition": "conditions live in BOTH health_conditions and chronic_conditions",
    "ChronicCondition": "conditions live in BOTH health_conditions and chronic_conditions",
    "MedicationDoseLog": "medications live in BOTH medications and medication_dose_logs",
    # The FOURTH view of a medication: drugs given during dialysis, one row per
    # flowsheet line, with the route and the time. `therapy_sessions.
    # drugs_administered` still holds the same administrations as free text, so
    # reading only one of the two hides either the timing or the history —
    # exactly the split §3aa exists for. `clinical_sources` reads it now
    # (`_structured_drugs_for_day`, preferring these rows over the text in the
    # one place `_flowsheet_items`); this guard stops the NEXT reader from
    # going straight to the table and emitting both, which doubles every dose.
    "SessionDrug": "administrations live in BOTH drugs_administered and session_drugs",
    # Hospital history arrives from THREE paths — a FHIR Encounter/Procedure
    # import, a parsed discharge summary, and manual entry — and a procedure
    # may exist with or without the admission it belonged to (day-case surgery
    # and anything recorded years later have no encounter). A reader that takes
    # `hospitalizations` alone misses standalone procedures; one that takes
    # `surgical_procedures` alone misses the stay. Guarded BEFORE a second
    # reader exists, rather than after one has already hidden half the history.
    "Hospitalization": "stays and procedures are separate rows and either can stand alone",
    "SurgicalProcedure": "a procedure may have no admission; an admission may have no procedure",
}

# Files allowed to touch them directly.
ALLOWED = {
    "services/clinical_sources.py",   # the canonical reader itself
    "models/",                        # model definitions and relationships
    "api/chronic_conditions.py",      # the WRITER for chronic_conditions
    "api/medications.py",             # the WRITER for medications + dose logs
    # The WRITER for stays and procedures (create / update / delete, plus the
    # ownership checks those need). Its one READ surface, `GET /history`, goes
    # through clinical_sources like every other clinical read — a query here
    # that started from `hospitalizations` would lose every procedure with no
    # admission, which is the exact fact these models exist to hold.
    "api/hospitalization.py",
    # The assistant's `log_medication` tool is also a WRITER of dose logs, and
    # the one read it does is an idempotency check scoped to the exact row it
    # is about to insert (same user, date, drug, dose) — not a clinical
    # question. §3aa exists because READING one of the split tables and calling
    # it the answer hides facts; every clinical read in this module still goes
    # through clinical_sources (see `get_medications`).
    "services/record_tools.py",
    # The WRITER that structures a flowsheet's drugs when the session is saved.
    # Until 2026-10-02 the only writer of `session_drugs` was the Excel
    # importer, so the table stopped at 2025-12-31 while dosing continued and
    # 1,299 sessions (2018-11-16 → 2026-09-25) held drug text with no rows.
    # Its single read is an existence check scoped to the one session it is
    # about to populate (`SELECT id WHERE session_id = :id LIMIT 1`) — not a
    # clinical question, and it is what enforces "fill a gap, never overwrite a
    # richer row". Every clinical READ still goes through clinical_sources.
    "services/session_drug_sync.py",
    "api/ehr.py",                     # the EHR/FHIR import writes both
    "services/med_nutrient_service.py",   # dose-log nutrient resolution
    "services/nutrient_goals_service.py",  # documented condition matching
    "api/diagnostics.py",
    "services/diagnostics_engine.py",  # already merges both, deliberately
    "api/nutrition.py",                # already merges both, deliberately
}


def _python_files() -> list[Path]:
    return [p for p in APP.rglob("*.py") if "__pycache__" not in str(p)]


def _is_allowed(path: Path) -> bool:
    rel = str(path.relative_to(APP))
    return any(rel.startswith(a) or rel == a for a in ALLOWED)


@pytest.mark.parametrize("model", sorted(GUARDED))
def test_guarded_models_are_not_queried_directly(model: str):
    """No new direct readers of a split-table model outside clinical_sources."""
    # `select(Model)` or `.query(Model)` — how a read actually starts.
    pattern = re.compile(rf"(select\(\s*{model}\b|\.query\(\s*{model}\b)")

    offenders = []
    for path in _python_files():
        if _is_allowed(path):
            continue
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            if pattern.search(line):
                offenders.append(f"{path.relative_to(APP)}:{lineno}: {line.strip()}")

    assert not offenders, (
        f"{model} is queried directly ({GUARDED[model]}).\n"
        "Use app/services/clinical_sources.py, or add the file to ALLOWED here "
        "with a comment saying why it is correct:\n  " + "\n  ".join(offenders)
    )


def test_clinical_sources_covers_every_guarded_model():
    """The guard is worthless if the canonical module stops reading a table."""
    source = (APP / "services" / "clinical_sources.py").read_text()
    for model in GUARDED:
        assert model in source, (
            f"{model} is guarded but clinical_sources.py no longer reads it — "
            "either the merge was dropped or the guard is stale."
        )
