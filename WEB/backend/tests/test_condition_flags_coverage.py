"""Coverage and correctness of condition → dietary-rule detection.

`detect_condition_flags()` recognises six diagnoses by substring-matching free
text. This app serves "cancers, renal diseases, diabetes, G6PD deficiency, etc"
against a 35,339-code ICD-11 catalog, so a hand-maintained list of six cannot
be the mechanism — and the matching is wrong in both directions.

These tests are the specification for the rewrite queued in TASKS.md
("AI must answer against THIS patient's nutrient limits"). The false-positive
cases below assert correct behaviour and are expected to FAIL until rules are
keyed to `icd11_code` instead of keywords. They are marked xfail rather than
deleted so the defect stays visible and flips to a pass when it is fixed.
"""

import pytest

from app.services.nutrient_goals_service import detect_condition_flags


def flags_for(name: str, category: str = "other", **extra) -> set[str]:
    row = {"condition_name": name, "category": category, **extra}
    return {k for k, v in detect_condition_flags([row]).items() if v}


# ── What it gets right today (guard against regression) ───────────────


@pytest.mark.parametrize(
    "name,expected",
    [
        ("End-Stage Renal Disease (ESRD)", {"ckd", "dialysis"}),
        ("Chronic kidney disease, stage 5", {"ckd"}),
        ("Type 2 diabetes mellitus", {"diabetes"}),
    ],
)
def test_recognised_conditions_keep_working(name, expected):
    assert expected <= flags_for(name)


# ── Wrong in the false-positive direction ─────────────────────────────


@pytest.mark.xfail(
    reason="substring matching: 'heartburn' contains 'heart'. GERD is not "
           "cardiovascular, and a cardiac sodium/fluid target is wrong for it.",
    strict=True,
)
def test_heartburn_is_not_cardiovascular():
    assert "cardiovascular" not in flags_for("Gastro-oesophageal reflux disease (heartburn)")


@pytest.mark.xfail(
    reason="'Diabetes insipidus' contains 'diabet' but is a water-balance "
           "disorder of ADH, not glycaemic. Carbohydrate targets are clinically "
           "wrong and the fluid guidance is close to inverted.",
    strict=True,
)
def test_diabetes_insipidus_is_not_diabetes_mellitus():
    assert "diabetes" not in flags_for("Diabetes insipidus")


# ── Wrong in the silent-omission direction ────────────────────────────
#
# Each of these is a real condition with real dietary consequences and each
# produces NO flags and no indication that nothing was produced. The patient
# receives generic targets that look authoritative — §3aa, an absent rule
# rendered as a normal answer.


@pytest.mark.parametrize(
    "name,why",
    [
        ("Sickle cell disease without crisis", "hydration and folate needs"),
        ("G6PD deficiency", "fava beans are contraindicated outright"),
        ("Crohn disease", "malabsorption; fibre and micronutrient handling"),
        ("Coeliac disease", "gluten is contraindicated outright"),
        ("Gout", "purine restriction"),
        ("Chronic liver disease", "protein and sodium handling"),
        ("Malignant neoplasms of breast", "treatment-phase energy and protein needs"),
    ],
)
@pytest.mark.xfail(
    reason="only six diagnoses are recognised; everything else yields no flags "
           "AND no signal, so the caller cannot distinguish 'no restriction' "
           "from 'not assessed'.",
    strict=True,
)
def test_condition_with_dietary_consequences_is_not_silently_ignored(name, why):
    assert flags_for(name), f"{name}: {why} — produced no flags and no gap marker"
