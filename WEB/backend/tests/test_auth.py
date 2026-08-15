"""Tests for authentication endpoints."""

import pytest
from httpx import AsyncClient

from app.core.security import create_password_reset_token


@pytest.mark.asyncio
async def test_register_success(client: AsyncClient):
    """POST /api/v1/auth/register creates a new user."""
    payload = {
        "email": "test@example.com",
        "password": "SecureP@ss123",
        "full_name": "Test User",
        # Registration enforces an adult date of birth (app/core/age_policy.py).
        "date_of_birth": "1990-01-01",
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
        "date_of_birth": "1990-01-01",
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
        json={"email": "login@example.com", "password": "SecureP@ss123", "full_name": "Login User", "date_of_birth": "1990-01-01"},
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
        json={"email": "bad@example.com", "password": "SecureP@ss123", "full_name": "Bad User", "date_of_birth": "1990-01-01"},
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
        json={"email": "refresh@example.com", "password": "SecureP@ss123", "full_name": "Refresh User", "date_of_birth": "1990-01-01"},
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
    register = await client.post(
        "/api/v1/auth/register",
        json={"email": "reset@example.com", "password": "OldPass123", "full_name": "Reset User", "date_of_birth": "1990-01-01"},
    )
    user_id = register.json()["id"]

    # Requesting a reset must NOT hand the token back. It used to be returned
    # when DEBUG was set, which put one boolean between the deployment and
    # trivial account takeover; the token is now delivered only by email.
    reset_resp = await client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "reset@example.com"},
    )
    assert reset_resp.status_code == 200
    assert "reset_token" not in reset_resp.json()
    assert "token" not in reset_resp.json()

    # Stand in for the emailed link by minting the token the same way the
    # endpoint does, so the rest of the flow is still covered end to end.
    token = create_password_reset_token(user_id)

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


@pytest.mark.asyncio
async def test_direct_registration_is_closed_when_two_step_is_required(client: AsyncClient):
    """The signup gate itself, which conftest turns off for every other test.

    Nothing covered this, so the default flipping to True was invisible here
    while it silently broke ~28 tests that build their fixture user by
    registering. Assert the gate directly instead.
    """
    from app.core.config import settings

    settings.TWO_STEP_SIGNUP_REQUIRED = True
    try:
        resp = await client.post(
            "/api/v1/auth/register",
            json={"email": "gated@example.com", "password": "SecureP@ss123", "full_name": "Gated User", "date_of_birth": "1990-01-01"},
        )
        assert resp.status_code == 410
        assert "/auth/signup/start" in resp.json()["detail"]
    finally:
        settings.TWO_STEP_SIGNUP_REQUIRED = False

    # And with the gate off, the same request succeeds.
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "ungated@example.com", "password": "SecureP@ss123", "full_name": "Ungated User", "date_of_birth": "1990-01-01"},
    )
    assert resp.status_code == 201
