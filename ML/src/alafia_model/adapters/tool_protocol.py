"""One tool shape for twenty providers.

The registry holds 20 providers across two wire formats plus Ollama, and none
of the adapters spoke tools at all. Adding tool support to one of them would
have given the feature on 2 providers and lost it the moment the chain fell
through — the §3ae failure, where something works until the provider order
moves and then silently does not.

So the capability layer speaks ONE shape and each adapter translates:

    tool definition   {"name", "description", "input_schema"}   (Anthropic's)
    tool call         {"id", "name", "arguments": dict}
    tool result       {"id", "name", "content": str}

Anthropic's schema is the internal one because it is the stricter of the two —
`input_schema` is a full JSON Schema, and OpenAI's `parameters` is the same
object under a different key, so the lossy direction is avoided.

Not every provider can do this. `ProviderSpec.supports_tools` is False for
Perplexity, whose search models ignore a `tools` field and answer in prose —
which is worse than refusing, because the caller waits for a call that never
comes. A request needing tools must skip those providers rather than discover
the gap mid-conversation.
"""

from __future__ import annotations

import json
from typing import Any


def to_openai_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Internal (Anthropic-shaped) definitions -> OpenAI function format."""
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("input_schema") or {"type": "object", "properties": {}},
            },
        }
        for t in tools
    ]


def parse_openai_tool_calls(message: dict[str, Any]) -> list[dict[str, Any]]:
    """Read tool calls off an OpenAI-style response message.

    Arguments arrive as a JSON *string* and are decoded here, so no call site
    has to remember. A provider that emits malformed JSON yields an empty dict
    rather than raising — the model asked for something, and reporting a bad
    argument beats collapsing the whole answer.
    """
    out: list[dict[str, Any]] = []
    for call in message.get("tool_calls") or []:
        fn = call.get("function") or {}
        raw = fn.get("arguments")
        if isinstance(raw, str):
            try:
                args = json.loads(raw or "{}")
            except (ValueError, json.JSONDecodeError):
                args = {}
        else:
            args = raw or {}
        out.append({
            "id": call.get("id") or fn.get("name", ""),
            "name": fn.get("name", ""),
            "arguments": args if isinstance(args, dict) else {},
        })
    return out


def parse_anthropic_tool_calls(content_blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Read tool calls off Anthropic content blocks."""
    return [
        {"id": b.get("id", ""), "name": b.get("name", ""),
         "arguments": b.get("input") or {}}
        for b in (content_blocks or [])
        if b.get("type") == "tool_use"
    ]


def openai_result_messages(calls: list[dict[str, Any]],
                           results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The assistant turn plus one `tool` message per result (OpenAI shape)."""
    assistant = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {"id": c["id"], "type": "function",
             "function": {"name": c["name"], "arguments": json.dumps(c["arguments"])}}
            for c in calls
        ],
    }
    tool_msgs = [
        {"role": "tool", "tool_call_id": r["id"], "name": r["name"],
         "content": r["content"]}
        for r in results
    ]
    return [assistant] + tool_msgs


def anthropic_result_messages(calls: list[dict[str, Any]],
                              results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The assistant turn plus a single user turn of tool_result blocks."""
    return [
        {"role": "assistant", "content": [
            {"type": "tool_use", "id": c["id"], "name": c["name"], "input": c["arguments"]}
            for c in calls
        ]},
        {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": r["id"], "content": r["content"]}
            for r in results
        ]},
    ]


def to_openai_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Internal conversation turns -> the OpenAI/Ollama wire shape.

    The internal assistant tool-call turn is Anthropic-flavoured —
    ``{"id", "name", "arguments": dict}``. OpenAI requires the call nested
    under ``function``, with ``arguments`` as a JSON **string** and a ``type``
    discriminator. Passing the internal shape through unchanged is a 400 from
    OpenAI, and is silently tolerated by Ollama.

    That difference is why this survived local testing: dev is Ollama-first and
    production is hosted-first (§3ak), so the verified path was the forgiving
    one and the eighteen providers behind `openai_compat` were never exercised.
    Both adapters now speak one dialect rather than two.

    ``role="tool"`` turns already match the OpenAI shape and pass through.
    """
    out: list[dict[str, Any]] = []
    for m in messages:
        if m.get("role") == "assistant" and m.get("tool_calls"):
            out.append({
                "role": "assistant",
                "content": m.get("content") or None,
                "tool_calls": [_openai_call(c) for c in m["tool_calls"]],
            })
        else:
            out.append(m)
    return out


def _openai_call(c: dict[str, Any]) -> dict[str, Any]:
    """One tool call in OpenAI shape, from EITHER the internal or that shape.

    Reading the name and arguments from both places is what makes the
    translation safe to apply twice: after one pass the name lives under
    ``function``, so a second pass that only looked at the top level silently
    produced a call named "" — a tool the model never asked for and the loop
    cannot run.
    """
    fn = c.get("function") or {}
    args = c.get("arguments")
    if args is None:
        args = fn.get("arguments")
    return {
        "id": c.get("id", ""),
        "type": "function",
        "function": {
            "name": c.get("name") or fn.get("name", ""),
            # Already-encoded arguments are left alone, never double-encoded.
            "arguments": args if isinstance(args, str) else json.dumps(args or {}),
        },
    }
