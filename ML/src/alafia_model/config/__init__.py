"""ALAFIAModel configuration."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

_PACKAGE_ROOT = Path(__file__).parent.parent


@dataclass
class ALAFIAModelConfig:
    """Runtime configuration for ALAFIAModel.

    All values can be overridden via environment variables with the
    ``ALAFIA_MODEL_`` prefix (e.g. ``ALAFIA_MODEL_OLLAMA_BASE_URL``).
    """

    # Ollama (primary LLM adapter)
    ollama_base_url: str = field(
        default_factory=lambda: os.environ.get("ALAFIA_MODEL_OLLAMA_BASE_URL", "http://localhost:11434")
    )
    ollama_model: str = field(
        default_factory=lambda: os.environ.get("ALAFIA_MODEL_OLLAMA_MODEL", "llama3.1:8b")
    )
    ollama_timeout: float = field(
        default_factory=lambda: float(os.environ.get("ALAFIA_MODEL_OLLAMA_TIMEOUT", "120"))
    )

    # OpenAI (cloud fallback — TEMPORARY until Phase 3)
    openai_api_key: str = field(
        default_factory=lambda: os.environ.get("OPENAI_API_KEY", "")
    )
    openai_model: str = field(
        default_factory=lambda: os.environ.get("ALAFIA_MODEL_OPENAI_MODEL", "gpt-4o-mini")
    )

    # Model artifacts
    models_dir: Path = field(
        default_factory=lambda: Path(
            os.environ.get("ALAFIA_MODEL_MODELS_DIR", str(_PACKAGE_ROOT / ".." / ".." / "models"))
        ).resolve()
    )

    # Logging
    log_level: str = field(
        default_factory=lambda: os.environ.get("ALAFIA_MODEL_LOG_LEVEL", "INFO")
    )

    def load_roadmap(self) -> dict:
        """Load the capability roadmap JSON."""
        roadmap_path = _PACKAGE_ROOT / "registry" / "roadmap.json"
        with open(roadmap_path) as f:
            return json.load(f)


# Module-level singleton
_config: ALAFIAModelConfig | None = None


def get_config() -> ALAFIAModelConfig:
    """Return the module-level config singleton."""
    global _config
    if _config is None:
        _config = ALAFIAModelConfig()
    return _config
