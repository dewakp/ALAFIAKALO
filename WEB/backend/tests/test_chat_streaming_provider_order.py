"""Streaming chat must exhaust paid providers before falling back to Ollama.

`/ai/chat/stream` used to POST straight to Ollama. That single shortcut meant:

  * a hosted provider was never used, so APP_REVIEW_RESPONSE.md telling Apple
    "currently Anthropic … our own servers as fallback" was inverted for the
    app's main AI surface;
  * answers came from a 20B local model, which invented a potassium limit ~10x
    too strict and told a dialysis patient to drop a staple food; and
  * the payload never passed `privacy.scrub_payload`, the one egress point where
    a patient stops being a name and becomes `subject_token()`.

These pin the order and the redaction, not the wording of any model's reply.
"""

import pytest


def _capability():
    from app.services.alafia_model_service import get_alafia_model
    get_alafia_model()                      # puts ALAFIAModel on sys.path
    from alafia_model.capabilities.llm import LLMCapability
    return LLMCapability()


class _Spec:
    def __init__(self, name):
        self.name, self.tier, self.kind = name, "paid", "openai"


class _Adapter:
    """A stand-in provider. `chunks=None` means it raises instead of streaming."""

    def __init__(self, chunks, seen):
        self._chunks, self._seen = chunks, seen

    async def stream_chat(self, messages, temperature=0.5, max_tokens=2048):
        self._seen.append(messages)
        if self._chunks is None:
            raise RuntimeError("provider is out of credit")
        for c in self._chunks:
            yield c


@pytest.mark.asyncio
async def test_a_paid_provider_is_used_before_ollama(monkeypatch):
    cap = _capability()
    seen = []
    monkeypatch.setattr(cap, "_adapter_for", lambda spec: _Adapter(["from-", "hosted"], seen))
    monkeypatch.setattr(
        cap, "_get_adapter",
        lambda *a, **k: pytest.fail("Ollama was used while a hosted provider was available"),
    )
    import alafia_model.registry.providers as reg
    monkeypatch.setattr(reg, "ordered_for_selection", lambda: [_Spec("anthropic")])

    out = [t async for t in cap.stream_chat([{"role": "user", "content": "hi"}])]
    assert "".join(out) == "from-hosted"


@pytest.mark.asyncio
async def test_it_tries_the_NEXT_paid_provider_before_ollama(monkeypatch):
    """One provider out of credit must not send the whole chain to Ollama."""
    cap = _capability()
    seen = []
    adapters = {
        "broke": _Adapter(None, seen),                 # raises
        "funded": _Adapter(["second-", "provider"], seen),
    }
    monkeypatch.setattr(cap, "_adapter_for", lambda spec: adapters[spec.name])
    monkeypatch.setattr(
        cap, "_get_adapter",
        lambda *a, **k: pytest.fail("fell back to Ollama while a funded provider remained"),
    )
    import alafia_model.registry.providers as reg
    monkeypatch.setattr(reg, "ordered_for_selection", lambda: [_Spec("broke"), _Spec("funded")])
    monkeypatch.setattr(reg, "mark_cooldown", lambda *_a, **_k: None)

    out = [t async for t in cap.stream_chat([{"role": "user", "content": "hi"}])]
    assert "".join(out) == "second-provider"


@pytest.mark.asyncio
async def test_ollama_is_the_terminal_fallback(monkeypatch):
    """When every hosted provider fails, the answer still comes — from Ollama."""
    cap = _capability()
    seen = []
    monkeypatch.setattr(cap, "_adapter_for", lambda spec: _Adapter(None, seen))
    monkeypatch.setattr(cap, "_get_adapter", lambda *a, **k: _Adapter(["local"], seen))
    import alafia_model.registry.providers as reg
    monkeypatch.setattr(reg, "ordered_for_selection", lambda: [_Spec("broke")])
    monkeypatch.setattr(reg, "mark_cooldown", lambda *_a, **_k: None)

    out = [t async for t in cap.stream_chat([{"role": "user", "content": "hi"}])]
    assert "".join(out) == "local"


@pytest.mark.asyncio
async def test_the_payload_is_redacted_before_it_reaches_a_hosted_provider(monkeypatch):
    """The regression that matters most: a name must not leave with the request."""
    cap = _capability()
    seen = []
    monkeypatch.setattr(cap, "_adapter_for", lambda spec: _Adapter(["ok"], seen))
    import alafia_model.registry.providers as reg
    monkeypatch.setattr(reg, "ordered_for_selection", lambda: [_Spec("anthropic")])

    messages = [{"role": "user", "content": "I'm Wole Akpose, dob 1974-03-15, is plantain ok?"}]
    _ = [t async for t in cap.stream_chat(messages, identity_hints=("Wole Akpose",))]

    sent = str(seen[0])
    assert "Wole" not in sent, f"the patient's name reached the provider: {sent}"
    assert "1974-03-15" not in sent, f"the date of birth reached the provider: {sent}"
    assert "[name]" in sent and "[dob]" in sent, sent


def test_every_enabled_provider_can_stream():
    """A provider that cannot stream is silently skipped — and the chain falls to
    Ollama with credit still unspent. Adding a provider must mean adding this."""
    cap = _capability()
    from alafia_model.registry.providers import enabled_providers

    missing = [
        s.name for s in enabled_providers()
        if not hasattr(cap._adapter_for(s), "stream_chat")
    ]
    assert not missing, f"these providers cannot stream and will be skipped: {missing}"
