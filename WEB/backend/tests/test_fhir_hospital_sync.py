# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""The portal sync writes hospital stays and links procedures to them.

The mappers are covered in test_fhir_hospital_mapping.py. This file covers the
IMPORT LOOP, which is where two claims live that a mapper test cannot reach and
that were asserted only in comments until now:

1. A procedure resolves to the stay it belongs to, and one whose encounter the
   portal never returned lands UNATTACHED rather than being dropped. That is
   the whole reason `hospitalization_id` is nullable.
2. A SECOND sync inserts nothing. §3ab: an import that cannot recognise its own
   rows produces two contradictory copies of one admission, and the parser-fix
   history in this repo is mostly that failure in different disguises.

Only `fhir_search` is stubbed. The connection carries a real Fernet-encrypted
token with a future expiry so `_valid_access_token` executes for real — a test
that stubs the auth helper proves less and would hide a token-handling change.
"""

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select

from app.models.ehr import EHRConnection
from app.models.hospitalization import Hospitalization, SurgicalProcedure
from app.models.user import User
from app.services import clinical_sources as sources
from app.services import smart_fhir

# NOT a `.test` address: `UserCreate.email` is an `EmailStr`, and
# email-validator refuses RFC 6761 special-use domains (.test, .example,
# .invalid, .localhost), so registration answers 422. The sibling file
# test_hospital_history.py uses `.test` freely because it inserts User rows
# directly and no validator ever runs.
EMAIL = "fhir-hospital-sync@example.com"
PASSWORD = "SecureP@ss123"
SNOMED = "http://snomed.info/sct"

ENCOUNTER = {
    "id": "enc-77",
    "status": "finished",
    "class": {"code": "EMER"},
    "period": {"start": "2024-03-02T14:00:00Z", "end": "2024-03-06T09:30:00Z"},
    "serviceProvider": {"display": "Montgomery General"},
    "reasonCode": [{"text": "Fluid overload"}],
}

PROCEDURE_IN_STAY = {
    "id": "proc-1",
    "status": "completed",
    "code": {"text": "AV fistula creation",
             "coding": [{"system": SNOMED, "code": "233468004"}]},
    "performedDateTime": "2024-03-03T10:00:00Z",
    "encounter": {"reference": "Encounter/enc-77"},
}

#: The case the nullable FK exists for: a real operation whose encounter the
#: portal does not return (historical, or recorded at another institution).
PROCEDURE_NO_STAY = {
    "id": "proc-2",
    "status": "completed",
    "code": {"text": "Parathyroidectomy",
             "coding": [{"system": SNOMED, "code": "36360001"}]},
    "performedDateTime": "2019-06-11T08:00:00Z",
}

#: Must never become a row: the operation did not happen.
PROCEDURE_NOT_DONE = {
    "id": "proc-3",
    "status": "not-done",
    "code": {"text": "Nephrectomy"},
    "performedDateTime": "2020-01-01T08:00:00Z",
}


async def _register_and_token(client: AsyncClient, email: str) -> str:
    created = await client.post("/api/v1/auth/register", json={
        "email": email, "password": PASSWORD,
        "full_name": "Ada Demo", "date_of_birth": "1990-01-01",
    })
    # Check the REGISTER response. Ignoring it meant a refused registration
    # surfaced one call later as `KeyError: 'access_token'` from the login —
    # a fixture reporting a missing token when the real event was a 422, which
    # sent me looking at the sync code instead of at the payload.
    assert created.status_code in (200, 201), (
        f"register failed {created.status_code}: {created.text}")
    r = await client.post("/api/v1/auth/login",
                          data={"username": email, "password": PASSWORD})
    assert r.status_code == 200, f"login failed {r.status_code}: {r.text}"
    return r.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _fake_search(encounters: list[dict], procedures: list[dict]):
    """Stand in for the portal. Every other resource type returns nothing."""
    async def _search(base: str, token: str, resource: str, params: dict) -> list[dict]:
        return {"Encounter": encounters, "Procedure": procedures}.get(resource, [])
    return _search


# `@pytest_asyncio.fixture`, not `@pytest.fixture`: asyncio_mode is OFF in this
# suite (pytest.ini declares a `[tool.pytest.ini_options]` section that is never
# read), so a plain fixture hands the test an un-awaited async generator.
@pytest_asyncio.fixture
async def connection(client: AsyncClient, db):
    """An authorized portal connection, committed so the endpoint can see it."""
    token = await _register_and_token(client, EMAIL)
    user = (await db.execute(
        select(User).where(User.email == EMAIL))).scalar_one()
    conn = EHRConnection(
        user_id=user.id,
        provider="epic",
        org_name="Montgomery General",
        status="connected",
        fhir_base_url="https://portal.example.org/api/FHIR/R4",
        patient_id="pat-1",
        # A REAL encrypted token with a future expiry: `_valid_access_token`
        # decrypts it and returns it without touching the network.
        access_token_enc=smart_fhir.encrypt_token("access-token"),
        token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db.add(conn)
    # The `client` fixture runs its own session. Flushed-but-uncommitted rows
    # are invisible to it, so the endpoint would 404 on the connection.
    await db.commit()
    return {"token": token, "conn_id": conn.id, "user_id": user.id}


@pytest.mark.asyncio
async def test_a_sync_imports_the_stay_and_links_its_procedure(
        client: AsyncClient, db, monkeypatch, connection):
    monkeypatch.setattr(smart_fhir, "fhir_search", _fake_search(
        [ENCOUNTER], [PROCEDURE_IN_STAY, PROCEDURE_NO_STAY, PROCEDURE_NOT_DONE]))

    r = await client.post(f"/api/v1/ehr/connections/{connection['conn_id']}/sync",
                          headers=_auth(connection["token"]))
    assert r.status_code == 200, r.text
    synced = r.json()["synced"]
    assert synced["hospitalizations"] == 1
    # Two, not three: the `not-done` procedure never happened.
    assert synced["procedures"] == 2

    await db.commit()   # read what the endpoint's session committed
    user_id = connection["user_id"]

    stays = await sources.hospitalizations(db, user_id)
    assert len(stays) == 1
    stay = stays[0]
    assert stay.admitted == "2024-03-02"
    assert stay.discharged == "2024-03-06"
    assert stay.nights == 4
    assert stay.facility == "Montgomery General"
    assert stay.admission_type == "emergency"
    assert stay.status == "discharged"
    assert stay.source == "fhir"
    # Only the procedure that named this encounter hangs off it.
    assert [p.name for p in stay.procedures] == ["AV fistula creation"]

    # …while the complete view holds both, newest first.
    procs = await sources.procedures(db, user_id)
    assert [p.name for p in procs] == ["AV fistula creation", "Parathyroidectomy"]
    assert procs[0].admission == "2024-03-02 — Montgomery General"
    assert procs[0].code == "233468004"
    assert procs[0].code_system == "SNOMED"
    assert procs[1].admission is None          # the orphan survived the import
    assert not any(p.name == "Nephrectomy" for p in procs)

    # FHIR states no lasting effect, so nothing claims one.
    assert await sources.lasting_surgical_effects(db, user_id) == []


@pytest.mark.asyncio
async def test_a_second_sync_inserts_nothing(
        client: AsyncClient, db, monkeypatch, connection):
    """§3ab: an import that cannot recognise its own rows duplicates them."""
    monkeypatch.setattr(smart_fhir, "fhir_search", _fake_search(
        [ENCOUNTER], [PROCEDURE_IN_STAY, PROCEDURE_NO_STAY]))
    url = f"/api/v1/ehr/connections/{connection['conn_id']}/sync"

    first = await client.post(url, headers=_auth(connection["token"]))
    assert first.json()["synced"] == {
        **first.json()["synced"], "hospitalizations": 1, "procedures": 2}

    second = await client.post(url, headers=_auth(connection["token"]))
    assert second.status_code == 200, second.text
    assert second.json()["synced"]["hospitalizations"] == 0
    assert second.json()["synced"]["procedures"] == 0

    await db.commit()
    user_id = connection["user_id"]
    # Count the ROWS, not the reported figure: a dedupe bug that reports 0
    # while inserting is exactly the silent-duplicate failure being guarded.
    stays = (await db.execute(select(Hospitalization).where(
        Hospitalization.user_id == user_id))).scalars().all()
    procs = (await db.execute(select(SurgicalProcedure).where(
        SurgicalProcedure.user_id == user_id))).scalars().all()
    assert len(stays) == 1
    assert len(procs) == 2
    assert sorted(p.external_ref for p in procs) == ["FHIR:proc-1", "FHIR:proc-2"]
    assert stays[0].external_ref == "FHIR:enc-77"


@pytest.mark.asyncio
async def test_a_procedure_syncing_after_its_stay_still_attaches(
        client: AsyncClient, db, monkeypatch, connection):
    """The stay arrives in one sync, the procedure in a later one.

    The lookup is keyed over every stay the patient has, not just the ones
    added in this run — otherwise a procedure whose encounter was imported
    weeks ago would be orphaned on every subsequent sync.
    """
    url = f"/api/v1/ehr/connections/{connection['conn_id']}/sync"

    monkeypatch.setattr(smart_fhir, "fhir_search", _fake_search([ENCOUNTER], []))
    assert (await client.post(url, headers=_auth(connection["token"]))
            ).json()["synced"]["hospitalizations"] == 1

    monkeypatch.setattr(smart_fhir, "fhir_search",
                        _fake_search([ENCOUNTER], [PROCEDURE_IN_STAY]))
    second = await client.post(url, headers=_auth(connection["token"]))
    assert second.json()["synced"]["hospitalizations"] == 0   # already held
    assert second.json()["synced"]["procedures"] == 1

    await db.commit()
    stays = await sources.hospitalizations(db, connection["user_id"])
    assert [p.name for p in stays[0].procedures] == ["AV fistula creation"]
