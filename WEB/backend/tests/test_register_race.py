"""Registering the same address twice must not 500.

Production, 2026-08-24 14:32:11 — four register POSTs inside 300ms:

    201  <- the account was created
    500  <- UniqueViolationError on ix_users_email, unhandled
    500
    400
    429  <- retries then tripped the auth rate limiter

The user saw a server error for a signup that had ALREADY SUCCEEDED, retried,
and was rate limited out of the app. The pre-check for an existing email is not
a lock: concurrent requests both pass it and both insert. Only the database can
settle a uniqueness race, so the loser must be given the same answer the
pre-check gives.
"""

import pytest

REGISTRATION = {
    "email": "race@example.com",
    "password": "RacePassw0rd!23",
    "full_name": "Race Condition",
    "date_of_birth": "1974-03-15",
}


@pytest.mark.asyncio
async def test_first_registration_succeeds(client):
    resp = await client.post("/api/v1/auth/register", json=REGISTRATION)
    assert resp.status_code == 201, resp.text


@pytest.mark.asyncio
async def test_registering_the_same_email_twice_is_400_not_500(client):
    first = await client.post("/api/v1/auth/register", json=REGISTRATION)
    assert first.status_code == 201, first.text

    second = await client.post("/api/v1/auth/register", json=REGISTRATION)
    assert second.status_code == 400, second.text
    assert "already registered" in second.json()["detail"].lower()


@pytest.mark.asyncio
async def test_the_duplicate_does_not_poison_the_session(client):
    """After the rollback, the app must still work — a failed flush that leaves
    the session broken turns one bad request into a broken worker."""
    await client.post("/api/v1/auth/register", json=REGISTRATION)
    await client.post("/api/v1/auth/register", json=REGISTRATION)

    other = await client.post("/api/v1/auth/register", json={
        **REGISTRATION, "email": "after-the-race@example.com",
    })
    assert other.status_code == 201, other.text
