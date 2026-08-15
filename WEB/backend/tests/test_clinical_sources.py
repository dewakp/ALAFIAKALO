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
}

# Files allowed to touch them directly.
ALLOWED = {
    "services/clinical_sources.py",   # the canonical reader itself
    "models/",                        # model definitions and relationships
    "api/chronic_conditions.py",      # the WRITER for chronic_conditions
    "api/medications.py",             # the WRITER for medications + dose logs
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
