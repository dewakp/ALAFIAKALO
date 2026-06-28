"""Tests for the Vision capability (food photo → nutrition estimate).

The OpenAI vision adapter is stubbed so these run offline. We verify graceful
degradation when no backend is configured, JSON parsing, and the success path.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

ML_SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(ML_SRC))

from alafia_model.capabilities.vision import VisionCapability


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_requires_image_bytes():
    cap = VisionCapability()
    result = _run(cap.infer({"task": "food_photo_nutrition"}))
    assert not result.success
    assert "image_bytes" in (result.error or "")


def test_degrades_without_backend(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    cap = VisionCapability()
    assert cap.is_available() is False
    result = _run(cap.infer({"task": "food_photo_nutrition", "image_bytes": b"\xff\xd8\xff"}))
    assert not result.success
    assert "not configured" in (result.error or "")


def test_is_available_with_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert VisionCapability().is_available() is True


def test_food_photo_success(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    cap = VisionCapability()

    async def fake_vision_chat(self, image_bytes, content_type, system_prompt):
        from alafia_model.capabilities.base import CapabilityResult
        return CapabilityResult(
            success=True,
            data={"text": '{"items": [{"name": "jollof rice", "estimated_portion": "1 cup", '
                          '"confidence": 0.8}], "estimated_nutrition": {"calories": 330}, '
                          '"notes": "looks like a full plate"}'},
            source="vision-llm:gpt-4o-mini",
        )

    monkeypatch.setattr(VisionCapability, "_vision_chat", fake_vision_chat)
    result = _run(cap.infer({"task": "food_photo_nutrition", "image_bytes": b"img"}))
    assert result.success
    assert result.data["items"][0]["name"] == "jollof rice"
    assert result.data["estimated_nutrition"]["calories"] == 330


def test_food_photo_unparseable(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    cap = VisionCapability()

    async def fake_vision_chat(self, image_bytes, content_type, system_prompt):
        from alafia_model.capabilities.base import CapabilityResult
        return CapabilityResult(success=True, data={"text": "sorry I cannot tell"}, source="x")

    monkeypatch.setattr(VisionCapability, "_vision_chat", fake_vision_chat)
    result = _run(cap.infer({"task": "food_photo_nutrition", "image_bytes": b"img"}))
    assert not result.success
    assert "unparseable" in (result.error or "")


def test_parse_json_extracts_embedded():
    obj = VisionCapability._parse_json('text before {"items": []} text after')
    assert obj == {"items": []}
