"""Adapter base — all external AI adapters must implement this interface.

Adapters are the ONLY place where external AI services (OpenAI, Anthropic,
Ollama) are called. Every adapter is a drop-in replacement for ALAFIAModel
capabilities until the native models are trained and deployed.

Once ALAFIAModel phase N is complete, the corresponding capability's infer()
stops calling the adapter and calls the native model instead.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseAdapter(ABC):
    """Abstract adapter for external AI services."""

    model_name: str = "unknown"
    is_available: bool = False

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.5,
        max_tokens: int = 2048,
    ) -> dict[str, Any]:
        """Send a chat completion request.

        Returns:
            dict with keys: "content" (str), "model" (str), "tokens_used" (int)
        """

    @abstractmethod
    async def complete(
        self,
        prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 1024,
    ) -> dict[str, Any]:
        """Send a text completion request."""

    async def health_check(self) -> bool:
        """Return True if the adapter endpoint is reachable."""
        return False
