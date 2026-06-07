"""ALAFIAModel capabilities package."""

from alafia_model.capabilities.base import BaseCapability, CapabilityResult
from alafia_model.capabilities.nlm import NLMCapability
from alafia_model.capabilities.llm import LLMCapability
from alafia_model.capabilities.vision import VisionCapability
from alafia_model.capabilities.voice import VoiceCapability
from alafia_model.capabilities.video import VideoCapability

__all__ = [
    "BaseCapability",
    "CapabilityResult",
    "NLMCapability",
    "LLMCapability",
    "VisionCapability",
    "VoiceCapability",
    "VideoCapability",
]
