# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""The therapy SWITCH over real HTTP, including the state a set cannot hold.

Operator, 2026-10-14: *"hard-coded enum for therapy will need a comprehensive
list with items zeroed out (no impact) when not present (like a switch) and a
mechanism for compounded therapies. current model lacks comprehensive list and
does not include switch mechanism."*

`tests/test_patient_surfaces.py` covers the derivation. These are the two
routes, and three decisions that are easy to "simplify" into bugs later:

- a code outside WHO's catalog is REFUSED by name, not stored (§3ad);
- an OMITTED entry is left alone — a client editing one switch must not
  retract every other statement on the condition;
- `receiving: false` is returned as a stated fact, while a code nobody asked
  about is simply absent. Collapsing those two is §3at's checkbox, and on this
  surface it decides which clinical screen a patient can reach.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.chronic_conditions import ConditionTherapy

BASE = "/api/v1/chronic"
PASSWORD = "SecureP@ss123"


async def _token(client: AsyncClient, email: str) -> str:
    """Register + log in. NOT a `.test` address — EmailStr refuses RFC 6761
    special-use domains, which answers 422 and then looks like a login bug."""
    created = await client.post("/api/v1/auth/register", json={
        "email": email, "password": PASSWORD,
        "full_name": "Ada Demo", "date_of_birth": "1990-01-01",
    })
    assert created.status_code in (200, 201), created.text
    r = await client.post("/api/v1/auth/login",
                          data={"username": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _condition(client: AsyncClient, token: str, name="ESRD") -> int:
    r = await client.post(f"{BASE}/conditions", headers=_auth(token), json={
        "condition_name": name,
        "category": "renal",
        "severity": "severe",
        "diagnosis_date": "2020-01-01",
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.mark.asyncio
async def test_the_option_set_is_the_catalogs_and_it_is_comprehensive(
        client: AsyncClient, db):
    """What the client renders. 32 codes with WHO's own titles — the previous
    version shipped 10 hand-picked ones, which is typing them with extra
    steps (§3ad, and the operator's *"against the rule"*)."""
    token = await _token(client, "therapy-options@example.com")
    r = await client.get(f"{BASE}/therapy-options", headers=_auth(token))
    assert r.status_code == 200, r.text
    options = r.json()["options"]
    assert len(options) >= 30, f"only {len(options)} options — curated again"
    codes = {o["code"] for o in options}
    # Branches the curated ten could not express at all:
    assert {"QB99", "QB9B", "QB95.0", "QB41"} <= codes
    # Every option carries a WHO title and the surface it opens.
    assert all(o["title"] and o["surface"] for o in options)
    by_code = {o["code"]: o for o in options}
    assert by_code["QB94.1"]["surface"] == "hemodialysis"
    assert by_code["QB94.2"]["surface"] == "peritoneal_dialysis"
    assert by_code["QB99"]["surface"] == "therapy_other"


@pytest.mark.asyncio
async def test_a_patient_can_STATE_they_are_on_a_therapy(
        client: AsyncClient, db):
    token = await _token(client, "therapy-on@example.com")
    cid = await _condition(client, token)
    r = await client.put(
        f"{BASE}/conditions/{cid}/therapies", headers=_auth(token),
        json={"therapies": [{"therapy_code": "QB94.2", "receiving": True,
                             "started_on": "2026-01-15"}]})
    assert r.status_code == 200, r.text
    rows = r.json()["therapies"]
    assert len(rows) == 1
    assert rows[0]["therapy_code"] == "QB94.2"
    assert rows[0]["receiving"] is True
    assert rows[0]["started_on"] == "2026-01-15"


@pytest.mark.asyncio
async def test_a_patient_can_STATE_they_are_NOT_on_one(client: AsyncClient, db):
    """The whole point. §3at: *"'absent', the finding that needs to shout, was
    indistinguishable from a box nobody had touched."* A set could only ever
    express the first state."""
    token = await _token(client, "therapy-off@example.com")
    cid = await _condition(client, token)
    r = await client.put(
        f"{BASE}/conditions/{cid}/therapies", headers=_auth(token),
        json={"therapies": [{"therapy_code": "QB94.1", "receiving": False}]})
    assert r.status_code == 200, r.text
    rows = r.json()["therapies"]
    assert rows[0]["receiving"] is False

    # Stored as a row, which is what distinguishes it from silence.
    stored = (await db.execute(
        select(ConditionTherapy).where(
            ConditionTherapy.condition_id == cid))).scalars().all()
    assert len(stored) == 1 and stored[0].receiving is False


@pytest.mark.asyncio
async def test_a_code_nobody_was_asked_about_is_ABSENT_not_false(
        client: AsyncClient, db):
    """A client must never receive 32 rows of `false` and conclude the patient
    was asked about apheresis and said no."""
    token = await _token(client, "therapy-silence@example.com")
    cid = await _condition(client, token)
    await client.put(
        f"{BASE}/conditions/{cid}/therapies", headers=_auth(token),
        json={"therapies": [{"therapy_code": "QB94.1", "receiving": True}]})
    r = await client.get(f"{BASE}/conditions/{cid}/therapies",
                         headers=_auth(token))
    codes = {row["therapy_code"] for row in r.json()["therapies"]}
    assert codes == {"QB94.1"}, "silence must not be reported as a zero"


@pytest.mark.asyncio
async def test_an_OMITTED_entry_is_left_alone(client: AsyncClient, db):
    """§3av from the other side: a partial save must not retract what it does
    not mention. The client may be editing one switch."""
    token = await _token(client, "therapy-partial@example.com")
    cid = await _condition(client, token)
    await client.put(
        f"{BASE}/conditions/{cid}/therapies", headers=_auth(token),
        json={"therapies": [{"therapy_code": "QB94.1", "receiving": True},
                            {"therapy_code": "QB98", "receiving": True}]})
    # Now change only ONE of them.
    r = await client.put(
        f"{BASE}/conditions/{cid}/therapies", headers=_auth(token),
        json={"therapies": [{"therapy_code": "QB98", "receiving": False}]})
    rows = {x["therapy_code"]: x["receiving"] for x in r.json()["therapies"]}
    assert rows == {"QB94.1": True, "QB98": False}


@pytest.mark.asyncio
async def test_a_switch_is_UPDATED_in_place_not_duplicated(
        client: AsyncClient, db):
    """The unique constraint is real protection: two rows for one code would
    let whichever was read first win — the arbitrary-order failure §3ax's
    duplicate analyte spellings already cost this codebase once."""
    token = await _token(client, "therapy-upsert@example.com")
    cid = await _condition(client, token)
    for receiving in (True, False, True):
        r = await client.put(
            f"{BASE}/conditions/{cid}/therapies", headers=_auth(token),
            json={"therapies": [{"therapy_code": "QB94.1",
                                 "receiving": receiving}]})
        assert r.status_code == 200, r.text
    stored = (await db.execute(
        select(ConditionTherapy).where(
            ConditionTherapy.condition_id == cid))).scalars().all()
    assert len(stored) == 1 and stored[0].receiving is True


@pytest.mark.asyncio
async def test_a_code_outside_the_WHO_CATALOG_is_refused_by_name(
        client: AsyncClient, db):
    """§3ad: the client never decides what a code means. A therapy nobody
    offers a screen for is worse than a rejected save, because the patient
    believes they declared it."""
    token = await _token(client, "therapy-bogus@example.com")
    cid = await _condition(client, token)
    r = await client.put(
        f"{BASE}/conditions/{cid}/therapies", headers=_auth(token),
        json={"therapies": [{"therapy_code": "ZZ99.9", "receiving": True}]})
    assert r.status_code == 422, r.text
    assert "ZZ99.9" in r.text and "therapy-options" in r.text
    assert (await db.execute(
        select(ConditionTherapy).where(
            ConditionTherapy.condition_id == cid))).first() is None


@pytest.mark.asyncio
async def test_a_REAL_icd_code_that_is_not_a_therapy_is_refused(
        client: AsyncClient, db):
    """GB61.5 is end-stage renal disease — a real WHO code and not a therapy.
    Format checks alone would accept it, which is how a diagnosis ends up on
    the axis that decides which treatment screens appear."""
    token = await _token(client, "therapy-notatherapy@example.com")
    cid = await _condition(client, token)
    r = await client.put(
        f"{BASE}/conditions/{cid}/therapies", headers=_auth(token),
        json={"therapies": [{"therapy_code": "GB61.5", "receiving": True}]})
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_RECEIVING_is_required_and_has_no_default(
        client: AsyncClient, db):
    """A default of False would make an omitted field read as a measured zero,
    which is the exact collapse this table exists to undo."""
    token = await _token(client, "therapy-norecv@example.com")
    cid = await _condition(client, token)
    r = await client.put(
        f"{BASE}/conditions/{cid}/therapies", headers=_auth(token),
        json={"therapies": [{"therapy_code": "QB94.1"}]})
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_COMPOUNDED_therapies_travel_as_one_regimen(
        client: AsyncClient, db):
    """The compounding mechanism, over the wire. It reports what is given
    together and asserts nothing about the effect (§3an)."""
    token = await _token(client, "therapy-regimen@example.com")
    cid = await _condition(client, token)
    r = await client.put(
        f"{BASE}/conditions/{cid}/therapies", headers=_auth(token),
        json={"therapies": [
            {"therapy_code": "QB94.1", "receiving": True,
             "regimen": "anaemia management"},
            {"therapy_code": "QB98", "receiving": True,
             "regimen": "anaemia management"},
            {"therapy_code": "QB95.1", "receiving": True},
        ]})
    assert r.status_code == 200, r.text
    rows = {x["therapy_code"]: x["regimen"] for x in r.json()["therapies"]}
    assert rows["QB94.1"] == rows["QB98"] == "anaemia management"
    assert rows["QB95.1"] is None


@pytest.mark.asyncio
async def test_another_patients_condition_is_a_404_on_both_routes(
        client: AsyncClient, db):
    """404 and not 403, so the status code cannot confirm a condition exists
    (§3b's rule, on this surface)."""
    owner = await _token(client, "therapy-owner@example.com")
    cid = await _condition(client, owner)
    stranger = await _token(client, "therapy-stranger@example.com")

    r = await client.get(f"{BASE}/conditions/{cid}/therapies",
                         headers=_auth(stranger))
    assert r.status_code == 404, r.text
    r = await client.put(
        f"{BASE}/conditions/{cid}/therapies", headers=_auth(stranger),
        json={"therapies": [{"therapy_code": "QB94.1", "receiving": True}]})
    assert r.status_code == 404, r.text
    assert (await db.execute(
        select(ConditionTherapy).where(
            ConditionTherapy.condition_id == cid))).first() is None


@pytest.mark.asyncio
async def test_the_switch_reaches_NAVIGATION(client: AsyncClient, db):
    """End to end: the statement is what decides which screens are offered.
    Without this the switch is a table nothing reads — §3ar's dead control."""
    token = await _token(client, "therapy-nav@example.com")
    cid = await _condition(client, token)
    await client.put(
        f"{BASE}/conditions/{cid}/therapies", headers=_auth(token),
        json={"therapies": [{"therapy_code": "QB94.2", "receiving": True},
                            {"therapy_code": "QB94.1", "receiving": False}]})
    r = await client.get("/api/v1/users/me/surfaces", headers=_auth(token))
    assert r.status_code == 200, r.text
    offered = set(r.json()["offered"])
    assert "peritoneal_dialysis" in offered
    assert "hemodialysis" not in offered, (
        "a stated zero must retire the screen")
