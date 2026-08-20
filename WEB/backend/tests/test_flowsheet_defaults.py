"""Pre-filling a new treatment form.

The point is to stop a patient re-typing what has not changed. The risk is
pre-filling something *wrong*, so the tests concentrate on the cases where a
naive implementation would quietly produce a bad default: a missing post weight
averaged in as zero, a stale dialysate prescription that is out of range, and
needle fields left enabled on a catheter.
"""

from datetime import date, datetime, timedelta

import pytest

from app.services.flowsheet_defaults import (
    ACCESS_CATHETER, ACCESS_NEEDLED, ACCESS_UNKNOWN,
    FISTULA_ONLY_FIELDS, TARGET_WEIGHT_WINDOW,
    classify_access, target_weight_from,
)


class _Session:
    """Enough of a TherapySession for the pure helpers."""

    def __init__(self, post_weight=None, when=None, access=None):
        self.post_dialysis_weight_kg = post_weight
        self.scheduled_date = when or datetime(2026, 8, 1)
        self.dialysis_access_type = access
        self.status = "COMPLETED"


class TestAccessClassification:
    """The column is free text: 'Catheter. URJ', 'AV Graft Left lower arm', and
    a misspelt 'Cather. URJ' all appear in real data."""

    @pytest.mark.parametrize("text", [
        "Catheter. URJ", "Central Catheter", "Right Arterial Catheter",
        "Catheter.", "perm-cath", "CVC", "Tunneled catheter",
    ])
    def test_catheters_are_recognised(self, text):
        assert classify_access(text) == ACCESS_CATHETER

    def test_a_misspelt_catheter_is_still_a_catheter(self):
        """'Cather. URJ' is in the data — a typo must not enable needle fields."""
        assert classify_access("Cather. URJ") == ACCESS_CATHETER

    @pytest.mark.parametrize("text", [
        "AV Graft Left lower arm", "AV Fistula", "Left arm fistula", "AVF", "AVG",
    ])
    def test_needled_accesses_are_recognised(self, text):
        assert classify_access(text) == ACCESS_NEEDLED

    def test_a_graft_counts_as_needled(self):
        """A graft is cannulated like a fistula — needle fields DO apply.

        454 sessions use one; disabling needle entry for them would stop the
        patient recording what actually happened.
        """
        assert classify_access("AV Graft Left lower arm") == ACCESS_NEEDLED

    @pytest.mark.parametrize("text", ["Access", "Arterio Vascular", "Arterial", "", None])
    def test_anything_unclear_disables_nothing(self, text):
        """Wrongly greying out a field is worse than an extra enabled one."""
        assert classify_access(text) == ACCESS_UNKNOWN


class TestTargetWeight:
    def test_it_averages_the_last_seven(self):
        sessions = [_Session(post_weight=70.0 + i) for i in range(10)]
        weight, basis, n = target_weight_from(sessions)
        assert n == TARGET_WEIGHT_WINDOW
        assert weight == pytest.approx(73.0)      # 70..76
        assert "last 7" in basis

    def test_a_missing_post_weight_is_skipped_not_counted_as_zero(self):
        """230 of this patient's 2005 sessions have no post weight.

        Averaging a null in as zero would drag the target down and set an unsafe
        fluid-removal goal.
        """
        sessions = [_Session(post_weight=70.0), _Session(post_weight=None), _Session(post_weight=72.0)]
        weight, _, n = target_weight_from(sessions)
        assert n == 2
        assert weight == pytest.approx(71.0)

    def test_an_implausible_weight_is_excluded(self):
        sessions = [_Session(post_weight=70.0), _Session(post_weight=0.4), _Session(post_weight=72.0)]
        weight, _, n = target_weight_from(sessions)
        assert n == 2
        assert weight == pytest.approx(71.0)

    def test_fewer_than_seven_says_so(self):
        """Don't silently average two and present it like a settled figure."""
        weight, basis, n = target_weight_from([_Session(post_weight=70.0), _Session(post_weight=72.0)])
        assert n == 2
        assert weight == pytest.approx(71.0)
        assert "fewer than 7" in basis

    def test_no_weights_at_all_asks_the_patient(self):
        weight, basis, n = target_weight_from([_Session(post_weight=None)])
        assert weight is None
        assert n == 0
        assert "enter today's target" in basis


@pytest.mark.asyncio
class TestDefaultsOverHttp:
    async def _token(self, client, email):
        await client.post("/api/v1/auth/register", json={
            "email": email, "password": "SecureP@ss123",
            "full_name": "Flow Tester", "date_of_birth": "1974-03-15",
        })
        r = await client.post("/api/v1/auth/login",
                              data={"username": email, "password": "SecureP@ss123"})
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    async def _session(self, client, headers, when, **fields):
        payload = {
            "therapy_type": "hemodialysis",
            "scheduled_date": datetime.combine(when, datetime.min.time()).isoformat(),
            "status": "completed",
        }
        payload.update(fields)
        r = await client.post("/api/v1/chronic/therapy-sessions", headers=headers, json=payload)
        assert r.status_code in (200, 201), r.text[:200]
        return r

    async def test_a_first_treatment_has_nothing_to_carry(self, client):
        headers = await self._token(client, "flow1@example.com")
        r = await client.get("/api/v1/chronic/therapy-sessions/defaults", headers=headers)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"
        body = r.json()
        assert body["target_weight_kg"] is None
        assert body["carried_forward"] == {}
        assert any("first recorded treatment" in n for n in body["notes"])

    async def test_settings_are_carried_from_the_last_session(self, client):
        headers = await self._token(client, "flow2@example.com")
        yesterday = date.today() - timedelta(days=1)
        await self._session(client, headers, yesterday,
                            attending_physician="Desai, Anand MD",
                            attending_nurse="R. Nurse",
                            dialysate_volume_liters=30,
                            dialysate_potassium_meq=1.0,
                            sak_number=4,
                            post_dialysis_weight_kg=70.0)

        body = (await client.get("/api/v1/chronic/therapy-sessions/defaults",
                                 headers=headers)).json()
        carried = body["carried_forward"]
        assert carried["attending_physician"] == "Desai, Anand MD"
        assert carried["dialysate_potassium_meq"] == 1.0
        assert carried["sak_number"] == 4
        assert body["carried_from_date"] == str(yesterday)

    async def test_an_out_of_range_dialysate_potassium_is_not_carried(self, client):
        """11 real sessions record 45 mEq/L — the lactate in the wrong column.

        Carrying it forward would seed a new treatment with an impossible
        prescription and skew the dialysis balance model.
        """
        headers = await self._token(client, "flow3@example.com")
        await self._session(client, headers, date.today() - timedelta(days=1),
                            dialysate_potassium_meq=45.0, post_dialysis_weight_kg=70.0)

        body = (await client.get("/api/v1/chronic/therapy-sessions/defaults",
                                 headers=headers)).json()
        assert "dialysate_potassium_meq" not in body["carried_forward"]
        assert any("outside the usual range" in n for n in body["notes"])

    async def test_a_catheter_disables_the_needle_fields(self, client):
        headers = await self._token(client, "flow4@example.com")
        await self._session(client, headers, date.today() - timedelta(days=1),
                            dialysis_access_type="Catheter. URJ",
                            post_dialysis_weight_kg=70.0)

        body = (await client.get("/api/v1/chronic/therapy-sessions/defaults",
                                 headers=headers)).json()
        assert body["access_kind"] == ACCESS_CATHETER
        assert set(body["disabled_fields"]) == set(FISTULA_ONLY_FIELDS)
        assert any("catheter" in n.lower() for n in body["notes"])

    async def test_a_graft_leaves_the_needle_fields_enabled(self, client):
        headers = await self._token(client, "flow5@example.com")
        await self._session(client, headers, date.today() - timedelta(days=1),
                            dialysis_access_type="AV Graft Left lower arm",
                            post_dialysis_weight_kg=70.0)

        body = (await client.get("/api/v1/chronic/therapy-sessions/defaults",
                                 headers=headers)).json()
        assert body["access_kind"] == ACCESS_NEEDLED
        assert body["disabled_fields"] == []

    async def test_the_target_weight_averages_past_sessions(self, client):
        headers = await self._token(client, "flow6@example.com")
        for i, weight in enumerate([70.0, 71.0, 72.0], start=1):
            await self._session(client, headers, date.today() - timedelta(days=i),
                                post_dialysis_weight_kg=weight)

        body = (await client.get("/api/v1/chronic/therapy-sessions/defaults",
                                 headers=headers)).json()
        assert body["target_weight_kg"] == pytest.approx(71.0)
        assert body["target_weight_sample_size"] == 3
        assert "fewer than 7" in body["target_weight_basis"]
