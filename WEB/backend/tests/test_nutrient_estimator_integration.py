"""Integration tests for nutrient estimation endpoint behavior."""

from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.services import nutrient_estimator as estimator_module


async def _auth_headers(client: AsyncClient) -> dict[str, str]:
    """Register + login and return auth headers for protected routes."""
    email = f"nutrient-{uuid4().hex[:10]}@example.com"
    password = "SecureP@ss123"

    register = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": "Nutrient Tester"},
    )
    assert register.status_code == 201

    login = await client.post(
        "/api/v1/auth/login",
        data={"username": email, "password": password},
    )
    assert login.status_code == 200

    token = login.json()["access_token"]
    return {
        "Authorization": f"Bearer {token}",
        "X-CSRF-Token": "test-csrf-token",
    }


@pytest.mark.asyncio
async def test_estimate_nutrients_usda_success_path(client: AsyncClient, monkeypatch):
    """USDA result is returned when USDA lookup succeeds."""

    async def fake_try_usda(food_name: str):
        return {
            "source": "usda",
            "fdc_id": 12345,
            "ai_model": None,
            "food_name": "apple, raw",
            "serving_size": "100 g",
            "serving_weight_g": 100.0,
            "confidence": 1.0,
            "nutrients": {
                "calories": 52.0,
                "protein_g": 0.3,
                "carbs_g": 13.8,
                "fat_g": 0.2,
            },
            "cached": False,
        }

    async def fake_try_ai(food_name: str, serving_size: str | None = None):
        raise AssertionError("AI fallback should not be called when USDA succeeds")

    monkeypatch.setattr(estimator_module, "_try_usda", fake_try_usda)
    monkeypatch.setattr(estimator_module, "_try_ai", fake_try_ai)

    headers = await _auth_headers(client)
    response = await client.post(
        "/api/v1/nutrition/estimate-nutrients",
        json={"food_name": "apple", "serving_size": "100 g"},
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "usda"
    assert data["fdc_id"] == 12345
    assert data["nutrients"]["calories"] == 52.0
    assert data["cached"] is False


@pytest.mark.asyncio
async def test_estimate_nutrients_ai_fallback_path(client: AsyncClient, monkeypatch):
    """AI fallback is used when USDA has no match."""

    async def fake_try_usda(food_name: str):
        return None

    async def fake_try_ai(food_name: str, serving_size: str | None = None):
        return {
            "source": "ai",
            "fdc_id": None,
            "ai_model": "llama3.2:latest",
            "food_name": food_name,
            "serving_size": serving_size or "1 plate",
            "serving_weight_g": 250.0,
            "confidence": 0.8,
            "nutrients": {
                # Physically valid per-100 g (macros sum < 100 g, Atwater-consistent),
                # so the believability layer keeps the source confidence.
                "calories": 550.0,
                "protein_g": 15.0,
                "carbs_g": 35.0,
                "fat_g": 40.0,
            },
            "cached": False,
        }

    async def fake_try_branded(food_name: str):
        return None  # no branded match → exercise the AI fallback deterministically

    monkeypatch.setattr(estimator_module, "_try_usda", fake_try_usda)
    monkeypatch.setattr(estimator_module, "_try_mcp_branded", fake_try_branded)
    monkeypatch.setattr(estimator_module, "_try_ai", fake_try_ai)

    headers = await _auth_headers(client)
    response = await client.post(
        "/api/v1/nutrition/estimate-nutrients",
        json={"food_name": "waakye with shito", "serving_size": "1 plate"},
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "ai"
    assert data["ai_model"] == "llama3.2:latest"
    assert data["confidence"] == 0.8
    assert data["nutrients"]["calories"] == 550.0
    assert data["cached"] is False


@pytest.mark.asyncio
async def test_estimate_nutrients_cache_hit_on_second_call(client: AsyncClient, monkeypatch):
    """Second identical lookup should hit cache and skip source lookup."""

    calls = {"usda": 0, "ai": 0}

    async def fake_try_usda(food_name: str):
        calls["usda"] += 1
        return {
            "source": "usda",
            "fdc_id": 778899,
            "ai_model": None,
            "food_name": "grilled chicken breast",
            "serving_size": "100 g",
            "serving_weight_g": 100.0,
            "confidence": 1.0,
            "nutrients": {
                "calories": 165.0,
                "protein_g": 31.0,
                "carbs_g": 0.0,
                "fat_g": 3.6,
            },
            "cached": False,
        }

    async def fake_try_ai(food_name: str, serving_size: str | None = None):
        calls["ai"] += 1
        return None

    monkeypatch.setattr(estimator_module, "_try_usda", fake_try_usda)
    monkeypatch.setattr(estimator_module, "_try_ai", fake_try_ai)

    headers = await _auth_headers(client)
    body = {"food_name": "grilled chicken breast", "serving_size": "170 g"}

    first = await client.post("/api/v1/nutrition/estimate-nutrients", json=body, headers=headers)
    second = await client.post("/api/v1/nutrition/estimate-nutrients", json=body, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200

    first_data = first.json()
    second_data = second.json()

    assert first_data["cached"] is False
    assert second_data["cached"] is True
    assert second_data["source"] == "usda"
    assert calls["usda"] == 1
    assert calls["ai"] == 0
