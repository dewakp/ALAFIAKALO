"""Condition→food knowledge is resolved once, stored, and converges.

This replaces a hardcoded dict. The tests that matter most are the ones proving
the dict cannot come back: nothing here names a food for a condition, and the
resolver is driven by a stubbed model so the assertions are about STORAGE and
CONVERGENCE rather than about what any particular model happens to know.
"""

import json

import pytest
from sqlalchemy import select

from app.models.condition_nutrition import ConditionNutritionFact
from app.services import condition_nutrition_service as cns


# ── condition names arrive spelled many ways ───────────────────────────


def test_a_misspelled_condition_is_NOT_silently_matched_by_name():
    """Recorded deliberately, like §3al's un-redactable-name test.

    The production row reads "G6PD Deficitency". Fuzzy string matching is the
    wrong instrument for clinical names — §3aj learned that when difflib
    flagged "Calcitriol" as a misspelling of calcitriol. So these are different
    keys, and the ICD-11 code is what reunites them (see the code test below).
    """
    assert cns.normalize_condition("G6PD Deficitency") != \
           cns.normalize_condition("G6PD Deficiency")


def test_noise_words_and_punctuation_do_not_split_a_condition():
    a = cns.normalize_condition("Coeliac Disease")
    b = cns.normalize_condition("coeliac")
    assert a == b
    assert cns.normalize_condition("End-Stage Renal Disease (ESRD)") == \
           cns.normalize_condition("end stage renal")


def test_empty_condition_yields_no_key():
    assert cns.normalize_condition("") == ""
    assert cns.normalize_condition(None) == ""


# ── resolution stores, with provenance ─────────────────────────────────


class _StubChat:
    """Stands in for the model. Records how many times it was asked."""

    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    async def __call__(self, messages, **kw):
        self.calls += 1
        return json.dumps(self.payload)


@pytest.fixture
def sickle_payload():
    # Deliberately NOT G6PD: proves the mechanism is general, not a dict entry
    # for the one condition that prompted the work.
    return {
        "avoid": [
            {"subject": "alcohol", "kind": "food",
             "mechanism": "promotes dehydration, a sickling precipitant",
             "evidence": "moderate"},
        ],
        "favour": [
            {"subject": "folate", "kind": "nutrient",
             "mechanism": "supports accelerated red cell turnover",
             "evidence": "high"},
            {"subject": "water", "kind": "food",
             "mechanism": "maintaining hydration reduces sickling",
             "evidence": "high"},
        ],
    }


@pytest.mark.asyncio
async def test_resolution_stores_both_directions(db, monkeypatch, sickle_payload):
    stub = _StubChat(sickle_payload)
    monkeypatch.setattr("app.services.alafia_model_service.alafia_chat", stub)

    facts = await cns.resolve_condition(db, "Sickle cell disease")
    assert {f.relation for f in facts} == {cns.AVOID, cns.FAVOUR}

    rows = (await db.execute(select(ConditionNutritionFact))).scalars().all()
    assert len(rows) == 3
    assert all(r.provenance == "llm" for r in rows)
    assert all(r.mechanism for r in rows), "a fact with no mechanism cannot explain itself"


@pytest.mark.asyncio
async def test_a_nutrient_subject_keeps_its_kind(db, monkeypatch, sickle_payload):
    monkeypatch.setattr("app.services.alafia_model_service.alafia_chat",
                        _StubChat(sickle_payload))
    await cns.resolve_condition(db, "Sickle cell disease")
    folate = (await db.execute(
        select(ConditionNutritionFact).where(
            ConditionNutritionFact.subject_normalized == "folate"))).scalar_one()
    # "nutrient" matters: it can be met from any cuisine, unlike a named food.
    assert folate.subject_kind == "nutrient"


@pytest.mark.asyncio
async def test_stored_facts_are_served_without_asking_again(
        db, monkeypatch, sickle_payload):
    stub = _StubChat(sickle_payload)
    monkeypatch.setattr("app.services.alafia_model_service.alafia_chat", stub)

    await cns.resolve_condition(db, "Sickle cell disease")
    assert stub.calls == 1

    facts = await cns.stored_facts(db, ["Sickle cell disease"])
    assert len(facts) == 3
    assert stub.calls == 1, "serving a stored fact must not call the model"


@pytest.mark.asyncio
async def test_re_resolving_converges_instead_of_duplicating(
        db, monkeypatch, sickle_payload):
    """§3ab: a re-import that inserts beside the row it meant to correct leaves
    the patient holding two contradictory facts."""
    monkeypatch.setattr("app.services.alafia_model_service.alafia_chat",
                        _StubChat(sickle_payload))
    await cns.resolve_condition(db, "Sickle cell disease")
    await cns.resolve_condition(db, "Sickle cell disease")

    rows = (await db.execute(select(ConditionNutritionFact))).scalars().all()
    assert len(rows) == 3, "re-resolution must sharpen, not duplicate"
    folate = next(r for r in rows if r.subject_normalized == "folate")
    assert folate.times_confirmed == 2
    assert folate.confidence > 0.6, "independent re-derivation is evidence"


# ── failure must never take the caller down ────────────────────────────


@pytest.mark.asyncio
async def test_an_unavailable_model_yields_no_facts_not_an_exception(
        db, monkeypatch):
    async def _boom(messages, **kw):
        raise RuntimeError("all providers failed")
    monkeypatch.setattr("app.services.alafia_model_service.alafia_chat", _boom)

    facts = await cns.resolve_condition(db, "Coeliac disease")
    assert facts == []


@pytest.mark.asyncio
async def test_unparseable_output_yields_no_facts(db, monkeypatch):
    async def _prose(messages, **kw):
        return "I'm afraid I can't help with that."
    monkeypatch.setattr("app.services.alafia_model_service.alafia_chat", _prose)

    assert await cns.resolve_condition(db, "Coeliac disease") == []


@pytest.mark.asyncio
async def test_a_condition_with_no_dietary_facts_is_not_invented(
        db, monkeypatch):
    """Rule 7 of the prompt. An empty answer is a legitimate answer."""
    monkeypatch.setattr("app.services.alafia_model_service.alafia_chat",
                        _StubChat({"avoid": [], "favour": []}))
    assert await cns.resolve_condition(db, "Myopia") == []
    rows = (await db.execute(select(ConditionNutritionFact))).scalars().all()
    assert rows == []


# ── the guard against the dict coming back ─────────────────────────────


def _executable_strings(module) -> str:
    """Every string literal in a module EXCEPT its docstrings.

    Documentation that explains why fava beans motivated this design is
    valuable and must not trip the guard; a fava bean sitting in a lookup table
    is the thing being prevented. Only code is inspected.
    """
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(module))
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                docstrings.add(doc)
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value not in docstrings:
                out.append(node.value)
    return " ".join(out).lower()


# Foods that are the classic trigger for a specific condition. If one of these
# appears in executable code, someone has typed clinical knowledge in again.
_TELLTALE_FOODS = ("fava", "broad bean", "faba", "gluten", "purine", "tyramine")


def test_the_service_hardcodes_no_condition_to_food_mapping():
    """Fails the build if anyone reintroduces a literal condition→food table."""
    src = _executable_strings(cns)
    for food in _TELLTALE_FOODS:
        assert food not in src, (
            f"{food!r} appears in condition_nutrition_service code. Condition "
            "knowledge is resolved and stored, never typed in (§3ad, §3c).")


def test_food_safety_hardcodes_no_condition_to_food_mapping():
    from app.services import food_safety
    src = _executable_strings(food_safety)
    for food in _TELLTALE_FOODS:
        assert food not in src, (
            f"{food!r} appears in food_safety code. It decides what to DO with "
            "condition knowledge; it must not contain any.")


def test_the_prompt_does_not_seed_a_condition_to_food_pair():
    """The resolution prompt showed "fava beans" as its example, which both
    hardcodes a mapping and biases the answer. It carries a SHAPE now."""
    assert "<food or ingredient>" in cns._RESOLVE_PROMPT
    for food in _TELLTALE_FOODS:
        assert food not in cns._RESOLVE_PROMPT.lower()


@pytest.mark.asyncio
async def test_the_icd11_code_reunites_a_misspelled_condition(db, monkeypatch, sickle_payload):
    """Names vary and are typo'd; the code is exact (§3ad)."""
    monkeypatch.setattr("app.services.alafia_model_service.alafia_chat",
                        _StubChat(sickle_payload))
    await cns.resolve_condition(db, "G6PD Deficiency", icd11_code="3A10.00")

    # A later lookup spelling it the way the production row does still finds it,
    # because the code matches even though the name does not.
    facts = await cns.stored_facts(db, ["G6PD Deficitency"], codes=["3A10.00"])
    assert facts, "the ICD-11 code should reunite the misspelling"

    # …and without the code, the misspelling legitimately misses.
    assert await cns.stored_facts(db, ["G6PD Deficitency"]) == []
