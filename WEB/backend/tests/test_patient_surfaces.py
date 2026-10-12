# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""Which screens a patient's record justifies.

Operator, 2026-10-12, having asked before:

  *"Primary goal == patient specific surfacing. for example someone who has
  listed no condition need not see therapies. they still do despite my repeated
  request. HD patient need not see PD in navigation."*

The web sidebar was a static 62-entry list, so every account saw HD Flowsheet,
PD Report and Therapy History whatever their record held. Measured on
production 2026-10-12: **2,035 therapy sessions, every one `HEMODIALYSIS`,
belonging to one user; zero peritoneal sessions exist for any account** — so
"PD Report" had never been a live screen for anybody, and it sat one row under
the screen the one dialysis patient actually uses.

Seeds its own users. Never reads a real record (dev holds real PHI).
"""

from datetime import datetime

import pytest

from app.models.chronic_conditions import (TherapySession, TherapyStatus,
                                           TherapyType)
from app.models.user import User
from app.services import patient_surfaces


async def _seed_user(db, email: str) -> User:
    user = User(email=email, hashed_password="not-a-real-hash",
                full_name="Ada Demo")
    db.add(user)
    await db.flush()
    return user


async def _seed_session(db, user, therapy_type: TherapyType) -> None:
    db.add(TherapySession(
        user_id=user.id, therapy_type=therapy_type,
        therapy_name="seeded", status=TherapyStatus.COMPLETED,
        scheduled_date=datetime(2026, 10, 1, 9, 0)))
    await db.flush()


@pytest.mark.asyncio
async def test_a_patient_with_no_therapy_sees_no_therapies(db):
    """The operator's first example. An account with nothing on record must not
    be offered a dialysis flowsheet."""
    user = await _seed_user(db, "no-conditions@example.test")
    s = await patient_surfaces.for_user(db, user.id)
    assert "therapies" not in s.offered
    assert "hemodialysis" not in s.offered
    assert "peritoneal_dialysis" not in s.offered
    assert "therapy_history" not in s.offered


@pytest.mark.asyncio
async def test_an_HD_patient_is_not_offered_PD(db):
    """The operator's second example, and the one with production behind it:
    zero peritoneal sessions exist anywhere, so that entry was dead for every
    user while sitting beside the screen the HD patient uses daily."""
    user = await _seed_user(db, "hd@example.test")
    await _seed_session(db, user, TherapyType.HEMODIALYSIS)
    s = await patient_surfaces.for_user(db, user.id)
    assert "hemodialysis" in s.offered
    assert "peritoneal_dialysis" not in s.offered
    assert "therapies" in s.offered
    assert "session" in s.because["hemodialysis"]


@pytest.mark.asyncio
async def test_a_PD_patient_is_not_offered_HD(db):
    """Symmetry matters: the rule must be about the record, not a preference
    for the modality that happens to be commoner here."""
    user = await _seed_user(db, "pd@example.test")
    await _seed_session(db, user, TherapyType.PERITONEAL_DIALYSIS)
    s = await patient_surfaces.for_user(db, user.id)
    assert "peritoneal_dialysis" in s.offered
    assert "hemodialysis" not in s.offered


@pytest.mark.asyncio
async def test_a_therapy_the_map_does_not_name_is_never_DROPPED(db):
    """Chemotherapy, infusion, phototherapy are real therapies. A modality
    missing from `_MODALITY_SURFACE` must still open the Therapies group —
    silently discarding it would hide a cancer patient's own sessions."""
    user = await _seed_user(db, "chemo@example.test")
    await _seed_session(db, user, TherapyType.CHEMOTHERAPY)
    s = await patient_surfaces.for_user(db, user.id)
    assert "therapies" in s.offered
    assert "therapy_history" in s.offered
    assert "therapy_other" in s.offered
    assert "hemodialysis" not in s.offered


@pytest.mark.asyncio
async def test_core_surfaces_are_never_gated(db):
    """You cannot hide the screen where a condition would be ADDED, or a new
    account has nowhere to begin."""
    user = await _seed_user(db, "empty@example.test")
    s = await patient_surfaces.for_user(db, user.id)
    for name in ("dashboard", "conditions", "labs", "medications", "profile"):
        assert name in s.offered


@pytest.mark.asyncio
async def test_every_offered_surface_says_WHY(db):
    """The reason travels so a client can explain itself and the decision is
    auditable rather than mysterious."""
    user = await _seed_user(db, "why@example.test")
    await _seed_session(db, user, TherapyType.HEMODIALYSIS)
    s = await patient_surfaces.for_user(db, user.id)
    assert s.offered and set(s.offered) == set(s.because)
    payload = s.as_payload()
    assert payload["offered"] == sorted(s.offered)


@pytest.mark.asyncio
async def test_DATA_beats_the_absence_of_a_diagnosis(db):
    """The rule that keeps this safe. A patient whose conditions were never
    coded still has their own sessions, and hiding the screen would hide their
    history from them — §3aa, absence of a diagnosis is not absence of records.
    """
    user = await _seed_user(db, "uncoded@example.test")
    await _seed_session(db, user, TherapyType.HEMODIALYSIS)
    s = await patient_surfaces.for_user(db, user.id)
    assert "conditions_active" not in s.offered     # nothing diagnosed
    assert "hemodialysis" in s.offered              # …and the screen still shows
    assert "session" in s.because["hemodialysis"], (
        "the reason must cite the DATA, not a diagnosis that does not exist")
