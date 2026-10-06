# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""The hospital-history endpoints, over real HTTP against the app.

Covers what neither the reader tests nor the mapper tests can reach: the nine
routes, the ownership boundary, and three decisions that are easy to "simplify"
into bugs later —

- a create that OMITS `status` must succeed (`status` is NOT NULL with a
  Python-side default, and an explicit None would insert NULL and 500);
- deleting a stay must leave its procedures standing, detached, because the
  deployed FK is ON DELETE SET NULL and an operation that happened is a fact
  about the patient's body;
- `lasting_effects` is NOT filtered by `since`, because a parathyroidectomy
  from 2019 still governs this patient's calcium today.
"""

from datetime import datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.hospitalization import Hospitalization, SurgicalProcedure

BASE = "/api/v1/hospital"
PASSWORD = "SecureP@ss123"


async def _token(client: AsyncClient, email: str) -> str:
    """Register + log in. NOT a `.test` address — EmailStr refuses RFC 6761
    special-use domains, which answers 422 and then looks like a login bug."""
    created = await client.post("/api/v1/auth/register", json={
        "email": email, "password": PASSWORD,
        "full_name": "Ada Demo", "date_of_birth": "1990-01-01",
    })
    assert created.status_code in (200, 201), (
        f"register failed {created.status_code}: {created.text}")
    r = await client.post("/api/v1/auth/login",
                          data={"username": email, "password": PASSWORD})
    assert r.status_code == 200, f"login failed {r.status_code}: {r.text}"
    return r.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_a_stay_arrives_with_its_procedures_in_one_request(
        client: AsyncClient, db):
    """How a discharge summary actually arrives."""
    token = await _token(client, "hospital-create@example.com")
    r = await client.post(f"{BASE}/stays", headers=_auth(token), json={
        "admitted_at": "2024-03-02T14:00:00Z",
        "discharged_at": "2024-03-06T09:30:00Z",
        "facility_name": "Montgomery General",
        "reason": "Fluid overload",
        "admission_type": "elective",
        "status": "discharged",
        "procedures": [{
            "name": "AV fistula creation",
            "code": "0JH60XZ", "code_system": "ICD-10-PCS",
            "performed_at": "2024-03-03T10:00:00Z",
            "outcome": "successful",
        }],
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["facility_name"] == "Montgomery General"
    assert body["admission_type"] == "elective"
    assert [p["name"] for p in body["procedures"]] == ["AV fistula creation"]
    assert body["procedures"][0]["code_system"] == "ICD-10-PCS"
    # What matters is what is STORED, not how it serialises. `admitted_at` is
    # `timestamp WITHOUT time zone`; an AWARE value in that column is the §3aa
    # fault that rendered 730 dialysis sessions as "no sessions found" — an
    # asyncpg DataError on the first comparison, swallowed into an empty state.
    #
    # The response STRING is evidence about serialisation only: measured on
    # pydantic 2.10.4, a naive datetime renders as `2024-03-02T14:00:00` and an
    # aware one as `2024-03-02T14:00:00Z`. Asserting on the suffix conflated
    # the two, which is why this check reads the column instead.
    await db.commit()
    stored = (await db.execute(select(Hospitalization).where(
        Hospitalization.id == body["id"]))).scalar_one()
    assert stored.admitted_at.tzinfo is None, (
        f"stored an AWARE datetime {stored.admitted_at!r} in a naive column — "
        "asyncpg raises DataError the first time anything compares against it")
    assert stored.admitted_at == datetime(2024, 3, 2, 14, 0)
    assert stored.discharged_at == datetime(2024, 3, 6, 9, 30)

    # Queried, NOT reached through `stored.procedures`: that relationship is
    # lazily loaded, and touching it on an AsyncSession raises MissingGreenlet
    # — the same hazard that keeps nested procedures off
    # `HospitalizationResponse`.
    proc = (await db.execute(select(SurgicalProcedure).where(
        SurgicalProcedure.hospitalization_id == stored.id))).scalar_one()
    assert proc.performed_at == datetime(2024, 3, 3, 10, 0)
    assert proc.performed_at.tzinfo is None


@pytest.mark.asyncio
async def test_a_create_that_omits_status_succeeds(client: AsyncClient):
    """`status` is NOT NULL with a Python-side default.

    `model_dump()` would emit `status: None`, SQLAlchemy applies its default
    only when the attribute was never SET, and an explicit None inserts NULL —
    a 500 on a create that simply left the field out.
    """
    token = await _token(client, "hospital-minimal@example.com")
    r = await client.post(f"{BASE}/stays", headers=_auth(token),
                          json={"admitted_at": "2026-09-30T03:15:00Z"})
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "discharged"      # the model default applied
    assert r.json()["discharged_at"] is None       # still an inpatient
    assert r.json()["source"] == "manual"


@pytest.mark.asyncio
async def test_a_discharge_before_the_admission_is_refused(client: AsyncClient):
    token = await _token(client, "hospital-inverted@example.com")
    r = await client.post(f"{BASE}/stays", headers=_auth(token), json={
        "admitted_at": "2024-03-06T00:00:00Z",
        "discharged_at": "2024-03-02T00:00:00Z",
    })
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_history_returns_stays_every_procedure_and_the_lasting_effects(
        client: AsyncClient):
    token = await _token(client, "hospital-history@example.com")
    stay = await client.post(f"{BASE}/stays", headers=_auth(token), json={
        "admitted_at": "2024-03-02T14:00:00Z",
        "discharged_at": "2024-03-06T09:30:00Z",
        "facility_name": "Montgomery General",
        "procedures": [{"name": "AV fistula creation",
                        "performed_at": "2024-03-03T10:00:00Z"}],
    })
    assert stay.status_code == 201, stay.text

    # A procedure with NO admission — the case the nullable FK exists for.
    orphan = await client.post(f"{BASE}/procedures", headers=_auth(token), json={
        "name": "Parathyroidectomy",
        "performed_at": "2019-06-11T08:00:00Z",
        "ongoing_effects": "Parathyroid glands removed; calcium must be supplemented.",
    })
    assert orphan.status_code == 201, orphan.text

    h = await client.get(f"{BASE}/history", headers=_auth(token))
    assert h.status_code == 200, h.text
    body = h.json()

    assert [s["admitted"] for s in body["stays"]] == ["2024-03-02"]
    assert body["stays"][0]["nights"] == 4
    assert [p["name"] for p in body["stays"][0]["procedures"]] == ["AV fistula creation"]

    # The complete list holds BOTH — this is the half a stays-only client loses.
    assert [p["name"] for p in body["procedures"]] == [
        "AV fistula creation", "Parathyroidectomy"]
    assert body["procedures"][0]["admission"] == "2024-03-02 — Montgomery General"
    assert body["procedures"][1]["admission"] is None

    assert len(body["lasting_effects"]) == 1
    assert "Parathyroid glands removed" in body["lasting_effects"][0]


@pytest.mark.asyncio
async def test_lasting_effects_are_not_windowed_away_by_since(client: AsyncClient):
    """A 2019 operation still governs today's calcium.

    `since` narrows the stays and procedures a caller asked about. Applying it
    to the lasting effects would hide the one fact that is never historical.
    """
    token = await _token(client, "hospital-window@example.com")
    await client.post(f"{BASE}/procedures", headers=_auth(token), json={
        "name": "Parathyroidectomy",
        "performed_at": "2019-06-11T08:00:00Z",
        "ongoing_effects": "Parathyroid glands removed.",
    })

    h = await client.get(f"{BASE}/history", headers=_auth(token),
                         params={"since": "2026-01-01"})
    assert h.status_code == 200, h.text
    body = h.json()
    assert body["procedures"] == []          # correctly outside the window
    assert len(body["lasting_effects"]) == 1  # and still reported
    assert "Parathyroid glands removed" in body["lasting_effects"][0]


@pytest.mark.asyncio
async def test_deleting_a_stay_leaves_its_procedures_standing(
        client: AsyncClient, db):
    """ON DELETE SET NULL, not a cascade.

    The model's relationship declares `cascade="all, delete-orphan"`, which an
    ORM delete would honour by destroying the procedures. The route uses
    explicit statements so the deployed FK's behaviour wins: a mistyped
    admission can be removed without erasing an operation that happened.
    """
    token = await _token(client, "hospital-delete@example.com")
    created = await client.post(f"{BASE}/stays", headers=_auth(token), json={
        "admitted_at": "2024-03-02T14:00:00Z",
        "facility_name": "Montgomery General",
        "procedures": [{"name": "AV fistula creation",
                        "performed_at": "2024-03-03T10:00:00Z",
                        "ongoing_effects": "Left forearm fistula in use."}],
    })
    assert created.status_code == 201, created.text
    stay_id = created.json()["id"]

    gone = await client.delete(f"{BASE}/stays/{stay_id}", headers=_auth(token))
    assert gone.status_code == 204, gone.text

    await db.commit()
    stays = (await db.execute(select(Hospitalization))).scalars().all()
    procs = (await db.execute(select(SurgicalProcedure))).scalars().all()
    assert stays == []
    assert [p.name for p in procs] == ["AV fistula creation"]
    assert procs[0].hospitalization_id is None       # detached, not deleted

    # And it still reports its lasting effect, with no stay to hang from.
    h = await client.get(f"{BASE}/history", headers=_auth(token))
    assert h.json()["stays"] == []
    assert [p["name"] for p in h.json()["procedures"]] == ["AV fistula creation"]
    assert len(h.json()["lasting_effects"]) == 1


@pytest.mark.asyncio
async def test_a_procedure_can_gain_its_lasting_effect_later(client: AsyncClient):
    """The field arrives from a clinician or the patient, in words."""
    token = await _token(client, "hospital-patch@example.com")
    created = await client.post(f"{BASE}/procedures", headers=_auth(token),
                                json={"name": "Parathyroidectomy",
                                      "performed_at": "2019-06-11T08:00:00Z"})
    assert created.status_code == 201, created.text
    assert (await client.get(f"{BASE}/history", headers=_auth(token))
            ).json()["lasting_effects"] == []

    patched = await client.patch(
        f"{BASE}/procedures/{created.json()['id']}", headers=_auth(token),
        json={"ongoing_effects": "Parathyroid glands removed."})
    assert patched.status_code == 200, patched.text

    effects = (await client.get(f"{BASE}/history", headers=_auth(token))
               ).json()["lasting_effects"]
    assert len(effects) == 1
    assert effects[0].startswith("Parathyroidectomy (2019-06-11):")


@pytest.mark.asyncio
async def test_another_patients_history_is_not_reachable(client: AsyncClient):
    """404, never 403 — the status must not confirm the row exists (§3b)."""
    mine = await _token(client, "hospital-mine@example.com")
    theirs = await _token(client, "hospital-theirs@example.com")

    created = await client.post(f"{BASE}/stays", headers=_auth(theirs),
                                json={"admitted_at": "2024-03-02T14:00:00Z"})
    assert created.status_code == 201, created.text
    other_stay = created.json()["id"]

    assert (await client.patch(f"{BASE}/stays/{other_stay}", headers=_auth(mine),
                               json={"ward": "B"})).status_code == 404
    assert (await client.delete(f"{BASE}/stays/{other_stay}",
                                headers=_auth(mine))).status_code == 404

    # And a procedure may not be attached to someone else's admission.
    attached = await client.post(f"{BASE}/procedures", headers=_auth(mine), json={
        "name": "Appendectomy", "hospitalization_id": other_stay})
    assert attached.status_code == 404, attached.text

    assert (await client.get(f"{BASE}/history", headers=_auth(mine))
            ).json()["stays"] == []


@pytest.mark.asyncio
async def test_the_endpoints_require_authentication(client: AsyncClient):
    for method, path in (("get", "/history"), ("get", "/stays"),
                         ("post", "/stays"), ("get", "/procedures"),
                         ("post", "/procedures")):
        r = await getattr(client, method)(
            f"{BASE}{path}", **({"json": {}} if method == "post" else {}))
        assert r.status_code == 401, f"{method} {path} → {r.status_code}"
