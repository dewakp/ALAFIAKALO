"""ALAFIAModel Unified Router — single entry point for all AI inference.

This is the Phase 9 target interface. All ALAFIA AI calls will eventually
route through here so that swapping the underlying model only requires
updating the capability class, not every call site.

Usage::

    from alafia_model.router import ALAFIAModel, Modality, InferencePayload

    model = ALAFIAModel()

    # NLM: parse a meal description
    result = await model.infer(
        Modality.NLM,
        InferencePayload(text="1.5 cup beef suya, garri", task="parse_meal")
    )

    # LLM: health coaching
    result = await model.infer(
        Modality.LLM,
        InferencePayload(
            messages=[{"role": "user", "content": "What should I eat to lower potassium?"}],
            task="health_chat",
            context={"user_profile": "..."}
        )
    )
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from alafia_model.capabilities.nlm import NLMCapability
from alafia_model.capabilities.llm import LLMCapability
from alafia_model.capabilities.vision import VisionCapability
from alafia_model.capabilities.voice import VoiceCapability
from alafia_model.capabilities.video import VideoCapability
from alafia_model.capabilities.base import CapabilityResult

logger = logging.getLogger(__name__)


class Modality(str, Enum):
    """Input modalities supported by ALAFIAModel."""

    NLM = "nlm"       # Natural Language → structured health data
    LLM = "llm"       # Language model reasoning / chat
    VISION = "vision" # Image / photo understanding
    VOICE = "voice"   # Speech / audio → text + NLP
    VIDEO = "video"   # Video → motion / form analysis


@dataclass
class InferencePayload:
    """Unified payload for all modalities.

    Only the fields relevant to the chosen modality need to be set.
    """

    # Text / chat fields
    text: str = ""
    messages: list[dict[str, str]] = field(default_factory=list)
    task: str = ""
    context: dict[str, Any] = field(default_factory=dict)

    # Media fields
    image_bytes: bytes | None = None
    audio_bytes: bytes | None = None
    video_bytes: bytes | None = None
    content_type: str = ""  # MIME type hint for media payloads (e.g. "image/jpeg")

    # Multi-image input: several shots of the SAME subject (e.g. a plate from
    # two angles), analysed in ONE model call so the result is a single combined
    # reading rather than N independent ones. Each entry is
    # {"image_bytes": bytes, "content_type": str}. When set, it supersedes the
    # single `image_bytes` field above; that field stays for single-shot callers.
    images: list[dict[str, Any]] = field(default_factory=list)

    # Options
    language: str = "en"
    temperature: float = 0.5
    max_tokens: int = 2048
    json_mode: bool = False  # request a strict JSON response from the model
    model: str = ""          # optional per-call model override (primary adapter)
    #: Tool/function definitions the model may call, in the internal shape
    #: {name, description, input_schema}. Passing them also narrows the provider
    #: chain to those that accept tools — see `ordered_for_selection`.
    tools: list[dict[str, Any]] | None = None
    #: Force ALAFIA-operated inference with no hosted fallback. Used by the
    #: question router, which decides whether data may leave and therefore must
    #: not itself be a hosted call.
    local_only: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "messages": self.messages,
            "task": self.task,
            "context": self.context,
            "image_bytes": self.image_bytes,
            "images": self.images,
            "audio_bytes": self.audio_bytes,
            "video_bytes": self.video_bytes,
            "content_type": self.content_type,
            "language": self.language,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "json_mode": self.json_mode,
            "tools": self.tools,
            "local_only": self.local_only,
            "model": self.model,
        }


@dataclass
class InferenceResult:
    """Unified result from ALAFIAModel.infer()."""

    modality: Modality
    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    source: str = ""
    latency_ms: float = 0.0
    error: str | None = None

    @classmethod
    def from_capability_result(
        cls, modality: Modality, result: CapabilityResult
    ) -> "InferenceResult":
        return cls(
            modality=modality,
            success=result.success,
            data=result.data,
            confidence=result.confidence,
            source=result.source,
            latency_ms=result.latency_ms,
            error=result.error,
        )


class ALAFIAModel:
    """Unified multimodal health AI model.

    Routes inference requests to the appropriate capability module.
    Acts as the single dependency injection point — swap a capability
    class without changing any caller code.

    Implementation status:
        NLM    — Phase 1 live (meal parser)
        LLM    — adapter delegation (Ollama → OpenAI fallback)
        VISION — Phase 5 planned
        VOICE  — Phase 7 planned
        VIDEO  — Phase 8 planned
    """

    def __init__(self) -> None:
        self._capabilities: dict[Modality, Any] = {
            Modality.NLM: NLMCapability(),
            Modality.LLM: LLMCapability(),
            Modality.VISION: VisionCapability(),
            Modality.VOICE: VoiceCapability(),
            Modality.VIDEO: VideoCapability(),
        }

    async def infer(
        self,
        modality: Modality,
        payload: InferencePayload,
    ) -> InferenceResult:
        """Route an inference request to the correct capability.

        Args:
            modality: The input modality (NLM, LLM, VISION, VOICE, VIDEO).
            payload:  Modality-specific InferencePayload.

        Returns:
            InferenceResult with success/data/confidence/source/error fields.
        """
        import time

        capability = self._capabilities.get(modality)
        if capability is None:
            return InferenceResult(
                modality=modality,
                success=False,
                error=f"Unsupported modality: {modality}",
            )

        t0 = time.monotonic()
        try:
            result: CapabilityResult = await capability.infer(payload.to_dict())
        except Exception as exc:
            logger.error(
                "ALAFIAModel.infer(%s) raised: %s", modality, exc, exc_info=True
            )
            result = CapabilityResult(success=False, error=str(exc))

        latency_ms = round((time.monotonic() - t0) * 1000, 1)

        inference_result = InferenceResult.from_capability_result(modality, result)
        inference_result.latency_ms = latency_ms

        logger.info(
            "ALAFIAModel.infer(%s, task=%s) → success=%s latency=%.0fms source=%s",
            modality,
            payload.task,
            inference_result.success,
            latency_ms,
            inference_result.source or "N/A",
        )
        return inference_result

    def status(self) -> dict[str, dict]:
        """Return implementation status for all capabilities."""
        return {
            modality.value: {
                "class": cap.__class__.__name__,
                "version": cap.version,
                "is_implemented": cap.is_implemented,
                "available": cap.is_available(),
            }
            for modality, cap in self._capabilities.items()
        }
