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

import logging
from typing import Any

from alafia_model.capabilities.base import BaseCapability, CapabilityResult

logger = logging.getLogger(__name__)


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

    def _not_yet_implemented(self, task: str, description: str) -> CapabilityResult:
        return CapabilityResult(
            success=False,
            error=f"NLM task '{task}' ({description}) is planned but not yet implemented. "
                  f"See docs/AI_ENGINE_ARCHITECTURE.md Phase 2.",
        )
