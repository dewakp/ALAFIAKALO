"""Ollama adapter — local LLM via Ollama server.

This is the PRIMARY LLM adapter — it runs on ALAFIA infrastructure (no data
leaves our servers). OpenAI is the cloud fallback only.

Default model: llama3.1:8b or BioMistral:7b (configured via OLLAMA_MODEL env).

TODO(alafia-model): Phase 3 — replace OLLAMA_MODEL default with the fine-tuned
    BioMistral 7B health coaching model once training is complete.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx

from alafia_model.adapters.base_adapter import BaseAdapter

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "http://localhost:11434"
_DEFAULT_MODEL = "llama3.1:8b"


class OllamaAdapter(BaseAdapter):
    """Adapter for Ollama local LLM server."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 120.0,
    ) -> None:
        self.base_url = (
            base_url
            or os.environ.get("OLLAMA_BASE_URL", _DEFAULT_BASE_URL)
        ).rstrip("/")
        self.model_name = (
            model
            or os.environ.get("OLLAMA_MODEL", _DEFAULT_MODEL)
        )
        self.timeout = timeout
        self.is_available = False  # set by health_check()

    async def health_check(self) -> bool:
        """Ping Ollama and verify the configured model is available."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
                if resp.status_code != 200:
                    return False
                tags = resp.json().get("models", [])
                available = any(
                    m.get("name", "").startswith(self.model_name.split(":")[0])
                    for m in tags
                )
                self.is_available = available
                return available
        except Exception:
            self.is_available = False
            return False

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.5,
        max_tokens: int = 2048,
        json_mode: bool = False,
        images: list[str] | None = None,
    ) -> dict[str, Any]:
        # TODO(alafia-model): Phase 3 — swap model_name for fine-tuned BioMistral 7B
        # Ollama multimodal: base64 images attach to a message via its "images" key.
        if images:
            messages = [dict(m) for m in messages]
            last_user = next((m for m in reversed(messages) if m.get("role") == "user"), None)
            if last_user is not None:
                last_user["images"] = images
            else:
                messages.append({"role": "user", "content": "", "images": images})
        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        if json_mode:
            payload["format"] = "json"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(f"{self.base_url}/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()

        content = data.get("message", {}).get("content", "")
        return {
            "content": content,
            "model": self.model_name,
            "tokens_used": data.get("eval_count", 0),
        }

    async def complete(
        self,
        prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 1024,
    ) -> dict[str, Any]:
        # TODO(alafia-model): Phase 3 — swap model_name for fine-tuned BioMistral 7B
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(f"{self.base_url}/api/generate", json=payload)
            resp.raise_for_status()
            data = resp.json()

        return {
            "content": data.get("response", ""),
            "model": self.model_name,
            "tokens_used": data.get("eval_count", 0),
        }
