"""Recipient lookup — the enumeration boundary.

The compose form needs to find people by name, email or phone instead of asking
a patient to type an internal member id. The risk that creates is that the same
endpoint becomes a directory: type "a", get every patient on the platform.

The rule under test: a PARTIAL name only ever matches a shared contact, while a
COMPLETE identifier resolves anyone — because the caller had to know it already.
"""

import pytest
from httpx import AsyncClient

from tests.test_clinician_board import _account, _auth, _share


async def _find(client: AsyncClient, token: str, q: str) -> list[dict]:
    r = await client.get("/api/v1/messaging/recipients", params={"q": q},
                         headers=_auth(token))
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.asyncio
async def test_partial_name_does_not_match_a_stranger(client: AsyncClient):
    """The directory must not be walkable by anyone with an account."""
    _, seeker = await _account(client, "seek.stranger@example.com", "Seeker One")
    await _account(client, "hidden.person@example.com", "Zebediah Uniquename")

    assert await _find(client, seeker, "Zebediah") == []
    assert await _find(client, seeker, "Uniquename") == []


@pytest.mark.asyncio
async def test_partial_name_matches_a_shared_contact(client: AsyncClient):
    """Sharing data with someone makes them findable by name — that is the point."""
    _, patient = await _account(client, "share.patient@example.com", "Sharing Patient")
    doc_id, _ = await _account(client, "share.doctor@example.com", "Adeyemi Nephrologist")
    await _share(client, patient, "share.doctor@example.com", "labs")

    hits = await _find(client, patient, "Adeyemi")
    assert [h["id"] for h in hits] == [doc_id]
    assert hits[0]["connected"] is True
    assert hits[0]["matched_on"] == "name"


@pytest.mark.asyncio
async def test_a_grant_makes_the_contact_mutual(client: AsyncClient):
    """The clinician can find the patient too — the edge is not one-directional."""
    pat_id, patient = await _account(client, "mutual.patient@example.com", "Mutual Patient")
    _, doctor = await _account(client, "mutual.doctor@example.com", "Mutual Doctor")
    await _share(client, patient, "mutual.doctor@example.com", "labs")

    assert [h["id"] for h in await _find(client, doctor, "Mutual Pat")] == [pat_id]


@pytest.mark.asyncio
async def test_full_email_resolves_anyone(client: AsyncClient):
    """You cannot browse to someone, but you can reach an address you were given."""
    _, seeker = await _account(client, "email.seeker@example.com", "Email Seeker")
    target_id, _ = await _account(client, "email.target@example.com", "Email Target")

    hits = await _find(client, seeker, "email.target@example.com")
    assert [h["id"] for h in hits] == [target_id]
    assert hits[0]["matched_on"] == "email"
    # They typed the address, so echoing it back confirms the right person.
    assert hits[0]["email"] == "email.target@example.com"
    assert hits[0]["connected"] is False


@pytest.mark.asyncio
async def test_a_near_miss_email_resolves_nothing(client: AsyncClient):
    """Identifier matching is exact — a prefix of an address is not an address."""
    _, seeker = await _account(client, "near.seeker@example.com", "Near Seeker")
    await _account(client, "near.target@example.com", "Near Target")

    assert await _find(client, seeker, "near.target@example.co") == []
    assert await _find(client, seeker, "near.target") == []


@pytest.mark.asyncio
async def test_contact_details_are_masked_for_a_name_match(client: AsyncClient):
    """Scraping your own contact list must not yield a list of addresses."""
    _, patient = await _account(client, "mask.patient@example.com", "Mask Patient")
    await _account(client, "mask.doctor@example.com", "Masked Clinician")
    await _share(client, patient, "mask.doctor@example.com", "labs")

    hit = (await _find(client, patient, "Masked"))[0]
    assert hit["email"] is None, "a name match must not hand back the address"
    # Fixed-width mask — the hint must not disclose the address length either.
    assert hit["email_hint"] == "m•••@example.com"


@pytest.mark.asyncio
async def test_a_short_query_returns_nothing(client: AsyncClient):
    """One character is a prefix scan, not a search."""
    _, seeker = await _account(client, "short.seeker@example.com", "Short Seeker")
    assert await _find(client, seeker, "a") == []
    assert await _find(client, seeker, "") == []


@pytest.mark.asyncio
async def test_you_never_match_yourself(client: AsyncClient):
    """A conversation with yourself is not a conversation."""
    _, seeker = await _account(client, "self.seeker@example.com", "Self Seeker")
    assert await _find(client, seeker, "self.seeker@example.com") == []
