"""Tests for Labs and Medications API endpoints."""

import pytest
from httpx import AsyncClient


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _register_and_token(client: AsyncClient, email: str) -> str:
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "SecureP@ss123", "full_name": "Test User", "date_of_birth": "1990-01-01"},
    )
    r = await client.post(
        "/api/v1/auth/login",
        data={"username": email, "password": "SecureP@ss123"},
    )
    return r.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ══════════════════════════════════════════════════════════════════════════════
# Labs
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_create_lab_result(client: AsyncClient):
    token = await _register_and_token(client, "lab1@example.com")
    r = await client.post(
        "/api/v1/labs/",
        json={
            "test_date": "2026-04-28",
            "test_name": "Hemoglobin",
            "value": 13.5,
            "unit": "g/dL",
            "reference_range_low": 12.0,
            "reference_range_high": 17.5,
            "performing_lab": "DaVita Labs",
            "status": "final",
        },
        headers=_auth(token),
    )
    assert r.status_code == 201
    data = r.json()
    assert data["test_name"] == "Hemoglobin"
    assert data["value"] == 13.5
    assert data["performing_lab"] == "DaVita Labs"


@pytest.mark.asyncio
async def test_list_lab_results(client: AsyncClient):
    token = await _register_and_token(client, "lab2@example.com")
    for name in ("Albumin", "Potassium"):
        await client.post(
            "/api/v1/labs/",
            json={"test_date": "2026-04-28", "test_name": name, "status": "final"},
            headers=_auth(token),
        )
    r = await client.get("/api/v1/labs/", headers=_auth(token))
    assert r.status_code == 200
    names = [e["test_name"] for e in r.json()]
    assert "Albumin" in names and "Potassium" in names


@pytest.mark.asyncio
async def test_lab_requires_auth(client: AsyncClient):
    r = await client.get("/api/v1/labs/")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_lab_category_filter(client: AsyncClient):
    token = await _register_and_token(client, "lab3@example.com")
    for cat, name in [("Metabolic", "Glucose"), ("CBC", "WBC")]:
        await client.post(
            "/api/v1/labs/",
            json={"test_date": "2026-04-28", "test_name": name, "category": cat, "status": "final"},
            headers=_auth(token),
        )
    r = await client.get("/api/v1/labs/", params={"category": "CBC"}, headers=_auth(token))
    names = [e["test_name"] for e in r.json()]
    assert "WBC" in names
    assert "Glucose" not in names


@pytest.mark.asyncio
async def test_lab_isolation_between_users(client: AsyncClient):
    token_a = await _register_and_token(client, "lab_a@example.com")
    token_b = await _register_and_token(client, "lab_b@example.com")
    await client.post(
        "/api/v1/labs/",
        json={"test_date": "2026-04-28", "test_name": "PrivateLab", "status": "final"},
        headers=_auth(token_a),
    )
    r = await client.get("/api/v1/labs/", headers=_auth(token_b))
    assert all(e["test_name"] != "PrivateLab" for e in r.json())


@pytest.mark.asyncio
async def test_delete_lab_result_is_forbidden(client: AsyncClient):
    """Lab entries are immutable-by-policy: deletion is forbidden (modify instead)."""
    token = await _register_and_token(client, "lab4@example.com")
    create = await client.post(
        "/api/v1/labs/",
        json={"test_date": "2026-04-28", "test_name": "Creatinine", "status": "final"},
        headers=_auth(token),
    )
    lab_id = create.json()["id"]
    r = await client.delete(f"/api/v1/labs/{lab_id}", headers=_auth(token))
    assert r.status_code == 403
    assert "cannot be deleted" in r.json()["detail"].lower()


# ══════════════════════════════════════════════════════════════════════════════
# Medications
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_create_medication(client: AsyncClient):
    token = await _register_and_token(client, "med1@example.com")
    r = await client.post(
        "/api/v1/medications/",
        json={
            "name": "Lisinopril",
            "dosage": "10",
            "dosage_unit": "mg",
            "frequency": "once daily",
            "route": "oral",
            "is_active": True,
        },
        headers=_auth(token),
    )
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "Lisinopril"
    assert data["dosage"] == "10"
    assert data["dosage_unit"] == "mg"


@pytest.mark.asyncio
async def test_list_medications(client: AsyncClient):
    token = await _register_and_token(client, "med2@example.com")
    for name in ("Metformin", "Aspirin"):
        await client.post(
            "/api/v1/medications/",
            json={"name": name, "is_active": True},
            headers=_auth(token),
        )
    r = await client.get("/api/v1/medications/", headers=_auth(token))
    assert r.status_code == 200
    names = [e["name"] for e in r.json()]
    assert "Metformin" in names and "Aspirin" in names


@pytest.mark.asyncio
async def test_list_medications_active_only_filter(client: AsyncClient):
    token = await _register_and_token(client, "med3@example.com")
    await client.post(
        "/api/v1/medications/",
        json={"name": "ActiveDrug", "is_active": True},
        headers=_auth(token),
    )
    await client.post(
        "/api/v1/medications/",
        json={"name": "StoppedDrug", "is_active": False},
        headers=_auth(token),
    )
    r = await client.get("/api/v1/medications/", params={"active_only": True}, headers=_auth(token))
    names = [e["name"] for e in r.json()]
    assert "ActiveDrug" in names
    assert "StoppedDrug" not in names


@pytest.mark.asyncio
async def test_medications_requires_auth(client: AsyncClient):
    r = await client.get("/api/v1/medications/")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_update_medication(client: AsyncClient):
    token = await _register_and_token(client, "med4@example.com")
    create = await client.post(
        "/api/v1/medications/",
        json={"name": "Warfarin", "is_active": True},
        headers=_auth(token),
    )
    med_id = create.json()["id"]
    r = await client.patch(  # updates are partial (PATCH), not PUT
        f"/api/v1/medications/{med_id}",
        json={"is_active": False},
        headers=_auth(token),
    )
    assert r.status_code == 200
    assert r.json()["is_active"] is False


@pytest.mark.asyncio
async def test_medication_isolation_between_users(client: AsyncClient):
    token_a = await _register_and_token(client, "med_a@example.com")
    token_b = await _register_and_token(client, "med_b@example.com")
    await client.post(
        "/api/v1/medications/",
        json={"name": "SecretMed", "is_active": True},
        headers=_auth(token_a),
    )
    r = await client.get("/api/v1/medications/", headers=_auth(token_b))
    assert all(e["name"] != "SecretMed" for e in r.json())
