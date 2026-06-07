"""Tests for authentication endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_success(client: AsyncClient):
    """POST /api/v1/auth/register creates a new user."""
    payload = {
        "email": "test@example.com",
        "password": "SecureP@ss123",
        "full_name": "Test User",
    }
    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "test@example.com"
    assert data["full_name"] == "Test User"
    assert "hashed_password" not in data


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient):
    """Registering with an existing email returns 400."""
    payload = {
        "email": "dup@example.com",
        "password": "SecureP@ss123",
        "full_name": "First User",
    }
    await client.post("/api/v1/auth/register", json=payload)
    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 400
    assert "already registered" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient):
    """POST /api/v1/auth/login returns access + refresh tokens."""
    # Register first
    await client.post(
        "/api/v1/auth/register",
        json={"email": "login@example.com", "password": "SecureP@ss123", "full_name": "Login User"},
    )
    # Login with form data
    response = await client.post(
        "/api/v1/auth/login",
        data={"username": "login@example.com", "password": "SecureP@ss123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    # Refresh token should be set as httpOnly cookie
    cookies = response.cookies
    assert "refresh_token" in cookies


@pytest.mark.asyncio
async def test_login_invalid_credentials(client: AsyncClient):
    """Login with wrong password returns 401."""
    await client.post(
        "/api/v1/auth/register",
        json={"email": "bad@example.com", "password": "SecureP@ss123", "full_name": "Bad User"},
    )
    response = await client.post(
        "/api/v1/auth/login",
        data={"username": "bad@example.com", "password": "wrong"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token(client: AsyncClient):
    """POST /api/v1/auth/refresh rotates tokens."""
    await client.post(
        "/api/v1/auth/register",
        json={"email": "refresh@example.com", "password": "SecureP@ss123", "full_name": "Refresh User"},
    )
    login = await client.post(
        "/api/v1/auth/login",
        data={"username": "refresh@example.com", "password": "SecureP@ss123"},
    )
    refresh_cookie = login.cookies.get("refresh_token")
    assert refresh_cookie

    response = await client.post(
        "/api/v1/auth/refresh",
        cookies={"refresh_token": refresh_cookie},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data


@pytest.mark.asyncio
async def test_password_reset_request(client: AsyncClient):
    """POST /api/v1/auth/password-reset/request returns 200 (no email enumeration)."""
    response = await client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "nonexistent@example.com"},
    )
    assert response.status_code == 200
    assert "reset link" in response.json()["message"].lower()


@pytest.mark.asyncio
async def test_password_reset_flow(client: AsyncClient):
    """Full password reset: request → confirm → login with new password."""
    await client.post(
        "/api/v1/auth/register",
        json={"email": "reset@example.com", "password": "OldPass123", "full_name": "Reset User"},
    )
    # Request reset (debug mode exposes token)
    reset_resp = await client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "reset@example.com"},
    )
    token = reset_resp.json().get("reset_token")
    assert token

    # Confirm reset
    confirm = await client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": token, "new_password": "NewPass456"},
    )
    assert confirm.status_code == 200

    # Login with new password
    login = await client.post(
        "/api/v1/auth/login",
        data={"username": "reset@example.com", "password": "NewPass456"},
    )
    assert login.status_code == 200
