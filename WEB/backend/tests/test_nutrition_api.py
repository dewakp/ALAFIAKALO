"""Tests for Nutrition API endpoints (/api/v1/nutrition/*)."""

import pytest
from httpx import AsyncClient


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _register_and_token(client: AsyncClient, email: str = "nutr@example.com") -> str:
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "SecureP@ss123", "full_name": "Nutr User", "date_of_birth": "1990-01-01"},
    )
    r = await client.post(
        "/api/v1/auth/login",
        data={"username": email, "password": "SecureP@ss123"},
    )
    return r.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── Nutrition log CRUD ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_nutrition_log(client: AsyncClient):
    token = await _register_and_token(client, "nutr1@example.com")
    r = await client.post(
        "/api/v1/nutrition/",
        json={
            "log_date": "2026-04-28",
            "meal_type": "breakfast",
            "food_name": "oatmeal",
            "calories": 150.0,
            "protein_g": 5.0,
            "carbs_g": 27.0,
            "fat_g": 2.5,
        },
        headers=_auth(token),
    )
    assert r.status_code == 201
    data = r.json()
    assert data["food_name"] == "oatmeal"
    assert data["meal_type"] == "breakfast"
    assert data["calories"] == 150.0


@pytest.mark.asyncio
async def test_list_nutrition_logs(client: AsyncClient):
    token = await _register_and_token(client, "nutr2@example.com")
    # Create two entries
    for name in ("rice", "chicken"):
        await client.post(
            "/api/v1/nutrition/",
            json={"log_date": "2026-04-28", "meal_type": "lunch", "food_name": name},
            headers=_auth(token),
        )
    r = await client.get("/api/v1/nutrition/", headers=_auth(token))
    assert r.status_code == 200
    names = [e["food_name"] for e in r.json()]
    assert "rice" in names and "chicken" in names


@pytest.mark.asyncio
async def test_nutrition_log_requires_auth(client: AsyncClient):
    r = await client.get("/api/v1/nutrition/")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_update_nutrition_log(client: AsyncClient):
    token = await _register_and_token(client, "nutr3@example.com")
    create = await client.post(
        "/api/v1/nutrition/",
        json={"log_date": "2026-04-28", "meal_type": "dinner", "food_name": "pasta"},
        headers=_auth(token),
    )
    log_id = create.json()["id"]
    # Updates are partial (PATCH), not PUT.
    r = await client.patch(
        f"/api/v1/nutrition/{log_id}",
        json={"calories": 400.0},
        headers=_auth(token),
    )
    assert r.status_code == 200
    assert r.json()["calories"] == 400.0


@pytest.mark.asyncio
async def test_delete_nutrition_log_is_forbidden(client: AsyncClient):
    """Nutrition entries are immutable-by-policy: deletion is forbidden (modify instead)."""
    token = await _register_and_token(client, "nutr4@example.com")
    create = await client.post(
        "/api/v1/nutrition/",
        json={"log_date": "2026-04-28", "meal_type": "snack", "food_name": "apple"},
        headers=_auth(token),
    )
    log_id = create.json()["id"]
    r = await client.delete(f"/api/v1/nutrition/{log_id}", headers=_auth(token))
    assert r.status_code == 403
    assert "cannot be deleted" in r.json()["detail"].lower()
    # Deletion is forbidden by policy, so the entry must still be present.
    r2 = await client.get("/api/v1/nutrition/", headers=_auth(token))
    assert any(e["id"] == log_id for e in r2.json())


@pytest.mark.asyncio
async def test_nutrition_log_isolation_between_users(client: AsyncClient):
    """User A cannot see User B's nutrition logs."""
    token_a = await _register_and_token(client, "nutr_a@example.com")
    token_b = await _register_and_token(client, "nutr_b@example.com")
    await client.post(
        "/api/v1/nutrition/",
        json={"log_date": "2026-04-28", "meal_type": "breakfast", "food_name": "private_food"},
        headers=_auth(token_a),
    )
    r = await client.get("/api/v1/nutrition/", headers=_auth(token_b))
    assert all(e["food_name"] != "private_food" for e in r.json())


@pytest.mark.asyncio
async def test_nutrition_log_date_filter(client: AsyncClient):
    token = await _register_and_token(client, "nutr5@example.com")
    for log_date, name in [("2026-01-01", "new_year_meal"), ("2026-04-28", "april_meal")]:
        await client.post(
            "/api/v1/nutrition/",
            json={"log_date": log_date, "meal_type": "lunch", "food_name": name},
            headers=_auth(token),
        )
    r = await client.get(
        "/api/v1/nutrition/",
        params={"start_date": "2026-04-01", "end_date": "2026-04-30"},
        headers=_auth(token),
    )
    names = [e["food_name"] for e in r.json()]
    assert "april_meal" in names
    assert "new_year_meal" not in names
