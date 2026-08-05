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

    async def fake_vision_chat(self, images, system_prompt):
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
    assert result.data["image_count"] == 1


def test_food_photo_unparseable(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    cap = VisionCapability()

    async def fake_vision_chat(self, images, system_prompt):
        from alafia_model.capabilities.base import CapabilityResult
        return CapabilityResult(success=True, data={"text": "sorry I cannot tell"}, source="x")

    monkeypatch.setattr(VisionCapability, "_vision_chat", fake_vision_chat)
    result = _run(cap.infer({"task": "food_photo_nutrition", "image_bytes": b"img"}))
    assert not result.success
    # Message names the offending model and the fix, rather than just "unparseable".
    assert "did not return JSON" in (result.error or "")
    assert "llava" in (result.error or "")


# ── Multi-image: several shots of ONE meal → ONE combined reading ──────


def test_collect_images_prefers_multi_and_falls_back():
    collect = VisionCapability._collect_images
    # multi-image entries win, per-entry content_type honoured, default applied
    assert collect({
        "images": [
            {"image_bytes": b"a", "content_type": "image/png"},
            {"image_bytes": b"b"},
        ],
        "content_type": "image/jpeg",
    }) == [(b"a", "image/png"), (b"b", "image/jpeg")]
    # legacy single-image callers still work
    assert collect({"image_bytes": b"z", "content_type": "image/webp"}) == [(b"z", "image/webp")]
    # empty / malformed lists fall back to the single field
    assert collect({"images": [], "image_bytes": b"z"}) == [(b"z", "image/jpeg")]
    assert collect({"images": [{"nope": 1}], "image_bytes": b"z"}) == [(b"z", "image/jpeg")]
    # nothing usable
    assert collect({}) == []
    assert collect({"images": [{"image_bytes": b""}]}) == []


def test_multi_image_sends_one_call_with_all_images(monkeypatch):
    """Three photos must produce ONE model call carrying all three — not three
    calls whose results get summed (that triple-counts a single plate)."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    cap = VisionCapability()
    calls = []

    async def fake_vision_chat(self, images, system_prompt):
        from alafia_model.capabilities.base import CapabilityResult
        calls.append((images, system_prompt))
        return CapabilityResult(
            success=True,
            data={"text": '{"items": [{"name": "jollof rice"}], '
                          '"estimated_nutrition": {"calories": 330}, "notes": ""}'},
            source="vision-ollama:llava",
        )

    monkeypatch.setattr(VisionCapability, "_vision_chat", fake_vision_chat)
    result = _run(cap.infer({
        "task": "food_photo_nutrition",
        "images": [
            {"image_bytes": b"one", "content_type": "image/jpeg"},
            {"image_bytes": b"two", "content_type": "image/jpeg"},
            {"image_bytes": b"three", "content_type": "image/png"},
        ],
    }))

    assert result.success
    assert len(calls) == 1, "multiple photos must be analysed in a single call"
    sent_images, prompt = calls[0]
    assert [raw for raw, _ in sent_images] == [b"one", b"two", b"three"]
    # The anti-double-count instruction is attached only for multi-image input.
    assert "3 photos of THE SAME meal" in prompt
    assert "Do NOT count a dish more than once" in prompt
    # One combined reading, not one per photo.
    assert result.data["estimated_nutrition"]["calories"] == 330
    assert result.data["image_count"] == 3


def test_single_image_omits_multi_image_rule(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    cap = VisionCapability()
    prompts = []

    async def fake_vision_chat(self, images, system_prompt):
        from alafia_model.capabilities.base import CapabilityResult
        prompts.append(system_prompt)
        return CapabilityResult(success=True, data={"text": '{"items": []}'}, source="x")

    monkeypatch.setattr(VisionCapability, "_vision_chat", fake_vision_chat)
    _run(cap.infer({"task": "food_photo_nutrition", "image_bytes": b"img"}))
    assert "THE SAME meal" not in prompts[0]


def test_parse_json_extracts_embedded():
    obj = VisionCapability._parse_json('text before {"items": []} text after')
    assert obj == {"items": []}


# ── Parser robustness + wrong-schema detection ────────────────────────
# Every case below is a real reply shape observed from a local vision model.


@pytest.mark.parametrize("label,raw,expect_parsed", [
    ("clean", '{"items":[{"name":"rice"}],"notes":"ok"}', True),
    ("markdown fenced", '```json\n{"items":[{"name":"rice"}]}\n```', True),
    ("prose around json", 'Sure!\n{"items":[]}\nHope that helps.', True),
    # Cut off by the token limit — previously a hard failure.
    ("truncated", '{"items":[{"name":"jollof rice","estimated_portion":"1 cup"', True),
    ("truncated nested", '{"items":[{"name":"beans"}],"estimated_nutrition":{"calories":300', True),
    ("pure prose", 'I see a plate of rice and beans.', False),
    ("empty", '', False),
])
def test_parse_json_handles_real_model_replies(label, raw, expect_parsed):
    assert (VisionCapability._parse_json(raw) is not None) is expect_parsed, label


def test_wrong_schema_fails_loudly_instead_of_reporting_no_food(monkeypatch):
    """moondream answers the food prompt with bounding boxes: valid JSON, wrong
    task, no `items` key. Reporting that as "no food recognised" blames the
    photo for a model misconfiguration — it must fail and name the cause."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    cap = VisionCapability()

    async def fake_vision_chat(self, images, system_prompt):
        from alafia_model.capabilities.base import CapabilityResult
        return CapabilityResult(
            success=True,
            data={"text": '{"top":[0.44,0.32],"middle":[0.36,0.34],"size":0.25}'},
            source="vision-ollama:moondream",
        )

    monkeypatch.setattr(VisionCapability, "_vision_chat", fake_vision_chat)
    result = _run(cap.infer({"task": "food_photo_nutrition", "image_bytes": b"img"}))

    assert not result.success
    assert "unexpected shape" in (result.error or "")
    assert "llava" in (result.error or "")      # tells the operator the fix


def test_truncated_json_recovers_partial_items(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    cap = VisionCapability()

    async def fake_vision_chat(self, images, system_prompt):
        from alafia_model.capabilities.base import CapabilityResult
        return CapabilityResult(
            success=True,
            data={"text": '{"items":[{"name":"jollof rice","estimated_portion":"1 cup"'},
            source="vision-ollama:llava",
        )

    monkeypatch.setattr(VisionCapability, "_vision_chat", fake_vision_chat)
    result = _run(cap.infer({"task": "food_photo_nutrition", "image_bytes": b"img"}))
    assert result.success
    assert result.data["items"][0]["name"] == "jollof rice"
