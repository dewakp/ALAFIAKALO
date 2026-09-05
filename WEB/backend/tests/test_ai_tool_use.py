"""The tool loop, pinned at every seam it broke at.

The assistant used to decide IN ADVANCE which slice of the record a question
needed — first an eight-keyword table (`_QUERY_SECTION_MAP`, which had no entry
for "sugar"), then the whole 40k-character record, then a token-overlap score
that picked NUTRITION LOGS for "what medications am I taking?". Each was the
backend guessing at the question. Now the model asks for what it needs.

Getting that working took seven fixes, each hidden by the one before it, and
none of them would have failed a test that stubbed the model. They are all here
because the chain is only as good as its worst-served provider — and the two
that shipped broken were found by reading the wire, not the code (§0).
"""

import json

import pytest

from alafia_model.adapters import tool_protocol as tp


# ── the wire shape: one dialect, eighteen providers ────────────────────

def _assistant_turn():
    return {"role": "assistant",
            "tool_calls": [{"id": "c1", "name": "get_meals",
                            "arguments": {"start_date": "2026-09-05"}}]}


def test_assistant_tool_turn_is_translated_to_openai_shape():
    """The bug that would have broken production and not dev.

    The internal turn is Anthropic-flavoured. OpenAI needs the call nested
    under `function` with `arguments` as a JSON STRING; sent raw it is a 400,
    so the SECOND round of every tool conversation died on 18 of 20 providers.
    Ollama tolerates the raw shape, and dev is Ollama-first (§3ak) — so the
    verified path was the forgiving one.
    """
    out = tp.to_openai_messages([_assistant_turn()])[0]
    call = out["tool_calls"][0]
    assert call["type"] == "function"
    assert call["function"]["name"] == "get_meals"
    assert isinstance(call["function"]["arguments"], str), (
        "OpenAI requires arguments as a JSON string, not a dict")
    assert json.loads(call["function"]["arguments"]) == {"start_date": "2026-09-05"}


def test_translation_is_idempotent():
    """Safe to apply twice — an already-encoded argument is not double-encoded."""
    once = tp.to_openai_messages([_assistant_turn()])
    twice = tp.to_openai_messages(once)
    assert once == twice


def test_tool_result_turns_pass_through_unchanged():
    msg = {"role": "tool", "tool_call_id": "c1", "name": "get_meals",
           "content": '{"count": 3}'}
    assert tp.to_openai_messages([msg]) == [msg]


@pytest.mark.asyncio
async def test_ollama_keeps_the_internal_tool_shape(monkeypatch):
    """Ollama must NOT get the OpenAI translation.

    It wants tool-call `arguments` as an OBJECT and answers 400 to the JSON
    string form. Sending it the OpenAI shape killed round 2 of every tool
    conversation — round 1 fetched the meals, round 2 was refused, and the
    fallback answered from the record dump with a figure that was in no row.
    """
    from alafia_model.adapters import ollama_adapter as mod

    sink = []
    _patch(monkeypatch, mod, {"message": {"content": "ok"}, "eval_count": 3}, sink)

    a = mod.OllamaAdapter.__new__(mod.OllamaAdapter)
    a.base_url, a.model_name, a.timeout = "http://ollama:11434", "m", 5.0
    monkeypatch.setattr(mod, "_ollama_auth_headers", lambda *a, **k: _noop_headers())

    await a.chat([_assistant_turn()])
    sent = sink[0]["messages"][0]["tool_calls"][0]
    assert isinstance(sent.get("arguments"), dict), (
        "Ollama needs arguments as an object; the OpenAI string form is a 400")


async def _noop_headers():
    return {}


def test_ordinary_turns_are_untouched():
    convo = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"},
             {"role": "assistant", "content": "a"}]
    assert tp.to_openai_messages(convo) == convo


def test_tool_definitions_map_input_schema_to_parameters():
    schema = {"type": "object", "properties": {"days": {"type": "integer"}}}
    fn = tp.to_openai_tools([{"name": "get_medications", "description": "d",
                              "input_schema": schema}])[0]
    assert fn["type"] == "function"
    assert fn["function"]["parameters"] == schema


def test_malformed_tool_arguments_do_not_raise():
    """A provider emitting bad JSON must not collapse the whole answer."""
    calls = tp.parse_openai_tool_calls(
        {"tool_calls": [{"id": "c1", "function": {"name": "get_meals",
                                                  "arguments": "{not json"}}]})
    assert calls[0]["arguments"] == {}


def test_anthropic_tool_use_blocks_are_read():
    calls = tp.parse_anthropic_tool_calls([
        {"type": "text", "text": "let me check"},
        {"type": "tool_use", "id": "t1", "name": "get_labs", "input": {"limit": 5}},
    ])
    assert calls == [{"id": "t1", "name": "get_labs", "arguments": {"limit": 5}}]


# ── every adapter must RETURN what it parsed ───────────────────────────

class _Resp:
    def __init__(self, payload):
        self._p = payload

    def json(self):
        return self._p

    def raise_for_status(self):
        return None


class _Client:
    """Captures the posted body and replays a canned response."""

    def __init__(self, payload, sink):
        self._payload, self._sink = payload, sink

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, **kw):
        self._sink.append(kw.get("json"))
        return _Resp(self._payload)


def _patch(monkeypatch, module, payload, sink):
    monkeypatch.setattr(module, "httpx",
                        type("x", (), {"AsyncClient": lambda *a, **k: _Client(payload, sink)}),
                        raising=False)


@pytest.mark.asyncio
async def test_openai_compat_returns_tool_calls(monkeypatch):
    """It parsed them into a local and then dropped them from the return dict.

    The tool loop saw prose, concluded the model had answered, and returned an
    answer built from framing context with NONE of the record in it — on the
    eighteen providers that serve production.
    """
    from alafia_model.adapters import openai_compat_adapter as mod

    sink = []
    _patch(monkeypatch, mod, {"choices": [{"message": {
        "content": "", "tool_calls": [{"id": "c1", "function": {
            "name": "get_meals", "arguments": "{}"}}]}}]}, sink)

    a = mod.OpenAICompatAdapter.__new__(mod.OpenAICompatAdapter)
    a._api_key, a.base_url, a.model_name = "k", "https://x/v1", "m"
    a.provider, a.extra_headers, a.timeout = "groq", {}, 5.0

    out = await a.chat([{"role": "user", "content": "hi"}], tools=[
        {"name": "get_meals", "description": "d", "input_schema": {"type": "object"}}])
    assert out.get("tool_calls"), "tool_calls parsed but not returned"
    assert out["tool_calls"][0]["name"] == "get_meals"


@pytest.mark.asyncio
async def test_openai_compat_sends_translated_history(monkeypatch):
    from alafia_model.adapters import openai_compat_adapter as mod

    sink = []
    _patch(monkeypatch, mod, {"choices": [{"message": {"content": "ok"}}]}, sink)

    a = mod.OpenAICompatAdapter.__new__(mod.OpenAICompatAdapter)
    a._api_key, a.base_url, a.model_name = "k", "https://x/v1", "m"
    a.provider, a.extra_headers, a.timeout = "groq", {}, 5.0

    await a.chat([_assistant_turn()])
    sent = sink[0]["messages"][0]["tool_calls"][0]
    assert sent["type"] == "function"
    assert isinstance(sent["function"]["arguments"], str)


@pytest.mark.asyncio
async def test_anthropic_keeps_tool_results_in_the_conversation(monkeypatch):
    """The adapter flattened every message to a string, so `role="tool"` turns
    vanished and the model never received the results of its own calls."""
    from alafia_model.adapters import anthropic_adapter as mod

    sink = []
    _patch(monkeypatch, mod, {"content": [{"type": "text", "text": "done"}],
                              "usage": {"input_tokens": 1, "output_tokens": 1}}, sink)

    a = mod.AnthropicAdapter.__new__(mod.AnthropicAdapter)
    a._api_key, a.base_url, a.model_name, a.timeout = "k", "https://api.anthropic.com", "m", 5.0

    await a.chat([
        {"role": "user", "content": "what did I eat"},
        _assistant_turn(),
        {"role": "tool", "tool_call_id": "c1", "name": "get_meals",
         "content": '{"count": 6}'},
    ])
    body = json.dumps(sink[0])
    assert "tool_result" in body, "tool results never reached the model"
    assert '{\\"count\\": 6}' in body or '"count": 6' in body


# ── a provider that cannot do tools must be skipped, not tried ─────────

def test_providers_without_tool_support_are_excluded():
    """Perplexity ignores a `tools` field and answers in prose — worse than
    refusing, because the caller waits for a call that never comes."""
    from alafia_model.registry.providers import ordered_for_selection

    names = {s.name for s in ordered_for_selection(require_tools=True)}
    assert "perplexity" not in names
    assert names, "requiring tools must not empty the pool"


def test_the_ordinary_path_keeps_every_provider():
    from alafia_model.registry.providers import ordered_for_selection

    assert len(ordered_for_selection()) >= len(ordered_for_selection(require_tools=True))


# ── the payload must actually carry tools to the capability ────────────

def test_inference_payload_carries_tools_through_to_dict():
    """The capability only ever sees `to_dict()`. A field added to the
    dataclass and not to that method is silently dropped."""
    from alafia_model.router import InferencePayload

    tools = [{"name": "get_meals", "description": "d", "input_schema": {}}]
    d = InferencePayload(task="chat", messages=[], tools=tools, local_only=True).to_dict()
    assert d["tools"] == tools
    assert d["local_only"] is True


# ── the server owns the clock ──────────────────────────────────────────

def test_omitted_dates_mean_today_not_a_window():
    """Told "Today is 2026-09-05" in the system prompt, a model still called
    get_meals for 2024-12-19 — its training cutoff — and reported no meals
    logged. A model cannot be asked to supply a date; the server has a clock."""
    from datetime import date

    from app.services.record_tools import _window

    assert _window(None, None) == (date.today(), date.today())


def test_a_reversed_range_is_repaired_not_returned_empty():
    from app.services.record_tools import _window

    s, e = _window("2026-09-05", "2026-09-01")
    assert s < e, "a backwards range would silently return nothing"


def test_a_garbled_date_falls_back_instead_of_raising():
    from datetime import date

    from app.services.record_tools import _window

    s, e = _window("not-a-date", None)
    assert e == date.today()


# ── a tool must report its failure, never abort the answer ─────────────

@pytest.mark.asyncio
async def test_unknown_tool_returns_an_error_not_an_exception():
    from app.services.record_tools import run_tool

    out = await run_tool(None, 1, "get_horoscope", {})
    assert "error" in out and "no such tool" in out["error"]


@pytest.mark.asyncio
async def test_bad_arguments_return_an_error_naming_the_tool():
    from app.services.record_tools import run_tool

    out = await run_tool(None, 1, "get_meals", {"nonsense_kwarg": 1})
    assert "error" in out and "get_meals" in out["error"]


# ── §3aa: medications come from THREE tables, not two ──────────────────

@pytest.mark.asyncio
async def test_medications_tool_reports_all_three_sources(db):
    """A review that checked prescriptions and dose logs concluded "no ESA
    prescribed or taken" while the patient had been on one for years — the
    drugs given during dialysis are in neither."""
    from app.models.user import User
    from app.services.record_tools import get_medications

    user = User(email="tools-meds@alafia.app", hashed_password="x", full_name="T")
    db.add(user)
    await db.flush()

    out = await get_medications(db, user.id)
    assert set(out) >= {"taken_by_patient", "administered_during_dialysis", "prescribed"}


# ── the lean context: framing only, detail through tools ───────────────

_SAMPLE = """=== TODAY IS 2026-09-05 ===
=== PATIENT PROFILE ===
age 54, male
=== GENETIC GROUND TRUTHS ===
G6PD deficiency — fava beans contraindicated
=== FOOD GUIDANCE ===
avoid: shellfish (allergy)
=== NUTRITION LOGS (last 90 days) ===
2026-06-02 breakfast — rice, sugar: 23g
=== LAB RESULTS ===
potassium 5.9
"""


def test_core_context_drops_the_record_dump():
    """Given the whole record AND tools, the model answered from the dump — it
    reported a three-month-old meal as today's. The detail must arrive through
    a tool call, dated, or it competes with the tools for the answer."""
    from app.api.ai import _core_context

    core = _core_context(_SAMPLE)
    assert "NUTRITION LOGS" not in core
    assert "LAB RESULTS" not in core


def test_core_context_keeps_the_safety_framing():
    """The allergy and genetic rails are NOT detail. A general question
    answered without them ("what can I eat as a coeliac") can recommend a food
    this patient must never have — the defect that made the allergy guard
    critical in the first place."""
    from app.api.ai import _core_context

    core = _core_context(_SAMPLE)
    for keep in ("TODAY IS", "PATIENT PROFILE", "GENETIC GROUND TRUTHS", "FOOD GUIDANCE"):
        assert keep in core, f"{keep} was dropped from the framing context"
    assert "G6PD" in core and "shellfish" in core


# ── §3ag: every column a tool reads must exist on its model ────────────

def test_every_field_a_tool_reads_exists_on_its_model():
    """A static check, because `getattr(row, name, None)` cannot fail.

    `get_vitals` read `systolic_bp`, `heart_rate`, `temperature_c`,
    `oxygen_saturation` and `blood_glucose` — five names VitalsLog does not
    have. Each became a silent omission, the tool returned a date and a weight,
    and the model correctly reported no blood pressure recorded on a patient
    who had it. Behavioural tests do not catch this; comparing the names to the
    table does, for free, for all of them at once (§3ag).
    """
    from app.models.elimination import BowelMovement, VomitingLog
    from app.models.labs import LabResult
    from app.models.nutrition import NutritionLog
    from app.models.vitals import VitalsLog
    from app.services import record_tools as rt

    for model, fields in (
        (NutritionLog, rt.MEAL_FIELDS),
        (VitalsLog, rt.VITALS_FIELDS),
        (BowelMovement, rt.BOWEL_FIELDS),
        (VomitingLog, rt.VOMIT_FIELDS),
        (LabResult, rt.LAB_FIELDS),
    ):
        columns = {c.key for c in model.__table__.columns}
        missing = set(fields) - columns
        assert not missing, f"{model.__name__} has no column(s): {sorted(missing)}"


def test_the_medication_serialiser_matches_the_view_it_is_given():
    """All three medication sources return MedicationView. Reading names off
    it that it does not have produced `{}` per row — four empty objects, which
    the model reported as "no medications taken"."""
    import dataclasses

    from app.services.clinical_sources import MedicationView

    fields = {f.name for f in dataclasses.fields(MedicationView)}
    assert {"name", "detail", "last", "doses", "active"} <= fields


@pytest.mark.asyncio
async def test_a_dose_logged_medication_is_not_serialised_empty(db):
    """The end of that bug, pinned on real rows: a logged dose must reach the
    model with its NAME, not as `{}`."""
    from datetime import date

    from app.models.med_nutrient import MedicationDoseLog
    from app.models.user import User
    from app.services.record_tools import get_medications

    user = User(email="tools-dose@alafia.app", hashed_password="x", full_name="T")
    db.add(user)
    await db.flush()
    db.add(MedicationDoseLog(user_id=user.id, medication_name="Calcium Carbonate",
                             log_date=date.today(), dose_amount=1000.0,
                             dose_unit="mg"))
    await db.flush()

    out = await get_medications(db, user.id)
    taken = out["taken_by_patient"]
    assert taken, "a logged dose did not reach the tool output"
    assert all(t for t in taken), "a medication serialised to an empty object"
    assert any("Calcium" in (t.get("name") or "") for t in taken)
