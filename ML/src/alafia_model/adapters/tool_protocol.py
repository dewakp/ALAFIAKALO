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


class StreamedToolCalls:
    """Assembles tool calls that arrive in fragments across a stream.

    Streaming is what lets the ANSWER appear as it is written instead of
    arriving whole after every round has finished. The cost is that a tool call
    no longer arrives as one object: OpenAI sends `arguments` as a run of string
    fragments keyed by index, Anthropic sends `input_json_delta` fragments per
    content block, and Ollama sends the finished call in a single chunk.

    All three land here so the loop above sees one shape.
    """

    def __init__(self) -> None:
        self._slots: dict[int, dict[str, Any]] = {}

    def _slot(self, index: int) -> dict[str, Any]:
        return self._slots.setdefault(index, {"id": "", "name": "", "args": ""})

    def openai_delta(self, deltas: list[dict[str, Any]] | None) -> None:
        """`choices[].delta.tool_calls` — id and name arrive once, args in pieces."""
        for d in deltas or []:
            slot = self._slot(d.get("index", 0))
            if d.get("id"):
                slot["id"] = d["id"]
            fn = d.get("function") or {}
            if fn.get("name"):
                slot["name"] = fn["name"]
            if fn.get("arguments"):
                slot["args"] += fn["arguments"]

    def anthropic_start(self, index: int, block: dict[str, Any]) -> None:
        if (block or {}).get("type") != "tool_use":
            return
        self._slots[index] = {"id": block.get("id", ""), "name": block.get("name", ""),
                              "args": ""}

    def anthropic_delta(self, index: int, partial_json: str) -> None:
        slot = self._slots.get(index)
        if slot is not None:
            slot["args"] += partial_json or ""

    def whole_calls(self, calls: list[dict[str, Any]] | None) -> None:
        """Ollama emits a finished call in one chunk, with args already an object."""
        for c in calls or []:
            fn = c.get("function") or {}
            index = len(self._slots)
            self._slots[index] = {
                "id": c.get("id") or f"call_{index}",
                "name": c.get("name") or fn.get("name", ""),
                "args": fn.get("arguments") if fn.get("arguments") is not None
                else c.get("arguments"),
            }

    def finish(self) -> list[dict[str, Any]]:
        """The completed calls, arguments decoded.

        A fragment run that never completed decodes to `{}` rather than raising:
        the model asked for something, and running the tool with no arguments —
        which every tool here reads as "today" — beats losing the whole answer.
        """
        out: list[dict[str, Any]] = []
        for index in sorted(self._slots):
            slot = self._slots[index]
            if not slot["name"]:
                continue
            args = slot["args"]
            if isinstance(args, str):
                try:
                    args = json.loads(args) if args.strip() else {}
                except ValueError:
                    args = {}
            out.append({
                "id": slot["id"] or f"call_{index}",
                "name": slot["name"],
                "arguments": args if isinstance(args, dict) else {},
            })
        return out
