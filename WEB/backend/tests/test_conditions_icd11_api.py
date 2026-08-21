"""ICD-11 on the chronic-conditions API.

Conditions are one of the app's cornerstones (CLAUDE.md §3aa) and this is the
path that puts a diagnosis code on a patient record. What is pinned here is the
boundary behaviour: a code the client sends is verified against the WHO catalog
before it is stored, and the title is the catalog's rather than the client's.
"""

import pytest
from httpx import AsyncClient


async def _register_and_token(client: AsyncClient, email: str) -> str:
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "SecureP@ss123",
            "full_name": "Test User",
            "date_of_birth": "1990-01-01",
        },
    )
    r = await client.post(
        "/api/v1/auth/login",
        data={"username": email, "password": "SecureP@ss123"},
    )
    return r.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _condition(**overrides) -> dict:
    payload = {
        "condition_name": "End-Stage Renal Disease",
        "category": "renal",
        "severity": "severe",
    }
    payload.update(overrides)
    return payload


# ── Catalog endpoints ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_icd11_search_requires_auth(client: AsyncClient):
    r = await client.get("/api/v1/chronic/icd11/search", params={"q": "ESRD"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_icd11_search_resolves_a_lay_abbreviation(client: AsyncClient):
    token = await _register_and_token(client, "icd11_search@example.com")
    r = await client.get(
        "/api/v1/chronic/icd11/search",
        params={"q": "ESRD", "limit": 5},
        headers=_auth(token),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["results"][0]["code"] == "GB61.5"
    assert body["results"][0]["title"] == "Chronic kidney disease, stage 5"
    assert body["results"][0]["chapter_title"]
    assert "ICD-11 MMS" in body["catalog_version"]


@pytest.mark.asyncio
async def test_icd11_search_handles_us_spelling(client: AsyncClient):
    # WHO writes "haemodialysis"; a US patient types "hemodialysis".
    token = await _register_and_token(client, "icd11_spell@example.com")
    r = await client.get(
        "/api/v1/chronic/icd11/search",
        params={"q": "hemodialysis"},
        headers=_auth(token),
    )
    assert r.status_code == 200
    assert r.json()["total"] >= 1


@pytest.mark.asyncio
async def test_icd11_single_code_and_unknown_code(client: AsyncClient):
    token = await _register_and_token(client, "icd11_code@example.com")

    r = await client.get("/api/v1/chronic/icd11/GB61.5", headers=_auth(token))
    assert r.status_code == 200
    assert r.json()["title"] == "Chronic kidney disease, stage 5"

    # Code-shaped but not real.
    r = await client.get("/api/v1/chronic/icd11/ZZ99.9", headers=_auth(token))
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_icd11_chapters(client: AsyncClient):
    token = await _register_and_token(client, "icd11_chapters@example.com")
    r = await client.get("/api/v1/chronic/icd11/chapters", headers=_auth(token))
    assert r.status_code == 200
    chapters = r.json()
    assert len(chapters) == 28
    assert {"chapter": "02", "title": "Neoplasms"} in chapters


# ── Writing a code onto a condition ───────────────────────────────────


@pytest.mark.asyncio
async def test_condition_stores_icd11_and_normalises_case(client: AsyncClient):
    token = await _register_and_token(client, "icd11_create@example.com")
    r = await client.post(
        "/api/v1/chronic/conditions",
        json=_condition(icd11_code="gb61.5"),
        headers=_auth(token),
    )
    assert r.status_code == 201
    assert r.json()["icd11_code"] == "GB61.5"


@pytest.mark.asyncio
async def test_title_comes_from_the_catalog_not_the_client(client: AsyncClient):
    """A client-supplied title is discarded.

    Otherwise a record could display any text at all next to a real code —
    the code would look verified and the label would be whatever was sent.
    """
    token = await _register_and_token(client, "icd11_title@example.com")
    r = await client.post(
        "/api/v1/chronic/conditions",
        json=_condition(icd11_code="GB61.5", icd11_title="Something else entirely"),
        headers=_auth(token),
    )
    assert r.status_code == 201
    assert r.json()["icd11_title"] == "Chronic kidney disease, stage 5"


@pytest.mark.asyncio
async def test_code_shaped_but_nonexistent_is_rejected(client: AsyncClient):
    # The important case: a typo in a 4-character stem code is usually still
    # code-shaped, so format validation alone would let it through.
    token = await _register_and_token(client, "icd11_fake@example.com")
    r = await client.post(
        "/api/v1/chronic/conditions",
        json=_condition(icd11_code="ZZ99.9"),
        headers=_auth(token),
    )
    assert r.status_code == 422
    assert "does not exist" in r.json()["detail"]


@pytest.mark.asyncio
async def test_malformed_code_is_rejected(client: AsyncClient):
    token = await _register_and_token(client, "icd11_malformed@example.com")
    r = await client.post(
        "/api/v1/chronic/conditions",
        json=_condition(icd11_code="not-a-code"),
        headers=_auth(token),
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_condition_without_a_code_still_saves(client: AsyncClient):
    # Coding is optional — a patient who does not know their code must still
    # be able to record the condition by name.
    token = await _register_and_token(client, "icd11_none@example.com")
    r = await client.post(
        "/api/v1/chronic/conditions",
        json=_condition(),
        headers=_auth(token),
    )
    assert r.status_code == 201
    assert r.json()["icd11_code"] is None


@pytest.mark.asyncio
async def test_icd10_and_icd11_coexist(client: AsyncClient):
    """Both codes survive on one record.

    They are different facts: ICD-10 is what the FHIR/PDF import read off a
    source document, ICD-11 is what the patient selected.
    """
    token = await _register_and_token(client, "icd11_both@example.com")
    r = await client.post(
        "/api/v1/chronic/conditions",
        json=_condition(icd10_code="N18.6", icd11_code="GB61.5"),
        headers=_auth(token),
    )
    assert r.status_code == 201
    body = r.json()
    assert body["icd10_code"] == "N18.6"
    assert body["icd11_code"] == "GB61.5"


# ── Updating ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_partial_update_leaves_the_code_alone(client: AsyncClient):
    token = await _register_and_token(client, "icd11_patch@example.com")
    created = await client.post(
        "/api/v1/chronic/conditions",
        json=_condition(icd11_code="GB61.5"),
        headers=_auth(token),
    )
    cid = created.json()["id"]

    r = await client.put(
        f"/api/v1/chronic/conditions/{cid}",
        json={"notes": "seen in clinic"},
        headers=_auth(token),
    )
    assert r.status_code == 200
    assert r.json()["icd11_code"] == "GB61.5"
    assert r.json()["icd11_title"] == "Chronic kidney disease, stage 5"


@pytest.mark.asyncio
async def test_explicit_null_clears_code_and_title(client: AsyncClient):
    token = await _register_and_token(client, "icd11_clear@example.com")
    created = await client.post(
        "/api/v1/chronic/conditions",
        json=_condition(icd11_code="GB61.5"),
        headers=_auth(token),
    )
    cid = created.json()["id"]

    r = await client.put(
        f"/api/v1/chronic/conditions/{cid}",
        json={"icd11_code": None},
        headers=_auth(token),
    )
    assert r.status_code == 200
    # The title must go with the code — a stale title beside a cleared code
    # would read as a diagnosis nobody entered.
    assert r.json()["icd11_code"] is None
    assert r.json()["icd11_title"] is None


@pytest.mark.asyncio
async def test_update_to_a_new_code_retitles(client: AsyncClient):
    token = await _register_and_token(client, "icd11_retitle@example.com")
    created = await client.post(
        "/api/v1/chronic/conditions",
        json=_condition(icd11_code="GB61.5"),
        headers=_auth(token),
    )
    cid = created.json()["id"]

    r = await client.put(
        f"/api/v1/chronic/conditions/{cid}",
        json={"icd11_code": "3A51.1"},
        headers=_auth(token),
    )
    assert r.status_code == 200
    assert r.json()["icd11_title"] == "Sickle cell disease without crisis"


# ── Many conditions per patient ───────────────────────────────────────


@pytest.mark.asyncio
async def test_a_patient_can_hold_many_independently_coded_conditions(client: AsyncClient):
    """Conditions are one row each, so a patient carries as many as they have.

    Comorbidity is the norm in this population, not the exception — the ESRD
    patient in the production record also has obesity and an old ligament
    injury. Each condition keeps its own code, severity and active flag; coding
    one must not disturb another.
    """
    token = await _register_and_token(client, "icd11_many@example.com")

    wanted = [
        ("End-Stage Renal Disease", "renal", "severe", "GB61.5",
         "Chronic kidney disease, stage 5"),
        ("Sickle cell disease", "blood_disorder", "moderate", "3A51.1",
         "Sickle cell disease without crisis"),
        ("G6PD deficiency", "blood_disorder", "mild", "3A10.00",
         "Haemolytic anaemia due to glucose-6-phosphate dehydrogenase deficiency"),
        ("Type 2 diabetes", "diabetes", "moderate", "5A11", "Type 2 diabetes mellitus"),
        # Deliberately uncoded: not knowing a code must never block recording.
        ("Chronic back pain", "other", "mild", None, None),
    ]

    for name, category, severity, code, _ in wanted:
        payload = _condition(condition_name=name, category=category, severity=severity)
        if code:
            payload["icd11_code"] = code
        r = await client.post(
            "/api/v1/chronic/conditions", json=payload, headers=_auth(token)
        )
        assert r.status_code == 201, r.text

    listed = await client.get(
        "/api/v1/chronic/conditions",
        params={"limit": 1000},
        headers=_auth(token),
    )
    assert listed.status_code == 200
    rows = listed.json()
    assert len(rows) == len(wanted)

    by_name = {row["condition_name"]: row for row in rows}
    for name, _, _, code, title in wanted:
        assert by_name[name]["icd11_code"] == code
        assert by_name[name]["icd11_title"] == title


@pytest.mark.asyncio
async def test_editing_one_condition_does_not_touch_the_others(client: AsyncClient):
    token = await _register_and_token(client, "icd11_isolate@example.com")

    first = await client.post(
        "/api/v1/chronic/conditions",
        json=_condition(condition_name="ESRD", icd11_code="GB61.5"),
        headers=_auth(token),
    )
    second = await client.post(
        "/api/v1/chronic/conditions",
        json=_condition(condition_name="Sickle cell", icd11_code="3A51.1"),
        headers=_auth(token),
    )

    await client.put(
        f"/api/v1/chronic/conditions/{first.json()['id']}",
        json={"icd11_code": "GB61.4"},
        headers=_auth(token),
    )

    untouched = await client.get(
        f"/api/v1/chronic/conditions/{second.json()['id']}", headers=_auth(token)
    )
    assert untouched.json()["icd11_code"] == "3A51.1"
