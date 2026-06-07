"""ALAFIAModel Vision Capability — Food Photos, Lab Reports, Skin, Pills.

Phase 5 (planned): Food photo → nutrition estimate
  - MobileNet V3 or EfficientNet-Lite fine-tuned on Food-101 + West African food dataset
  - On-device export: Core ML (iOS), TFLite (Android)
  - Backend validation for confidence < 0.7

Phase 6 (planned): Lab report OCR → structured nutrient / biomarker data
  - Tesseract + layout parser (already partially in pipeline)
  - LayoutLM or Donut for form understanding

TODO(alafia-model): Phase 5 — train MobileNetV3 food classifier on Food-101 + WAFCT foods
TODO(alafia-model): Phase 5 — export to Core ML (.mlmodel) and TFLite (.tflite)
TODO(alafia-model): Phase 6 — build LayoutLM pipeline for lab report parsing
"""

from __future__ import annotations

import logging
from typing import Any

from alafia_model.capabilities.base import BaseCapability, CapabilityResult

logger = logging.getLogger(__name__)


class VisionCapability(BaseCapability):
    """Vision capability for food recognition, lab OCR, skin triage, and pill ID.

    Supported tasks (all PLANNED unless marked):
        "food_photo_nutrition"  → food image → nutrition estimate [PLANNED Ph5]
        "lab_report_ocr"        → lab report image → structured biomarkers [PLANNED Ph6]
        "skin_triage"           → skin photo → care level guidance [PLANNED]
        "pill_identification"   → pill photo → medication name [PLANNED]
    """

    capability_id = "vision"
    version = "0.1.0-scaffold"
    is_implemented = False  # No model loaded yet

    async def infer(self, payload: dict[str, Any]) -> CapabilityResult:
        task = payload.get("task", "food_photo_nutrition")

        if task == "food_photo_nutrition":
            return await self._food_photo_nutrition(payload)
        if task == "lab_report_ocr":
            return await self._lab_report_ocr(payload)
        if task in ("skin_triage", "pill_identification"):
            return self._scaffold_stub(task)

        return CapabilityResult(
            success=False,
            error=f"Unknown vision task: {task}",
        )

    async def _food_photo_nutrition(self, payload: dict) -> CapabilityResult:
        # TODO(alafia-model): Phase 5 — load fine-tuned MobileNetV3 food classifier
        # For now, fall back to LLM vision API if available
        image_bytes: bytes | None = payload.get("image_bytes")
        if image_bytes is None:
            return CapabilityResult(success=False, error="image_bytes required")

        logger.info(
            "Vision food_photo_nutrition: Phase 5 model not yet trained. "
            "Returning scaffold stub."
        )
        return CapabilityResult(
            success=False,
            error=(
                "food_photo_nutrition is planned for ALAFIAModel Phase 5. "
                "Use POST /nutrition/estimate-meal with a text description for now."
            ),
        )

    async def _lab_report_ocr(self, payload: dict) -> CapabilityResult:
        # TODO(alafia-model): Phase 6 — integrate Tesseract + LayoutLM
        return CapabilityResult(
            success=False,
            error=(
                "lab_report_ocr is planned for ALAFIAModel Phase 6. "
                "Manual lab entry is currently supported via the app."
            ),
        )

    def _scaffold_stub(self, task: str) -> CapabilityResult:
        return CapabilityResult(
            success=False,
            error=f"Vision task '{task}' is scaffolded but not yet implemented. "
                  "See docs/AI_ENGINE_ARCHITECTURE.md for the roadmap.",
        )

    @classmethod
    def get_model_spec(cls) -> dict:
        """Return the specification for the food recognition model to be trained."""
        return {
            "architecture": "MobileNetV3-Small",
            "base_weights": "imagenet",
            "fine_tune_dataset": "Food-101 + West African food photos (to be collected)",
            "target_classes": 200,
            "input_size": [224, 224, 3],
            "export_targets": ["Core ML (iOS)", "TFLite (Android)", "ONNX (backend)"],
            "training_script": "ML/scripts/train_food_vision.py",  # to be created
            "phase": 5,
            "status": "planned",
        }
