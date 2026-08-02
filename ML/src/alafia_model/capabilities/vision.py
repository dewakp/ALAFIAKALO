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

import base64
import json
import logging
import os
import re
from typing import Any

from alafia_model.capabilities.base import BaseCapability, CapabilityResult

logger = logging.getLogger(__name__)

# Vision-capable models used until the on-device MobileNetV3 classifier (Ph5) ships.
# Dev default routes through local Ollama (a llava-family model); OpenAI is fallback.
_DEFAULT_OLLAMA_VISION_MODEL = "llava"
_DEFAULT_OPENAI_VISION_MODEL = "gpt-4o-mini"

_FOOD_VISION_PROMPT = """\
You are ALAFIA's food vision analyzer. Identify the foods in the photo and give a
rough portion + nutrition estimate. You know West African, African diaspora, and
global cuisines. Return ONLY a JSON object with exactly these keys:
{
  "items": [
    {"name": "food name", "estimated_portion": "e.g. 1 cup / 150 g", "confidence": 0.0}
  ],
  "estimated_nutrition": {
    "calories": null, "protein_g": null, "carbs_g": null, "fat_g": null
  },
  "notes": "one short line; mention if the photo is unclear"
}

Rules:
- Estimates only — never claim precision. Use null when you cannot tell.
- If the image has no food, return an empty items array and say so in notes.
- Do NOT invent foods that are not visible.
"""

# Appended when the caller sends several photos. They are shots of ONE meal, so
# the model must return one combined reading — the single most common failure
# here is counting the same plate once per photo and tripling the calories.
_MULTI_IMAGE_RULE = """\

You are being shown {n} photos of THE SAME meal (different angles, lighting, or
close-ups). Analyze them together and return ONE combined result:
- Do NOT count a dish more than once because it appears in more than one photo.
- Merge duplicates into a single item; use the clearest photo to judge portion.
- Only list a food twice if there are genuinely two separate servings visible.
- Use the extra angles to raise confidence, not to inflate the totals.
"""


class VisionCapability(BaseCapability):
    """Vision capability for food recognition, lab OCR, skin triage, and pill ID.

    Supported tasks (all PLANNED unless marked):
        "food_photo_nutrition"  → food image → nutrition estimate [PLANNED Ph5]
        "lab_report_ocr"        → lab report image → structured biomarkers [PLANNED Ph6]
        "skin_triage"           → skin photo → care level guidance [PLANNED]
        "pill_identification"   → pill photo → medication name [PLANNED]
    """

    capability_id = "vision"
    version = "0.3.0-vision-llm-multi"
    is_implemented = False  # No native model yet; relies on a vision LLM backend

    def is_available(self) -> bool:
        """Available when a vision-capable LLM backend is reachable.

        Dev: local Ollama (OLLAMA_BASE_URL, a llava-family model). Prod/fallback:
        OpenAI vision (OPENAI_API_KEY). Returns False only when neither is set,
        so callers degrade to the manual capture flow.
        """
        return bool(os.environ.get("OLLAMA_BASE_URL") or os.environ.get("OPENAI_API_KEY"))

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

    @staticmethod
    def _collect_images(payload: dict) -> list[tuple[bytes, str]]:
        """Normalize the single- and multi-image payload shapes into one list.

        Accepts `images` (list of {"image_bytes", "content_type"}) and falls back
        to the single `image_bytes` + `content_type` pair. Entries without bytes
        are dropped so a half-filled payload cannot reach an adapter.
        """
        default_type = payload.get("content_type") or "image/jpeg"

        entries = payload.get("images") or []
        if entries:
            collected = [
                (e["image_bytes"], e.get("content_type") or default_type)
                for e in entries
                if isinstance(e, dict) and e.get("image_bytes")
            ]
            if collected:
                return collected

        single = payload.get("image_bytes")
        return [(single, default_type)] if single else []

    async def _food_photo_nutrition(self, payload: dict) -> CapabilityResult:
        # TODO(alafia-model): Phase 5 — load fine-tuned MobileNetV3 food classifier.
        # Until then, use a vision-capable LLM (OpenAI gpt-4o family) when configured.
        images = self._collect_images(payload)
        if not images:
            return CapabilityResult(success=False, error="image_bytes required")

        if not self.is_available():
            return CapabilityResult(
                success=False,
                error=(
                    "Vision backend not configured (no OPENAI_API_KEY). "
                    "Save the photo via Capture or describe the meal in text."
                ),
            )

        prompt = _FOOD_VISION_PROMPT
        if len(images) > 1:
            prompt += _MULTI_IMAGE_RULE.format(n=len(images))

        result = await self._vision_chat(images, prompt)
        if not result.success:
            return result

        parsed = self._parse_json(result.data.get("text", ""))
        if parsed is None:
            return CapabilityResult(
                success=False, source=result.source,
                error="Vision model returned unparseable output",
            )
        items = parsed.get("items") if isinstance(parsed.get("items"), list) else []
        return CapabilityResult(
            success=True,
            data={
                "items": items,
                "estimated_nutrition": parsed.get("estimated_nutrition") or {},
                "notes": parsed.get("notes") or "",
                "image_count": len(images),
            },
            confidence=0.5,  # LLM estimate — deliberately modest until Ph5 model
            source=result.source,
        )

    async def _vision_chat(
        self, images: list[tuple[bytes, str]], system_prompt: str
    ) -> CapabilityResult:
        """Send one or more images + an instruction to a vision LLM in ONE call.

        Dev default is local Ollama (a llava-family model); OpenAI vision is the
        fallback. Returns the first successful response.
        """
        encoded = [
            (base64.b64encode(raw).decode("ascii"), content_type)
            for raw, content_type in images
        ]
        errors: list[str] = []

        if os.environ.get("OLLAMA_BASE_URL"):
            result = await self._ollama_vision(encoded, system_prompt)
            if result.success:
                return result
            errors.append(result.error or "ollama failed")

        if os.environ.get("OPENAI_API_KEY"):
            result = await self._openai_vision(encoded, system_prompt)
            if result.success:
                return result
            errors.append(result.error or "openai failed")

        return CapabilityResult(
            success=False,
            error="; ".join(errors) or "No vision backend configured",
        )

    async def _ollama_vision(
        self, encoded: list[tuple[str, str]], system_prompt: str
    ) -> CapabilityResult:
        """Run image understanding through a local Ollama vision model (llava)."""
        from alafia_model.adapters.ollama_adapter import OllamaAdapter

        model = os.environ.get("OLLAMA_VISION_MODEL", _DEFAULT_OLLAMA_VISION_MODEL)
        adapter = OllamaAdapter(model=model, timeout=300.0)
        noun = "this image" if len(encoded) == 1 else f"these {len(encoded)} images"
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Analyze {noun}."},
        ]
        try:
            response = await adapter.chat(
                messages,
                temperature=0.2,
                max_tokens=700,
                json_mode=True,
                images=[b64 for b64, _ in encoded],
            )
        except Exception as exc:
            logger.warning("Ollama vision failed (%s); will try fallback if configured", exc)
            return CapabilityResult(success=False, error=f"Ollama vision: {exc}")
        return CapabilityResult(
            success=True,
            data={"text": response.get("content", "")},
            source=f"vision-ollama:{response.get('model', model)}",
        )

    async def _openai_vision(
        self, encoded: list[tuple[str, str]], system_prompt: str
    ) -> CapabilityResult:
        """Run image understanding through the OpenAI vision API (fallback)."""
        from alafia_model.adapters.openai_adapter import OpenAIAdapter

        adapter = OpenAIAdapter(
            model=os.environ.get("OPENAI_VISION_MODEL", _DEFAULT_OPENAI_VISION_MODEL)
        )
        if not getattr(adapter, "is_available", False):
            return CapabilityResult(success=False, error="OpenAI vision adapter unavailable")

        noun = "this image" if len(encoded) == 1 else f"these {len(encoded)} images"
        content: list[dict[str, Any]] = [{"type": "text", "text": f"Analyze {noun}."}]
        content.extend(
            {
                "type": "image_url",
                "image_url": {"url": f"data:{content_type};base64,{b64}"},
            }
            for b64, content_type in encoded
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": content},
        ]
        try:
            response = await adapter.chat(messages, temperature=0.2, max_tokens=700, json_mode=True)
        except Exception as exc:
            logger.error("OpenAI vision call failed: %s", exc, exc_info=True)
            return CapabilityResult(success=False, error=f"OpenAI vision: {exc}")
        return CapabilityResult(
            success=True,
            data={"text": response.get("content", "")},
            source=f"vision-openai:{response.get('model', adapter.model_name)}",
        )

    @staticmethod
    def _parse_json(raw: str) -> dict | None:
        if not raw:
            return None
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except (json.JSONDecodeError, ValueError):
            return None

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
