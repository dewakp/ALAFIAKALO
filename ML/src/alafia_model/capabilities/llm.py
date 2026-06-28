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

    def _get_fallback_adapter(self) -> Any:
        """OpenAI cloud fallback. Returns None when no API key is configured."""
        if self._fallback is None:
            try:
                from alafia_model.adapters.openai_adapter import OpenAIAdapter
                self._fallback = OpenAIAdapter()
            except Exception:  # pragma: no cover
                self._fallback = None
        return self._fallback

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
        """Run `kind` ("chat"|"complete") on the primary adapter, falling back to OpenAI."""
        primary = self._get_adapter(model)
        try:
            response = await self._call(primary, kind, arg, temperature, max_tokens, json_mode)
            return CapabilityResult(
                success=True,
                data={"text": response["content"]},
                confidence=0.75,
                source=f"adapter:{response.get('model', primary.model_name)}",
            )
        except Exception as exc:
            logger.warning("Ollama LLM %s failed (%s); trying OpenAI fallback", kind, exc)

        fallback = self._get_fallback_adapter()
        if fallback is None or not getattr(fallback, "is_available", False):
            return CapabilityResult(
                success=False,
                error="LLM unavailable: Ollama call failed and no OpenAI fallback configured",
            )
        try:
            response = await self._call(fallback, kind, arg, temperature, max_tokens, json_mode)
            return CapabilityResult(
                success=True,
                data={"text": response["content"]},
                confidence=0.6,
                source=f"adapter:openai:{response.get('model', '')}",
            )
        except Exception as exc:
            logger.error("OpenAI fallback LLM %s failed: %s", kind, exc, exc_info=True)
            return CapabilityResult(success=False, error=str(exc))

    @staticmethod
    async def _call(adapter, kind, arg, temperature, max_tokens, json_mode):
        if kind == "chat":
            return await adapter.chat(arg, temperature=temperature, max_tokens=max_tokens, json_mode=json_mode)
        return await adapter.complete(arg, temperature=temperature, max_tokens=max_tokens)
