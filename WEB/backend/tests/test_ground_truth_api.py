"""Smoke tests for ground-truth endpoints (genetics + environmental/social).

Auth-gating runs offline; full CRUD happy-path runs in CI/Docker.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
@pytest.mark.parametrize("path", [
    "/api/v1/ground-truth/genetics",
    "/api/v1/ground-truth/env-social",
])
async def test_list_requires_auth(client: AsyncClient, path):
    assert (await client.get(path)).status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("path", [
    "/api/v1/ground-truth/genetics",
    "/api/v1/ground-truth/env-social",
])
async def test_create_requires_auth(client: AsyncClient, path):
    assert (await client.post(path, json={})).status_code in (401, 403)
