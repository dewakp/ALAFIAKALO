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

    def _get_adapter(self) -> Any:
        if self._adapter is None:
            from alafia_model.adapters.ollama_adapter import OllamaAdapter
            self._adapter = OllamaAdapter()
        return self._adapter

    async def infer(self, payload: dict[str, Any]) -> CapabilityResult:
        task = payload.get("task", "health_chat")
        messages = payload.get("messages", [])
        context = payload.get("context", {})

        if task == "health_chat":
            return await self._health_chat(messages, context)
        if task == "nutrition_guidance":
            return await self._nutrition_guidance(messages, context)
        if task in ("symptom_triage", "cbt_support"):
            return CapabilityResult(
                success=False,
                error=f"LLM task '{task}' is planned but not yet implemented. See ALAFIAModel Phase 3.",
            )
        return CapabilityResult(
            success=False,
            error=f"Unknown LLM task: {task}",
        )

    async def _health_chat(
        self, messages: list[dict], context: dict
    ) -> CapabilityResult:
        # TODO(alafia-model): replace with ALAFIAModel.LLM fine-tuned BioMistral 7B
        system = _HEALTH_SYSTEM_PROMPT
        if context.get("user_profile"):
            system += f"\n\nUser profile context:\n{context['user_profile']}"

        full_messages = [{"role": "system", "content": system}] + messages

        adapter = self._get_adapter()
        try:
            response = await adapter.chat(full_messages, temperature=0.7)
            return CapabilityResult(
                success=True,
                data={"text": response["content"]},
                confidence=0.75,
                source=f"adapter:{adapter.model_name}",
            )
        except Exception as exc:
            logger.error("LLM health_chat failed: %s", exc, exc_info=True)
            return CapabilityResult(success=False, error=str(exc))

    async def _nutrition_guidance(
        self, messages: list[dict], context: dict
    ) -> CapabilityResult:
        # TODO(alafia-model): replace with ALAFIAModel.LLM + RAG over USDA/WAFCT
        system = _NUTRITION_SYSTEM_PROMPT
        if context.get("nutrition_summary"):
            system += f"\n\nRecent nutrition summary:\n{context['nutrition_summary']}"

        full_messages = [{"role": "system", "content": system}] + messages

        adapter = self._get_adapter()
        try:
            response = await adapter.chat(full_messages, temperature=0.5)
            return CapabilityResult(
                success=True,
                data={"text": response["content"]},
                confidence=0.75,
                source=f"adapter:{adapter.model_name}",
            )
        except Exception as exc:
            logger.error("LLM nutrition_guidance failed: %s", exc, exc_info=True)
            return CapabilityResult(success=False, error=str(exc))
