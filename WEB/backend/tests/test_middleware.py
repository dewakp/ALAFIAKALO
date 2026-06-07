"""Tests for middleware (CSRF, security headers)."""

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_security_headers_present(client: AsyncClient):
    """All security headers are present on responses."""
    response = await client.get("/api/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["x-xss-protection"] == "1; mode=block"
    assert "strict-origin" in response.headers["referrer-policy"]


@pytest.mark.asyncio
async def test_csrf_cookie_set(client: AsyncClient):
    """First request sets a csrf_token cookie."""
    response = await client.get("/api/health")
    assert "csrf_token" in response.cookies


@pytest.mark.asyncio
async def test_csrf_rejects_mutating_without_token():
    """POST without CSRF token returns 403."""
    from app.main import app as _app
    transport = ASGITransport(app=_app)
    async with AsyncClient(transport=transport, base_url="http://test") as bare_client:
        response = await bare_client.post(
            "/api/v1/auth/password-reset/request",
            json={"email": "test@example.com"},
        )
    assert response.status_code == 403
    assert "CSRF" in response.json()["detail"]


@pytest.mark.asyncio
async def test_csrf_accepts_with_valid_token(client: AsyncClient):
    """POST with matching CSRF cookie + header succeeds."""
    # First get a CSRF cookie
    get_resp = await client.get("/api/health")
    csrf_token = get_resp.cookies["csrf_token"]
    # Now POST with the token
    response = await client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "test@example.com"},
        headers={"X-CSRF-Token": csrf_token},
        cookies={"csrf_token": csrf_token},
    )
    assert response.status_code == 200
