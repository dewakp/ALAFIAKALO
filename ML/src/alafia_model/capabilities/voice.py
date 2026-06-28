"""ALAFIAModel Voice Capability — Speech → Clinical NLP (Phase 7).

Pipeline: audio → Whisper (multilingual transcription) → LLM clinical extraction.

  - Transcription via the Whisper adapter (self-hosted OpenAI-compatible server
    first, OpenAI hosted Whisper as fallback). Auto-detects language; supports
    English, Yoruba, Hausa, Igbo, Nigerian Pidgin, French, Swahili, Portuguese.
  - Clinical NLP runs the transcript through the LLM capability with a structured
    extraction prompt → symptoms, medications, vitals, complaints, follow-ups.

TODO(alafia-model): Phase 7 — fine-tune Whisper on Nigerian English + Yoruba/Hausa
    clinical speech; on-device whisper.cpp (Core ML / TFLite) for offline use.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from alafia_model.capabilities.base import BaseCapability, CapabilityResult

logger = logging.getLogger(__name__)

# Languages Whisper covers that ALAFIA targets (ISO-639-1, plus pcm pidgin).
SUPPORTED_LANGUAGES = ["en", "yo", "ha", "ig", "pcm", "fr", "sw", "pt"]

_CLINICAL_SYSTEM_PROMPT = """\
You are ALAFIA's clinical NLP extractor. You receive a transcript of a patient
speaking about their health (often in West-African English, Pidgin, Yoruba, Hausa
or Igbo). Extract the clinically relevant information into STRICT JSON.

Return ONLY a JSON object with exactly these keys:
{
  "summary": "one-sentence plain-language summary",
  "symptoms": ["symptom phrases mentioned"],
  "medications": [{"name": "drug", "dose": "amount if stated or null"}],
  "vitals": {"blood_pressure": null, "blood_glucose": null, "weight": null, "temperature": null, "heart_rate": null},
  "complaints": ["chief complaints"],
  "follow_up": ["any follow-up actions or questions for a provider"]
}

Rules:
- Use null / empty arrays when nothing is mentioned. Never invent data.
- Do NOT diagnose. Only extract what the patient actually said.
- Keep medication names and doses verbatim where possible.
"""


class VoiceCapability(BaseCapability):
    """Voice capability: speech → clinical NLP.

    Supported tasks:
        "transcribe"          → audio → text (+ detected language)
        "transcribe_and_nlm"  → audio → text → structured clinical data
        "voice_log_meal"      → spoken meal description → text for the NLM pipeline
    """

    capability_id = "voice"
    version = "1.0.0-phase7"
    is_implemented = True

    def __init__(self) -> None:
        super().__init__()
        self._whisper: Any = None
        self._llm: Any = None

    def _get_whisper(self) -> Any:
        if self._whisper is None:
            from alafia_model.adapters.whisper_adapter import WhisperAdapter
            self._whisper = WhisperAdapter()
        return self._whisper

    def _get_llm(self) -> Any:
        if self._llm is None:
            from alafia_model.capabilities.llm import LLMCapability
            self._llm = LLMCapability()
        return self._llm

    def is_available(self) -> bool:
        try:
            return self._get_whisper().is_available()
        except Exception:  # pragma: no cover
            return False

    async def infer(self, payload: dict[str, Any]) -> CapabilityResult:
        task = payload.get("task", "transcribe")
        if task not in ("transcribe", "transcribe_and_nlm", "voice_log_meal"):
            return CapabilityResult(success=False, error=f"Unknown voice task: {task}")

        audio = payload.get("audio_bytes")
        if not audio:
            return CapabilityResult(success=False, error="No audio_bytes provided")

        language = payload.get("language") or None

        # 1) Transcribe
        try:
            tr = await self._get_whisper().transcribe(audio, language=language)
        except Exception as exc:  # noqa: BLE001
            logger.error("Voice transcription failed: %s", exc, exc_info=True)
            return CapabilityResult(success=False, error=str(exc))

        transcript = tr.get("text", "")
        detected = tr.get("language")
        data: dict[str, Any] = {"transcript": transcript, "language": detected}
        source = f"whisper:{tr.get('source')}"

        if not transcript:
            return CapabilityResult(success=True, data=data, confidence=0.3, source=source)

        # 2a) Meal voice logging → hand the transcript to the NLM nutrition pipeline.
        if task == "voice_log_meal":
            data["meal_description"] = transcript
            return CapabilityResult(success=True, data=data, confidence=0.7, source=source)

        # 2b) Clinical NLP extraction (transcribe_and_nlm)
        if task == "transcribe_and_nlm":
            data["clinical"] = await self._extract_clinical(transcript)

        return CapabilityResult(success=True, data=data, confidence=0.75, source=source)

    async def _extract_clinical(self, transcript: str) -> dict[str, Any]:
        """Run the transcript through the LLM to produce structured clinical JSON."""
        messages = [
            {"role": "system", "content": _CLINICAL_SYSTEM_PROMPT},
            {"role": "user", "content": f"Transcript:\n{transcript}"},
        ]
        result = await self._get_llm().infer({
            "task": "chat", "messages": messages, "temperature": 0.1, "json_mode": True,
        })
        if not result.success:
            return {"error": result.error or "clinical extraction unavailable", "raw": None}

        raw = (result.data or {}).get("text", "")
        parsed = _safe_json(raw)
        return parsed if parsed is not None else {"error": "unparseable", "raw": raw[:500]}

    @classmethod
    def get_model_spec(cls) -> dict:
        return {
            "transcription_model": "whisper (configurable via WHISPER_MODEL)",
            "on_device_model": "whisper.cpp (Core ML / TFLite) — planned",
            "supported_languages": SUPPORTED_LANGUAGES,
            "pipeline": "audio → Whisper → LLM clinical extractor",
            "phase": 7,
            "status": "implemented",
        }


def _safe_json(raw: str) -> dict[str, Any] | None:
    """Parse JSON, tolerating markdown code fences."""
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                return None
    return None
