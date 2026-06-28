"""ALAFIAModel NLM Capability — Natural Language → Structured Health Data.

Phase 1 (implemented): food text → (food_name, qty_g) component list.
  The production meal_parser.py in WEB/backend is the active implementation.
  This capability wraps it so ALAFIAModel.infer(Modality.NLM, ...) works.

Phase 2 (planned): clinical text → ICD-10 codes / symptom extraction.
  Will use BioBERT / PubMedBERT fine-tuned on MIMIC-III discharge summaries.

Phase 3 (planned): food text → full USDA nutrient profile via custom NER +
  RAG over USDA SR Legacy and West African Food Composition Table (WAFCT 2019).

TODO(alafia-model): Phase 2 — train and load a fine-tuned BioBERT for clinical NLP
TODO(alafia-model): Phase 3 — build WAFCT+USDA RAG index and wire into NLM infer
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from alafia_model.capabilities.base import BaseCapability, CapabilityResult

logger = logging.getLogger(__name__)

# Fixed intent taxonomy. MUST stay in sync with INTENT_ROUTE_MAP in
# WEB/backend/app/api/ai.py — the client maps these to existing app screens.
INTENT_LABELS = (
    "log_meal",
    "log_medication",
    "log_elimination",
    "log_symptom",
    "log_activity",
    "log_sleep",
    "journal",
    "view_labs",
    "view_trends",
    "vision_capture",
    "ask_question",
)

_INTENT_SYSTEM_PROMPT = """\
You are ALAFIA's intent router. A user typed or spoke a short prompt. Classify it
into EXACTLY ONE intent and extract any structured entities, then return STRICT JSON.

Valid intents (choose the single best match):
- log_meal        : user ate/drank something (food, drinks, water)
- log_medication  : user took/wants to log a medication or dose
- log_elimination : urination, bowel movement, vomiting
- log_symptom     : pain, injury, feeling unwell, a physical/emotional symptom
- log_activity    : exercise, walking, workout, physical activity
- log_sleep       : sleep duration/quality
- journal         : a thought, reflection, or diary-style note
- view_labs       : wants to see lab results / biomarkers
- view_trends     : wants to see trends, patterns, history, or relationships
- vision_capture  : refers to a photo/image with no clear text intent
- ask_question    : a health question or anything that doesn't fit above (fallback)

Return ONLY a JSON object:
{
  "intent": "<one of the valid intents>",
  "confidence": 0.0,
  "entities": { ...flat key/values you can extract, e.g. name, dose, food, duration_hours... }
}

Rules:
- Never invent an intent outside the list. When unsure, use "ask_question".
- confidence is your calibrated certainty 0.0-1.0.
- entities is {} when nothing structured is present. Never fabricate values.
"""


class NLMCapability(BaseCapability):
    """NLM (Nutritional / Clinical Language Matching) capability.

    Current status: Phase 1 scaffolded — delegates to the production
    meal_parser module when running inside the backend. When run standalone
    (e.g. in ML training scripts), uses the bundled lite parser.

    Supported tasks:
        "parse_meal"     → extract (food_name, qty_g) from free-text meal
        "extract_icd10"  → [PLANNED] extract ICD-10 codes from clinical notes
        "extract_symptoms" → [PLANNED] symptom → SNOMED-CT mapping
    """

    capability_id = "nlm"
    version = "1.0.0-phase1"
    is_implemented = True   # Phase 1 is live via meal_parser.py delegation

    async def infer(self, payload: dict[str, Any]) -> CapabilityResult:
        task = payload.get("task", "parse_meal")
        text = payload.get("text", "")

        if task == "parse_meal":
            return await self._parse_meal(text)
        if task == "classify_intent":
            return await self._classify_intent(text, payload)
        if task == "extract_icd10":
            return self._not_yet_implemented("extract_icd10", "BioBERT ICD-10 extraction")
        if task == "extract_symptoms":
            return self._not_yet_implemented("extract_symptoms", "DistilBERT symptom NER")

        return CapabilityResult(
            success=False,
            error=f"Unknown NLM task: {task}. Valid: parse_meal, extract_icd10, extract_symptoms",
        )

    async def _parse_meal(self, text: str) -> CapabilityResult:
        """Delegate to the production meal_parser module."""
        try:
            # Try production backend path first (when running inside the backend)
            import sys
            import os

            backend_path = os.path.join(
                os.path.dirname(__file__), "..", "..", "..", "..", "..",
                "WEB", "backend"
            )
            backend_path = os.path.normpath(backend_path)
            if backend_path not in sys.path:
                sys.path.insert(0, backend_path)

            from app.services.meal_parser import parse_meal_text  # type: ignore

            components = parse_meal_text(text)
            return CapabilityResult(
                success=True,
                data={
                    "components": [
                        {
                            "food_name": c.food_name,
                            "qty_g": c.qty_g,
                            "qty_text": c.qty_text,
                        }
                        for c in components
                    ],
                    "total_weight_g": round(sum(c.qty_g for c in components), 1),
                },
                confidence=0.85,
                source="alafia-meal-parser-v1",
            )
        except ImportError:
            logger.warning("meal_parser not available — NLM parse_meal requires backend path")
            return CapabilityResult(
                success=False,
                error="meal_parser not available in current environment",
            )
        except Exception as exc:
            logger.error("NLM parse_meal failed: %s", exc, exc_info=True)
            return CapabilityResult(success=False, error=str(exc))

    async def _classify_intent(self, text: str, payload: dict) -> CapabilityResult:
        """Classify a prompt into an intent + entities via the LLM (json_mode).

        Drives ALAFIA's "prompt determines what UI is surfaced" model. Falls back
        to the deterministic ``ask_question`` intent whenever the model is
        unavailable or returns unparseable output, so the caller always gets a
        usable result.
        """
        text = (text or "").strip()
        if not text:
            # No text (e.g. a bare image/voice attachment) — let the caller decide
            # based on modality; default to a low-confidence vision/question intent.
            return CapabilityResult(
                success=True,
                data={"intent": "ask_question", "confidence": 0.0, "entities": {}},
                confidence=0.0,
                source="nlm-intent-empty",
            )

        from alafia_model.capabilities.llm import LLMCapability

        llm = LLMCapability()
        llm_result = await llm.infer(
            {
                "task": "chat",
                "messages": [
                    {"role": "system", "content": _INTENT_SYSTEM_PROMPT},
                    {"role": "user", "content": text},
                ],
                "temperature": 0.0,
                "max_tokens": 256,
                "json_mode": True,
            }
        )

        if not llm_result.success:
            logger.warning("classify_intent LLM unavailable: %s", llm_result.error)
            return self._fallback_intent(text, reason=llm_result.error)

        parsed = self._parse_intent_json((llm_result.data or {}).get("text", ""))
        if parsed is None:
            return self._fallback_intent(text, reason="unparseable model output")

        return CapabilityResult(
            success=True,
            data=parsed,
            confidence=float(parsed.get("confidence") or 0.0),
            source=f"nlm-intent:{llm_result.source}",
        )

    @staticmethod
    def _parse_intent_json(raw: str) -> dict | None:
        """Extract and validate the intent JSON from a model response."""
        if not raw:
            return None
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            return None
        try:
            obj = json.loads(match.group(0))
        except (json.JSONDecodeError, ValueError):
            return None
        intent = obj.get("intent")
        if intent not in INTENT_LABELS:
            return None
        entities = obj.get("entities")
        try:
            confidence = float(obj.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        return {
            "intent": intent,
            "confidence": max(0.0, min(1.0, confidence)),
            "entities": entities if isinstance(entities, dict) else {},
        }

    @staticmethod
    def _fallback_intent(text: str, reason: str | None = None) -> CapabilityResult:
        """Deterministic low-confidence fallback when the model can't classify."""
        return CapabilityResult(
            success=True,
            data={
                "intent": "ask_question",
                "confidence": 0.3,
                "entities": {"text": text},
            },
            confidence=0.3,
            source="nlm-intent-fallback",
            error=reason,
        )

    def _not_yet_implemented(self, task: str, description: str) -> CapabilityResult:
        return CapabilityResult(
            success=False,
            error=f"NLM task '{task}' ({description}) is planned but not yet implemented. "
                  f"See docs/AI_ENGINE_ARCHITECTURE.md Phase 2.",
        )
