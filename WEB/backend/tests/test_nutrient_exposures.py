"""Collecting a day's agents from all three sources — and missing none of them.

§3aa names two medication tables and warns about a third. The reference record
holds Epogene x1,962 and Venofer x1,248 in that third one and ZERO of them in a
dose log, which is how a review of it concluded "no ESA prescribed or taken"
while the patient had been on one for years.

The guard that matters most here is the dose query's ABSENCE of a
`nutrients_resolved` filter. `_aggregate_daily_nutrients` has one, and
`api/medications.py` sets that flag as `bool(nutrients)` — so a drug that
contributes nothing ADDITIVELY is marked false forever. A phosphate binder
subtracts the phosphorus the patient ate; it adds none. On the dev copy of
production, Sevelamer is logged 168 times and every row is invisible to
nutrient tracking today.
"""

from __future__ import annotations

from datetime import date, datetime, time

import pytest

from app.models.chronic_conditions import TherapySession
from app.models.med_nutrient import MedicationDoseLog
from app.models.user import User
from app.services.nutrient_exposures import agent_pairs, exposures_for_day

DAY = date(2026, 5, 4)


async def _user(db, email: str) -> User:
    u = User(email=email, hashed_password="x", full_name="Exposure Test")
    db.add(u)
    await db.flush()
    return u


def _session(user_id: int, **kw) -> TherapySession:
    base = dict(
        user_id=user_id,
        therapy_type="hemodialysis",
        status="completed",
        scheduled_date=datetime.combine(DAY, time(9, 0)),
        dialysate_volume_liters=30.0,
    )
    base.update(kw)
    return TherapySession(**base)


def _dose(user_id: int, name: str, amount: float, unit: str, resolved: bool) -> MedicationDoseLog:
    return MedicationDoseLog(
        user_id=user_id, medication_name=name, log_date=DAY,
        dose_amount=amount, dose_unit=unit, nutrients_resolved=resolved,
    )


@pytest.mark.asyncio
async def test_a_completed_session_becomes_a_treatment_exposure(db):
    user = await _user(db, "exp-treatment@example.com")
    db.add(_session(user.id))
    await db.flush()

    exps = await exposures_for_day(db, user.id, DAY)
    treatments = [e for e in exps if e.kind == "treatment"]
    assert len(treatments) == 1
    assert treatments[0].key == "hemodialysis"
    assert treatments[0].context["dialysate_volume_l"] == 30.0


@pytest.mark.asyncio
async def test_an_unfinished_session_credits_nothing(db):
    """Booked, in progress or cancelled: the treatment did not happen."""
    user = await _user(db, "exp-inprogress@example.com")
    db.add(_session(user.id, status="IN_PROGRESS"))
    await db.flush()

    exps = await exposures_for_day(db, user.id, DAY)
    assert [e for e in exps if e.kind == "treatment"] == []


@pytest.mark.asyncio
async def test_a_session_with_no_recorded_volume_omits_the_key(db):
    """"Not recorded" must never be written as 0.0.

    `scaled_magnitude` reads a missing key as "no basis to scale on" and
    returns the unscaled prior. A fabricated zero behaves the same only while
    0.0 stays falsy — and would silently clamp to 0.5x the day that changed.
    """
    user = await _user(db, "exp-novolume@example.com")
    db.add(_session(user.id, dialysate_volume_liters=None))
    await db.flush()

    exps = await exposures_for_day(db, user.id, DAY)
    treatment = next(e for e in exps if e.kind == "treatment")
    assert "dialysate_volume_l" not in treatment.context


@pytest.mark.asyncio
async def test_drugs_given_by_the_unit_are_collected(db):
    """The third source. These never appear in a dose log the patient fills in."""
    user = await _user(db, "exp-administered@example.com")
    db.add(_session(user.id, drugs_administered="Epogene (4000 units)"))
    await db.flush()

    exps = await exposures_for_day(db, user.id, DAY)
    meds = [e for e in exps if e.kind == "medication"]
    assert meds, "the flowsheet's administered drugs were dropped"
    # Folded to the ingredient, so one drug is one agent however it was written.
    assert any(e.key == "epoetin alfa" for e in meds), [e.key for e in meds]


@pytest.mark.asyncio
async def test_an_unresolved_dose_is_still_an_exposure(db):
    """The guard this module exists for.

    Sevelamer binds dietary phosphorus and contributes no nutrient, so it is
    stored `nutrients_resolved=False` and excluded from the totals query
    forever. If this layer reused that filter it would be blind to exactly the
    agents it was built for.
    """
    user = await _user(db, "exp-binder@example.com")
    db.add(_dose(user.id, "Sevelamer", 800.0, "mg", resolved=False))
    await db.flush()

    exps = await exposures_for_day(db, user.id, DAY)
    assert any(e.key == "sevelamer" for e in exps), \
        "an unresolved dose was filtered out — the binder is invisible again"


@pytest.mark.asyncio
async def test_each_dose_is_its_own_exposure(db):
    """Three tablets is three exposures, not one.

    The effects layer sums across exposures, so collapsing them here would
    under-count a drug taken more than once in a day.
    """
    user = await _user(db, "exp-threedoses@example.com")
    for _ in range(3):
        db.add(_dose(user.id, "Calcium Carbonate", 500.0, "mg", resolved=False))
    await db.flush()

    exps = await exposures_for_day(db, user.id, DAY)
    assert len([e for e in exps if e.key == "calcium carbonate"]) == 3


@pytest.mark.asyncio
async def test_agent_pairs_are_labels_not_keys(db):
    """`stored_effects` normalises on the way in; handing it a pre-normalised
    key would fold a canonical drug name twice."""
    user = await _user(db, "exp-pairs@example.com")
    db.add(_dose(user.id, "Sevelamer", 800.0, "mg", resolved=False))
    await db.flush()

    pairs = agent_pairs(await exposures_for_day(db, user.id, DAY))
    assert ("medication", "Sevelamer") in pairs
