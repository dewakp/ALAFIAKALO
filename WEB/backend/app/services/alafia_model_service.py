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

# Ensure the ML/src path is available so we can import ALAFIAModel
_ML_SRC = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "ML", "src")
)
if _ML_SRC not in sys.path:
    sys.path.insert(0, _ML_SRC)

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
