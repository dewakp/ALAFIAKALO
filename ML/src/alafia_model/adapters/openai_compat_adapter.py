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

import json
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
            raise RuntimeError("openai-compat: API key not configured")
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
            **self.extra_headers,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream("POST", f"{self.base_url}/chat/completions", headers=headers, json=body) as resp:
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
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if not self._api_key:
            raise RuntimeError(f"{self.provider}: API key not configured")
        # Translate the internal assistant tool-call turn into OpenAI's shape.
        # Without this, the SECOND round of any tool conversation is a 400 and
        # the model never sees the call it just made.
        from alafia_model.adapters.tool_protocol import to_openai_messages
        body: dict[str, Any] = {
            "model": self.model_name,
            "messages": to_openai_messages(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        if tools:
            # This adapter serves EIGHTEEN of the twenty registry providers, so
            # tool support here is most of the fleet — not an add-on for one.
            from alafia_model.adapters.tool_protocol import to_openai_tools
            body["tools"] = to_openai_tools(tools)
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
        message = choice.get("message") or {}
        content = message.get("content", "") or ""
        from alafia_model.adapters.tool_protocol import parse_openai_tool_calls
        tool_calls = parse_openai_tool_calls(message)
        tokens = (data.get("usage") or {}).get("total_tokens", 0)
        # `tool_calls` was parsed and then dropped from this dict, so the tool
        # loop saw prose and answered from framing context alone — a confident
        # answer with none of the record in it, on 18 of the 20 providers.
        return {"content": content, "tool_calls": tool_calls,
                "model": data.get("model", self.model_name), "tokens_used": tokens}

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
