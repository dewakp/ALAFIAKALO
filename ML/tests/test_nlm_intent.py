"""Tests for the NLM classify_intent task (ALAFIAModel intent router).

The LLM call is stubbed so these run offline and deterministically. We verify
JSON parsing/validation, the safe fallback, and the empty-input shortcut.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

# Put ML/src on the path so `alafia_model` is importable.
ML_SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(ML_SRC))

from alafia_model.capabilities.base import CapabilityResult
from alafia_model.capabilities.nlm import NLMCapability, INTENT_LABELS


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ── Pure JSON parsing / validation ─────────────────────────────────────────────

def test_parse_intent_json_valid():
    raw = '{"intent": "log_medication", "confidence": 0.9, "entities": {"name": "lisinopril", "dose": "10mg"}}'
    parsed = NLMCapability._parse_intent_json(raw)
    assert parsed["intent"] == "log_medication"
    assert parsed["entities"]["name"] == "lisinopril"
    assert parsed["entities"]["dose"] == "10mg"
    assert 0.0 <= parsed["confidence"] <= 1.0


def test_parse_intent_json_rejects_unknown_intent():
    assert NLMCapability._parse_intent_json('{"intent": "make_coffee", "confidence": 1}') is None


def test_parse_intent_json_handles_surrounding_text():
    raw = 'Sure! Here is the result:\n{"intent": "journal", "confidence": 0.7}\nHope that helps.'
    parsed = NLMCapability._parse_intent_json(raw)
    assert parsed["intent"] == "journal"
    assert parsed["entities"] == {}


def test_parse_intent_json_garbage_returns_none():
    assert NLMCapability._parse_intent_json("not json at all") is None


def test_intent_labels_contains_fallback():
    assert "ask_question" in INTENT_LABELS


# ── Full task path with a stubbed LLM ───────────────────────────────────────────

def test_classify_intent_empty_text():
    cap = NLMCapability()
    result = _run(cap.infer({"task": "classify_intent", "text": "   "}))
    assert result.success
    assert result.data["intent"] == "ask_question"
    assert result.confidence == 0.0


def test_classify_intent_medication(monkeypatch):
    cap = NLMCapability()

    async def fake_infer(self, payload):
        return CapabilityResult(
            success=True,
            data={"text": '{"intent": "log_medication", "confidence": 0.95, '
                          '"entities": {"name": "lisinopril", "dose": "10mg"}}'},
            source="stub-llm",
        )

    monkeypatch.setattr("alafia_model.capabilities.llm.LLMCapability.infer", fake_infer)
    result = _run(cap.infer({"task": "classify_intent", "text": "took my 10mg lisinopril"}))
    assert result.success
    assert result.data["intent"] == "log_medication"
    assert result.data["entities"]["name"] == "lisinopril"
    assert result.data["entities"]["dose"] == "10mg"


def test_classify_intent_falls_back_when_llm_unavailable(monkeypatch):
    cap = NLMCapability()

    async def fake_infer(self, payload):
        return CapabilityResult(success=False, error="no model")

    monkeypatch.setattr("alafia_model.capabilities.llm.LLMCapability.infer", fake_infer)
    result = _run(cap.infer({"task": "classify_intent", "text": "anything"}))
    assert result.success            # always usable
    assert result.data["intent"] == "ask_question"
    assert result.confidence == 0.3  # deterministic fallback confidence
