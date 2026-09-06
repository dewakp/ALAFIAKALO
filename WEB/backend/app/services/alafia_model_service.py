"""ALAFIAModel service bridge — makes ALAFIAModel available inside the FastAPI backend.

This module provides:
  - ``get_alafia_model()`` — singleton accessor for use in route handlers
  - ``alafia_infer()`` — convenience async wrapper

All AI calls in the backend that are destined to become ALAFIAModel calls
should route through this service. This keeps the migration path clean:
once a capability goes native in ALAFIAModel, only this service file changes.

TODO(alafia-model): Phase 3 — update LLM capability to use fine-tuned BioMistral 7B
TODO(alafia-model): Phase 5 — update Vision capability to use MobileNetV3 food classifier
"""

import logging
import sys
import os
from typing import Any

logger = logging.getLogger(__name__)

# Make the ALAFIAModel package importable in every environment:
#   - dev checkout: it lives at <repo>/ML/src/alafia_model
#   - prod image:   deploy.sh vendors it to <backend root>/alafia_model
# Add both candidate roots to sys.path (a missing one is harmless).
_ML_SRC = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "ML", "src")
)
_BACKEND_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
for _p in (_ML_SRC, _BACKEND_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

_model_instance = None


def get_alafia_model():
    """Return the module-level ALAFIAModel singleton.

    Lazy-initialises on first call. Safe to call from async route handlers.
    """
    global _model_instance
    if _model_instance is None:
        try:
            from alafia_model.router import ALAFIAModel  # type: ignore
            _model_instance = ALAFIAModel()
            logger.info("ALAFIAModel singleton initialised: %s", _model_instance.status())
        except ImportError as exc:
            logger.warning(
                "ALAFIAModel package not importable (%s). "
                "Ensure ML/src is in PYTHONPATH. Falling back to None.",
                exc,
            )
    return _model_instance


async def alafia_infer(
    modality: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Run inference via ALAFIAModel and return a plain dict result.

    Args:
        modality: One of "nlm", "llm", "vision", "voice", "video"
        payload:  Modality-specific payload dict matching InferencePayload fields.

    Returns:
        dict with keys: success, data, confidence, source, latency_ms, error
    """
    model = get_alafia_model()
    if model is None:
        return {
            "success": False,
            "data": {},
            "confidence": 0.0,
            "source": None,
            "latency_ms": 0.0,
            "error": "ALAFIAModel not available in this environment",
        }

    from alafia_model.router import Modality, InferencePayload  # type: ignore

    try:
        mod = Modality(modality)
    except ValueError:
        return {
            "success": False,
            "data": {},
            "confidence": 0.0,
            "source": None,
            "latency_ms": 0.0,
            "error": f"Unknown modality: {modality}. Valid: nlm, llm, vision, voice, video",
        }

    inf_payload = InferencePayload(**{k: v for k, v in payload.items() if v is not None})
    result = await model.infer(mod, inf_payload)
    return {
        "success": result.success,
        "data": result.data,
        "confidence": result.confidence,
        "source": result.source,
        "latency_ms": result.latency_ms,
        "error": result.error,
    }


class ALAFIAModelError(RuntimeError):
    """Raised when an ALAFIAModel LLM call fails (so callers can catch/handle)."""


async def alafia_chat(
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.7,
    max_tokens: int = 2048,
    json_mode: bool = False,
    task: str = "chat",
    model: str | None = None,
    context: dict[str, Any] | None = None,
) -> str:
    """Route a chat completion through ALAFIAModel's LLM capability and return text.

    This is the single entry point backend services should use instead of calling
    a provider directly.

    Order (see capabilities/llm.py): the hosted provider pool FIRST — free tier
    shuffled by weight, then paid — with self-hosted Ollama as the TERMINAL
    fallback. This docstring used to claim the reverse ("Ollama → OpenAI"), which
    is wrong and actively misleading: with no provider keys configured the hosted
    pool is empty, so every call went straight to Ollama and looked Ollama-first.
    That is a configuration state, not the routing policy.

    Args:
        model: optional per-call model override for the Ollama fallback adapter.

    Raises:
        ALAFIAModelError: if the model is unavailable or the call fails.
    """
    result = await alafia_infer(
        "llm",
        {
            "messages": messages,
            "task": task,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "json_mode": json_mode,
            "model": model or "",
            "context": context or {},
        },
    )
    if not result.get("success"):
        raise ALAFIAModelError(result.get("error") or "ALAFIAModel LLM call failed")
    return (result.get("data") or {}).get("text", "")


async def stream_alafia_chat(
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.7,
    max_tokens: int = 2048,
    model: str | None = None,
    identity_hints: tuple = (),
):
    """Stream a chat completion through ALAFIAModel, yielding text chunks.

    The streaming twin of `alafia_chat`, and it exists for the same reason: so
    that no backend code talks to a provider directly. `/ai/chat/stream` used to,
    which meant token streaming was the single LLM path that never passed
    `privacy.scrub_payload` and could never reach a hosted provider.

    Same order as the non-streaming path — hosted pool first, Ollama as the
    terminal fallback when a provider is unreachable or out of credit.

    Raises:
        ALAFIAModelError: if no provider could produce a stream.
    """
    from alafia_model.router import Modality  # type: ignore

    model_obj = get_alafia_model()
    capability = model_obj._capabilities.get(Modality.LLM)
    streamer = getattr(capability, "stream_chat", None)
    if streamer is None:
        raise ALAFIAModelError("ALAFIAModel LLM capability does not support streaming")

    try:
        async for chunk in streamer(
            messages,
            identity_hints=identity_hints,
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            yield chunk
    except Exception as exc:  # noqa: BLE001 - surfaced to the caller, named
        raise ALAFIAModelError(f"{type(exc).__name__}: {exc}".rstrip(": ")) from exc


async def stream_alafia_events(
    messages: list[dict[str, str]],
    *,
    tools: list[dict] | None = None,
    temperature: float = 0.7,
    max_tokens: int = 2048,
    identity_hints: tuple = (),
):
    """Stream events — text as it is written, plus any tool calls made.

    The tool loop cannot know in advance whether a round will fetch data or
    answer, so it streams every round and finds out. Without this the final
    round was generated whole before the patient saw a character of it.

    Goes through the capability for the same reason as `stream_alafia_chat`:
    the provider order and `privacy.scrub_payload` live there, and a caller
    that has to remember to scrub is a caller that eventually forgets (§3al).
    """
    from alafia_model.router import Modality  # type: ignore

    model_obj = get_alafia_model()
    capability = model_obj._capabilities.get(Modality.LLM)
    streamer = getattr(capability, "stream_events", None)
    if streamer is None:
        raise ALAFIAModelError("ALAFIAModel LLM capability cannot stream events")

    try:
        async for event in streamer(
            messages,
            tools=tools,
            identity_hints=identity_hints,
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            yield event
    except Exception as exc:  # noqa: BLE001 - surfaced to the caller, named
        raise ALAFIAModelError(f"{type(exc).__name__}: {exc}".rstrip(": ")) from exc


async def alafia_chat_detailed(
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.7,
    max_tokens: int = 2048,
    json_mode: bool = False,
    task: str = "chat",
    model: str | None = None,
    context: dict[str, Any] | None = None,
    tools: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Same as `alafia_chat`, but returns the accounting alongside the text.

    `alafia_chat` returns only a string, which is why per-user token usage was
    never recorded — the count reached telemetry and was then thrown away. Use
    this at any call site that persists an AIInteraction.

    Returns: {"text", "tokens_used", "model", "provider", "source"}
    """
    result = await alafia_infer(
        "llm",
        {
            "messages": messages,
            "task": task,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "json_mode": json_mode,
            "model": model or "",
            "context": context or {},
            # In alafia_chat_detailed's OWN payload. An earlier edit put this in
            # alafia_chat by matching the first occurrence, so this function
            # accepted `tools`, never forwarded them, and the model answered
            # "I don't have access to your food data" while holding five tools.
            "tools": tools or None,
        },
    )
    if not result.get("success"):
        raise ALAFIAModelError(result.get("error") or "ALAFIAModel LLM call failed")
    data = result.get("data") or {}
    return {
        "text": data.get("text", ""),
        # The model asking for data is a normal outcome, not an empty answer.
        "tool_calls": data.get("tool_calls") or [],
        "tokens_used": int(data.get("tokens_used") or 0),
        "model": data.get("model") or "",
        "provider": data.get("provider") or "",
        "source": result.get("source") or "",
    }


async def alafia_complete(
    prompt: str,
    *,
    temperature: float = 0.3,
    max_tokens: int = 1024,
) -> str:
    """Route a single-prompt (JSON) completion through ALAFIAModel. Returns text.

    Raises:
        ALAFIAModelError: if the model is unavailable or the call fails.
    """
    result = await alafia_infer(
        "llm",
        {"text": prompt, "task": "complete", "temperature": temperature, "max_tokens": max_tokens},
    )
    if not result.get("success"):
        raise ALAFIAModelError(result.get("error") or "ALAFIAModel LLM completion failed")
    return (result.get("data") or {}).get("text", "")
