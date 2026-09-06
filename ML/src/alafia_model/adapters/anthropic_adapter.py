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


def anthropic_headers(api_key: str, *, json_content: bool = False) -> dict[str, str]:
    """The headers EVERY Anthropic call needs — one builder, three call sites.

    Chat, streaming and model discovery each used to build these independently,
    so a change to one could silently miss the others.
    """
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }
    if json_content:
        headers["content-type"] = "application/json"
    return headers


def _anthropic_conversation(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Messages in Anthropic's shape, tool turns included.

    Shared by `chat()` and the streaming path ON PURPOSE. The streamer used to
    build its own with a flat comprehension over user/assistant roles, which
    dropped every `role="tool"` message — the identical bug `chat()` had, still
    live on the path the product actually uses. One builder, one behaviour.
    """
    conversation: list[dict[str, Any]] = []
    for m in messages:
        role = m.get("role")
        if role == "assistant" and m.get("tool_calls"):
            conversation.append({"role": "assistant", "content": [
                {"type": "tool_use", "id": c["id"], "name": c["name"],
                 "input": c.get("arguments") or {}}
                for c in m["tool_calls"]
            ]})
        elif role == "tool":
            # Anthropic carries tool results on a USER turn, and consecutive
            # results belong to the same turn.
            block = {"type": "tool_result",
                     "tool_use_id": m.get("tool_call_id") or m.get("id", ""),
                     "content": m.get("content", "")}
            if (conversation and conversation[-1]["role"] == "user"
                    and isinstance(conversation[-1].get("content"), list)):
                conversation[-1]["content"].append(block)
            else:
                conversation.append({"role": "user", "content": [block]})
        elif role in ("user", "assistant"):
            conversation.append({"role": role, "content": m.get("content", "")})
    return conversation


def _name_config_error(exc: httpx.HTTPStatusError) -> None:
    """Turn Anthropic's workspace-id 400 into a message that names the fix.

    Canon: an error is not an empty state. A bare 400 here sends the pool to the
    next provider and the real cause — an unset env var — never surfaces.
    """
    if exc.response.status_code != 400:
        return
    try:
        message = (exc.response.json().get("error") or {}).get("message", "")
    except ValueError:
        return
    if "anthropic-workspace-id" in message:
        raise RuntimeError(
            "anthropic: this API key is identity-linked (a Personal key scoped to "
            "'All workspaces'), so every request is refused. Issue a key whose "
            "Scope is a single workspace instead — those carry the workspace "
            "implicitly and need no extra header."
        ) from exc


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
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if not self._api_key:
            raise RuntimeError("anthropic: API key not configured")
        # Anthropic wants system prompts hoisted out of the message list.
        system = "\n\n".join(
            m.get("content", "") for m in messages if m.get("role") == "system"
        ).strip()
        # Tool turns must survive the hoist. The plain version of this dropped
        # every {"role": "tool"} message and flattened the assistant turn to a
        # string, so the model's tool RESULTS never came back to it: it called
        # get_meals, received nothing it could see, called again, and finally
        # answered "I don't have access to your food data" while holding three
        # successful results.
        conversation = _anthropic_conversation(messages)

        body: dict[str, Any] = {
            "model": self.model_name,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": conversation,
        }
        if system:
            body["system"] = system
        if tools:
            # Anthropic's native shape IS the internal one — {name, description,
            # input_schema} — so no translation is needed here. The other 18
            # providers translate to OpenAI's `function` wrapper instead.
            body["tools"] = tools
        headers = anthropic_headers(self._api_key, json_content=True)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(_MESSAGES_URL, headers=headers, json=body)
            try:
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                _name_config_error(exc)
                raise
            data = resp.json()

        blocks = data.get("content", [])
        content = "".join(
            block.get("text", "")
            for block in blocks
            if block.get("type") == "text"
        )
        from alafia_model.adapters.tool_protocol import parse_anthropic_tool_calls
        tool_calls = parse_anthropic_tool_calls(blocks)
        usage = data.get("usage") or {}
        tokens = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
        return {"content": content, "tool_calls": tool_calls,
                "model": data.get("model", self.model_name), "tokens_used": tokens}

    async def stream_chat_events(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.5,
        max_tokens: int = 2048,
        tools: list[dict[str, Any]] | None = None,
    ):
        """Stream text as it is written, and assemble any tool calls made.

        Anthropic announces a tool call with `content_block_start` (carrying the
        id and name) and then streams its arguments as `input_json_delta`
        fragments, so the call is only whole at the end of the block.
        """
        from alafia_model.adapters.tool_protocol import StreamedToolCalls

        if not self._api_key:
            raise RuntimeError("anthropic: API key not configured")
        system = "\n\n".join(
            m.get("content", "") for m in messages if m.get("role") == "system"
        ).strip()
        body: dict[str, Any] = {
            "model": self.model_name,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": _anthropic_conversation(messages),
            "stream": True,
        }
        if system:
            body["system"] = system
        if tools:
            body["tools"] = tools
        headers = anthropic_headers(self._api_key, json_content=True)
        pending = StreamedToolCalls()
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream("POST", _MESSAGES_URL, headers=headers, json=body) as resp:
                try:
                    resp.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    await exc.response.aread()
                    _name_config_error(exc)
                    raise
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
                    kind = event.get("type")
                    if kind == "content_block_start":
                        pending.anthropic_start(event.get("index", 0),
                                                event.get("content_block") or {})
                    elif kind == "content_block_delta":
                        delta = event.get("delta") or {}
                        if delta.get("type") == "input_json_delta":
                            pending.anthropic_delta(event.get("index", 0),
                                                    delta.get("partial_json", ""))
                        elif delta.get("text"):
                            yield {"type": "text", "text": delta["text"]}
        calls = pending.finish()
        if calls:
            yield {"type": "tool_calls", "calls": calls}

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
        conversation = _anthropic_conversation(messages)
        body: dict[str, Any] = {
            "model": self.model_name,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": conversation,
            "stream": True,
        }
        if system:
            body["system"] = system
        headers = anthropic_headers(self._api_key, json_content=True)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream("POST", _MESSAGES_URL, headers=headers, json=body) as resp:
                try:
                    resp.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    await exc.response.aread()
                    _name_config_error(exc)
                    raise
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
