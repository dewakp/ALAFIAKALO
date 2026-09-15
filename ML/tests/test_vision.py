"""Tests for the Vision capability (food photo → nutrition estimate).

The OpenAI vision adapter is stubbed so these run offline. We verify graceful
degradation when no backend is configured, JSON parsing, and the success path.
"""

from __future__ import annotations

import asyncio
import base64
import io
import sys
from pathlib import Path

import pytest

ML_SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(ML_SRC))

from alafia_model.capabilities import vision as vision_module
from alafia_model.capabilities.vision import VisionCapability


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_requires_image_bytes():
    cap = VisionCapability()
    result = _run(cap.infer({"task": "food_photo_nutrition"}))
    assert not result.success
    assert "image_bytes" in (result.error or "")


def test_degrades_without_backend(monkeypatch):
    from alafia_model.registry.providers import PROVIDERS
    for spec in PROVIDERS:
        if spec.supports_vision:
            monkeypatch.delenv(spec.api_key_env, raising=False)
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


# ── 2026-09-15 production failure: a looping list cut off by the token limit ──
# llava repeated one item until num_predict (700) ended the reply mid-word. The
# old repair recovered 0 of 84 cut points and /ai/vision answered 503 — on iOS,
# "Image analysis unavailable" after two and a half minutes.

_LOOPED_ITEM = '    {"name": "Fried Chicken", "estimated_portion": "2 pieces", "confidence": 0.9},\n'
_LOOPED_REPLY = '{\n  "items": [\n' + _LOOPED_ITEM * 60


def test_a_looping_list_cut_off_at_any_point_is_recovered():
    period = len(_LOOPED_ITEM)
    unrecovered = []
    for cut in range(1870 - period, 1871):
        parsed, cut_off = VisionCapability._parse_json_with_repair(_LOOPED_REPLY[:cut])
        if parsed is None or not parsed.get("items") or not cut_off:
            unrecovered.append(cut)
    assert unrecovered == []


def test_a_half_written_value_is_dropped_not_guessed():
    parsed, cut_off = VisionCapability._parse_json_with_repair(
        '{"items": [{"name": "Rice", "estimated_portion": "1 cup"}, {"name": "Fried Chi')
    assert cut_off is True
    assert parsed == {"items": [{"name": "Rice", "estimated_portion": "1 cup"}]}


def test_a_complete_reply_is_not_reported_as_cut_off():
    parsed, cut_off = VisionCapability._parse_json_with_repair('{"items": [{"name": "Rice"}], "notes": ""}')
    assert parsed["items"] == [{"name": "Rice"}]
    assert cut_off is False


def test_the_logged_production_reply_yields_one_food_and_says_why(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    cap = VisionCapability()

    async def fake_vision_chat(self, images, system_prompt):
        from alafia_model.capabilities.base import CapabilityResult
        return CapabilityResult(success=True, data={"text": _LOOPED_REPLY[:1870]}, source="vision-ollama:llava")

    monkeypatch.setattr(VisionCapability, "_vision_chat", fake_vision_chat)
    result = _run(cap.infer({"task": "food_photo_nutrition",
                             "images": [{"image_bytes": b"one"}, {"image_bytes": b"two"}]}))
    assert result.success, result.error
    assert [item["name"] for item in result.data["items"]] == ["Fried Chicken"]
    assert "cut short" in result.data["notes"]
    assert "combined" in result.data["notes"]


def test_distinct_foods_and_portions_are_not_merged():
    items, repeats = VisionCapability._merge_repeated_items([
        {"name": "Rice", "estimated_portion": "1 cup"},
        {"name": "rice ", "estimated_portion": "1 cup"},
        {"name": "Rice", "estimated_portion": "2 cups"},
        {"name": "Stew", "estimated_portion": "1 cup"},
        {"name": "Stew"},  # the half-written tail of a repeated row
        "not an object",
    ])
    assert [(i["name"], i["estimated_portion"]) for i in items] == [
        ("Rice", "1 cup"), ("Rice", "2 cups"), ("Stew", "1 cup")]
    assert repeats == 2


def test_a_row_without_an_amount_gives_way_to_the_same_food_with_one():
    items, repeats = VisionCapability._merge_repeated_items([
        {"name": "Beans"}, {"name": "Beans", "estimated_portion": "1 cup"}])
    assert items == [{"name": "Beans", "estimated_portion": "1 cup"}]
    assert repeats == 1


def test_a_reply_cut_off_before_any_food_says_so_instead_of_blaming_configuration(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    cap = VisionCapability()

    async def fake_vision_chat(self, images, system_prompt):
        from alafia_model.capabilities.base import CapabilityResult
        return CapabilityResult(success=True, data={"text": '{\n  "items": [\n    {"na'},
                                source="vision-ollama:llava")

    monkeypatch.setattr(VisionCapability, "_vision_chat", fake_vision_chat)
    result = _run(cap.infer({"task": "food_photo_nutrition", "image_bytes": b"img"}))
    assert not result.success
    assert "cut off before a single food" in (result.error or "")
    assert "Configure" not in (result.error or "")


# ── Provider order. Production: local DB (the caller), hosted, then Ollama ───


class _FakeAdapter:
    def __init__(self, name, calls, *, fail=False):
        self.name, self.calls, self.fail = name, calls, fail
        self.model_name = f"{name}-model"

    async def chat(self, messages, **kwargs):
        self.calls.append((self.name, messages, kwargs))
        if self.fail:
            raise RuntimeError(f"{self.name} is down")
        return {"content": '{"items": [{"name": "rice"}]}', "model": self.model_name, "tokens_used": 3}


@pytest.fixture
def providers(monkeypatch):
    """A hosted provider of each wire kind plus Ollama, all fake, order chosen per test."""
    from alafia_model.registry.providers import ProviderSpec

    specs = {
        "anthropic": ProviderSpec("anthropic", "", "ANTHROPIC_API_KEY", "claude", "paid",
                                  kind="anthropic", supports_vision=True),
        "openai": ProviderSpec("openai", "https://x/v1", "OPENAI_API_KEY", "gpt", "paid", supports_vision=True),
    }

    def build(order=("anthropic",), fail=(), ollama_first=False, ollama_required=False):
        calls, requested = [], {}

        def fake_ordered(**kwargs):
            requested.update(kwargs)
            return [specs[name] for name in order]

        monkeypatch.setattr("alafia_model.registry.providers.ordered_for_selection", fake_ordered)
        monkeypatch.setattr("alafia_model.registry.providers.adapter_for",
                            lambda spec: _FakeAdapter(spec.name, calls, fail=spec.name in fail))
        monkeypatch.setattr("alafia_model.adapters.ollama_adapter.OllamaAdapter",
                            lambda **kwargs: _FakeAdapter("ollama", calls, fail="ollama" in fail))
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama")
        monkeypatch.setenv("OLLAMA_FIRST", "true" if ollama_first else "false")
        monkeypatch.setenv("OLLAMA_REQUIRED", "true" if ollama_required else "false")
        return calls, requested

    return build


def _ask(images=((b"img", "image/jpeg"),)):
    return _run(VisionCapability()._vision_chat(list(images), "prompt"))


def test_production_reads_the_photo_with_a_hosted_provider_and_never_wakes_ollama(providers):
    calls, requested = providers(order=("anthropic",))
    result = _ask()
    assert result.success
    assert result.source == "vision-anthropic:anthropic-model"
    assert [name for name, _, _ in calls] == ["anthropic"]
    assert requested == {"require_vision": True}


def test_ollama_is_the_provider_of_last_resort_in_production(providers):
    calls, _ = providers(order=("anthropic", "openai"), fail=("anthropic", "openai"))
    result = _ask()
    assert result.success
    assert result.source.startswith("vision-ollama:")
    assert [name for name, _, _ in calls] == ["anthropic", "openai", "ollama"]


def test_dev_asks_ollama_first_and_refuses_a_hosted_stand_in(providers):
    calls, _ = providers(order=("anthropic",), fail=("ollama",), ollama_first=True, ollama_required=True)
    result = _ask()
    assert not result.success
    assert [name for name, _, _ in calls] == ["ollama"]
    assert "OLLAMA_REQUIRED" in result.error


def test_every_failure_is_named_when_nothing_answers(providers):
    providers(order=("anthropic",), fail=("anthropic", "ollama"))
    result = _ask()
    assert not result.success
    assert "anthropic vision: RuntimeError: anthropic is down" in result.error
    assert "Ollama vision: RuntimeError: ollama is down" in result.error


def test_each_wire_receives_the_photo_in_its_own_shape(providers):
    calls, _ = providers(order=("anthropic", "openai"), fail=("anthropic",))
    _ask(images=[(b"img", "image/png")])
    data = base64.b64encode(b"img").decode()
    (_, anthropic_messages, _), (_, openai_messages, openai_kwargs) = calls
    assert anthropic_messages[0] == {"role": "system", "content": "prompt"}
    assert anthropic_messages[1]["content"][0] == {
        "type": "image", "source": {"type": "base64", "media_type": "image/png", "data": data}}
    assert openai_messages[1]["content"][1] == {
        "type": "image_url", "image_url": {"url": f"data:image/png;base64,{data}"}}
    assert openai_kwargs["json_mode"] is True


def test_only_providers_that_read_images_are_offered_a_photo(monkeypatch):
    from alafia_model.registry import providers as registry
    for spec in registry.PROVIDERS:
        monkeypatch.delenv(spec.api_key_env, raising=False)
    for key in ("GROQ_API_KEY", "DEEPSEEK_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.setenv(key, "test-key")
    assert [s.name for s in registry.ordered_for_selection(require_vision=True)] == ["anthropic"]
    assert {"groq", "deepseek", "anthropic"} <= {s.name for s in registry.ordered_for_selection()}


def test_a_full_resolution_photo_is_shrunk_for_the_model_only():
    Image = pytest.importorskip("PIL.Image")
    big = io.BytesIO()
    Image.new("RGB", (4032, 3024), (180, 90, 30)).save(big, format="JPEG", quality=95)
    sent, content_type = vision_module._fit_for_upload(big.getvalue(), "image/jpeg")
    assert content_type == "image/jpeg"
    with Image.open(io.BytesIO(sent)) as shrunk:
        assert max(shrunk.size) == 1568

    small = io.BytesIO()
    Image.new("RGB", (800, 600), (1, 2, 3)).save(small, format="PNG")
    assert vision_module._fit_for_upload(small.getvalue(), "image/png") == (small.getvalue(), "image/png")
    assert vision_module._fit_for_upload(b"not an image", "image/heic") == (b"not an image", "image/heic")
