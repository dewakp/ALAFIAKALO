"""ALAFIAModel Vision Capability — Food Photos, Lab Reports, Skin, Pills.

Phase 5 (pipeline built, no trained model yet): Food photo → dish, components, stage
  - MobileNetV3-Small; components are multi-label, so a composite names what it contains
  - Training, evaluation and verified ONNX / TFLite / Core ML export: ML/food_vision/
    (VISION_TRAINING.md)
  - Backend validation for confidence < 0.7

Phase 6 (planned): Lab report OCR → structured nutrient / biomarker data
  - Tesseract + layout parser (already partially in pipeline)
  - LayoutLM or Donut for form understanding

TODO(alafia-model): Phase 5 — train on a labelled photo collection (VISION_TRAINING.md)
TODO(alafia-model): Phase 5 — on-device inference in iOS and Android; backend ONNX path
TODO(alafia-model): Phase 6 — build LayoutLM pipeline for lab report parsing
"""

from __future__ import annotations

import base64
import io
import json
import logging
import os
import re
from typing import Any

from alafia_model.capabilities.base import BaseCapability, CapabilityResult

logger = logging.getLogger(__name__)

# Until the on-device classifier (Phase 5) ships, a vision-capable LLM reads the
# photo. WHICH one follows the chat assistant's per-environment order (§3ak):
# production asks hosted vision providers first and Ollama last; dev asks Ollama
# first and fails loudly without it.
_DEFAULT_OLLAMA_VISION_MODEL = "llava"
# One output budget for every provider. A plate rarely needs 300 tokens; the cap
# exists for a model that loops, and the cut-off repair below keeps what it wrote.
_VISION_MAX_TOKENS = 1024
# The model's copy of a photo is shrunk to this. See _fit_for_upload.
_UPLOAD_LONG_EDGE = 1568
_UPLOAD_MAX_BYTES = 2 * 1024 * 1024

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


def _vision_messages(kind: str, system_prompt: str, noun: str, encoded: list[tuple[str, str]]) -> list[dict]:
    """The same request in each hosted wire's image shape."""
    instruction = f"Analyze {noun}."
    if kind == "anthropic":
        content: list[dict[str, Any]] = [
            {"type": "image", "source": {"type": "base64", "media_type": content_type, "data": b64}}
            for b64, content_type in encoded
        ]
        content.append({"type": "text", "text": instruction})
    else:
        content = [{"type": "text", "text": instruction}]
        content.extend(
            {"type": "image_url", "image_url": {"url": f"data:{content_type};base64,{b64}"}}
            for b64, content_type in encoded
        )
    return [{"role": "system", "content": system_prompt}, {"role": "user", "content": content}]


def _fit_for_upload(raw: bytes, content_type: str) -> tuple[bytes, str]:
    """Shrink a full-resolution phone photo before it travels to a model.

    Every reader here looks at far fewer pixels than a phone captures — llava
    encodes 336x336 — so the rest is upload time: the two photos iOS sent on
    2026-09-15 were 9.6 MB of request body. This is the MODEL's copy only; the
    patient's stored photo is the original. Anything that will not decode is
    sent as it came, and the provider says what is wrong with it.
    """
    try:
        from PIL import Image, ImageOps
    except ImportError:
        return raw, content_type
    try:
        with Image.open(io.BytesIO(raw)) as original:
            if max(original.size) <= _UPLOAD_LONG_EDGE and len(raw) <= _UPLOAD_MAX_BYTES:
                return raw, content_type
            image = ImageOps.exif_transpose(original).convert("RGB")
        image.thumbnail((_UPLOAD_LONG_EDGE, _UPLOAD_LONG_EDGE), Image.LANCZOS)
        out = io.BytesIO()
        image.save(out, format="JPEG", quality=85)
        return out.getvalue(), "image/jpeg"
    except Exception:
        return raw, content_type


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
        """Available when any vision backend is configured — a hosted provider
        whose models read images, or Ollama. False only when there is none, so
        callers degrade to manual entry."""
        from alafia_model.registry.providers import enabled_providers
        return bool(os.environ.get("OLLAMA_BASE_URL")) or any(
            spec.supports_vision for spec in enabled_providers())

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
        # Until then, a vision-capable LLM, in the environment's provider order.
        images = self._collect_images(payload)
        if not images:
            return CapabilityResult(success=False, error="image_bytes required")

        if not self.is_available():
            return CapabilityResult(
                success=False,
                error=(
                    "Vision backend not configured (no image-capable provider key and no "
                    "OLLAMA_BASE_URL). Save the photo via Capture or describe the meal in text."
                ),
            )

        prompt = _FOOD_VISION_PROMPT
        if len(images) > 1:
            prompt += _MULTI_IMAGE_RULE.format(n=len(images))

        result = await self._vision_chat(images, prompt)
        if not result.success:
            return result

        raw = result.data.get("text", "")
        parsed, cut_off = self._parse_json_with_repair(raw)

        # Log what the model actually said. Without this a parse failure is
        # undiagnosable — you get "unparseable output" and no way to tell whether
        # the model refused, rambled, or answered a different question entirely.
        if parsed is None or "items" not in parsed:
            logger.warning(
                "Vision model %s returned unusable output (%d chars): %r",
                result.source, len(raw), raw[:500],
            )

        if parsed is None:
            if "{" in raw:
                # It answered in JSON and was cut off before finishing a single
                # food. Pointing at model configuration here sends the hunt to
                # the wrong place: on 2026-09-15 the model WAS llava, looping on
                # one item until the token limit ended the reply mid-word.
                error = (
                    f"The vision model ({result.source}) answered in JSON, but its reply "
                    f"({len(raw)} characters) was cut off before a single food was complete."
                )
            else:
                error = (
                    f"The vision model ({result.source}) did not return JSON. "
                    "Configure a vision model that follows an output schema "
                    "(e.g. OLLAMA_VISION_MODEL=llava)."
                )
            return CapabilityResult(success=False, source=result.source, error=error)

        # A model can return perfectly valid JSON for a completely different task.
        # moondream, for instance, answers with bounding boxes
        # ({"top": [...], "middle": [...]}) and never emits `items` at all.
        # Treating that as "no food recognised" would be a lie — the model failed,
        # the photo was fine — so fail loudly and name the cause instead.
        if "items" not in parsed:
            return CapabilityResult(
                success=False, source=result.source,
                error=(
                    f"The vision model ({result.source}) returned JSON in an "
                    f"unexpected shape (keys: {sorted(parsed)[:6]}). It is likely "
                    "not a schema-following vision model — try "
                    "OLLAMA_VISION_MODEL=llava."
                ),
            )

        items = parsed.get("items") if isinstance(parsed.get("items"), list) else []
        items, repeats = self._merge_repeated_items(items)
        # Say so when this list is not the model's whole answer. The patient
        # corrects these rows, and a silently shortened list reads as complete.
        caveats = []
        if cut_off:
            caveats.append("The analysis was cut short — check the list and add anything missing.")
        if repeats:
            caveats.append("Repeated entries for the same food were combined.")
        notes = " ".join(part for part in [str(parsed.get("notes") or ""), *caveats] if part)
        return CapabilityResult(
            success=True,
            data={
                "items": items,
                "estimated_nutrition": parsed.get("estimated_nutrition") or {},
                "notes": notes,
                "image_count": len(images),
            },
            confidence=0.5,  # LLM estimate — deliberately modest until Ph5 model
            source=result.source,
        )

    async def _vision_chat(
        self, images: list[tuple[bytes, str]], system_prompt: str
    ) -> CapabilityResult:
        """Send one or more images + an instruction to ONE vision model, in ONE call.

        The order is the environment's, as for chat (§3ak):

          production  hosted vision providers first; Ollama is the provider of
                      last resort. Production's Ollama is one scale-to-zero GPU:
                      on 2026-09-15 a cold start and two queued requests took
                      134-153 s, and llava then looped on one item until the
                      token limit cut its reply off. The slowest, least reliable
                      reader must not be the front door.
          dev         Ollama first, and REQUIRED — a hosted stand-in is how an AI
                      path goes unproven locally.

        The local database comes before all of it: the caller recalls a meal this
        patient labelled before from their own history, and sends it nowhere.
        """
        from alafia_model.capabilities.llm import _ollama_first, _ollama_required

        prepared = [_fit_for_upload(raw, content_type) for raw, content_type in images]
        encoded = [(base64.b64encode(raw).decode("ascii"), content_type) for raw, content_type in prepared]
        noun = "this image" if len(encoded) == 1 else f"these {len(encoded)} images"
        errors: list[str] = []
        has_ollama = bool(os.environ.get("OLLAMA_BASE_URL"))
        ollama_first = has_ollama and _ollama_first()

        if ollama_first:
            result = await self._ollama_vision(encoded, system_prompt, noun)
            if result.success:
                return result
            errors.append(result.error or "Ollama vision failed")
            if _ollama_required():
                return CapabilityResult(
                    success=False,
                    error=("Ollama vision failed and OLLAMA_REQUIRED is set, so no hosted "
                           f"provider was tried: {errors[-1]}"),
                )

        result = await self._hosted_vision(encoded, system_prompt, noun, errors)
        if result is not None:
            return result

        if has_ollama and not ollama_first:
            result = await self._ollama_vision(encoded, system_prompt, noun)
            if result.success:
                return result
            errors.append(result.error or "Ollama vision failed")

        return CapabilityResult(
            success=False,
            error="; ".join(errors) or "No vision backend configured",
        )

    async def _hosted_vision(
        self, encoded: list[tuple[str, str]], system_prompt: str, noun: str, errors: list[str]
    ) -> CapabilityResult | None:
        """Each hosted provider whose models read images, in selection order.

        Returns the first answer, or None when none answered (their failures are
        appended to `errors`). Nothing identifying travels with the photo: the
        request is the fixed prompt and the images — no name, no account id.
        """
        import time

        from alafia_model import telemetry
        from alafia_model.registry.providers import adapter_for, mark_cooldown, ordered_for_selection

        for spec in ordered_for_selection(require_vision=True):
            started = time.monotonic()
            try:
                response = await adapter_for(spec).chat(
                    _vision_messages(spec.kind, system_prompt, noun, encoded),
                    temperature=0.2, max_tokens=_VISION_MAX_TOKENS, json_mode=True,
                )
            except Exception as exc:
                status = getattr(getattr(exc, "response", None), "status_code", None)
                blob = str(exc).lower()
                if status in (401, 402, 403, 429) or "quota" in blob or "rate" in blob or "insufficient" in blob:
                    mark_cooldown(spec.name)
                # Name the TYPE: an httpx timeout stringifies to nothing (§3ae).
                detail = f"{type(exc).__name__}: {exc}".rstrip(": ")
                errors.append(f"{spec.name} vision: {detail}")
                telemetry.record(provider=spec.name, task="vision", tier=spec.tier, success=False,
                                 latency_ms=int((time.monotonic() - started) * 1000), error=detail[:300])
                logger.warning("Hosted vision via %s failed (%s); trying next", spec.name, detail)
                continue
            model = response.get("model") or spec.resolved_model()
            # Metadata only. The photos are the patient's and never go to a sink.
            telemetry.record(provider=spec.name, model=model, task="vision", tier=spec.tier, success=True,
                             latency_ms=int((time.monotonic() - started) * 1000),
                             tokens=response.get("tokens_used", 0))
            return CapabilityResult(
                success=True,
                data={"text": response.get("content", "")},
                source=f"vision-{spec.name}:{model}",
            )
        return None

    async def _ollama_vision(
        self, encoded: list[tuple[str, str]], system_prompt: str, noun: str
    ) -> CapabilityResult:
        """Run image understanding through Ollama (llava)."""
        from alafia_model.adapters.ollama_adapter import OllamaAdapter

        model = os.environ.get("OLLAMA_VISION_MODEL", _DEFAULT_OLLAMA_VISION_MODEL)
        # No timeout argument: OLLAMA_TIMEOUT (290 s) is this rung of the ladder.
        # The hardcoded 300 that stood here EQUALLED Cloud Run's limit (§3ae).
        adapter = OllamaAdapter(model=model)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Analyze {noun}."},
        ]
        try:
            response = await adapter.chat(
                messages,
                temperature=0.2,
                max_tokens=_VISION_MAX_TOKENS,
                json_mode=True,
                images=[b64 for b64, _ in encoded],
            )
        except Exception as exc:
            detail = f"{type(exc).__name__}: {exc}".rstrip(": ")
            logger.warning("Ollama vision failed (%s)", detail)
            return CapabilityResult(success=False, error=f"Ollama vision: {detail}")
        return CapabilityResult(
            success=True,
            data={"text": response.get("content", "")},
            source=f"vision-ollama:{response.get('model', model)}",
        )

    @staticmethod
    def _parse_json(raw: str) -> dict | None:
        """Pull a JSON object out of a vision model's reply (see _parse_json_with_repair)."""
        return VisionCapability._parse_json_with_repair(raw)[0]

    @staticmethod
    def _parse_json_with_repair(raw: str) -> tuple[dict | None, bool]:
        """Pull a JSON object out of a vision model's reply.

        Returns (object, cut_off). cut_off is True when the object had to be
        recovered from a reply the token limit ended part-way, so the caller can
        say the list may be incomplete.

        Models wrap JSON in prose and ```json fences, and sometimes get cut off
        mid-object by the token limit. Each strategy below is a failure actually
        seen from a local vision model, so they are tried in order rather than
        assuming a clean response.
        """
        if not raw:
            return None, False

        candidates: list[str] = []

        # 1. Whole reply is JSON (what `format: json` is supposed to give).
        candidates.append(raw.strip())

        # 2. Fenced block: ```json { ... } ```
        fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
        if fence:
            candidates.append(fence.group(1))

        # 3. Greedy first-brace-to-last-brace (prose on both sides).
        greedy = re.search(r"\{.*\}", raw, re.DOTALL)
        if greedy:
            candidates.append(greedy.group(0))

        for candidate in candidates:
            try:
                obj = json.loads(candidate)
            except (json.JSONDecodeError, ValueError):
                continue
            if isinstance(obj, dict):
                return obj, False

        # 4. Cut off by the token limit — an object that opens and never closes.
        repaired = VisionCapability._close_truncated(raw)
        if repaired is not None:
            logger.info("Recovered truncated JSON from vision model")
            return repaired, True
        return None, False

    @staticmethod
    def _close_truncated(raw: str) -> dict | None:
        """Recover the complete part of a JSON object the token limit cut off.

        The previous repair counted every opening bracket in the text and closed
        the LAST ones — which, in a list of finished items, are brackets already
        closed. A reply cut after its third complete food got `}}` where it
        needed `]}`, so every cut-off list failed: 0 of 84 cut points recovered
        on the reply production logged on 2026-09-15. This tracks the brackets
        that are actually still open.

        Two attempts, in order:
          1. close at the very end — keeps a final value that happened to finish
             (`..."estimated_portion": "1 cup"`);
          2. otherwise cut back to where a value last finished (a closed item, or
             the comma after one), dropping the half-written tail rather than
             guessing at it. A half-typed "Fried Chi" is worse than no row.
        """
        start = raw.find("{")
        if start == -1:
            return None
        text = raw[start:]
        owed: list[str] = []  # closers still owed, innermost last
        in_string = escaped = False
        safe_end, safe_owed = None, None
        for i, ch in enumerate(text):
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch in "{[":
                owed.append("}" if ch == "{" else "]")
            elif ch in "}]":
                if not owed or owed[-1] != ch:
                    return None  # malformed, not merely cut off
                owed.pop()
                if not owed:
                    return None  # the object closed; the parses above already judged it
                safe_end, safe_owed = i + 1, list(owed)
            elif ch == "," and owed:
                safe_end, safe_owed = i, list(owed)
        if not owed:
            return None

        attempts = []
        if not in_string:
            attempts.append((text.rstrip().rstrip(","), owed))
        if safe_end is not None:
            attempts.append((text[:safe_end].rstrip().rstrip(","), safe_owed))
        for body, closers in attempts:
            try:
                obj = json.loads(body + "".join(reversed(closers)))
            except (json.JSONDecodeError, ValueError):
                continue
            if isinstance(obj, dict):
                return obj
        return None

    @staticmethod
    def _merge_repeated_items(items: list) -> tuple[list[dict], int]:
        """Collapse a food listed again with the same portion. Returns (items, repeats).

        That is the model looping, not a second serving: on 2026-09-15 llava wrote
        `{"name": "Fried Chicken", "estimated_portion": "2 pieces"}` over and over
        for photos of one plate until the token limit stopped it. The prompt
        already says a second serving must be genuinely separate, and it would
        carry its own portion.

        A row naming an already-listed food with NO portion is the half-written
        tail of that loop — the cut-off repair closes `{"name": "Fried Chicken",`
        as a row of its own — so it counts as a repeat too, and gives way if the
        complete row comes after it. Non-object entries are dropped: every
        consumer reads items as objects.
        """
        kept: list[dict] = []
        seen: set[tuple[str, str]] = set()
        named: set[str] = set()
        without_portion: dict[str, int] = {}  # name -> index of its row with no amount
        repeats = 0
        for item in items:
            if not isinstance(item, dict):
                continue
            name = " ".join(str(item.get("name") or "").split()).lower()
            portion = " ".join(str(item.get("estimated_portion") or "").split()).lower()
            if not name:
                kept.append(item)
                continue
            if (name, portion) in seen or (not portion and name in named):
                repeats += 1
                continue
            if portion and name in without_portion:
                kept[without_portion.pop(name)] = item
                seen.add((name, portion))
                repeats += 1
                continue
            if not portion:
                without_portion[name] = len(kept)
            seen.add((name, portion))
            named.add(name)
            kept.append(item)
        return kept, repeats

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
        """The Phase 5 on-device food classifier. Pipeline: ML/food_vision/."""
        return {
            "architecture": "MobileNetV3-Small with three outputs: dish (softmax), "
                            "components (sigmoid, multi-label), stage (softmax)",
            "base_weights": "imagenet",
            "fine_tune_dataset": "a labelled photo folder (labels.csv) — see VISION_TRAINING.md",
            "classes": "derived from the labels; there is no fixed class list",
            "input_size": [224, 224, 3],
            "export_targets": ["Core ML (iOS)", "TFLite (Android)", "ONNX (backend)"],
            "training_script": "ML/scripts/train_food_vision.py",
            "phase": 5,
            "status": "pipeline built; awaiting a labelled photo collection",
        }
