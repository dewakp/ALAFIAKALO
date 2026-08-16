"""Duplicate therapy sessions and duplicate intradialytic readings.

Both were real, and both came from a save that half-succeeded:

  - Editing a session PUT the session and then POSTed every reading again, so
    each edit re-inserted the whole grid.
  - A save that created the session and then failed on its readings left an
    empty row behind; the user retried and got two sessions for one treatment.
    On 2026-08-15 that is id 2739 (23:20, every clinical field NULL, no
    readings) beside id 2740 (00:49, the real data).

Both guards have to stay narrow, and the first attempt at one was NOT.

Deduplicating readings on (session_id, reading_time) looked obvious and would
have merged 1816 rows across 1267 sessions: the flowsheet import never captured
the clock time, so 3664 readings — 22.6% of the table — sit at 00:00:00, and
1263 of the 1271 same-time collisions are at exactly that value. Session 757
holds two midnight rows reading 144/95 p102 and 140/88 p111 — two observations
with one lost timestamp, not one observation stored twice.

Sessions are the same shape: two treatments in a day are told apart by their
start and finish times, and only 16 of 150 same-day rows carry a start time at
all because the import dropped those too.
"""

import pytest
from httpx import AsyncClient


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _account(client: AsyncClient, email: str) -> tuple[int, str]:
    reg = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "SecureP@ss123", "full_name": "Dup Test",
              "date_of_birth": "1990-01-01"},
    )
    uid = reg.json()["id"]
    login = await client.post("/api/v1/auth/login",
                              data={"username": email, "password": "SecureP@ss123"})
    return uid, login.json()["access_token"]


async def _create_session(client, token, **fields) -> dict:
    body = {"therapy_type": "hemodialysis", "scheduled_date": "2026-08-15T00:00:00Z",
            "status": "completed"}
    body.update(fields)
    r = await client.post("/api/v1/chronic/therapy-sessions", json=body, headers=_auth(token))
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.asyncio
async def test_two_readings_at_the_same_time_are_both_kept(client: AsyncClient):
    """THE regression test. reading_time is not a key — the import made it useless.

    Session 757 in production holds two 00:00:00 rows with different vitals.
    Deduplicating on the timepoint would erase one of them.
    """
    _, token = await _account(client, "dup-same-time@example.com")
    sid = (await _create_session(client, token, pre_dialysis_weight_kg=55.1))["id"]

    for sys_bp, dia, pulse in ((144, 95, 102), (140, 88, 111)):
        r = await client.post(
            f"/api/v1/chronic/therapy-sessions/{sid}/readings",
            json={"session_id": sid, "reading_time": "00:00", "systolic_bp": sys_bp,
                  "diastolic_bp": dia, "pulse": pulse},
            headers=_auth(token))
        assert r.status_code == 201, r.text

    rows = (await client.get(f"/api/v1/chronic/therapy-sessions/{sid}/readings",
                             headers=_auth(token))).json()
    assert len(rows) == 2, f"a distinct reading was merged away: {rows}"
    assert sorted(x["systolic_bp"] for x in rows) == [140, 144]


@pytest.mark.asyncio
async def test_an_exact_resend_does_not_duplicate(client: AsyncClient):
    """Every clinical column equal = a double submit. That, and only that."""
    _, token = await _account(client, "dup-exact@example.com")
    sid = (await _create_session(client, token, pre_dialysis_weight_kg=55.1))["id"]

    reading = {"session_id": sid, "reading_time": "14:30", "systolic_bp": 120,
               "diastolic_bp": 80, "pulse": 70}
    for _ in range(3):
        r = await client.post(f"/api/v1/chronic/therapy-sessions/{sid}/readings",
                              json=reading, headers=_auth(token))
        assert r.status_code == 201, r.text

    rows = (await client.get(f"/api/v1/chronic/therapy-sessions/{sid}/readings",
                             headers=_auth(token))).json()
    assert len(rows) == 1, f"an identical re-send was stored again: {rows}"


@pytest.mark.asyncio
async def test_one_differing_value_makes_it_a_new_reading(client: AsyncClient):
    """A single changed vital is a different observation, not a duplicate."""
    _, token = await _account(client, "dup-one-diff@example.com")
    sid = (await _create_session(client, token, pre_dialysis_weight_kg=55.1))["id"]

    base = {"session_id": sid, "reading_time": "14:30", "systolic_bp": 120,
            "diastolic_bp": 80, "pulse": 70}
    await client.post(f"/api/v1/chronic/therapy-sessions/{sid}/readings",
                      json=base, headers=_auth(token))
    await client.post(f"/api/v1/chronic/therapy-sessions/{sid}/readings",
                      json={**base, "pulse": 71}, headers=_auth(token))

    rows = (await client.get(f"/api/v1/chronic/therapy-sessions/{sid}/readings",
                             headers=_auth(token))).json()
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_two_distinct_timepoints_are_both_kept(client: AsyncClient):
    _, token = await _account(client, "dup-two-times@example.com")
    sid = (await _create_session(client, token, pre_dialysis_weight_kg=55.1))["id"]

    for t, sys_bp in (("14:30", 120), ("15:00", 110), ("15:30", 105)):
        r = await client.post(f"/api/v1/chronic/therapy-sessions/{sid}/readings",
                              json={"session_id": sid, "reading_time": t,
                                    "systolic_bp": sys_bp},
                              headers=_auth(token))
        assert r.status_code == 201, r.text

    rows = (await client.get(f"/api/v1/chronic/therapy-sessions/{sid}/readings",
                             headers=_auth(token))).json()
    assert len(rows) == 3


@pytest.mark.asyncio
async def test_an_empty_shell_is_reused_not_duplicated(client: AsyncClient):
    """The 2026-08-15 case: retry after a failed save must not leave two rows."""
    _, token = await _account(client, "dup-shell@example.com")

    # The save that died before writing any clinical values.
    shell = await _create_session(client, token)
    # The user retries the form, this time completely.
    retry = await _create_session(client, token, pre_dialysis_weight_kg=55.1,
                                  post_dialysis_weight_kg=55.3, fluid_removed_ml=-200)

    assert retry["id"] == shell["id"], "the retry created a second session"

    listed = (await client.get("/api/v1/chronic/therapy-sessions",
                               headers=_auth(token))).json()
    assert len(listed) == 1, f"expected one session for the day, got {len(listed)}"
    assert listed[0]["pre_dialysis_weight_kg"] == 55.1, "the retry's data must survive"


@pytest.mark.asyncio
async def test_a_second_real_session_on_the_same_day_is_allowed(client: AsyncClient):
    """133 of 150 same-day rows in production are real treatments. Do not block them."""
    _, token = await _account(client, "dup-two-real@example.com")

    first = await _create_session(client, token, pre_dialysis_weight_kg=55.1)
    second = await _create_session(client, token, pre_dialysis_weight_kg=54.0)

    assert second["id"] != first["id"], "a populated same-day session was swallowed"
    listed = (await client.get("/api/v1/chronic/therapy-sessions",
                               headers=_auth(token))).json()
    assert len(listed) == 2


@pytest.mark.asyncio
async def test_a_shell_of_a_different_therapy_is_not_recycled(client: AsyncClient):
    """Recycling is keyed on the therapy too — a chemo shell is not a dialysis slot."""
    _, token = await _account(client, "dup-other-therapy@example.com")

    shell = await _create_session(client, token, therapy_type="chemotherapy")
    hd = await _create_session(client, token, therapy_type="hemodialysis",
                               pre_dialysis_weight_kg=55.1)
    assert hd["id"] != shell["id"]


@pytest.mark.asyncio
async def test_same_day_different_start_times_are_two_treatments(client: AsyncClient):
    """Two treatments in a day are told apart by start and finish."""
    _, token = await _account(client, "dup-two-slots@example.com")

    morning = await _create_session(client, token, pre_dialysis_weight_kg=55.1,
                                    actual_start_time="2026-08-15T08:00:00Z",
                                    actual_end_time="2026-08-15T11:30:00Z")
    evening = await _create_session(client, token, pre_dialysis_weight_kg=54.2,
                                    actual_start_time="2026-08-15T19:00:00Z",
                                    actual_end_time="2026-08-15T22:30:00Z")
    assert evening["id"] != morning["id"], "a second treatment was swallowed"


@pytest.mark.asyncio
async def test_same_day_same_start_time_is_the_same_treatment(client: AsyncClient):
    """Resubmitting the same slot must not create a second row."""
    _, token = await _account(client, "dup-same-slot@example.com")

    first = await _create_session(client, token, pre_dialysis_weight_kg=55.1,
                                  actual_start_time="2026-08-15T08:00:00Z",
                                  actual_end_time="2026-08-15T11:30:00Z")
    again = await _create_session(client, token, pre_dialysis_weight_kg=55.4,
                                  actual_start_time="2026-08-15T08:00:00Z",
                                  actual_end_time="2026-08-15T11:30:00Z")
    assert again["id"] == first["id"], "the same slot was stored twice"

    listed = (await client.get("/api/v1/chronic/therapy-sessions",
                               headers=_auth(token))).json()
    assert len(listed) == 1
    assert listed[0]["pre_dialysis_weight_kg"] == 55.4, "the resubmission must win"


@pytest.mark.asyncio
async def test_editing_a_reading_updates_it_rather_than_adding_one(client: AsyncClient):
    """The edit path the web form now uses: PUT an existing row, POST only new ones."""
    _, token = await _account(client, "dup-edit@example.com")
    sid = (await _create_session(client, token, pre_dialysis_weight_kg=55.1))["id"]

    created = (await client.post(
        f"/api/v1/chronic/therapy-sessions/{sid}/readings",
        json={"session_id": sid, "reading_time": "14:30", "systolic_bp": 120,
              "diastolic_bp": 80, "pulse": 70},
        headers=_auth(token))).json()

    edited = await client.put(
        f"/api/v1/chronic/readings/{created['id']}",
        json={"session_id": sid, "reading_time": "14:35", "systolic_bp": 118,
              "diastolic_bp": 78, "pulse": 72},
        headers=_auth(token))
    assert edited.status_code == 200, edited.text

    rows = (await client.get(f"/api/v1/chronic/therapy-sessions/{sid}/readings",
                             headers=_auth(token))).json()
    assert len(rows) == 1, f"editing added a row instead of changing one: {rows}"
    assert rows[0]["systolic_bp"] == 118
    assert rows[0]["reading_time"].startswith("14:35")


@pytest.mark.asyncio
async def test_a_reading_cannot_be_edited_across_accounts(client: AsyncClient):
    _, mine = await _account(client, "dup-owner@example.com")
    _, theirs = await _account(client, "dup-stranger@example.com")
    sid = (await _create_session(client, mine, pre_dialysis_weight_kg=55.1))["id"]
    created = (await client.post(
        f"/api/v1/chronic/therapy-sessions/{sid}/readings",
        json={"session_id": sid, "reading_time": "14:30", "systolic_bp": 120},
        headers=_auth(mine))).json()

    r = await client.put(f"/api/v1/chronic/readings/{created['id']}",
                         json={"session_id": sid, "systolic_bp": 999},
                         headers=_auth(theirs))
    assert r.status_code == 404
