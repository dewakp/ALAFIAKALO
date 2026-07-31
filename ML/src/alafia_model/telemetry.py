"""LLM call telemetry — the substrate for the ALAFIA model ("so we learn").

Every provider attempt (success or failure) is recorded. By DEFAULT only
metadata is logged (provider, model, latency, tokens, outcome) — never prompts
or responses, which are health-sensitive. To capture the full
(messages → response) training corpus, the backend registers a sink via
``register_sink`` that persists rows to a consent-gated store (respecting the
user's ai_training_consent). That corpus is what a future fine-tuned ALAFIA
model distills from.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

logger = logging.getLogger("alafia_model.telemetry")

# Full-record sinks (backend registers a DB/BigQuery writer). Metadata is always
# logged; the raw messages/response go ONLY to sinks, never to the app log.
_sinks: list[Callable[[dict[str, Any]], None]] = []

_META_KEYS = ("provider", "model", "task", "tier", "latency_ms", "tokens", "success", "error")


def register_sink(fn: Callable[[dict[str, Any]], None]) -> None:
    """Register a full-record consumer (e.g. persist to the training corpus)."""
    _sinks.append(fn)


def clear_sinks() -> None:
    _sinks.clear()


def record(**fields: Any) -> None:
    """Log one provider attempt. `messages`/`response` (if present) are passed to
    sinks only; the app log gets metadata."""
    meta = {k: fields.get(k) for k in _META_KEYS if fields.get(k) is not None}
    logger.info("llm_call %s", json.dumps(meta, default=str))
    if not _sinks:
        return
    for fn in _sinks:
        try:
            fn(dict(fields))
        except Exception:  # a bad sink must never break inference
            logger.debug("telemetry sink error", exc_info=True)
