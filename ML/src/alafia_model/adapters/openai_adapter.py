"""OpenAI adapter — cloud LLM fallback (TEMPORARY).

IMPORTANT: This adapter is a FALLBACK only. All PHI must be de-identified
before any call. See section 3.2 of .github/copilot-instructions.md.

TODO(alafia-model): Phase 3 — remove OpenAI fallback once BioMistral 7B is deployed
    on ALAFIA infrastructure. Track at: ML/src/alafia_model/registry/roadmap.json
"""

from __future__ import annotations

import logging
import os
from typing import Any

import json
import httpx

from alafia_model.adapters.base_adapter import BaseAdapter

logger = logging.getLogger(__name__)

_OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"
_DEFAULT_MODEL = "gpt-4o-mini"


class OpenAIAdapter(BaseAdapter):
    """Adapter for OpenAI API — cloud fallback only.

    WARNING: Do NOT pass raw PHI in messages. De-identify all health data
    before calling this adapter. See data sovereignty constraints in
    .github/copilot-instructions.md §3.2.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        key = api_key or os.environ.get("OPENAI_API_KEY", "")
        if not key:
            logger.warning("OPENAI_API_KEY not set — OpenAI adapter disabled")
        self._api_key = key
        self.model_name = model or os.environ.get("OPENAI_MODEL", _DEFAULT_MODEL)
        self.timeout = timeout
        self.is_available = bool(key)

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.5,
        max_tokens: int = 2048,
    ):
        """Yield text deltas from the OpenAI-style SSE stream.

        Every hosted provider needs this, not just one: `_stream_hosted()` skips
        an adapter that cannot stream, so a provider without it is passed over
        even when it has credit — and the chain falls back to Ollama with money
        still on the table.
        """
        if not self._api_key:
            raise RuntimeError("openai: API key not configured")
        body: dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream("POST", _OPENAI_CHAT_URL, headers=headers, json=body) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    if not raw or raw == "[DONE]":
                        continue
                    try:
                        event = json.loads(raw)
                    except ValueError:
                        continue
                    for choice in event.get("choices", []):
                        text = (choice.get("delta") or {}).get("content")
                        if text:
                            yield text

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
            raise RuntimeError("OpenAI API key not configured")
        # TODO(alafia-model): remove this adapter once ALAFIAModel Phase 3 is live
        body: dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                _OPENAI_CHAT_URL,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()

        content = data["choices"][0]["message"]["content"]
        tokens = data.get("usage", {}).get("total_tokens", 0)
        return {"content": content, "model": self.model_name, "tokens_used": tokens}

    async def complete(
        self,
        prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 1024,
    ) -> dict[str, Any]:
        # OpenAI completion via chat endpoint (legacy /completions is deprecated).
        # complete() is used for structured generation, so request JSON output.
        return await self.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=True,
        )
