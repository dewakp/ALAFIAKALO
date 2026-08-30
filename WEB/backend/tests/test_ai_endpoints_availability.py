"""Availability contract for the LLM-backed endpoints.

These two routers had **no test coverage at all** — that is how
`/personalization/*` returned "AI service is not configured" in production for
27 days. The gate asked `if not ai_engine.api_key`, i.e. whether
`OPENAI_API_KEY` was set, on a deployment whose LLM is Ollama and needs no key.
It could never have passed in prod, and nothing in 696 tests noticed.

What is pinned here is the boundary, not the model:

- a working provider must NOT be refused because a provider-specific key is absent
- a genuinely unavailable provider must produce 503 *naming the reason*, never
  a blank or a generic "not configured"

The model itself is stubbed. The point is the decision the endpoint makes about
it, which is exactly the part that was wrong.
"""

from pathlib import Path

import pytest
from httpx import AsyncClient

from app.services.alafia_model_service import ALAFIAModelError


async def _register_and_token(client: AsyncClient, email: str) -> str:
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "SecureP@ss123",
            "full_name": "Test User",
            "date_of_birth": "1990-01-01",
        },
    )
    r = await client.post(
        "/api/v1/auth/login",
        data={"username": email, "password": "SecureP@ss123"},
    )
    return r.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── The gate that broke production ────────────────────────────────────


def test_engine_does_not_require_a_provider_api_key(monkeypatch):
    """The regression itself, at its smallest.

    Prod has no OPENAI_API_KEY and never will — its provider is Ollama. An
    engine that reports itself unusable in that situation is the bug.
    """
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    from app.services.ai_engine import AIPersonalizationEngine

    engine = AIPersonalizationEngine(db=None)

    # The vestigial fields are gone: nothing may gate on them again.
    assert not hasattr(engine, "api_key"), (
        "api_key is back — /personalization/* will 503 in any deployment "
        "without an OpenAI key, which includes production"
    )
    assert not hasattr(engine, "api_url")


def test_engine_calls_go_through_the_model_router(monkeypatch):
    """Provider choice is ALAFIAModel's job, not this class's (CLAUDE.md §3)."""
    import app.services.alafia_model_service as ams
    from app.services.ai_engine import AIPersonalizationEngine

    seen = {}

    async def fake_chat(messages, **kw):
        seen["called"] = True
        return "ok"

    monkeypatch.setattr(ams, "alafia_chat", fake_chat)
    engine = AIPersonalizationEngine(db=None)

    import asyncio
    result = asyncio.get_event_loop().run_until_complete(
        engine._call_llm([{"role": "user", "content": "hi"}])
    )
    assert seen.get("called") is True
    assert result == "ok"


# ── Endpoint behaviour when the model really is down ──────────────────


@pytest.mark.asyncio
async def test_recommendations_reports_the_real_reason_when_model_is_down(
    client: AsyncClient, monkeypatch
):
    token = await _register_and_token(client, "ai_avail_rec@example.com")

    from app.services.ai_engine import AIPersonalizationEngine

    async def boom(*a, **k):
        raise ALAFIAModelError("ollama connect timeout after 300s")

    monkeypatch.setattr(
        AIPersonalizationEngine, "generate_personalized_recommendations", boom
    )

    r = await client.post(
        "/api/v1/personalization/recommendations",
        json={"type": "wellness"},
        headers=_auth(token),
    )
    # 403 is legitimate when ai_coaching is off for the account; what must never
    # happen is a 503 that blames configuration when nothing was ever asked.
    if r.status_code == 403:
        pytest.skip("ai_coaching_enabled defaults off for new accounts")
    assert r.status_code == 503
    detail = r.json()["detail"]
    assert "ollama connect timeout" in detail, (
        f"the real cause must survive to the client, got: {detail!r}"
    )
    assert "not configured" not in detail


@pytest.mark.asyncio
async def test_meal_suggestions_names_the_failure(client: AsyncClient, monkeypatch):
    """A model that errors and a model that returns junk are different faults.

    Both used to collapse into "The AI meal engine is unavailable right now",
    which sent an operator hunting a downed service while the model was up and
    simply slower than the client's timeout.
    """
    token = await _register_and_token(client, "ai_avail_meal@example.com")

    import app.api.planners as planners

    async def boom(*a, **k):
        raise ALAFIAModelError("model returned HTTP 429")

    monkeypatch.setattr(planners, "_generate_meal_suggestions", boom)

    r = await client.post(
        "/api/v1/planners/meal-suggestions",
        json={"health_goals": "improve hemoglobin", "count": 1},
        headers=_auth(token),
    )
    assert r.status_code == 503
    assert "429" in r.json()["detail"]


@pytest.mark.asyncio
async def test_unparseable_model_output_is_502_not_503(
    client: AsyncClient, monkeypatch
):
    """502 (bad upstream answer) is not 503 (upstream unreachable)."""
    token = await _register_and_token(client, "ai_avail_junk@example.com")

    import app.api.planners as planners

    async def empty(*a, **k):
        return []

    monkeypatch.setattr(planners, "_generate_meal_suggestions", empty)

    r = await client.post(
        "/api/v1/planners/meal-suggestions",
        json={"health_goals": "x", "count": 1},
        headers=_auth(token),
    )
    assert r.status_code == 502


@pytest.mark.asyncio
async def test_planners_still_fall_back_to_a_template(client: AsyncClient, monkeypatch):
    """The meal/exercise PLAN paths must keep degrading gracefully.

    Unlike suggestions, these have a deterministic template, so a model outage
    must still return a usable plan rather than an error.
    """
    token = await _register_and_token(client, "ai_avail_plan@example.com")

    # Patch the LLM call, not the helper: the fallback lives *inside*
    # _ollama_generate_meal_plan, so replacing the helper would bypass the very
    # behaviour under test.
    import app.services.alafia_model_service as ams

    async def boom(*a, **k):
        raise ALAFIAModelError("down")

    monkeypatch.setattr(ams, "alafia_chat", boom)

    r = await client.post(
        "/api/v1/planners/meal-plan",
        json={"pattern": "balanced", "days": 7},
        headers=_auth(token),
    )
    assert r.status_code in (200, 422), r.text
    if r.status_code == 200:
        assert r.json().get("weekly_plan"), "template fallback produced no plan"


# ── Session type ──────────────────────────────────────────────────────


def test_personalization_uses_a_sync_session():
    """These endpoints must not be wired to the async session dependency.

    `get_db` yields an AsyncSession. Every path in this router — and all of
    ai_engine — uses the SYNC ORM API (`db.query`, `db.commit`, `db.refresh`).
    The `db: Session` annotation converts nothing, so the mismatch produced
    `AttributeError: 'AsyncSession' object has no attribute 'query'` on the
    first query and the endpoints could never have worked.

    A behavioural test did not catch this: stubbing the engine skips right past
    `_build_user_context`, which is where the query lives. This checks the
    wiring itself, which is the thing that was wrong.
    """
    import inspect
    from app.core.database import get_db, get_sync_db
    import app.api.personalization as personalization

    for route in personalization.router.routes:
        endpoint = getattr(route, "endpoint", None)
        if endpoint is None:
            continue
        for name, param in inspect.signature(endpoint).parameters.items():
            default = param.default
            dependency = getattr(default, "dependency", None)
            if dependency is None:
                continue
            assert dependency is not get_db, (
                f"{endpoint.__name__}() takes the ASYNC session via '{name}'; "
                "this router uses the sync ORM API and will raise "
                "AttributeError on the first db.query()"
            )
            if name == "db":
                assert dependency is get_sync_db, (
                    f"{endpoint.__name__}() should depend on get_sync_db"
                )


# ── The context builder actually runs ─────────────────────────────────


def test_ai_engine_references_only_real_model_columns():
    """Every `Model.attribute` in ai_engine must exist on that model.

    This module was written against a schema that never existed. Removing the
    api_key gate exposed it one layer at a time, each fix revealing the next:

        NutritionLog.consumed_at        -> log_date
        NutritionLog.carbohydrates_g    -> carbs_g
        FitnessLog.performed_at         -> log_date
        SleepLog.bedtime                -> sleep_date
        MoodEntry.recorded_at           -> entry_date
        SymptomLog.started_at           -> log_date
        VitalsLog.recorded_at           -> log_date
        VitalsLog.systolic_bp           -> blood_pressure_systolic
        Medication.status == "active"   -> is_active

    Nine wrong names in one file, none reachable while the gate above them
    returned 503 first. A static check costs nothing and finds them all at once
    instead of one production deploy at a time.
    """
    import re
    import app.services.ai_engine as engine_module

    src = (Path(engine_module.__file__)).read_text()
    bad = []
    for model_name, attr in sorted(set(re.findall(r"\b([A-Z][A-Za-z]+)\.([a-z_]+)\b", src))):
        model = getattr(engine_module, model_name, None)
        if model is None or not hasattr(model, "__table__"):
            continue  # not an ORM model in this module's namespace
        if not hasattr(model, attr):
            cols = sorted(c.name for c in model.__table__.columns)
            bad.append(f"{model_name}.{attr} (real columns include: {cols[:6]})")
    assert not bad, "ai_engine references columns that do not exist:\n  " + "\n  ".join(bad)


def test_ai_engine_reads_only_real_columns_off_query_results():
    """Every `row.attribute` must exist too, not just `Model.attribute`.

    The class-level check above matches `Medication.is_active` but not
    `m.medication_name`, and that is exactly where the tenth wrong name hid:

        for m in db.query(Medication)...:  m.medication_name   -> name

    `/personalization/health-score` therefore raised AttributeError for any user
    holding an ACTIVE prescription, and looked healthy only because the
    reference account had none. `POST /medications/promote-logged` creates
    precisely those rows, so using that feature broke the health score.

    Each loop or comprehension variable is resolved back to the model its
    `db.query(...)` named, then every attribute read off it is checked.
    """
    import ast
    import app.services.ai_engine as engine_module

    src = Path(engine_module.__file__).read_text()
    tree = ast.parse(src)

    def queried_model(node):
        """The model in a `db.query(Model)` chain anywhere inside `node`."""
        for n in ast.walk(node):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                    and n.func.attr == "query" and n.args
                    and isinstance(n.args[0], ast.Name)):
                return n.args[0].id
        return None

    reads: dict[tuple[str, str], str] = {}
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        rowvars: dict[str, str] = {}
        for n in ast.walk(fn):
            if (isinstance(n, ast.Assign) and len(n.targets) == 1
                    and isinstance(n.targets[0], ast.Name)):
                model = queried_model(n.value)
                if model:
                    rowvars[n.targets[0].id] = model
        for n in ast.walk(fn):
            if isinstance(n, ast.For):
                gens = [(n.target, n.iter)]
            elif isinstance(n, (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)):
                gens = [(g.target, g.iter) for g in n.generators]
            else:
                continue
            for target, it in gens:
                if not isinstance(target, ast.Name):
                    continue
                model = rowvars.get(it.id) if isinstance(it, ast.Name) else queried_model(it)
                if model:
                    rowvars[target.id] = model
        for n in ast.walk(fn):
            if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name):
                model = rowvars.get(n.value.id)
                if model:
                    reads.setdefault((model, n.attr), fn.name)

    # A resolver that resolves nothing would pass this test while checking
    # nothing at all — the empty-state lie in test form. Refuse to be vacuous.
    assert len(reads) >= 20, (
        f"the attribute resolver found only {len(reads)} reads; it has stopped "
        "tracking query results and is no longer checking anything"
    )

    bad = []
    for (model_name, attr), fname in sorted(reads.items()):
        model = getattr(engine_module, model_name, None)
        if model is None or not hasattr(model, "__table__"):
            continue
        if not hasattr(model, attr):
            cols = sorted(c.name for c in model.__table__.columns)
            bad.append(f"{fname}(): {model_name} row has no .{attr} "
                       f"(real columns include: {cols[:6]})")
    assert not bad, "ai_engine reads columns that do not exist:\n  " + "\n  ".join(bad)


def test_profile_list_fields_survive_comma_separated_text():
    """Allergies are stored as "Penicilin, Latex, Heparine", not JSON.

    `json.loads()` on that raises JSONDecodeError and takes the whole context
    build down, so /personalization/* 500d for any user who had filled in an
    allergy — which is most of them.
    """
    from app.services.ai_engine import AIPersonalizationEngine as E

    assert E._as_list("Penicilin, Latex, Heparine") == ["Penicilin", "Latex", "Heparine"]
    assert E._as_list('["a", "b"]') == ["a", "b"]          # JSON still works
    assert E._as_list("") == []
    assert E._as_list(None) == []
    assert E._as_list("single") == ["single"]
