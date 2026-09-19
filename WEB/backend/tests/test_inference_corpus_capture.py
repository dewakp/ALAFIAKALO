"""Every resolution reaches the ALAFIA corpus — whatever rung answered it.

ALAFIA is the model we train ourselves. Ollama is not ALAFIA: it is a runtime
serving third-party weights and it is the terminal rung of the lookup path
(local DB search -> external provider -> local runtime). The order is unchanged
by any of this. What these tests pin is that the pair travelling through that
chain is actually captured, because for a long time it was not:
`telemetry.register_sink` was written for exactly this purpose and had no
callers, so `record()` hit `if not _sinks: return` and dropped it.

Two of these fail against the previous implementation for reasons worth naming:

  * it held `chat_msgs = arg if kind == "chat" else None`, so every
    single-prompt completion recorded its ANSWER with its QUESTION missing;
  * the hosted rung recorded `outbound` — the scrubbed copy — while the local
    rung recorded the raw one, so an identical question trained two different
    ways depending on which provider happened to win the race.
"""

import pytest

from alafia_model import privacy, telemetry
from alafia_model.capabilities.llm import LLMCapability
from alafia_model.registry.providers import ProviderSpec


class _Adapter:
    """Stands in for an adapter, recording what it was actually HANDED.

    Recording the argument is the point: it lets one test prove both halves at
    once — that the vendor received the redacted copy, and that the corpus
    received the patient's own words.
    """

    def __init__(self, name, seen):
        self.name, self.seen = name, seen
        self.model_name = f"{name}-model"

    async def chat(self, *a, **k):
        self.seen.append((self.name, a[0] if a else None))
        return {"content": f"hello from {self.name}", "tokens_used": 7,
                "model": self.model_name}

    complete = chat


class _FailingAdapter(_Adapter):
    async def chat(self, *a, **k):
        self.seen.append((self.name, a[0] if a else None))
        raise RuntimeError(f"{self.name} is down")

    complete = chat


@pytest.fixture
def captured():
    """Whatever telemetry hands a sink — the corpus's actual input."""
    records: list[dict] = []
    telemetry.clear_sinks()
    telemetry.register_sink(records.append)
    yield records
    telemetry.clear_sinks()


@pytest.fixture
def wired(monkeypatch):
    def _build(ollama_fails=False, hosted_fails=False):
        seen: list[tuple] = []
        cap = LLMCapability.__new__(LLMCapability)
        spec = ProviderSpec("groq", "https://x/v1", "GROQ_API_KEY", "m", "free", 1.0)
        monkeypatch.setattr("alafia_model.registry.providers.ordered_for_selection",
                            lambda **k: [spec])
        ollama_cls = _FailingAdapter if ollama_fails else _Adapter
        hosted_cls = _FailingAdapter if hosted_fails else _Adapter
        monkeypatch.setattr(cap, "_get_adapter",
                            lambda model=None: ollama_cls("ollama", seen), raising=False)
        monkeypatch.setattr(cap, "_adapter_for",
                            lambda s: hosted_cls("hosted", seen), raising=False)
        return cap, seen
    return _build


def _pair(records):
    """The first record that carries an input — the corpus's unit of work."""
    return next((r for r in records if r.get("messages") is not None), None)


@pytest.mark.asyncio
async def test_the_local_rung_records_the_pair(wired, captured, monkeypatch):
    monkeypatch.setenv("OLLAMA_FIRST", "true")
    cap, _ = wired()

    result = await cap._dispatch("chat", [{"role": "user", "content": "how is my potassium?"}],
                                 0.2, 64, False, None, False)

    assert result.success
    rec = _pair(captured)
    assert rec is not None, "the local rung answered and the corpus got nothing"
    assert rec["tier"] == "local"
    assert "how is my potassium?" in str(rec["messages"])
    assert rec["response"] == "hello from ollama"


@pytest.mark.asyncio
async def test_the_hosted_rung_records_the_patients_own_words(wired, captured, monkeypatch):
    """The vendor gets the scrubbed copy; the corpus gets the real one.

    Both halves, in one test. Redaction at the egress point (§3al) is unchanged
    and still proven here — what changes is that we stop keeping the vendor's
    sanitised copy as our own training data. ALAFIA runs on our infrastructure
    against text that still has names in it, so a corpus full of `[name]`
    teaches it to expect a token that never arrives.
    """
    monkeypatch.delenv("OLLAMA_FIRST", raising=False)
    privacy.register_identity(42, "Jane Doe", "jane@example.com", None)
    try:
        cap, seen = wired()

        await cap._dispatch("chat", [{"role": "user", "content": "I'm Jane Doe, K was 5.8"}],
                            0.2, 64, False, None, False, ("Jane Doe",))

        sent_to_vendor = str(next(arg for name, arg in seen if name == "hosted"))
        assert "Jane Doe" not in sent_to_vendor, "redaction regressed — a name reached a vendor"

        rec = _pair(captured)
        assert rec is not None
        assert "Jane Doe" in str(rec["messages"]), (
            "the corpus stored the vendor's scrubbed copy instead of the patient's words"
        )
        assert rec["input_was_redacted"] is False
    finally:
        privacy.clear_identity()


@pytest.mark.asyncio
async def test_a_single_prompt_completion_records_its_question(wired, captured, monkeypatch):
    """`complete` passes a bare string. It used to be recorded as None.

    An answer whose question was thrown away is not a training sample. This is
    the half of the corpus that never existed at all.
    """
    monkeypatch.setenv("OLLAMA_FIRST", "true")
    cap, _ = wired()

    await cap._dispatch("complete", "Estimate nutrients for 2 cups jollof rice",
                        0.2, 64, True, None, False)

    rec = _pair(captured)
    assert rec is not None, "a completion recorded its answer and dropped its question"
    assert "jollof rice" in str(rec["messages"])


@pytest.mark.asyncio
async def test_a_failed_attempt_records_the_question(wired, captured, monkeypatch):
    """A question nothing could answer is the clearest statement of what to learn."""
    monkeypatch.setenv("OLLAMA_FIRST", "true")
    cap, _ = wired(ollama_fails=True, hosted_fails=True)

    await cap._dispatch("chat", [{"role": "user", "content": "why am I purging?"}],
                        0.2, 64, False, None, False)

    failures = [r for r in captured if r.get("success") is False]
    assert failures, "nothing recorded the failure at all"
    assert any("why am I purging?" in str(r.get("messages")) for r in failures), (
        "a failure was recorded without the question that caused it"
    )


@pytest.mark.asyncio
async def test_every_record_names_its_modality(wired, captured, monkeypatch):
    """The corpus spans modalities, so a row that cannot say which is unusable."""
    monkeypatch.setenv("OLLAMA_FIRST", "true")
    cap, _ = wired()

    await cap._dispatch("chat", [{"role": "user", "content": "hi"}], 0.2, 64, False, None, False)

    rec = _pair(captured)
    assert rec["modality"] == "llm"
