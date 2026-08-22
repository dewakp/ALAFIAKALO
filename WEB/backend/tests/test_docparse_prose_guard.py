"""Boilerplate is not a lab result.

Production shows a clinician this, among real results, on a shared patient board:

    up to and including termination of      employment with DaVita.

That is DaVita's disciplinary-policy footer. The lab PDFs carry it verbatim —
"disciplinary action, up to and including termination of employment with
DaVita." — and it parsed into a test name and a value as happily as haemoglobin
did.

The corpus harness could not catch this: it measures reference-range RECOVERY
(recall) and has no notion of precision, so a parser could emit a hundred prose
rows and still score 100%.

The guard is shape-based, not a blocklist of phrases, so the next document's
boilerplate is caught too.
"""

import pytest

from app.services.docparse.normalize import looks_like_prose


@pytest.mark.parametrize(
    "text",
    [
        # The exact row that reached production.
        "up to and including termination of",
        "disciplinary action, up to and including termination of employment with DaVita.",
        "employment with DaVita",
        "please refer to the report printed on page 2",
        "this report shall not be used for the purpose of",
        "",
        "   ",
    ],
)
def test_prose_is_rejected(text):
    assert looks_like_prose(text) is True


@pytest.mark.parametrize(
    "name",
    [
        "Hemoglobin",
        "Calcium, Total",
        "25-OH Vitamin D",
        "Kt/V (single pool)",
        "WEIGHT - PRE DAY",
        "Weight (kg)",
        "Weight - Pre Day 1",
        "Phosphorus",
        "Parathyroid hormone (intact)",
        # Long LOINC names are the hard case — a naive length rule kills these.
        "Erythrocyte distribution width [Entitic volume] by Automated count",
        "Platelet mean volume [Entitic volume] in Blood by Automated count",
        "Leukocytes [#/volume] in Blood by Automated count",
    ],
)
def test_real_analyte_names_are_kept(name):
    assert looks_like_prose(name) is False, f"{name!r} is a real analyte and must survive"


def test_guard_is_applied_when_building_records():
    """The check must run at the point records are built, not just exist."""
    from pathlib import Path
    import app.services.docparse.normalize as mod

    src = Path(mod.__file__).read_text()
    assert "if looks_like_prose(raw_name):" in src, "the guard is defined but never called"


def test_corpus_recovery_is_unaffected():
    """The guard must not cost a single real result.

    Verified against the real PHI corpus (§3ab): 510/510 ranges recovered, 0
    regressions, before and after. This test records the requirement; the
    harness itself is the measurement and is deliberately not in CI.
    """
    # Names taken from the corpus that a careless guard would have dropped.
    for name in ["Erythrocyte distribution width [Entitic volume] by Automated count",
                 "Platelet distribution width [Entitic volume] in Blood by Automated count"]:
        assert looks_like_prose(name) is False
