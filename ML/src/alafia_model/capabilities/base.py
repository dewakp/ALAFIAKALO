"""Base capability interface for ALAFIAModel capabilities.

Every capability (NLM, LLM, Vision, Voice, Video) must inherit from
``BaseCapability`` and implement ``infer()``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CapabilityResult:
    """Standardised output from any ALAFIAModel capability."""

    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    source: str = ""          # e.g. "alafia-model-v1", "openai-gpt4o-mini-fallback"
    latency_ms: float = 0.0
    error: str | None = None


class BaseCapability(ABC):
    """Abstract base for all ALAFIAModel capabilities."""

    capability_id: str = "base"
    version: str = "0.0.0"
    is_implemented: bool = False   # Set to True when the capability has a real model

    @abstractmethod
    async def infer(self, payload: dict[str, Any]) -> CapabilityResult:
        """Run inference for this capability.

        Args:
            payload: Modality-specific input dictionary.
                     NLM:   {"text": str, "task": str}
                     LLM:   {"messages": list, "context": dict}
                     Vision:{"image_bytes": bytes, "task": str}
                     Voice: {"audio_bytes": bytes, "language": str}
                     Video: {"video_bytes": bytes, "task": str}

        Returns:
            CapabilityResult with data dict containing modality-specific output.
        """

    def is_available(self) -> bool:
        """Return True when this capability has a real model loaded."""
        return self.is_implemented

    def __repr__(self) -> str:
        status = "ready" if self.is_available() else "scaffold-only"
        return f"<{self.__class__.__name__} v{self.version} [{status}]>"
