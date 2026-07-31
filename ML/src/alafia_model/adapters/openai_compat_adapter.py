"""Generic OpenAI-compatible chat adapter.

Most hosted LLM providers (Gemini via its OpenAI endpoint, Groq, Cerebras,
SambaNova, Mistral, DeepSeek, Moonshot/Kimi, OpenRouter, GitHub Models, NVIDIA
NIM, Together, Fireworks, DeepInfra, xAI, Qwen, Zhipu, OpenAI itself, …) expose
the same ``POST {base_url}/chat/completions`` shape with a Bearer key. One
parameterized adapter serves all of them — adding a provider is a registry row,
not new code. See ``alafia_model/registry/providers.py``.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from alafia_model.adapters.base_adapter import BaseAdapter

logger = logging.getLogger(__name__)


class OpenAICompatAdapter(BaseAdapter):
    """Adapter for any OpenAI-compatible /chat/completions endpoint."""

    def __init__(
        self,
        *,
        provider: str,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 60.0,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self.provider = provider
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self.model_name = model
        self.timeout = timeout
        self.extra_headers = extra_headers or {}
        self.is_available = bool(api_key)

    async def health_check(self) -> bool:
        return bool(self._api_key)

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.5,
        max_tokens: int = 2048,
        json_mode: bool = False,
    ) -> dict[str, Any]:
        if not self._api_key:
            raise RuntimeError(f"{self.provider}: API key not configured")
        body: dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            **self.extra_headers,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions", headers=headers, json=body
            )
            resp.raise_for_status()
            data = resp.json()

        choice = (data.get("choices") or [{}])[0]
        content = (choice.get("message") or {}).get("content", "") or ""
        tokens = (data.get("usage") or {}).get("total_tokens", 0)
        return {"content": content, "model": data.get("model", self.model_name), "tokens_used": tokens}

    async def complete(
        self,
        prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 1024,
    ) -> dict[str, Any]:
        return await self.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=True,
        )
