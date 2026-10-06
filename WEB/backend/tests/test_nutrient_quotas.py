# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""A nutrient quota must be cited, scoped, and never silently reconciled.

**Which of these are regression GUARDS and which are coverage.** Run against
the pre-change tree, the four `compute_goals` tests fail — three with
`TypeError: compute_goals() got an unexpected keyword argument 'quotas'` and
one on the missing `authority` key — because that function and its eighteen
call sites existed before. Those four are guards.

Everything else in this file exercises a module that did not exist, so it
cannot "fail against the old code" in any meaningful sense: it is coverage for
new behaviour. Calling all of it guards would be §3al's mistake, where a PII
test passed against the broken implementation and was counted anyway.
"""

import ast
import inspect
import re

import pytest

from app.models.nutrient_quota import (
    BASIS_ABSOLUTE, BASIS_PER_1000_KCAL, BASIS_PER_DOSE, BASIS_PER_KG,
    LIMIT, TARGET, ConditionNutrientQuota,
)
from app.services import nutrient_quota_service as nqs
from app.services.nutrient_goals_service import compute_goals


def _quota(**kw) -> ConditionNutrientQuota:
    """A detached row. Column defaults only apply at flush, so set them here."""
    base = dict(
        condition_key="chronic kidney disease",
        condition_label="Chronic kidney disease",
        subject="total elemental calcium",
        subject_normalized="calcium_mg",
        kind=TARGET,
        amount=800.0,
        unit="mg",
        basis=BASIS_ABSOLUTE,
        includes_supplements=False,
        time_course=None,
        scope_key="",
        stage=None,
        therapy=None,
        sex=None,
        age_min=None,
        age_max=None,
        source="KDOQI 2020",
        citation_url=None,
        cited_text="a total elemental calcium intake of 800-1,000 mg/d",
        evidence_level="moderate",
        provenance="guideline_seed",
        confidence=0.8,
        times_confirmed=1,
        is_active=True,
    )
    base.update(kw)
    return ConditionNutrientQuota(**base)


class _Stub:
    """Stands in for `alafia_chat`, counting calls."""

    def __init__(self, reply: str = "", raises: Exception | None = None):
        self.reply, self.raises, self.calls = reply, raises, 0

    async def __call__(self, *a, **kw):
        self.calls += 1
        if self.raises:
            raise self.raises
        return self.reply


def _install(monkeypatch, stub):
    import app.services.alafia_model_service as ams
    monkeypatch.setattr(ams, "alafia_chat", stub, raising=False)


_GOOD = """{"quotas": [
 {"nutrient_key": "calcium_mg", "kind": "limit", "amount": 1500,
  "unit": "mg", "basis": "absolute", "includes_supplements": true,
  "time_course": null, "stage": null, "therapy": null,
  "source": "European consensus statement, NDT 2024",
  "citation_url": "https://example.org/x",
  "cited_text": "not to exceed a total elemental calcium intake of 1500 mg/day",
  "evidence": "expert_opinion"}
]}"""


# ─────────────────────────────────────────────────────────────────────
# The citation is the point: what gets refused
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ["cited_text", "source"])
async def test_a_quota_with_no_citation_is_refused(db, monkeypatch, missing):
    """§3az forbids inventing a figure. An untraceable one WILL be quoted."""
    import json
    payload = json.loads(_GOOD)
    payload["quotas"][0][missing] = ""
    _install(monkeypatch, _Stub(json.dumps(payload)))

    stored = await nqs.resolve_quota(
        db, "Chronic kidney disease", nutrient_keys=["calcium_mg"])
    assert stored == []


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [
    ("nutrient_key", "unobtainium_mg"),   # not in the 116-nutrient catalog
    ("nutrient_key", "potassium_mg"),     # real, but not the key requested
    ("amount", "lots"),
    ("amount", -5),
    ("amount", 0),
    ("kind", "suggestion"),
    ("basis", "per_fortnight"),
])
async def test_a_malformed_quota_is_refused(db, monkeypatch, field, value):
    import json
    payload = json.loads(_GOOD)
    payload["quotas"][0][field] = value
    _install(monkeypatch, _Stub(json.dumps(payload)))

    stored = await nqs.resolve_quota(
        db, "Chronic kidney disease", nutrient_keys=["calcium_mg"])
    assert stored == []


@pytest.mark.asyncio
async def test_a_good_quota_is_stored_with_its_sentence(db, monkeypatch):
    _install(monkeypatch, _Stub(_GOOD))
    stored = await nqs.resolve_quota(
        db, "Chronic kidney disease", nutrient_keys=["calcium_mg"])

    assert len(stored) == 1
    row = stored[0]
    assert (row.kind, row.amount, row.unit) == (LIMIT, 1500.0, "mg")
    assert row.includes_supplements is True
    assert "1500 mg/day" in row.cited_text
    assert row.provenance == "llm"
    assert row.evidence_level == "expert_opinion"


# ─────────────────────────────────────────────────────────────────────
# Re-resolution must CONVERGE (§3ab's contradictory duplicate)
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_re_resolution_sharpens_instead_of_duplicating(db, monkeypatch):
    stub = _Stub(_GOOD)
    _install(monkeypatch, stub)

    await nqs.resolve_quota(db, "Chronic kidney disease",
                            nutrient_keys=["calcium_mg"])
    again = await nqs.resolve_quota(db, "Chronic kidney disease",
                                    nutrient_keys=["calcium_mg"])

    rows = await nqs.stored_quotas(db, ["Chronic kidney disease"])
    assert len(rows) == 1, "re-resolution must sharpen, not duplicate"
    assert again[0].times_confirmed == 2
    assert again[0].confidence > 0.5, "independent re-derivation is evidence"
    assert stub.calls == 2


@pytest.mark.asyncio
async def test_an_unstated_scope_still_converges(db, monkeypatch):
    """The Postgres NULL-distinct trap, which is why `scope_key` is NOT NULL.

    Both resolutions carry stage=null and therapy=null. With the unique key
    over the nullable columns, Postgres would treat the two as distinct and
    the second would land BESIDE the first — two contradictory quotas for one
    nutrient, which is exactly §3ab.
    """
    _install(monkeypatch, _Stub(_GOOD))
    await nqs.resolve_quota(db, "Chronic kidney disease", nutrient_keys=["calcium_mg"])
    await nqs.resolve_quota(db, "Chronic kidney disease", nutrient_keys=["calcium_mg"])

    rows = await nqs.stored_quotas(db, ["Chronic kidney disease"])
    assert len(rows) == 1
    assert rows[0].scope_key == ""


@pytest.mark.asyncio
async def test_a_second_opinion_does_not_overwrite_a_cited_amount(db, monkeypatch):
    """A disagreeing re-derivation is a reason to look, not to rewrite."""
    import json
    _install(monkeypatch, _Stub(_GOOD))
    await nqs.resolve_quota(db, "Chronic kidney disease", nutrient_keys=["calcium_mg"])

    disagreeing = json.loads(_GOOD)
    disagreeing["quotas"][0]["amount"] = 2500
    _install(monkeypatch, _Stub(json.dumps(disagreeing)))
    await nqs.resolve_quota(db, "Chronic kidney disease", nutrient_keys=["calcium_mg"])

    rows = await nqs.stored_quotas(db, ["Chronic kidney disease"])
    assert len(rows) == 1
    assert rows[0].amount == 1500.0, "the cited figure must stand"
    assert rows[0].times_confirmed == 2


# ─────────────────────────────────────────────────────────────────────
# Failure is never an answer, and the read path never calls a model
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_an_unavailable_model_yields_no_quotas_not_an_exception(db, monkeypatch):
    _install(monkeypatch, _Stub(raises=RuntimeError("all providers failed")))
    assert await nqs.resolve_quota(
        db, "Chronic kidney disease", nutrient_keys=["calcium_mg"]) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("reply", ["not json at all", "{}", '{"quotas": "none"}'])
async def test_unparseable_output_yields_nothing(db, monkeypatch, reply):
    _install(monkeypatch, _Stub(reply))
    assert await nqs.resolve_quota(
        db, "Chronic kidney disease", nutrient_keys=["calcium_mg"]) == []


@pytest.mark.asyncio
async def test_a_condition_with_no_guideline_figure_is_not_invented(db, monkeypatch):
    """KDIGO states no calcium figure for dialysis. Empty is a real answer."""
    _install(monkeypatch, _Stub('{"quotas": []}'))
    assert await nqs.resolve_quota(
        db, "End-stage renal disease", nutrient_keys=["calcium_mg"]) == []
    assert await nqs.stored_quotas(db, ["End-stage renal disease"]) == []


@pytest.mark.asyncio
async def test_the_read_path_makes_no_model_call(db, monkeypatch):
    """`quotas_for_conditions` has no resolve flag to leave in the wrong state."""
    stub = _Stub(raises=AssertionError("the read path must not call a model"))
    _install(monkeypatch, stub)

    result = await nqs.quotas_for_conditions(
        db, ["Chronic kidney disease"], weight_kg=55.0, energy_kcal=1688.0)
    assert stub.calls == 0
    assert result.daily == {}


# ─────────────────────────────────────────────────────────────────────
# Applying a quota to a patient — the part a scalar column could not do
# ─────────────────────────────────────────────────────────────────────

def test_a_per_dose_ceiling_never_becomes_a_daily_goal():
    """Hypoparathyroidism: 2-3 g/day, but ≤500 mg per ingestion.

    Collapsing the per-dose ceiling into the daily figure would cut a
    2,000 mg/day requirement to a quarter of itself.
    """
    rows = [
        _quota(condition_key="hypoparathyroidism",
               condition_label="Chronic hypoparathyroidism",
               kind=TARGET, amount=2000.0, basis=BASIS_ABSOLUTE),
        _quota(condition_key="hypoparathyroidism",
               condition_label="Chronic hypoparathyroidism",
               kind=LIMIT, amount=500.0, basis=BASIS_PER_DOSE),
    ]
    out = nqs.resolve_for_patient(rows)

    assert out.daily["calcium_mg"].amount == 2000.0
    assert out.daily["calcium_mg"].kind == TARGET
    assert [q.amount for q in out.per_dose] == [500.0]
    assert out.tensions == [], "a per-dose ceiling does not conflict with a daily floor"


def test_a_floor_above_a_ceiling_is_a_stated_tension_and_the_ceiling_governs():
    rows = [
        _quota(condition_key="hungry bone syndrome",
               condition_label="Hungry bone syndrome",
               kind=TARGET, amount=3200.0),
        _quota(kind=LIMIT, amount=1500.0,
               condition_label="Chronic kidney disease"),
    ]
    out = nqs.resolve_for_patient(rows)

    assert len(out.tensions) == 1
    t = out.tensions[0]
    assert t["nutrient_key"] == "calcium_mg"
    assert t["governing"] == "limit"
    assert "Hungry bone syndrome" in t["reason"]
    assert "Chronic kidney disease" in t["reason"]
    # The ceiling governs, and the disagreement is reported rather than
    # averaged into a number that hides it.
    assert out.daily["calcium_mg"].amount == 1500.0
    assert out.daily["calcium_mg"].kind == LIMIT


def test_two_floors_that_merely_differ_is_not_a_tension():
    rows = [_quota(kind=TARGET, amount=800.0),
            _quota(kind=TARGET, amount=1000.0, scope_key="stage=any", stage="any")]
    out = nqs.resolve_for_patient(rows)

    assert out.tensions == []
    assert out.daily["calcium_mg"].amount == 1000.0, "the binding floor governs"


def test_the_tightest_ceiling_binds():
    rows = [_quota(kind=LIMIT, amount=1500.0),
            _quota(kind=LIMIT, amount=1200.0, scope_key="stage=5", stage="5")]
    out = nqs.resolve_for_patient(rows)
    assert out.daily["calcium_mg"].amount == 1200.0


def test_per_kg_without_a_weight_is_unscoped_not_a_reference_adult():
    """§3am: an unreadable input raises rather than assuming. 70 kg is a guess."""
    rows = [_quota(basis=BASIS_PER_KG, amount=40.0,
                   subject_normalized="potassium_mg")]

    without = nqs.resolve_for_patient(rows, weight_kg=None)
    assert without.daily == {}
    assert without.unscoped == ["potassium_mg"]

    with_weight = nqs.resolve_for_patient(rows, weight_kg=55.0)
    assert with_weight.daily["potassium_mg"].amount == 2200.0
    assert with_weight.unscoped == []


def test_per_1000_kcal_scales_with_energy():
    rows = [_quota(basis=BASIS_PER_1000_KCAL, amount=10.0,
                   subject_normalized="fiber_g", unit="g")]
    out = nqs.resolve_for_patient(rows, energy_kcal=1688.0)
    assert out.daily["fiber_g"].amount == pytest.approx(16.88, abs=0.01)


def test_scope_filters_by_age_and_sex():
    stones = _quota(condition_key="calcium oxalate kidney stones",
                    condition_label="Calcium oxalate kidney stones",
                    amount=1000.0, age_max=70)
    assert nqs.resolve_for_patient([stones], age=52).daily
    assert not nqs.resolve_for_patient([stones], age=75).daily
    # An unstated bound excludes nobody.
    assert nqs.resolve_for_patient([stones], age=None).daily


def test_includes_supplements_travels_with_the_figure():
    """A patient told to 'reach 800 mg' while taking 1,500 mg of binder is
    being told the opposite of the guideline."""
    out = nqs.resolve_for_patient([_quota(includes_supplements=True)])
    r = out.daily["calcium_mg"]
    assert r.includes_supplements is True
    assert "INCLUDING supplements" in r.rationale


def test_a_time_course_is_carried_into_the_rationale():
    out = nqs.resolve_for_patient([_quota(
        condition_label="Hungry bone syndrome", amount=3200.0,
        time_course="~3.2 g/day in week 1, decreasing to ~2.4 g by week 6")])
    assert "week 6" in out.daily["calcium_mg"].rationale


def test_scope_key_is_never_null_for_any_combination():
    assert nqs.scope_key_for(None, None) == ""
    assert nqs.scope_key_for("3-4", None) == "stage=3-4"
    assert nqs.scope_key_for(None, "Dialysis") == "therapy=dialysis"
    assert nqs.scope_key_for(" G5D ", "X") == "stage=g5d|therapy=x"


# ─────────────────────────────────────────────────────────────────────
# GUARDS — these four fail against the pre-change tree
# ─────────────────────────────────────────────────────────────────────

_PROFILE = dict(date_of_birth="1974-03-02", sex="female", height_cm=176.0,
                current_weight_kg=55.0, activity_level="sedentary")


def test_compute_goals_without_quotas_is_unchanged():
    """The default path must stay byte-identical for all eighteen callers."""
    payload = compute_goals(**_PROFILE, conditions=[
        {"condition_name": "End-stage renal disease", "category": "renal"}])
    by_key = {g["key"]: g for g in payload["goals"]}

    calcium = by_key["calcium_mg"]
    assert (calcium["goal"], calcium["kind"]) == (1200.0, "target")
    assert calcium["authority"] is None
    assert "quota" not in calcium
    assert "not scoped to your conditions" in calcium["rationale"]


def test_every_goal_states_where_its_figure_came_from():
    payload = compute_goals(**_PROFILE, conditions=[])
    assert payload["goals"]
    for g in payload["goals"]:
        assert "authority" in g, f"{g['key']} cannot say where its figure came from"


def test_a_cited_quota_supersedes_the_ladder():
    """The §8a case: calcium stops being a bone-health target to aim FOR."""
    overrides = nqs.resolve_for_patient([
        _quota(kind=LIMIT, amount=1500.0, includes_supplements=True,
               source="European consensus statement, NDT 2024",
               cited_text="not to exceed a total elemental calcium intake of "
                          "1500 mg/day"),
    ]).as_goal_overrides()

    payload = compute_goals(**_PROFILE, quotas=overrides, conditions=[
        {"condition_name": "End-stage renal disease", "category": "renal"}])
    calcium = {g["key"]: g for g in payload["goals"]}["calcium_mg"]

    assert calcium["kind"] == "limit", "a ceiling must not be served as a target"
    assert calcium["goal"] == 1500.0
    assert calcium["authority"] == "European consensus statement, NDT 2024"
    assert "1500 mg/day" in calcium["quota"]["cited_text"]
    assert calcium["quota"]["includes_supplements"] is True


def test_the_override_reaches_every_nutrient_not_just_calcium():
    """The override sits in `add()`, so it is not a per-nutrient change."""
    overrides = nqs.resolve_for_patient([
        _quota(subject_normalized="potassium_mg", kind=LIMIT, amount=2200.0,
               condition_label="Haemodialysis", source="KDOQI 2020",
               cited_text="individualized to serum potassium"),
        _quota(subject_normalized="phosphorus_mg", kind=LIMIT, amount=850.0,
               condition_label="Haemodialysis", source="KDOQI 2020",
               cited_text="limit phosphorus to protect bones and vessels"),
    ]).as_goal_overrides()

    payload = compute_goals(**_PROFILE, quotas=overrides, conditions=[
        {"condition_name": "End-stage renal disease", "category": "renal"}])
    by_key = {g["key"]: g for g in payload["goals"]}

    assert by_key["potassium_mg"]["goal"] == 2200.0
    assert by_key["phosphorus_mg"]["goal"] == 850.0
    assert by_key["potassium_mg"]["authority"] == "KDOQI 2020"
    # Untouched nutrients keep the ladder AND say so.
    assert by_key["iron_mg"]["authority"] is None


# ─────────────────────────────────────────────────────────────────────
# The seed, and the rule that no condition may be special-cased in code
# ─────────────────────────────────────────────────────────────────────

#: Every module that computes goals for a real patient. If one of these calls
#: `compute_goals` without passing `quotas`, the store is plumbing nobody is
#: connected to — §3ar's control that sets a flag nothing observes, and §3ay's
#: corpus sink that was built, documented, and never called.
_WIRED_MODULES = ("app/api/nutrition.py", "app/api/wellness.py",
                  "app/api/personalization.py", "app/api/ai.py")


def test_every_live_goal_computation_passes_quotas():
    """The dead-control guard. A static check, per §3ag.

    Behavioural tests skip straight past this: stub the engine and the call
    site is never reached. Reading the call sites is what catches a surface
    that silently kept serving the general ladder — and it fails against the
    pre-change tree, where no `quotas` keyword existed anywhere.
    """
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    unwired: list[str] = []
    seen = 0

    for rel in _WIRED_MODULES:
        tree = ast.parse((root / rel).read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = (node.func.id if isinstance(node.func, ast.Name)
                    else getattr(node.func, "attr", None))
            if name not in ("compute_goals", "_cg"):
                continue
            seen += 1
            if not any(kw.arg == "quotas" for kw in node.keywords):
                unwired.append(f"{rel}:{node.lineno}")

    assert seen >= 5, f"expected every known call site, found {seen}"
    assert not unwired, (
        "these compute a patient's goals while ignoring their cited quotas: "
        f"{unwired}")


def test_the_read_path_used_by_those_modules_cannot_resolve():
    """Wiring a live surface must not put a model call in a request path.

    `quotas_for_conditions` is what the four modules call, and it takes no
    `resolve_missing` flag — there is no parameter to leave in the wrong
    position on a redeploy (§3az made the same argument about a cutoff
    constant).
    """
    import inspect as _inspect

    sig = _inspect.signature(nqs.quotas_for_conditions)
    assert "resolve_missing" not in sig.parameters
    src = _inspect.getsource(nqs.quotas_for_conditions)
    assert "alafia_chat" not in src
    assert "resolve_quota" not in src


def _migration_source() -> str:
    from pathlib import Path
    p = (Path(__file__).resolve().parent.parent
         / "alembic" / "versions" / "ap001_nutrient_quotas.py")
    assert p.exists(), p
    return p.read_text()


def test_every_seeded_quota_carries_a_citation():
    """Checked against the migration: the test DB is built from models, not
    migrations, so the seed rows are not present in it (as
    `test_no_hardcoded_thresholds` already established for an001)."""
    tree = ast.parse(_migration_source())
    dicts = [n for n in ast.walk(tree) if isinstance(n, ast.Dict)]
    seeds = [d for d in dicts
             if any(isinstance(k, ast.Constant) and k.value == "cited_text"
                    for k in d.keys)]
    assert len(seeds) >= 7, f"expected the measured calcium rows, found {len(seeds)}"

    for d in seeds:
        pairs = {k.value: v for k, v in zip(d.keys, d.values)
                 if isinstance(k, ast.Constant)}
        for required in ("source", "cited_text", "subject_normalized", "kind",
                         "amount", "unit", "basis"):
            assert required in pairs, f"a seeded quota omits {required}"
        # A citation that is an empty string is not a citation.
        for field_name in ("source", "cited_text"):
            node = pairs[field_name]
            if isinstance(node, ast.Constant):
                assert node.value and str(node.value).strip()


def test_every_seeded_scope_key_matches_the_normaliser():
    """A hand-written scope_key the resolver would never compute is a latent
    duplicate.

    This caught a real one on 2026-10-05: the stones row was seeded with
    `scope_key="age_max=70"`, which `scope_key_for()` cannot produce (it
    encodes stage and therapy only — an age bound lives in `age_max` and is
    applied by `_applies_to`). A later re-resolution of that condition would
    compute `""`, fail to match the seeded row, and insert beside it: two
    contradictory calcium quotas for one condition, created by the column
    added to prevent exactly that (§3ab).
    """
    tree = ast.parse(_migration_source())

    def _const(node):
        return node.value if isinstance(node, ast.Constant) else ...

    checked = 0
    for d in [n for n in ast.walk(tree) if isinstance(n, ast.Dict)]:
        pairs = {k.value: v for k, v in zip(d.keys, d.values)
                 if isinstance(k, ast.Constant)}
        if "scope_key" not in pairs:
            continue
        scope = _const(pairs["scope_key"])
        stage = _const(pairs.get("stage", ast.Constant(None)))
        therapy = _const(pairs.get("therapy", ast.Constant(None)))
        if ... in (scope, stage, therapy):
            continue  # a computed value; nothing to compare statically
        assert scope == nqs.scope_key_for(stage, therapy), (
            f"seeded scope_key {scope!r} is not what scope_key_for("
            f"{stage!r}, {therapy!r}) produces ({nqs.scope_key_for(stage, therapy)!r})")
        checked += 1

    assert checked >= 7, f"expected to check every seeded row, checked {checked}"


def test_no_dialysis_calcium_figure_is_seeded():
    """KDOQI 2020 and KDIGO 2009/2017 state none. Absence is the answer."""
    src = _migration_source()
    seeded_scopes = re.findall(r'"scope_key":\s*"([^"]*)"', src)
    assert seeded_scopes, "scope keys should be explicit in the seed"
    for scope in seeded_scopes:
        assert "g5d" not in scope.lower()
        assert "dialysis" not in scope.lower()


_CONDITION_TERMS = ("dialysis", "ckd", "kidney", "diabet", "hypoparathyroid",
                    "sarcoid", "hungry bone", "oxalate", "esrd")

#: The ONE place a condition may be named in this module, with its reason.
#: `_RESOLVE_PROMPT` tells the model that an absent recommendation is a real
#: answer, and cites the measured case — KDIGO states no calcium figure for
#: dialysis at all. That sentence is what stops the model filling the gap with
#: a plausible number, so deleting it to satisfy this check would break the
#: thing the check exists to protect (§3ar: classify a static finding before
#: acting on it). An exemption carries a reason or it is not an exemption.
_NAMED_EXEMPTIONS = {"_RESOLVE_PROMPT"}


def _service_tree() -> ast.Module:
    return ast.parse(inspect.getsource(nqs))


def test_no_condition_appears_in_a_collection_or_a_comparison():
    """The actual anti-lookup-table rule.

    A condition→amount dict, a tuple of condition names, or an
    `if condition == "ckd"` is the ladder coming back. This is the rule the
    first version of this guard was reaching for when it instead flagged the
    resolver prompt — a string that merely MENTIONS a condition is not a
    branch on one, which is the same distinction §3aw draws between a literal
    an expression tests and one it merely displays.
    """
    tree = _service_tree()
    offenders = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.Dict, ast.Set, ast.List, ast.Tuple)):
            parts = list(node.elts) if not isinstance(node, ast.Dict) else [
                *[k for k in node.keys if k is not None], *node.values]
            for sub in parts:
                if (isinstance(sub, ast.Constant) and isinstance(sub.value, str)
                        and any(t in sub.value.lower() for t in _CONDITION_TERMS)):
                    offenders.append(("collection", sub.value[:60]))
        if isinstance(node, ast.Compare):
            for sub in [node.left, *node.comparators]:
                if (isinstance(sub, ast.Constant) and isinstance(sub.value, str)
                        and any(t in sub.value.lower() for t in _CONDITION_TERMS)):
                    offenders.append(("comparison", sub.value[:60]))

    assert not offenders, (
        "a condition in a collection or a comparison is the hand-written "
        f"ladder returning: {offenders}")


def test_the_service_names_no_condition_outside_its_documented_exemption():
    """Everything else: docstrings and the named prompt are exempt, nothing is."""
    tree = _service_tree()

    skip: set[int] = set()
    for node in ast.walk(tree):
        # Docstrings — documentation explaining the design is allowed.
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                skip.add(id(body[0].value))
        # The exempt prompt constants, by assignment target name.
        if isinstance(node, ast.Assign):
            names = {t.id for t in node.targets if isinstance(t, ast.Name)}
            if names & _NAMED_EXEMPTIONS:
                for sub in ast.walk(node.value):
                    skip.add(id(sub))

    offenders = [
        n.value[:70] for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
        and id(n) not in skip
        and any(t in n.value.lower() for t in _CONDITION_TERMS)
    ]
    assert not offenders, (
        f"a condition named in executable code, outside the exemption: {offenders}")


def test_the_exemption_is_not_a_blank_cheque():
    """A prompt may MENTION a condition; it may not map one to a number.

    Without this, `_NAMED_EXEMPTIONS` would be a hole big enough to hide the
    very lookup table the other two tests forbid — just moved into a string.
    """
    prompt = nqs._RESOLVE_PROMPT
    for term in _CONDITION_TERMS:
        for match in re.finditer(re.escape(term), prompt.lower()):
            window = prompt.lower()[match.start():match.start() + 120]
            assert not re.search(r"\d{3,}\s*(mg|g|mcg|iu)", window), (
                f"the prompt attaches a quantity to {term!r}: {window!r}")
