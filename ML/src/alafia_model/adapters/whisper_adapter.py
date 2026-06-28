"""Whisper adapter — multilingual speech-to-text.

Mirrors the Ollama → OpenAI fallback pattern used for the LLM:

  PRIMARY  : a self-hosted, OpenAI-compatible Whisper server (faster-whisper /
             whisper.cpp / whisper-asr-webservice) at ``WHISPER_BASE_URL``.
             Keeps audio (PHI) on ALAFIA infrastructure.
  FALLBACK : OpenAI's hosted Whisper (``/v1/audio/transcriptions``) when
             ``OPENAI_API_KEY`` is set and no local server is reachable.

Both expose the same multipart endpoint (``file``, ``model``, ``language``,
``response_format=json``) so a single code path serves both.

TODO(alafia-model): Phase 7 — swap WHISPER_MODEL for a fine-tune on Nigerian
    English + Yoruba/Hausa/Igbo clinical speech once the dataset is recorded.
TODO(alafia-model): Phase 7 — on-device whisper.cpp (Core ML / TFLite) for offline.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_OPENAI_TRANSCRIBE_URL = "https://api.openai.com/v1/audio/transcriptions"


class WhisperAdapter:
    """Speech-to-text via an OpenAI-compatible Whisper endpoint."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        timeout: float = 120.0,
    ) -> None:
        # A local server is optional; when unset we go straight to OpenAI.
        self.base_url = (base_url or os.environ.get("WHISPER_BASE_URL", "")).rstrip("/")
        self.model = model or os.environ.get("WHISPER_MODEL", "whisper-1")
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.timeout = timeout

    @property
    def model_name(self) -> str:
        return self.model

    def is_available(self) -> bool:
        """True when at least one backend (local server or OpenAI key) is configured."""
        return bool(self.base_url or self._api_key)

    async def transcribe(
        self,
        audio_bytes: bytes,
        language: str | None = None,
        filename: str = "audio.wav",
    ) -> dict[str, Any]:
        """Transcribe audio. Returns {text, language, model, source}.

        Tries the local server first, then OpenAI. Raises RuntimeError if neither
        is configured or both fail.
        """
        if not audio_bytes:
            raise RuntimeError("No audio provided")

        errors: list[str] = []

        # 1) Local / self-hosted OpenAI-compatible server (PHI stays in-house)
        if self.base_url:
            try:
                return await self._post(
                    f"{self.base_url}/v1/audio/transcriptions",
                    audio_bytes, language, filename, headers=None, source="local",
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(f"local: {exc}")
                logger.warning("Local Whisper failed (%s); trying OpenAI fallback", exc)

        # 2) OpenAI hosted Whisper fallback
        if self._api_key:
            try:
                return await self._post(
                    _OPENAI_TRANSCRIBE_URL, audio_bytes, language, filename,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    source="openai", model_override="whisper-1",
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(f"openai: {exc}")
                logger.error("OpenAI Whisper failed: %s", exc, exc_info=True)

        raise RuntimeError(
            "No speech-to-text backend available. Set WHISPER_BASE_URL (local) or "
            "OPENAI_API_KEY (fallback). " + ("; ".join(errors) if errors else "")
        )

    async def _post(
        self,
        url: str,
        audio_bytes: bytes,
        language: str | None,
        filename: str,
        headers: dict[str, str] | None,
        source: str,
        model_override: str | None = None,
    ) -> dict[str, Any]:
        data = {"model": model_override or self.model, "response_format": "json"}
        # "auto" / empty → let Whisper auto-detect the language.
        if language and language not in ("auto", ""):
            data["language"] = language
        files = {"file": (filename, audio_bytes, "application/octet-stream")}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(url, data=data, files=files, headers=headers)
            resp.raise_for_status()
            body = resp.json()

        return {
            "text": (body.get("text") or "").strip(),
            "language": body.get("language") or language,
            "model": model_override or self.model,
            "source": source,
        }
