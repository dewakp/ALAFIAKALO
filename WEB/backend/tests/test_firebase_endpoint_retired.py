"""/auth/firebase is retired, and says so.

Social sign-in now verifies the provider's own ID token (app/services/oidc.py).
The old endpoint is kept as a 410 rather than deleted so anything still pointed
at it is told what happened — and pinned here because the difference between a
410, a 404 and a 500 is invisible until someone hits it.

It never worked in production anyway: Apple was never configured as a provider,
and this route answered 503 to everything because FIREBASE_SERVICE_ACCOUNT was
empty while the `firebase-sa` secret sat unmounted in Secret Manager.
"""

import pytest

URL = "/api/v1/auth/firebase"


@pytest.mark.asyncio
async def test_the_endpoint_is_gone_not_missing(client):
    """410, not 404. 'Gone' says the route existed and was withdrawn; 404 would
    read as a typo and send someone looking for the right path."""
    res = await client.post(URL, json={"id_token": "anything"})

    assert res.status_code == 410, res.text


@pytest.mark.asyncio
async def test_it_names_the_replacement(client):
    """A refusal with no route forward is the failure this whole change was
    about (§3aj). Say where to go instead."""
    detail = (await client.post(URL, json={"id_token": "x"})).json()["detail"]

    assert "/auth/oidc" in detail


@pytest.mark.asyncio
async def test_it_refuses_without_needing_a_body(client):
    """The request model went with the handler, so an empty or malformed body
    must still answer 410 rather than 422 — the caller is not being asked to
    correct their payload, the door is closed."""
    res = await client.post(URL, json={})

    assert res.status_code == 410, res.text
