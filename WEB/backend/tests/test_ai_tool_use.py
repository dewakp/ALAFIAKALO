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


def test_a_garbled_date_is_now_refused_rather_than_defaulted():
    """This test previously asserted the OPPOSITE — that an unreadable date
    quietly fell back to a default. That fallback is what turned "yesterday"
    into a seven-day window whose potassium total was reported as one day's."""
    import pytest as _pytest

    from app.services.record_tools import _window

    with _pytest.raises(ValueError):
        _window("not-a-date", None)


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


# ── progress: what the patient is shown during a 40-second wait ────────

def test_every_tool_has_a_patient_facing_label():
    """The label is sent by the SERVER so web, iOS and Android cannot drift and
    a new tool does not need three app releases to get a name."""
    from app.services.record_tools import TOOL_LABELS, TOOL_SPECS

    missing = {t["name"] for t in TOOL_SPECS} - set(TOOL_LABELS)
    assert not missing, f"no status label for: {sorted(missing)}"


def test_tool_specs_carry_only_fields_the_wire_expects():
    """The Anthropic adapter sends these dicts to the provider VERBATIM, so an
    extra key here reaches the API as an unknown field. That is why the labels
    live in a separate map rather than inside the spec."""
    from app.services.record_tools import TOOL_SPECS

    for spec in TOOL_SPECS:
        assert set(spec) <= {"name", "description", "input_schema"}, (
            f"{spec.get('name')} carries a field the provider will not expect")


def test_display_detail_never_reports_a_failure_as_an_empty_result():
    """§3aa in a status chip: "nothing recorded" is a real finding, and a tool
    that failed must not borrow that wording."""
    from app.services.ai_conversation import _display_detail

    assert _display_detail({"error": "boom"}) == "could not read that"
    assert _display_detail({"meals": []}) == "nothing recorded"
    assert _display_detail({"meals": [1, 2, 3]}) == "3 found"


@pytest.mark.asyncio
async def test_the_loop_reports_each_step_it_actually_takes(monkeypatch):
    """The rounds take tens of seconds and cannot stream, so the wait used to be
    a blinking cursor. These frames are REPORTS: each one names a step the
    server really took, in the order it took them."""
    from app.services import ai_conversation as ac

    replies = [
        {"text": "", "tool_calls": [{"id": "c1", "name": "get_meals", "arguments": {}}],
         "provider": "p", "model": "m", "tokens_used": 1},
        {"text": "You ate rice.", "tool_calls": [],
         "provider": "p", "model": "m", "tokens_used": 1},
    ]

    async def _fake_chat(prompt, **kw):
        return replies.pop(0)

    async def _fake_tool(db, user_id, name, args, today=None):
        return {"meals": [1, 2, 3, 4, 5, 6], "count": 6}

    monkeypatch.setattr("app.services.alafia_model_service.alafia_chat_detailed",
                        _fake_chat, raising=False)
    monkeypatch.setattr(ac, "run_tool", _fake_tool)

    seen: list[dict] = []

    async def _progress(event):
        seen.append(event)

    convo = await ac.answer_with_tools(None, 1, "sys", [{"role": "user", "content": "q"}],
                                       progress=_progress)
    assert convo.text == "You ate rice."

    phases = [e["phase"] for e in seen]
    assert phases == ["thinking", "tool", "tool_done", "thinking", "composing"], phases
    assert seen[1]["label"] == "Checking your meals"
    assert seen[2]["detail"] == "6 found"
    assert all(e.get("label") for e in seen), "every frame must carry text to show"


@pytest.mark.asyncio
async def test_a_broken_progress_callback_never_fails_the_answer(monkeypatch):
    """A display problem must not cost the patient their answer."""
    from app.services import ai_conversation as ac

    async def _fake_chat(prompt, **kw):
        return {"text": "fine", "tool_calls": [], "provider": "p", "model": "m",
                "tokens_used": 0}

    async def _boom(event):
        raise RuntimeError("ui exploded")

    monkeypatch.setattr("app.services.alafia_model_service.alafia_chat_detailed",
                        _fake_chat, raising=False)
    convo = await ac.answer_with_tools(None, 1, "sys", [{"role": "user", "content": "q"}],
                                       progress=_boom)
    assert convo.text == "fine"


@pytest.mark.asyncio
async def test_the_loop_still_works_with_no_progress_callback(monkeypatch):
    """/ai/chat does not stream and passes none."""
    from app.services import ai_conversation as ac

    async def _fake_chat(prompt, **kw):
        return {"text": "ok", "tool_calls": [], "provider": "p", "model": "m",
                "tokens_used": 0}

    monkeypatch.setattr("app.services.alafia_model_service.alafia_chat_detailed",
                        _fake_chat, raising=False)
    convo = await ac.answer_with_tools(None, 1, "sys", [{"role": "user", "content": "q"}])
    assert convo.text == "ok"


# ── streaming: the answer appears as it is written ─────────────────────

def test_openai_tool_call_fragments_are_reassembled():
    """`arguments` arrives as a run of string pieces keyed by index. Treating a
    fragment as a whole call sends the tool a truncated argument."""
    from alafia_model.adapters.tool_protocol import StreamedToolCalls

    acc = StreamedToolCalls()
    acc.openai_delta([{"index": 0, "id": "c1", "function": {"name": "get_meals",
                                                            "arguments": '{"start_'}}])
    acc.openai_delta([{"index": 0, "function": {"arguments": 'date": "2026-09-05"}'}}])
    assert acc.finish() == [
        {"id": "c1", "name": "get_meals", "arguments": {"start_date": "2026-09-05"}}]


def test_anthropic_tool_call_fragments_are_reassembled():
    from alafia_model.adapters.tool_protocol import StreamedToolCalls

    acc = StreamedToolCalls()
    acc.anthropic_start(1, {"type": "tool_use", "id": "t1", "name": "get_labs"})
    acc.anthropic_delta(1, '{"limit"')
    acc.anthropic_delta(1, ': 5}')
    assert acc.finish() == [{"id": "t1", "name": "get_labs", "arguments": {"limit": 5}}]


def test_a_text_block_is_not_mistaken_for_a_tool_call():
    from alafia_model.adapters.tool_protocol import StreamedToolCalls

    acc = StreamedToolCalls()
    acc.anthropic_start(0, {"type": "text"})
    assert acc.finish() == []


def test_ollama_sends_whole_calls_with_object_arguments():
    from alafia_model.adapters.tool_protocol import StreamedToolCalls

    acc = StreamedToolCalls()
    acc.whole_calls([{"function": {"name": "get_vitals", "arguments": {"days": 7}}}])
    out = acc.finish()
    assert out[0]["name"] == "get_vitals"
    assert out[0]["arguments"] == {"days": 7}
    assert out[0]["id"], "a call with no id must still be addressable"


def test_an_unfinished_fragment_run_does_not_lose_the_call():
    """A truncated stream yields {} rather than raising — every tool here reads
    no arguments as "today", which beats losing the whole answer."""
    from alafia_model.adapters.tool_protocol import StreamedToolCalls

    acc = StreamedToolCalls()
    acc.openai_delta([{"index": 0, "id": "c1",
                       "function": {"name": "get_meals", "arguments": '{"start_'}}])
    assert acc.finish() == [{"id": "c1", "name": "get_meals", "arguments": {}}]


@pytest.mark.asyncio
async def test_streaming_loop_retracts_a_preamble_that_preceded_a_tool_call(monkeypatch):
    """Models narrate before calling ("Let me check your food log…"). That text
    belongs to a FETCH, not the answer, and leaving it splices the preamble onto
    the front of an answer it was never part of."""
    from app.services import ai_conversation as ac

    rounds = [
        [{"type": "text", "text": "Let me check your log."},
         {"type": "tool_calls", "calls": [{"id": "c1", "name": "get_meals", "arguments": {}}]}],
        [{"type": "text", "text": "You ate rice."}],
    ]

    async def _fake_stream(prompt, **kw):
        for ev in rounds.pop(0):
            yield ev

    async def _fake_tool(db, user_id, name, args, today=None):
        return {"meals": [1, 2, 3]}

    monkeypatch.setattr("app.services.alafia_model_service.stream_alafia_events",
                        _fake_stream, raising=False)
    monkeypatch.setattr(ac, "run_tool", _fake_tool)

    text, retracted, convo = "", 0, None
    async for ev in ac.stream_with_tools(None, 1, "sys", [{"role": "user", "content": "q"}]):
        if "text" in ev:
            text += ev["text"]
        elif "retract" in ev:
            retracted += ev["retract"]
            text = text[:max(0, len(text) - ev["retract"])]
        elif "done" in ev:
            convo = ev["done"]

    assert retracted == len("Let me check your log.")
    assert text == "You ate rice.", "the preamble was left on the front of the answer"
    assert convo.text == "You ate rice."
    assert len(convo.traces) == 1


@pytest.mark.asyncio
async def test_streaming_loop_reports_the_same_steps_as_the_buffered_one(monkeypatch):
    from app.services import ai_conversation as ac

    rounds = [
        [{"type": "tool_calls", "calls": [{"id": "c1", "name": "get_meals", "arguments": {}}]}],
        [{"type": "text", "text": "done"}],
    ]

    async def _fake_stream(prompt, **kw):
        for ev in rounds.pop(0):
            yield ev

    async def _fake_tool(db, user_id, name, args, today=None):
        return {"meals": [1]}

    monkeypatch.setattr("app.services.alafia_model_service.stream_alafia_events",
                        _fake_stream, raising=False)
    monkeypatch.setattr(ac, "run_tool", _fake_tool)

    phases = [ev["phase"] async for ev in
              ac.stream_with_tools(None, 1, "sys", [{"role": "user", "content": "q"}])
              if "phase" in ev]
    assert phases == ["thinking", "tool", "tool_done", "thinking", "composing"], phases


def test_both_loops_share_one_set_of_instructions():
    """Two copies is how the streaming path and the buffered one start answering
    the same question differently."""
    import inspect

    from app.services import ai_conversation as ac

    for fn in (ac.answer_with_tools, ac.stream_with_tools):
        assert "_TOOL_LOOP_INSTRUCTIONS" in inspect.getsource(fn)


# ── an adapter that predates the events API ────────────────────────────

@pytest.mark.asyncio
async def test_a_text_only_adapter_still_serves_a_request_without_tools(monkeypatch):
    """Requiring `stream_chat_events` everywhere would drop a funded provider
    that can perfectly well stream text."""
    from alafia_model.capabilities.llm import LLMCapability
    from alafia_model.registry.providers import ProviderSpec

    class _TextOnly:
        model_name = "old"

        async def stream_chat(self, messages, temperature=0.5, max_tokens=2048):
            yield "hello"

    cap = LLMCapability.__new__(LLMCapability)
    spec = ProviderSpec("groq", "https://x/v1", "GROQ_API_KEY", "m", "free", 1.0)
    monkeypatch.setattr("alafia_model.registry.providers.ordered_for_selection",
                        lambda **kw: [spec])
    monkeypatch.setattr(cap, "_adapter_for", lambda s: _TextOnly(), raising=False)
    monkeypatch.setattr(cap, "_get_adapter", lambda model=None: _TextOnly(), raising=False)
    monkeypatch.setattr("alafia_model.capabilities.llm._ollama_first", lambda: False)

    out = [e async for e in cap.stream_events([{"role": "user", "content": "hi"}])]
    assert out == [{"type": "text", "text": "hello"}]


@pytest.mark.asyncio
async def test_a_text_only_adapter_is_SKIPPED_when_tools_are_required(monkeypatch):
    """It would answer in prose while the caller waits for a tool call — worse
    than refusing, and the whole reason `supports_tools` gates selection."""
    from alafia_model.capabilities.llm import LLMCapability
    from alafia_model.registry.providers import ProviderSpec

    class _TextOnly:
        model_name = "old"

        async def stream_chat(self, messages, temperature=0.5, max_tokens=2048):
            yield "prose instead of a tool call"

    cap = LLMCapability.__new__(LLMCapability)
    spec = ProviderSpec("groq", "https://x/v1", "GROQ_API_KEY", "m", "free", 1.0)
    monkeypatch.setattr("alafia_model.registry.providers.ordered_for_selection",
                        lambda **kw: [spec])
    monkeypatch.setattr(cap, "_adapter_for", lambda s: _TextOnly(), raising=False)
    monkeypatch.setattr(cap, "_get_adapter", lambda model=None: _TextOnly(), raising=False)
    monkeypatch.setattr("alafia_model.capabilities.llm._ollama_first", lambda: False)

    tools = [{"name": "get_meals", "description": "d", "input_schema": {}}]
    with pytest.raises(Exception):
        [e async for e in cap.stream_events([{"role": "user", "content": "hi"}],
                                            tools=tools)]


# ── whose "today" is it ────────────────────────────────────────────────

def test_the_patients_zone_beats_the_servers_utc():
    """The bug, exactly: at 20:54 on 2026-09-05 in New York the container's
    `date.today()` already reads 2026-09-06, so "what did I eat today?" queried
    a day with no rows and reported nothing eaten to a patient with six meals
    and 58.4 g of sugar logged."""
    from datetime import datetime, timezone as tz
    from unittest.mock import patch

    from app.core.patient_time import patient_today

    utc_now = datetime(2026, 9, 6, 0, 54, tzinfo=tz.utc)  # = 20:54 on the 5th in NY
    with patch("app.core.patient_time.datetime") as fake:
        fake.now.return_value = utc_now
        assert str(patient_today("America/New_York")) == "2026-09-05"
        assert str(patient_today(None)) == "2026-09-06", "UTC remains the fallback"


def test_an_unusable_timezone_is_discarded_not_guessed_at():
    """Production holds "America/New York" — not a valid IANA name. Silently
    "correcting" it to America/New_York would be inventing a fact about where
    someone lives; falling back to UTC is honest."""
    from app.core.patient_time import zone_name

    assert zone_name("America/New York") == "UTC"
    assert zone_name("Not/AZone") == "UTC"
    assert zone_name("") == "UTC"
    assert zone_name(None, "America/Chicago") == "America/Chicago"


def test_the_client_hint_wins_over_a_stale_stored_zone():
    """83 of 85 production users have `users.timezone` NULL, and a traveller's
    stored value is out of date the moment they land."""
    from app.core.patient_time import zone_name

    assert zone_name("Europe/London", "America/Chicago") == "Europe/London"


def test_tools_use_the_date_they_are_given():
    from datetime import date

    from app.services.record_tools import _window

    given = date(2026, 9, 5)
    assert _window(None, None, given) == (given, given)


@pytest.mark.asyncio
async def test_the_loop_passes_the_patients_date_to_every_tool(monkeypatch):
    """A model must never be asked what day it is, so the loop supplies it —
    and it has to be the PATIENT's date, not the container's."""
    from datetime import date

    from app.services import ai_conversation as ac

    seen = {}

    async def _fake_chat(prompt, **kw):
        if "calls" not in seen:
            seen["calls"] = True
            return {"text": "", "tool_calls": [
                {"id": "c1", "name": "get_meals", "arguments": {}}],
                "provider": "p", "model": "m", "tokens_used": 0}
        return {"text": "done", "tool_calls": [], "provider": "p", "model": "m",
                "tokens_used": 0}

    async def _fake_tool(db, user_id, name, args, today=None):
        seen["today"] = today
        return {"meals": [1]}

    monkeypatch.setattr("app.services.alafia_model_service.alafia_chat_detailed",
                        _fake_chat, raising=False)
    monkeypatch.setattr(ac, "run_tool", _fake_tool)

    given = date(2026, 9, 5)
    await ac.answer_with_tools(None, 1, "sys", [{"role": "user", "content": "q"}],
                               today=given)
    assert seen["today"] == given


# ── the whole nutrient panel, not a curated fourteen ───────────────────

def test_meals_expose_every_nutrient_column_on_the_model():
    """The tool used to return a hand-written 14-nutrient allowlist while
    NutritionLog has 58 columns, so 44 were dropped before the model saw them —
    `vitamin_b9_folate_mcg` among them, populated on 1,215 of 1,286 rows. Asked
    about folate, the assistant said the breakdown "does not include folic acid
    data" on a patient with chronic anaemia. The number was in the row.
    """
    from app.models.nutrition import NutritionLog
    from app.services.record_tools import _nutrient_columns

    fields = set(_nutrient_columns(NutritionLog))
    assert "vitamin_b9_folate_mcg" in fields, "folate is dropped again"
    for nutrient in ("vitamin_c_mg", "zinc_mg", "selenium_mcg", "iodine_mcg",
                     "choline_mg", "vitamin_d_iu", "vitamin_k_mcg", "copper_mg",
                     "omega3_g", "caffeine_mg"):
        assert nutrient in fields, f"{nutrient} is not reaching the assistant"
    assert len(fields) > 40, f"only {len(fields)} nutrients exposed"


def test_no_identity_or_bookkeeping_column_is_served_as_a_nutrient():
    from app.models.nutrition import NutritionLog
    from app.services.record_tools import _nutrient_columns

    fields = set(_nutrient_columns(NutritionLog))
    for junk in ("id", "user_id", "log_date", "food_name", "created_at",
                 "recipe_url", "food_image_uris", "nutrient_status"):
        assert junk not in fields


@pytest.mark.asyncio
async def test_a_named_nutrient_is_answered_from_wherever_it_lives(db):
    """"Folic acid" must find the value whether it sits in a column or in the
    extended JSON panel. The screenshot that started this said "the nutrient
    breakdown provided does not include folic acid data" — on a patient with
    chronic anaemia, with the figure in the row the whole time."""
    from datetime import date

    from app.models.nutrition import NutritionLog
    from app.models.user import User
    from app.services.record_tools import get_meals

    user = User(email="panel@alafia.app", hashed_password="x", full_name="P")
    db.add(user)
    await db.flush()
    db.add(NutritionLog(
        user_id=user.id, log_date=date.today(), meal_type="breakfast",
        food_name="Fortified cereal", calories=200.0,
        vitamin_b9_folate_mcg=180.0, nutrient_status="done",
        extended_nutrients={"folate_dfe_mcg": 306.0, "food_folate_mcg": 22.8,
                            "lycopene_mcg": 45.6},
    ))
    await db.flush()

    out = await get_meals(db, user.id, nutrients=["folic acid"])
    meal = out["meals"][0]
    assert meal["vitamin_b9_folate_mcg"] == 180.0, "column value missing"
    assert meal["folate_dfe_mcg"] == 306.0, "extended panel value missing"
    assert out["nutrient_reference"]["vitamin_b9_folate_mcg"][
        "general_adult_reference"] == 400, (
        "a reference figure must travel with the value, or the model can only "
        "say 'your daily aim for folate is not specified'")


@pytest.mark.asyncio
async def test_a_targeted_question_does_not_haul_back_the_whole_panel(db):
    """A question about folate should fetch folate. The full panel is 101
    fields a meal and ~48k characters for a week."""
    from datetime import date

    from app.models.nutrition import NutritionLog
    from app.models.user import User
    from app.services.record_tools import get_meals

    user = User(email="narrow@alafia.app", hashed_password="x", full_name="N")
    db.add(user)
    await db.flush()
    db.add(NutritionLog(
        user_id=user.id, log_date=date.today(), meal_type="lunch",
        food_name="Rice", calories=300.0, potassium_mg=400.0, zinc_mg=2.0,
        vitamin_b9_folate_mcg=50.0, nutrient_status="done",
        extended_nutrients={"lycopene_mcg": 12.0, "leucine_g": 0.5},
    ))
    await db.flush()

    meal = (await get_meals(db, user.id, nutrients=["folate"]))["meals"][0]
    assert "vitamin_b9_folate_mcg" in meal
    assert "lycopene_mcg" not in meal, "unrequested nutrients were included"
    assert "zinc_mg" not in meal


@pytest.mark.asyncio
async def test_tracked_but_absent_is_not_the_same_as_untracked(db):
    """Two different facts, and the model must be able to say which: "we have no
    zinc figure for these meals" vs "we do not track unobtainium" (§3aa)."""
    from datetime import date

    from app.models.nutrition import NutritionLog
    from app.models.user import User
    from app.services.record_tools import get_meals

    user = User(email="absent@alafia.app", hashed_password="x", full_name="A")
    db.add(user)
    await db.flush()
    db.add(NutritionLog(user_id=user.id, log_date=date.today(), meal_type="lunch",
                        food_name="Rice", calories=300.0, nutrient_status="done"))
    await db.flush()

    out = await get_meals(db, user.id, nutrients=["zinc", "unobtainium"])
    assert "zinc_mg" in out["tracked_but_no_value"]
    assert out["not_tracked"] == ["unobtainium"]


def test_the_nutrient_vocabulary_is_the_shared_catalog():
    """116 nutrients with their USDA ids, names, units and RDAs. Matching
    against raw column names instead would miss the 75 that live in the
    extended panel, and would not know what "folic acid" is called."""
    from app.core.nutrition_data import get_nutrient_catalog
    from app.services.record_tools import _match_nutrients

    assert len(get_nutrient_catalog()) >= 116
    hits, misses, ref, _fam = _match_nutrients(["folic acid"])
    assert "folic_acid_mcg" in hits and not misses
    hits, _, _, _ = _match_nutrients(["vitamin d"])
    assert any("vitamin_d" in h for h in hits)


# ── a bad date must not become a different window ──────────────────────

def test_relative_days_are_understood():
    """Claude said "yesterday" on the very first real question asked of this
    tool. The words are what models actually write."""
    from datetime import date

    from app.services.record_tools import _window

    today = date(2026, 9, 6)
    assert _window("yesterday", "yesterday", today) == (date(2026, 9, 5),) * 2
    assert _window("today", "today", today) == (today, today)
    assert _window("3 days ago", "today", today) == (date(2026, 9, 3), today)


def test_an_unreadable_date_is_refused_not_silently_widened():
    """THE bug: "yesterday" fell through to a default and produced a SEVEN-DAY
    window. The model summed 20 meals and reported 7,699 mg of potassium as one
    day's intake. A bad argument became a confident wrong clinical number —
    worse than an error, which the model can act on."""
    from datetime import date

    import pytest as _pytest

    from app.services.record_tools import _window

    with _pytest.raises(ValueError, match="not a date"):
        _window("last Tuesday-ish", None, date(2026, 9, 6))


@pytest.mark.asyncio
async def test_the_tool_returns_that_refusal_to_the_model():
    from app.services.record_tools import run_tool

    out = await run_tool(None, 1, "get_meals", {"start_date": "sometime last week"})
    assert "error" in out and "not a date" in out["error"]
    assert "yesterday" in out["error"], "the error must name the accepted forms"


def test_a_single_date_does_not_open_a_week():
    """Given only a start, the old code walked back _DEFAULT_DAYS from a
    default end. One named day means that day."""
    from datetime import date

    from app.services.record_tools import _window

    today = date(2026, 9, 6)
    assert _window("2026-09-01", None, today) == (date(2026, 9, 1),) * 2


def test_a_generic_rda_is_never_presented_as_the_patients_limit():
    """Potassium's adult RDA is 4,700 mg; this patient's computed limit is
    2,800 mg max. Handing the model a field called "rda" invited it to quote
    the wrong one to a renal patient — it did exactly that in testing."""
    from app.services.record_tools import _match_nutrients

    _, _, ref, _fam = _match_nutrients(["potassium"])
    entry = ref["potassium_mg"]
    assert "rda" not in entry, "a bare 'rda' reads as the patient's own target"
    assert entry["general_adult_reference"] == 4700


@pytest.mark.asyncio
async def test_a_family_with_a_value_is_not_reported_as_missing(db):
    """Asking for "folate" returns four USDA measurements and three are usually
    NULL. Listing them individually put "tracked_but_no_value: 3" in front of
    the model beside a perfectly good 306 mcg folate figure — and it answered
    "there is no folic-acid target recorded"."""
    from datetime import date

    from app.models.nutrition import NutritionLog
    from app.models.user import User
    from app.services.record_tools import get_meals

    user = User(email="family@alafia.app", hashed_password="x", full_name="F")
    db.add(user)
    await db.flush()
    db.add(NutritionLog(user_id=user.id, log_date=date.today(), meal_type="lunch",
                        food_name="Greens", calories=100.0,
                        vitamin_b9_folate_mcg=92.0, nutrient_status="done"))
    await db.flush()

    out = await get_meals(db, user.id, nutrients=["folate"])
    assert out["meals"][0]["vitamin_b9_folate_mcg"] == 92.0
    assert "tracked_but_no_value" not in out, (
        "the folate family has a value; its empty siblings must not read as "
        "'no folate data'")
