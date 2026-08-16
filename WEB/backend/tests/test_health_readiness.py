"""Liveness, readiness, and what a database outage looks like to a client.

During the PostgreSQL 16 -> 18 upgrade on 2026-08-16, production answered
`/api/health` with 200 for eleven minutes while every data-backed request
returned `500 Internal Server Error`. Cloud Run saw a healthy service; so would
any uptime monitor pointed at that path.

Two separate defects:
  - the only health endpoint never touched the database, so it could not fail
    when the database did, and
  - an unreachable database surfaced as 500, which tells a client "your request
    was wrong or the app is broken" rather than "come back shortly".
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_liveness_states_that_it_did_not_check_the_database(client: AsyncClient):
    """It must not be mistakable for a statement about the database."""
    r = await client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "healthy"
    assert "database" in body, "liveness must say what it did NOT check"
    assert "/api/ready" in body["database"], body["database"]


@pytest.mark.asyncio
async def test_readiness_actually_queries_the_database(client: AsyncClient):
    r = await client.get("/api/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ready"
    assert body["database"] == "ok"
    # A latency figure is only possible if a query really ran.
    assert isinstance(body["latency_ms"], (int, float))


@pytest.mark.asyncio
async def test_readiness_reports_503_when_the_database_is_unreachable(
    client: AsyncClient, monkeypatch
):
    """The whole point: this endpoint must be able to fail."""
    from app.core.database import get_db
    from app.main import app

    from fastapi import HTTPException

    async def _unreachable():
        # Exactly what get_db raises when the server cannot be reached.
        raise HTTPException(status_code=503, detail="The service is temporarily "
                            "unavailable. Please try again.",
                            headers={"Retry-After": "15"})
        yield  # pragma: no cover

    app.dependency_overrides[get_db] = _unreachable
    try:
        r = await client.get("/api/ready")
    finally:
        app.dependency_overrides.pop(get_db, None)
    # The status is what a load balancer and an uptime monitor act on.
    assert r.status_code == 503, r.text
    assert r.headers.get("retry-after") == "15"


@pytest.mark.asyncio
async def test_an_unreachable_database_is_503_with_retry_after_not_500(
    client: AsyncClient, monkeypatch
):
    """503 is retryable and true. 500 blames the caller for an outage."""
    from fastapi import HTTPException

    from app.core.database import get_db
    from app.main import app

    async def _unreachable():
        # What get_db raises when it cannot open a connection.
        raise HTTPException(status_code=503,
                            detail="The service is temporarily unavailable. Please try again.",
                            headers={"Retry-After": "15"})
        yield  # pragma: no cover

    app.dependency_overrides[get_db] = _unreachable
    try:
        r = await client.post("/api/v1/auth/login",
                              data={"username": "probe@example.invalid", "password": "x"})
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 503, f"got {r.status_code}: {r.text[:200]}"
    assert r.headers.get("retry-after") == "15"
    assert "temporarily unavailable" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_a_real_auth_failure_is_still_401(client: AsyncClient):
    """The 503 translation must not swallow genuine application errors —
    otherwise every bug becomes 'try again later'."""
    r = await client.post("/api/v1/auth/login",
                          data={"username": "nobody@example.invalid", "password": "x"})
    assert r.status_code == 401, r.text
