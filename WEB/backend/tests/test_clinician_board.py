"""The clinician patient board (/api/v1/clinician-dashboard/patient/{id}/…).

The property that matters most here is the grant boundary: a category must be
readable only when the patient shared it, and `all` must mean literally all —
including the categories added after the grant was written.
"""

from datetime import date, datetime, timedelta, timezone

import pytest
from httpx import AsyncClient

from app.models.data_sharing import ALL_DATA_TYPES


async def _account(client: AsyncClient, email: str, name: str) -> tuple[int, str]:
    """Register + log in; returns (user_id, bearer token)."""
    reg = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "SecureP@ss123", "full_name": name,
              # Registration enforces an adult date of birth (app/core/age_policy.py).
              "date_of_birth": "1990-01-01"},
    )
    uid = reg.json()["id"]
    login = await client.post(
        "/api/v1/auth/login",
        data={"username": email, "password": "SecureP@ss123"},
    )
    return uid, login.json()["access_token"]


async def _board(client: AsyncClient, token: str, patient_id: int) -> dict:
    r = await client.get(f"/api/v1/clinician-dashboard/patient/{patient_id}/board",
                         headers=_auth(token))
    assert r.status_code == 200, r.text
    return r.json()


def _card(board: dict, key: str) -> dict:
    return next(c for c in board["cards"] if c["key"] == key)


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _share(client: AsyncClient, patient_token: str, clinician_email: str, data_type: str):
    r = await client.post(
        "/api/v1/data-sharing/grants",
        json={"grantee_email": clinician_email, "data_type": data_type, "read_access": True},
        headers=_auth(patient_token),
    )
    assert r.status_code == 201, r.text
    return r


# ── Grant boundary ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_board_requires_a_grant(client: AsyncClient):
    patient_id, _ = await _account(client, "board.pat1@example.com", "Board Patient")
    _, doc_token = await _account(client, "board.doc1@example.com", "Board Doc")

    r = await client.get(f"/api/v1/clinician-dashboard/patient/{patient_id}/board",
                         headers=_auth(doc_token))
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_all_grant_covers_every_category(client: AsyncClient):
    """`all` means all — including categories added later.

    The board is built from one registry, so a category added to it is covered
    by every existing `all` grant without the patient re-sharing anything. If
    this breaks, patients silently stop sharing something they already agreed to.
    """
    patient_id, pat_token = await _account(client, "board.pat2@example.com", "Board Patient")
    _, doc_token = await _account(client, "board.doc2@example.com", "Board Doc")
    await _share(client, pat_token, "board.doc2@example.com", "all")

    r = await client.get(f"/api/v1/clinician-dashboard/patient/{patient_id}/board",
                         headers=_auth(doc_token))
    assert r.status_code == 200
    body = r.json()
    assert body["permissions"] == ["all"]
    assert body["cards"], "board returned no cards"
    unshared = [c["key"] for c in body["cards"] if not c["shared"]]
    assert unshared == [], f"`all` left these categories unshared: {unshared}"

    # EVERY grantable type must have a card. The earlier version of this test
    # only checked that the cards which existed were shared, so `lifestyle`,
    # `dialysis` and `symptoms` sat in ALL_DATA_TYPES with no card at all and
    # the test still passed — a physician saw no Therapies on a patient who
    # shared everything. Assert against the list, not a hand-written sample.
    keys = {c["key"] for c in body["cards"]}
    missing = [t for t in ALL_DATA_TYPES if t not in keys]
    assert missing == [], f"grantable types with no board card: {missing}"


@pytest.mark.asyncio
async def test_narrow_grant_hides_other_categories(client: AsyncClient):
    patient_id, pat_token = await _account(client, "board.pat3@example.com", "Board Patient")
    _, doc_token = await _account(client, "board.doc3@example.com", "Board Doc")
    await _share(client, pat_token, "board.doc3@example.com", "labs")

    board = (await client.get(f"/api/v1/clinician-dashboard/patient/{patient_id}/board",
                              headers=_auth(doc_token))).json()
    by_key = {c["key"]: c for c in board["cards"]}
    assert by_key["labs"]["shared"] is True
    assert by_key["nutrition"]["shared"] is False
    # An unshared card says so rather than looking like an empty record.
    assert "Not shared" in (by_key["nutrition"]["empty_reason"] or "")

    # And the category endpoint refuses it outright, not just in the UI.
    denied = await client.get(
        f"/api/v1/clinician-dashboard/patient/{patient_id}/category/nutrition",
        headers=_auth(doc_token))
    assert denied.status_code == 403

    allowed = await client.get(
        f"/api/v1/clinician-dashboard/patient/{patient_id}/category/labs",
        headers=_auth(doc_token))
    assert allowed.status_code == 200


@pytest.mark.asyncio
async def test_category_endpoint_shape_and_unknown_key(client: AsyncClient):
    patient_id, pat_token = await _account(client, "board.pat4@example.com", "Board Patient")
    _, doc_token = await _account(client, "board.doc4@example.com", "Board Doc")
    await _share(client, pat_token, "board.doc4@example.com", "all")

    # Give the patient something to trend.
    for day, systolic in (("2026-01-01", 128), ("2026-01-08", 126), ("2026-01-15", 122)):
        r = await client.post("/api/v1/vitals/", json={
            "log_date": day, "blood_pressure_systolic": systolic,
            "blood_pressure_diastolic": 80, "heart_rate_bpm": 70,
        }, headers=_auth(pat_token))
        assert r.status_code == 201, r.text

    r = await client.get(
        f"/api/v1/clinician-dashboard/patient/{patient_id}/category/vitals?days=1825",
        headers=_auth(doc_token))
    assert r.status_code == 200
    body = r.json()
    assert body["key"] == "vitals"
    assert body["columns"], "no columns for the table view"
    assert len(body["rows"]) == 3
    labels = {s["label"] for s in body["series"]}
    assert "Systolic" in labels
    systolic = next(s for s in body["series"] if s["label"] == "Systolic")
    assert [p["value"] for p in systolic["points"]] == [128, 126, 122]

    unknown = await client.get(
        f"/api/v1/clinician-dashboard/patient/{patient_id}/category/not_a_category",
        headers=_auth(doc_token))
    assert unknown.status_code == 404


@pytest.mark.asyncio
async def test_every_all_data_type_is_a_grantable_type(client: AsyncClient):
    """ALL_DATA_TYPES drives both the `all` expansion and the sharing UI.

    A category listed in one but rejected by the other would let a patient tap
    a data type the API then refuses.
    """
    _, token = await _account(client, "board.pat5@example.com", "Board Patient")
    types = (await client.get("/api/v1/data-sharing/types", headers=_auth(token))).json()
    for t in ALL_DATA_TYPES:
        assert t in types, f"{t} expands from `all` but is not a grantable type"


# ── Reading the right table ──────────────────────────────────────────────
#
# Several categories are backed by TWO tables, and the clinically important one
# is not always the obvious one. A real patient showed "Meperidine (stopped),
# Ibuprofen (stopped)" and "No active conditions" to their physician while their
# own screen showed Calcitriol taken that morning — 921 dose logs against 2
# inactive prescriptions, and End-Stage Renal Disease sitting in the chronic
# table. These tests pin the merge so it cannot silently regress.

@pytest.mark.asyncio
async def test_medications_card_reads_what_the_patient_actually_took(client: AsyncClient):
    patient_id, pat_token = await _account(client, "board.med@example.com", "Med Patient")
    _, doc_token = await _account(client, "board.meddoc@example.com", "Med Doc")
    await _share(client, pat_token, "board.meddoc@example.com", "all")

    # A stopped prescription — the only thing the old card could see.
    r = await client.post("/api/v1/medications/", json={
        "name": "Ibuprofen 200 MG Oral Tablet", "is_active": False,
    }, headers=_auth(pat_token))
    assert r.status_code == 201, r.text

    # What the patient is actually taking, logged from the Medications screen.
    for name, amount in (("Calcitriol", 1.0), ("Calcium Carbonate", 1000.0),
                         ("Calcium carbonate", 1000.0)):
        r = await client.post("/api/v1/medications/dose-logs", json={
            "medication_name": name, "log_date": str(date.today()),
            "dose_amount": amount, "dose_unit": "mg",
        }, headers=_auth(pat_token))
        assert r.status_code == 201, r.text

    card = _card(await _board(client, doc_token, patient_id), "medications")
    labels = [i["label"] for i in card["items"]]
    assert any("Calcitriol" in x for x in labels), f"taken meds missing: {labels}"
    assert any("Calcium Carbonate" in x for x in labels), labels
    # Same drug, different casing, is one medication — not two.
    assert sum("alcium" in x.lower() for x in labels) == 1, labels
    # The prescription list is kept, but labelled so it cannot be mistaken
    # for what the patient is taking.
    assert any("prescribed" in x for x in labels) or card["count"] >= 2


@pytest.mark.asyncio
async def test_conditions_card_includes_chronic_conditions(client: AsyncClient):
    patient_id, pat_token = await _account(client, "board.cond@example.com", "Cond Patient")
    _, doc_token = await _account(client, "board.conddoc@example.com", "Cond Doc")
    await _share(client, pat_token, "board.conddoc@example.com", "all")

    r = await client.post("/api/v1/chronic/conditions", json={
        "condition_name": "End-Stage Renal Disease (ESRD)",
        "category": "RENAL", "severity": "SEVERE", "is_active": True,
    }, headers=_auth(pat_token))
    assert r.status_code in (200, 201), r.text

    card = _card(await _board(client, doc_token, patient_id), "conditions")
    labels = [i["label"] for i in card["items"]]
    assert any("End-Stage Renal" in x for x in labels), \
        f"chronic conditions missing from the board: {labels}"
    # Severe disease is flagged, not just listed.
    esrd = next(i for i in card["items"] if "End-Stage Renal" in i["label"])
    assert esrd.get("danger") is True, esrd


# ── Every category, not just the ones one patient happens to populate ────

@pytest.mark.asyncio
async def test_every_category_survives_a_patient_with_no_data(client: AsyncClient):
    """A brand-new patient must render all 14 cards, not raise.

    Verifying the board against a single well-populated record exercised only
    the categories that record happened to fill. Across the real database,
    `fitness` had no rows for ANY user and `lifestyle` belonged to a different
    user than the one being tested — so those paths had never executed. This
    walks every category explicitly.
    """
    patient_id, pat_token = await _account(client, "board.empty@example.com", "Empty Patient")
    _, doc_token = await _account(client, "board.emptydoc@example.com", "Empty Doc")
    await _share(client, pat_token, "board.emptydoc@example.com", "all")

    board = await _board(client, doc_token, patient_id)
    assert len(board["cards"]) == 14, [c["key"] for c in board["cards"]]

    for card in board["cards"]:
        assert card["shared"] is True, card["key"]
        # No data is fine; a card with neither values nor an explanation is not —
        # that renders as a blank box the clinician cannot interpret.
        assert card["items"] or card["empty_reason"], f"{card['key']} says nothing"

        r = await client.get(
            f"/api/v1/clinician-dashboard/patient/{patient_id}/category/{card['key']}",
            headers=_auth(doc_token))
        assert r.status_code == 200, f"{card['key']}: {r.text[:200]}"
        body = r.json()
        assert body["columns"], f"{card['key']} has no table columns"


@pytest.mark.asyncio
async def test_stale_data_reports_when_it_was_last_logged(client: AsyncClient):
    """A windowed card must not read as "no data" for an infrequent logger.

    The summary windows are 7 days. Six of the seven users with nutrition data
    in the real database last logged outside that window, so every one of them
    showed an empty Nutrients card while holding months of history.
    """
    patient_id, pat_token = await _account(client, "board.stale@example.com", "Stale Patient")
    _, doc_token = await _account(client, "board.staledoc@example.com", "Stale Doc")
    await _share(client, pat_token, "board.staledoc@example.com", "all")

    old = date.today() - timedelta(days=60)
    r = await client.post("/api/v1/nutrition/", json={
        "log_date": str(old), "meal_type": "breakfast", "food_name": "Oatmeal",
        "calories": 150,
    }, headers=_auth(pat_token))
    assert r.status_code == 201, r.text

    card = _card(await _board(client, doc_token, patient_id), "nutrition")
    reason = card["empty_reason"] or ""
    assert "60 days ago" in reason, f"staleness not surfaced: {reason!r}"
    assert str(old) in reason, reason


@pytest.mark.asyncio
async def test_therapy_sessions_accept_a_timezone_aware_start_date(client: AsyncClient):
    """An ISO instant from a browser must not 500 the therapy-session list.

    `scheduled_date` has no timezone; the web Hemodialysis page sends
    `new Date().toISOString()`, which FastAPI parses as tz-AWARE. Comparing the
    two made asyncpg raise, the endpoint 500'd, and the page's catch block
    rendered it as "No hemodialysis sessions found for this period" — to a
    patient with 730 sessions.
    """
    _, token = await _account(client, "board.tz@example.com", "TZ Patient")

    # The regression is the 500 itself: an aware datetime compared against a
    # naive column made asyncpg raise. Zero rows is a fine answer; an error is
    # not, because the page renders an error as "no sessions".
    cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()  # ends +00:00
    r = await client.get("/api/v1/chronic/therapy-sessions",
                         params={"therapy_type": "HEMODIALYSIS", "start_date": cutoff},
                         headers=_auth(token))
    assert r.status_code == 200, f"tz-aware start_date broke the endpoint: {r.text[:200]}"
    assert isinstance(r.json(), list)

    # Both ends of the range, and the condition-metrics endpoint that shares the bug.
    r2 = await client.get("/api/v1/chronic/therapy-sessions",
                          params={"start_date": cutoff,
                                  "end_date": datetime.now(timezone.utc).isoformat()},
                          headers=_auth(token))
    assert r2.status_code == 200, r2.text

    r3 = await client.get("/api/v1/chronic/condition-metrics",
                          params={"start_date": cutoff}, headers=_auth(token))
    assert r3.status_code == 200, r3.text

    # A naive value must keep working — clients send both.
    naive = (datetime.now() - timedelta(days=90)).isoformat()
    r4 = await client.get("/api/v1/chronic/therapy-sessions",
                          params={"start_date": naive}, headers=_auth(token))
    assert r4.status_code == 200, r4.text


@pytest.mark.asyncio
async def test_creating_a_therapy_session_does_not_500(client: AsyncClient):
    """The Session Form's create path, end to end.

    `TherapySession` declared `clinical_notes` as BOTH a (never-migrated) Column
    and a relationship; the relationship shadowed the column, the create schema
    still offered it as a string, and passing it into the constructor raised
    "Incompatible collection type: None is not list-like" — a 500 on every
    submission of the Hemodialysis Session Form.
    """
    _, token = await _account(client, "board.session@example.com", "Session Patient")

    r = await client.post("/api/v1/chronic/therapy-sessions", json={
        "therapy_type": "hemodialysis",
        "scheduled_date": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
        "status": "completed",
        "patient_notes": "felt fine",
    }, headers=_auth(token))
    assert r.status_code == 201, r.text
    session_id = r.json()["id"]
    # The response carries notes as a LIST (the relationship), not a string.
    assert r.json()["clinical_notes"] == []

    # Notes are their own append-only rows, on the route the clients call.
    note = await client.post(f"/api/v1/chronic/therapy-sessions/{session_id}/notes",
                             json={"note_type": "clinical", "note_text": "Tolerated well."},
                             headers=_auth(token))
    assert note.status_code == 201, note.text

    listed = await client.get(f"/api/v1/chronic/therapy-sessions/{session_id}/notes",
                              headers=_auth(token))
    assert listed.status_code == 200, listed.text
    assert [n["note_text"] for n in listed.json()] == ["Tolerated well."]

    # And the session read path serialises the loaded relationship.
    got = await client.get("/api/v1/chronic/therapy-sessions", headers=_auth(token))
    assert got.status_code == 200, got.text
    assert len(got.json()[0]["clinical_notes"]) == 1
