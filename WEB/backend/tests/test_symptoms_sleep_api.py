"""Smoke tests for the Symptoms and Sleep CRUD endpoints.

Full CRUD needs an authenticated user (unavailable offline); here we assert the
routes exist and are auth-gated. Full happy-path coverage runs in CI/Docker.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/api/v1/symptoms/", "/api/v1/sleep/"])
async def test_list_requires_auth(client: AsyncClient, path):
    r = await client.get(path)
    assert r.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/api/v1/symptoms/", "/api/v1/sleep/"])
async def test_create_requires_auth(client: AsyncClient, path):
    r = await client.post(path, json={})
    assert r.status_code in (401, 403)
