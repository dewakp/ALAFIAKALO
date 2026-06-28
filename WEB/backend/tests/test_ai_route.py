"""Tests for the Prompt-Hub intent router (POST /api/v1/ai/route).

The AI classification is stubbed so the test is deterministic and offline —
we verify the intent→route mapping and prefill assembly, not the model.
"""

import pytest
from httpx import AsyncClient

import app.services.alafia_model_service as alafia_service


async def _register_and_token(client: AsyncClient, email: str) -> str:
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "SecureP@ss123", "full_name": "Route User"},
    )
    r = await client.post(
        "/api/v1/auth/login",
        data={"username": email, "password": "SecureP@ss123"},
    )
    return r.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _stub_infer(intent: str, confidence: float, entities: dict):
    async def _fake(modality: str, payload: dict):
        assert modality == "nlm"
        assert payload["task"] == "classify_intent"
        return {
            "success": True,
            "data": {"intent": intent, "confidence": confidence, "entities": entities},
            "confidence": confidence,
            "source": "stub",
            "error": None,
        }
    return _fake


@pytest.mark.asyncio
async def test_route_log_meal(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(
        alafia_service, "alafia_infer",
        _stub_infer("log_meal", 0.92, {"food": "jollof rice and beef suya"}),
    )
    token = await _register_and_token(client, "route1@example.com")
    r = await client.post(
        "/api/v1/ai/route",
        json={"text": "I ate jollof rice and beef suya", "modality": "text"},
        headers=_auth(token),
    )
    assert r.status_code == 200
    data = r.json()
    assert data["intent"] == "log_meal"
    assert data["route"] == "/nutrition"
    assert data["action"] == "create"
    # prefill carries the raw prompt text plus extracted entities
    assert "jollof rice and beef suya" in data["prefill"]["text"]
    assert data["prefill"]["food"] == "jollof rice and beef suya"


@pytest.mark.asyncio
async def test_route_low_confidence_falls_back_to_chat(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(
        alafia_service, "alafia_infer",
        _stub_infer("log_meal", 0.30, {}),  # below 0.5 threshold
    )
    token = await _register_and_token(client, "route2@example.com")
    r = await client.post(
        "/api/v1/ai/route",
        json={"text": "hmm", "modality": "text"},
        headers=_auth(token),
    )
    assert r.status_code == 200
    data = r.json()
    assert data["intent"] == "ask_question"
    assert data["route"] == "/ai"


@pytest.mark.asyncio
async def test_route_question_guard_overrides_log_intent(client: AsyncClient, monkeypatch):
    # Small models mislabel "what foods lower potassium?" as log_meal; the
    # trailing "?" guard must downgrade it to a question.
    monkeypatch.setattr(
        alafia_service, "alafia_infer",
        _stub_infer("log_meal", 0.9, {}),
    )
    token = await _register_and_token(client, "routeq@example.com")
    r = await client.post(
        "/api/v1/ai/route",
        json={"text": "what foods lower potassium?", "modality": "text"},
        headers=_auth(token),
    )
    assert r.status_code == 200
    data = r.json()
    assert data["intent"] == "ask_question"
    assert data["route"] == "/ai"


@pytest.mark.asyncio
async def test_route_bare_image_goes_to_capture(client: AsyncClient):
    token = await _register_and_token(client, "route3@example.com")
    r = await client.post(
        "/api/v1/ai/route",
        json={"text": "", "modality": "image", "has_attachment": True},
        headers=_auth(token),
    )
    assert r.status_code == 200
    data = r.json()
    assert data["intent"] == "vision_capture"
    assert data["route"] == "/capture"


@pytest.mark.asyncio
async def test_route_requires_auth(client: AsyncClient):
    r = await client.post("/api/v1/ai/route", json={"text": "hello"})
    assert r.status_code == 401
