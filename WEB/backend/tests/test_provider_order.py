"""Dev and production want OPPOSITE provider orders.

Dev prefers Ollama: free, never rate-limited, no user content leaving our
infrastructure, and it is the provider production ultimately runs. Production
prefers the hosted pool, because ITS Ollama is Cloud Run with `minScale` unset —
a cold call pays a ~77 s model load on top of generation, about 250 s all in
(canon 5). That cost is right for a fallback and wrong for a front door.

Picking one order globally is wrong in whichever half it is not, so the order is
per-environment. Dev additionally makes Ollama REQUIRED: when it is down the
dispatch fails loudly instead of quietly borrowing a hosted provider — a silent
fallback is how the AI tier stayed unproven locally while every AI change was
verified against production instead.
"""

import pytest

from alafia_model.capabilities.llm import LLMCapability
from alafia_model.registry.providers import ProviderSpec


class _Adapter:
    """Stands in for an Ollama or hosted adapter, recording that it was called."""

    def __init__(self, name, calls, fail=False):
        self.name, self.calls, self.fail = name, calls, fail
        self.model_name = f"{name}-model"

    async def chat(self, *a, **k):
        self.calls.append(self.name)
        if self.fail:
            raise RuntimeError(f"{self.name} is down")
        return {"content": f"hello from {self.name}", "tokens_used": 7, "model": self.model_name}

    complete = chat


@pytest.fixture
def wired(monkeypatch):
    """An LLMCapability with one hosted provider and one Ollama, both fakeable."""
    calls: list[str] = []

    def _build(ollama_fails=False, hosted_fails=False):
        cap = LLMCapability.__new__(LLMCapability)
        spec = ProviderSpec("groq", "https://x/v1", "GROQ_API_KEY", "m", "free", 1.0)
        monkeypatch.setattr("alafia_model.registry.providers.ordered_for_selection",
                            lambda: [spec])
        monkeypatch.setattr(cap, "_get_adapter",
                            lambda model=None: _Adapter("ollama", calls, ollama_fails),
                            raising=False)
        monkeypatch.setattr(cap, "_adapter_for",
                            lambda s: _Adapter("hosted", calls, hosted_fails),
                            raising=False)
        return cap, calls

    return _build


async def _dispatch(cap):
    return await cap._dispatch("chat", [{"role": "user", "content": "hi"}], 0.2, 64, False)


@pytest.mark.asyncio
async def test_dev_tries_ollama_first(wired, monkeypatch):
    monkeypatch.setenv("OLLAMA_FIRST", "true")
    cap, calls = wired()
    result = await _dispatch(cap)
    assert result.success
    assert result.data["provider"] == "ollama"
    assert calls == ["ollama"], "a hosted provider must not be touched when Ollama answers"


@pytest.mark.asyncio
async def test_production_tries_hosted_first(wired, monkeypatch):
    """Default (no env set) is production's order — the ~250 s cold start stays a fallback."""
    monkeypatch.delenv("OLLAMA_FIRST", raising=False)
    monkeypatch.delenv("OLLAMA_REQUIRED", raising=False)
    cap, calls = wired()
    result = await _dispatch(cap)
    assert result.success
    assert result.data["provider"] == "groq"
    assert calls == ["hosted"], "Ollama must stay the terminal fallback in production"


@pytest.mark.asyncio
async def test_production_still_falls_back_to_ollama(wired, monkeypatch):
    monkeypatch.delenv("OLLAMA_FIRST", raising=False)
    cap, calls = wired(hosted_fails=True)
    result = await _dispatch(cap)
    assert result.success
    assert result.data["provider"] == "ollama"
    assert calls == ["hosted", "ollama"]


@pytest.mark.asyncio
async def test_dev_fails_loudly_when_ollama_is_down(wired, monkeypatch):
    """The whole point: no silent hosted stand-in."""
    monkeypatch.setenv("OLLAMA_FIRST", "true")
    monkeypatch.setenv("OLLAMA_REQUIRED", "true")
    cap, calls = wired(ollama_fails=True)
    result = await _dispatch(cap)
    assert result.success is False
    assert "Ollama is required" in result.error
    assert "ollama serve" in result.error, "the error must say how to fix it"
    assert calls == ["ollama"], "no hosted provider may stand in for a required Ollama"


@pytest.mark.asyncio
async def test_ollama_first_without_required_still_falls_back(wired, monkeypatch):
    monkeypatch.setenv("OLLAMA_FIRST", "true")
    monkeypatch.setenv("OLLAMA_REQUIRED", "false")
    cap, calls = wired(ollama_fails=True)
    result = await _dispatch(cap)
    assert result.success
    assert result.data["provider"] == "groq"
    assert calls == ["ollama", "hosted"]


@pytest.mark.asyncio
async def test_a_total_failure_names_the_exception_type(wired, monkeypatch):
    """An empty str(exc) once rendered as "all providers failed (last: )"."""
    monkeypatch.delenv("OLLAMA_FIRST", raising=False)
    cap, _ = wired(ollama_fails=True, hosted_fails=True)
    result = await _dispatch(cap)
    assert result.success is False
    assert result.error.strip().endswith(")")
    assert "last: )" not in result.error, "the error must never be blank"
