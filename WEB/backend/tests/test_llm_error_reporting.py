"""An LLM failure must say what failed.

Production returned this, repeatedly:

    503  {"detail": "The AI meal engine could not complete this request:
          LLM unavailable: all providers failed (last: )"}

The reason was empty. The message is built as `last: {last_error or exc}`, and
httpx timeout exceptions carry an EMPTY str() — so a timeout, the single most
likely failure for a 13 GB model on a cold GPU, rendered as nothing at all.
That sent an operator hunting a downed service while the model was simply
slower than the timeout.

Same rule as CLAUDE.md §3aa's "an error is not an empty state", applied to the
error text itself.
"""

import httpx
import pytest


@pytest.mark.parametrize(
    "exc",
    [
        httpx.ReadTimeout(""),
        httpx.ConnectTimeout(""),
        httpx.PoolTimeout(""),
    ],
)
def test_timeout_exceptions_stringify_to_nothing(exc):
    """The premise. If this ever stops being true the fix is still harmless."""
    assert str(exc) == "", "httpx timeouts used to have an empty str()"


@pytest.mark.parametrize(
    "exc,expected",
    [
        (httpx.ReadTimeout(""), "ReadTimeout"),
        (httpx.ConnectTimeout(""), "ConnectTimeout"),
        (RuntimeError("boom"), "RuntimeError: boom"),
    ],
)
def test_failure_detail_always_names_something(exc, expected):
    """Formatting used by capabilities/llm.py's terminal fallback."""
    detail = f"{type(exc).__name__}: {exc}".rstrip(": ")
    assert detail == expected
    assert detail.strip(), "an LLM error must never be blank"


def test_llm_capability_does_not_emit_an_empty_reason():
    """Guard the actual source, so the f-string cannot regress to `{exc}`."""
    from pathlib import Path
    import alafia_model.capabilities.llm as llm_mod

    src = Path(llm_mod.__file__).read_text()
    assert "all providers failed (last: {last_error or exc})" not in src, (
        "the bare {exc} renders empty for httpx timeouts — use the exception type"
    )
    assert "type(exc).__name__" in src
