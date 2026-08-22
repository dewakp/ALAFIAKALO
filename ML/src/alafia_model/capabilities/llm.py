"""ALAFIAModel LLM Capability — Health Coaching & Clinical Reasoning.

Phase 3 (planned): Fine-tuned BioMistral 7B served via Ollama for:
  - Health coaching chat (personalized to ALAFIA user profile)
  - Nutrition guidance with RAG over USDA + WAFCT
  - CBT-style mental health support (with safety guardrails)
  - Exercise recommendation formatting

Current behavior: Routes to adapter layer (Ollama local → OpenAI fallback).
All calls are logged with TODO(alafia-model) markers so we can track
migration progress.

TODO(alafia-model): Phase 3 — fine-tune BioMistral 7B on ALAFIA health coaching data
TODO(alafia-model): Phase 4 — build RAG index over USDA + WAFCT and wire into LLM infer
"""

from __future__ import annotations

import logging
import time
from typing import Any

from alafia_model.capabilities.base import BaseCapability, CapabilityResult

logger = logging.getLogger(__name__)

_HEALTH_SYSTEM_PROMPT = """\
You are ALAFIA's AI health coach. You provide personalized, evidence-based
health and wellness guidance. You are knowledgeable about nutrition, exercise,
chronic disease management, and preventive care.

Guidelines:
- Always recommend consulting a healthcare provider for medical decisions
- Use plain, empathetic language appropriate for non-clinical users
- Reference West African, African diaspora, and global food traditions
- Never diagnose; guide toward professional care when symptoms arise
- Keep responses concise and actionable
"""

_NUTRITION_SYSTEM_PROMPT = """\
You are ALAFIA's nutrition AI. You provide personalized dietary guidance
grounded in clinical nutrition science and global food traditions.
You have deep knowledge of West African, South Asian, Caribbean, and
Western food composition from USDA SR Legacy, WAFCT 2019, and IFCT.
"""


class LLMCapability(BaseCapability):
    """LLM (Language Model) capability for health coaching and clinical reasoning.

    Current status: Delegates to adapter layer (Ollama → OpenAI).
    Target state: Fine-tuned BioMistral 7B running on ALAFIA's own GPU VM.

    Supported tasks:
        "health_chat"        → conversational health coaching
        "nutrition_guidance" → dietary advice with food context
        "symptom_triage"     → guide user to appropriate care level [PLANNED]
        "cbt_support"        → CBT-style mental health guidance [PLANNED]
    """

    capability_id = "llm"
    version = "0.1.0-adapter-delegation"
    is_implemented = True  # Implemented via adapter delegation

    def __init__(self) -> None:
        super().__init__()
        self._adapter: Any = None
        self._fallback: Any = None
        self._pool: dict[str, Any] = {}   # provider name → cached adapter

    def _get_adapter(self, model: str | None = None) -> Any:
        from alafia_model.adapters.ollama_adapter import OllamaAdapter
        # A per-call model override gets its own (uncached) adapter so it doesn't
        # disturb the shared default instance.
        if model:
            if self._adapter is not None and getattr(self._adapter, "model_name", None) == model:
                return self._adapter
            return OllamaAdapter(model=model)
        if self._adapter is None:
            self._adapter = OllamaAdapter()
        return self._adapter

    def _adapter_for(self, spec) -> Any:
        """Build (and cache) the adapter for a registry provider spec."""
        cached = self._pool.get(spec.name)
        if cached is not None:
            return cached
        if spec.kind == "anthropic":
            from alafia_model.adapters.anthropic_adapter import AnthropicAdapter
            adapter = AnthropicAdapter(api_key=spec.api_key, model=spec.resolved_model())
        else:
            from alafia_model.adapters.openai_compat_adapter import OpenAICompatAdapter
            from alafia_model.registry.providers import base_url_for
            adapter = OpenAICompatAdapter(
                provider=spec.name,
                base_url=base_url_for(spec),
                api_key=spec.api_key,
                model=spec.resolved_model(),
                extra_headers=spec.extra_headers,
            )
        self._pool[spec.name] = adapter
        return adapter

    async def infer(self, payload: dict[str, Any]) -> CapabilityResult:
        task = payload.get("task", "health_chat")
        messages = payload.get("messages", [])
        context = payload.get("context", {})
        temperature = payload.get("temperature", 0.7)
        max_tokens = payload.get("max_tokens", 2048)
        json_mode = bool(payload.get("json_mode", False))
        model = payload.get("model") or None

        # Tasks that prepend an ALAFIA system prompt
        if task == "health_chat":
            system = _HEALTH_SYSTEM_PROMPT
            if context.get("user_profile"):
                system += f"\n\nUser profile context:\n{context['user_profile']}"
            return await self._chat(system, messages, temperature, max_tokens, json_mode, model)

        if task == "nutrition_guidance":
            system = _NUTRITION_SYSTEM_PROMPT
            if context.get("nutrition_summary"):
                system += f"\n\nRecent nutrition summary:\n{context['nutrition_summary']}"
            return await self._chat(system, messages, temperature, max_tokens, json_mode, model)

        # Generic passthrough — the caller supplies its own system message (if any).
        # This is the entry point backend services use so every LLM call is routed
        # through ALAFIAModel rather than hitting Ollama/OpenAI directly.
        if task in ("chat", "raw_chat", "health_coaching"):
            return await self._chat(None, messages, temperature, max_tokens, json_mode, model)

        # Single-prompt completion (maps to /api/generate style structured output).
        if task == "complete":
            return await self._complete(payload.get("text", ""), temperature, max_tokens, model)

        if task in ("symptom_triage", "cbt_support"):
            return CapabilityResult(
                success=False,
                error=f"LLM task '{task}' is planned but not yet implemented. See ALAFIAModel Phase 3.",
            )
        return CapabilityResult(
            success=False,
            error=f"Unknown LLM task: {task}",
        )

    # ── Internal dispatch with Ollama → OpenAI fallback ────────────────────────

    async def _chat(
        self,
        system: str | None,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
        json_mode: bool,
        model: str | None = None,
    ) -> CapabilityResult:
        # TODO(alafia-model): replace adapters with native fine-tuned BioMistral 7B
        full_messages = ([{"role": "system", "content": system}] if system else []) + list(messages)
        return await self._dispatch("chat", full_messages, temperature, max_tokens, json_mode, model)

    async def _complete(
        self, prompt: str, temperature: float, max_tokens: int, model: str | None = None
    ) -> CapabilityResult:
        return await self._dispatch("complete", prompt, temperature, max_tokens, True, model)

    async def _dispatch(
        self, kind: str, arg: Any, temperature: float, max_tokens: int, json_mode: bool,
        model: str | None = None,
    ) -> CapabilityResult:
        """Free-first weighted round-robin over the hosted provider pool, then a
        terminal fall back to self-hosted Ollama. Every attempt is recorded for the
        ALAFIA-model training corpus (telemetry)."""
        from alafia_model.registry.providers import ordered_for_selection, mark_cooldown
        from alafia_model import telemetry

        chat_msgs = arg if kind == "chat" else None
        last_error: str | None = None

        for spec in ordered_for_selection():
            t0 = time.monotonic()
            try:
                resp = await self._call(self._adapter_for(spec), kind, arg, temperature, max_tokens, json_mode)
                telemetry.record(
                    provider=spec.name, model=resp.get("model"), task=kind, tier=spec.tier,
                    latency_ms=int((time.monotonic() - t0) * 1000), tokens=resp.get("tokens_used", 0),
                    success=True, messages=chat_msgs, response=resp.get("content"),
                )
                return CapabilityResult(
                    # tokens_used/model travel in `data`, not just telemetry: the
                    # backend records per-user usage from here, and dropping them
                    # is why AIInteraction.tokens_used was always 0.
                    success=True,
                    data={
                        "text": resp["content"],
                        "tokens_used": resp.get("tokens_used", 0),
                        "model": resp.get("model", spec.resolved_model()),
                        "provider": spec.name,
                    },
                    confidence=0.7,
                    source=f"{spec.name}:{resp.get('model', spec.resolved_model())}",
                )
            except Exception as exc:
                last_error = str(exc)
                status = getattr(getattr(exc, "response", None), "status_code", None)
                blob = str(exc).lower()
                if status in (401, 402, 403, 429) or "quota" in blob or "rate" in blob or "insufficient" in blob:
                    mark_cooldown(spec.name)  # back this provider off; free tier likely spent
                telemetry.record(
                    provider=spec.name, task=kind, tier=spec.tier,
                    latency_ms=int((time.monotonic() - t0) * 1000), success=False, error=str(exc)[:300],
                )
                logger.warning("provider %s %s failed (%s); trying next", spec.name, kind, exc)

        # ── Terminal fallback: self-hosted Ollama (never rate-limited) ──
        ollama = self._get_adapter(model)
        t0 = time.monotonic()
        try:
            resp = await self._call(ollama, kind, arg, temperature, max_tokens, json_mode)
            telemetry.record(
                provider="ollama", model=resp.get("model"), task=kind, tier="local",
                latency_ms=int((time.monotonic() - t0) * 1000), tokens=resp.get("tokens_used", 0),
                success=True, messages=chat_msgs, response=resp.get("content"),
            )
            return CapabilityResult(
                success=True,
                data={
                    "text": resp["content"],
                    "tokens_used": resp.get("tokens_used", 0),
                    "model": resp.get("model", ollama.model_name),
                    "provider": "ollama",
                },
                confidence=0.75,
                source=f"ollama:{resp.get('model', ollama.model_name)}",
            )
        except Exception as exc:
            telemetry.record(provider="ollama", task=kind, tier="local", success=False, error=str(exc)[:300])
            logger.error("all LLM providers failed; last cloud=%s ollama=%s", last_error, exc, exc_info=True)
            # Name the exception TYPE, not just its message. httpx timeout
            # exceptions carry an EMPTY str(), so "last: {exc}" rendered as
            # "all providers failed (last: )" — an error that says nothing,
            # and which sent an operator looking for a downed service when the
            # model was simply slower than the timeout.
            detail = last_error or f"{type(exc).__name__}: {exc}".rstrip(": ")
            return CapabilityResult(
                success=False,
                error=f"LLM unavailable: all providers failed (last: {detail})",
            )

    @staticmethod
    async def _call(adapter, kind, arg, temperature, max_tokens, json_mode):
        if kind == "chat":
            return await adapter.chat(arg, temperature=temperature, max_tokens=max_tokens, json_mode=json_mode)
        return await adapter.complete(arg, temperature=temperature, max_tokens=max_tokens)
