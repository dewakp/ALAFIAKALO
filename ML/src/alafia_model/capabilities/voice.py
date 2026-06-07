"""ALAFIAModel Voice Capability — Speech → Clinical NLP.

Phase 7 (planned): speech audio → clinical text transcription + NLP.
  - Whisper (openai/whisper-large-v3) for multilingual transcription
    supporting English, Yoruba, Hausa, Igbo, Pidgin, French, Swahili
  - Pipeline: audio → Whisper transcript → NLM clinical parser
  - On-device: whisper.cpp (iOS/Android) for offline capability

TODO(alafia-model): Phase 7 — integrate whisper.cpp for on-device transcription
TODO(alafia-model): Phase 7 — build Whisper fine-tune dataset for Nigerian English + Yoruba/Hausa
"""

from __future__ import annotations

import logging
from typing import Any

from alafia_model.capabilities.base import BaseCapability, CapabilityResult

logger = logging.getLogger(__name__)

# Languages with planned support
SUPPORTED_LANGUAGES = [
    "en",        # English
    "yo",        # Yoruba
    "ha",        # Hausa
    "ig",        # Igbo
    "pcm",       # Nigerian Pidgin (Creole)
    "fr",        # French (West Africa)
    "sw",        # Swahili
    "pt",        # Portuguese (Lusophone Africa)
]


class VoiceCapability(BaseCapability):
    """Voice capability for speech → clinical NLP pipeline.

    Supported tasks (all PLANNED):
        "transcribe"         → audio → text [PLANNED Ph7]
        "transcribe_and_nlm" → audio → text → clinical structured data [PLANNED Ph7]
        "voice_log_meal"     → spoken meal description → NutritionLog [PLANNED Ph7]
    """

    capability_id = "voice"
    version = "0.1.0-scaffold"
    is_implemented = False

    async def infer(self, payload: dict[str, Any]) -> CapabilityResult:
        task = payload.get("task", "transcribe")

        if task in ("transcribe", "transcribe_and_nlm", "voice_log_meal"):
            return self._scaffold_stub(task)

        return CapabilityResult(
            success=False,
            error=f"Unknown voice task: {task}",
        )

    def _scaffold_stub(self, task: str) -> CapabilityResult:
        return CapabilityResult(
            success=False,
            error=(
                f"Voice task '{task}' is planned for ALAFIAModel Phase 7. "
                f"Planned languages: {', '.join(SUPPORTED_LANGUAGES)}. "
                "See docs/AI_ENGINE_ARCHITECTURE.md for the roadmap."
            ),
        )

    @classmethod
    def get_model_spec(cls) -> dict:
        """Return the specification for the voice pipeline to be built."""
        return {
            "transcription_model": "openai/whisper-large-v3",
            "on_device_model": "whisper.cpp (Core ML / TFLite)",
            "supported_languages": SUPPORTED_LANGUAGES,
            "pipeline": "audio → Whisper → NLM clinical parser",
            "training_data": "Nigerian health conversations (to be recorded)",
            "phase": 7,
            "status": "planned",
        }
