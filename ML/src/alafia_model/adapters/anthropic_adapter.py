"""Anthropic (Claude) adapter — native Messages API.

Anthropic's wire format differs from OpenAI (system is a top-level field, not a
message), so it gets its own adapter rather than the generic OpenAI-compatible
one. Same {content, model, tokens_used} return contract as every other adapter.
"""

from __future__ import annotations

import logging
from typing import Any

import json
import httpx

from alafia_model.adapters.base_adapter import BaseAdapter

logger = logging.getLogger(__name__)

_MESSAGES_URL = "https://api.anthropic.com/v1/messages"


class AnthropicAdapter(BaseAdapter):
    """Adapter for the Anthropic Messages API."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout: float = 60.0,
    ) -> None:
        self._api_key = api_key
        self.model_name = model
        self.timeout = timeout
        self.is_available = bool(api_key)

    async def health_check(self) -> bool:
        return bool(self._api_key)

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.5,
        max_tokens: int = 2048,
        json_mode: bool = False,  # accepted for interface parity; Anthropic has no flag
    ) -> dict[str, Any]:
        if not self._api_key:
            raise RuntimeError("anthropic: API key not configured")
        # Anthropic wants system prompts hoisted out of the message list.
        system = "\n\n".join(
            m.get("content", "") for m in messages if m.get("role") == "system"
        ).strip()
        conversation = [
            {"role": m["role"], "content": m.get("content", "")}
            for m in messages
            if m.get("role") in ("user", "assistant")
        ]
        body: dict[str, Any] = {
            "model": self.model_name,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": conversation,
        }
        if system:
            body["system"] = system
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(_MESSAGES_URL, headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()

        content = "".join(
            block.get("text", "")
            for block in data.get("content", [])
            if block.get("type") == "text"
        )
        usage = data.get("usage") or {}
        tokens = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
        return {"content": content, "model": data.get("model", self.model_name), "tokens_used": tokens}

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.5,
        max_tokens: int = 2048,
    ):
        """Yield text deltas as Anthropic produces them.

        Same request shape as `chat()` with `stream: true`; only the transport
        differs. Kept beside `chat()` deliberately — if the body ever diverges
        (system hoisting, model resolution) the two must diverge together.
        """
        if not self._api_key:
            raise RuntimeError("anthropic: API key not configured")
        system = "\n\n".join(
            m.get("content", "") for m in messages if m.get("role") == "system"
        ).strip()
        conversation = [
            {"role": m["role"], "content": m.get("content", "")}
            for m in messages
            if m.get("role") in ("user", "assistant")
        ]
        body: dict[str, Any] = {
            "model": self.model_name,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": conversation,
            "stream": True,
        }
        if system:
            body["system"] = system
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream("POST", _MESSAGES_URL, headers=headers, json=body) as resp:
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
                    # Only text deltas carry content; the other event types
                    # (message_start, ping, message_stop) are control frames.
                    if event.get("type") == "content_block_delta":
                        text = (event.get("delta") or {}).get("text")
                        if text:
                            yield text

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
        )
