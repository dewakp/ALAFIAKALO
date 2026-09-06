"""Ollama adapter — local LLM via Ollama server.

This is the PRIMARY LLM adapter — it runs on ALAFIA infrastructure (no data
leaves our servers). OpenAI is the cloud fallback only.

Default model: llama3.1:8b or BioMistral:7b (configured via OLLAMA_MODEL env).

TODO(alafia-model): Phase 3 — replace OLLAMA_MODEL default with the fine-tuned
    BioMistral 7B health coaching model once training is complete.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import time
from typing import Any

import httpx

from alafia_model.adapters.base_adapter import BaseAdapter

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "http://localhost:11434"
_DEFAULT_MODEL = "llama3.1:8b"

# ── Auth for a private (IAM-protected) Ollama Cloud Run service ────────────────
# Prod runs Ollama as a private GPU Cloud Run service; callers must attach a
# Google OIDC ID token whose audience is the service URL. We fetch it from the
# instance metadata server and cache it. For a non-Cloud-Run URL (local dev) no
# auth is needed → {} (same code path works everywhere). Mirrors the backend's
# app/services/ollama_auth.py (this package is standalone and can't import it).
_METADATA_IDENTITY = (
    "http://metadata.google.internal/computeMetadata/v1/instance/"
    "service-accounts/default/identity"
)
_auth_cache: dict = {"token": None, "exp": 0.0, "aud": None}


def _jwt_exp(token: str) -> float:
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return float(json.loads(base64.urlsafe_b64decode(payload)).get("exp", 0))
    except Exception:
        return time.time() + 3000


async def _ollama_auth_headers(base_url: str) -> dict:
    """OIDC Authorization header for a private Cloud Run Ollama, or {} for local dev."""
    if ".run.app" not in (base_url or ""):
        return {}
    aud = base_url.rstrip("/")
    now = time.time()
    if _auth_cache["token"] and _auth_cache["aud"] == aud and _auth_cache["exp"] - now > 60:
        return {"Authorization": f"Bearer {_auth_cache['token']}"}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                _METADATA_IDENTITY,
                params={"audience": aud, "format": "full"},
                headers={"Metadata-Flavor": "Google"},
            )
        r.raise_for_status()
        token = r.text.strip()
        _auth_cache.update(token=token, exp=_jwt_exp(token), aud=aud)
        return {"Authorization": f"Bearer {token}"}
    except Exception:
        return {}


def _env_timeout(default: float = 290.0) -> float:
    """Seconds to wait on Ollama, from OLLAMA_TIMEOUT.

    Default 290, strictly BELOW Cloud Run's 300s request timeout. At an equal
    value the platform kills the request first and the caller gets Cloud Run's
    error instead of ours, which says less. Every rung of the ladder must be
    strictly ordered — see AI_TIMEOUT_MS in services/api.js.
    """
    raw = os.environ.get("OLLAMA_TIMEOUT")
    if not raw:
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


class OllamaAdapter(BaseAdapter):
    """Adapter for Ollama local LLM server."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self.base_url = (
            base_url
            or os.environ.get("OLLAMA_BASE_URL", _DEFAULT_BASE_URL)
        ).rstrip("/")
        self.model_name = (
            model
            or os.environ.get("OLLAMA_MODEL", _DEFAULT_MODEL)
        )
        # OLLAMA_TIMEOUT, like base_url and model above. It was the one setting
        # that did NOT read its environment variable: the default was a
        # hardcoded 120.0 and every construction site calls OllamaAdapter()
        # with no timeout, so production's OLLAMA_TIMEOUT=300 -- set explicitly
        # by deploy.sh -- was silently ignored and the real limit was 120s.
        #
        # These prompts legitimately take 98-121s against gpt-oss:20b, so
        # requests were dying just past the boundary and reporting
        # "ReadTimeout" on a model that was still working.
        self.timeout = timeout if timeout is not None else _env_timeout()
        self.is_available = False  # set by health_check()

    async def health_check(self) -> bool:
        """Ping Ollama and verify the configured model is available."""
        try:
            headers = await _ollama_auth_headers(self.base_url)
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.base_url}/api/tags", headers=headers)
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
        tools: list[dict[str, Any]] | None = None,
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
            # NOT `to_openai_messages` — Ollama and OpenAI disagree here, and
            # measuring settled it. Ollama wants tool-call `arguments` as an
            # OBJECT and answers 400 to OpenAI's JSON-STRING form, so applying
            # that translation here killed round 2 of every tool conversation:
            # round 1 fetched six meals, round 2 was refused, and the fallback
            # then answered from the record dump with an invented figure.
            # One dialect was the tidier idea; the wire disagreed (§0).
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        if json_mode:
            payload["format"] = "json"
        if tools:
            # Ollama takes OpenAI-shaped tools on /api/chat. This is the LOCAL
            # and the production FALLBACK path, so without it a tool-using
            # conversation would work until the chain fell through and then
            # quietly stop working (§3ae).
            from alafia_model.adapters.tool_protocol import to_openai_tools
            payload["tools"] = to_openai_tools(tools)
        headers = await _ollama_auth_headers(self.base_url)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(f"{self.base_url}/api/chat", json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        message = data.get("message", {}) or {}
        content = message.get("content", "")
        from alafia_model.adapters.tool_protocol import parse_openai_tool_calls
        tool_calls = parse_openai_tool_calls(message)
        return {
            "content": content,
            "tool_calls": tool_calls,
            "model": self.model_name,
            "tokens_used": data.get("eval_count", 0),
        }

    async def stream_chat_events(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.5,
        max_tokens: int = 2048,
        tools: list[dict[str, Any]] | None = None,
    ):
        """Stream, yielding text as it is written AND any tool calls made.

        The loop needs both from one request: it cannot know in advance whether
        a round will fetch data or answer, so it must stream every round and
        find out. Ollama sends a finished tool call in a single chunk, so no
        fragment assembly is needed here — unlike the hosted adapters.

        NOT `to_openai_messages`: Ollama wants tool-call arguments as an OBJECT
        and answers 400 to OpenAI's JSON-string form (§3am).
        """
        from alafia_model.adapters.tool_protocol import (
            StreamedToolCalls, to_openai_tools,
        )

        url = f"{self.base_url.rstrip('/')}/api/chat"
        body: dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "stream": True,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        if tools:
            body["tools"] = to_openai_tools(tools)
        pending = StreamedToolCalls()
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream("POST", url, json=body,
                                     headers=await _ollama_auth_headers(self.base_url)) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        chunk = json.loads(line)
                    except ValueError:
                        continue
                    message = chunk.get("message") or {}
                    text = message.get("content")
                    if text:
                        yield {"type": "text", "text": text}
                    if message.get("tool_calls"):
                        pending.whole_calls(message["tool_calls"])
                    if chunk.get("done"):
                        break
        calls = pending.finish()
        if calls:
            yield {"type": "tool_calls", "calls": calls}

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.5,
        max_tokens: int = 2048,
    ):
        """Yield text chunks from Ollama's newline-delimited JSON stream."""
        url = f"{self.base_url.rstrip('/')}/api/chat"
        body = {
            "model": self.model_name,
            "messages": messages,
            "stream": True,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream("POST", url, json=body, headers=await _ollama_auth_headers(self.base_url)) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        chunk = json.loads(line)
                    except ValueError:
                        continue
                    text = (chunk.get("message") or {}).get("content")
                    if text:
                        yield text
                    if chunk.get("done"):
                        break

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
        headers = await _ollama_auth_headers(self.base_url)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(f"{self.base_url}/api/generate", json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        return {
            "content": data.get("response", ""),
            "model": self.model_name,
            "tokens_used": data.get("eval_count", 0),
        }
