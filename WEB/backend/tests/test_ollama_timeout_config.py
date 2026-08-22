"""The Ollama client must honour OLLAMA_TIMEOUT.

Production sets OLLAMA_TIMEOUT=300 — deploy.sh configures it explicitly — and
the adapter ignored it. `timeout` defaulted to a hardcoded 120.0 and every
construction site calls `OllamaAdapter()` with no timeout, so the real limit
was 120s regardless of configuration.

These prompts legitimately take 98–121s against gpt-oss:20b, so requests died
just past the boundary and reported `ReadTimeout` on a model that was still
working. A config value that is set, documented, and silently ignored is worse
than one that was never offered.
"""

import pytest

from alafia_model.adapters.ollama_adapter import OllamaAdapter


def test_timeout_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("OLLAMA_TIMEOUT", "300")
    assert OllamaAdapter().timeout == 300.0


def test_default_is_not_the_old_hardcoded_120(monkeypatch):
    """120s sat below the observed 98–121s range, so the default itself was
    the bug for anyone who had not set the variable."""
    monkeypatch.delenv("OLLAMA_TIMEOUT", raising=False)
    assert OllamaAdapter().timeout >= 300.0


def test_explicit_argument_still_wins(monkeypatch):
    monkeypatch.setenv("OLLAMA_TIMEOUT", "300")
    assert OllamaAdapter(timeout=42.0).timeout == 42.0


@pytest.mark.parametrize("bad", ["", "abc", "0", "-5"])
def test_unusable_values_fall_back_rather_than_crash(monkeypatch, bad):
    # A malformed env var must not take the LLM path down at import time.
    monkeypatch.setenv("OLLAMA_TIMEOUT", bad)
    assert OllamaAdapter().timeout >= 300.0


def test_timeout_does_not_exceed_cloud_run_request_limit(monkeypatch):
    """Waiting longer than the platform allows just swaps one error for a worse
    one: Cloud Run cuts the request at 300s regardless."""
    monkeypatch.delenv("OLLAMA_TIMEOUT", raising=False)
    assert OllamaAdapter().timeout <= 300.0


def test_base_url_and_model_still_read_their_environment(monkeypatch):
    # These already worked; the timeout was the odd one out. Guard the pattern.
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://example.test:11434/")
    monkeypatch.setenv("OLLAMA_MODEL", "some-model")
    a = OllamaAdapter()
    assert a.base_url == "http://example.test:11434"
    assert a.model_name == "some-model"
