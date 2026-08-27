"""The intake picker must offer what the patient actually takes.

From production: an account with **943 dose logs and 0 prescriptions** typed
"Calcium" and got no suggestion, while its own history held Calcium carbonate
recorded 489 times. The picker read `/medications/` — the PRESCRIPTION table —
and called that the answer. Canon 3aa in the intake form: prescribed and taken
are different facts.
"""

from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.api.medications import frequently_logged_medications, promote_logged_medications
from app.models.med_nutrient import MedicationDoseLog
from app.models.medications import Medication
from app.models.user import User


async def _user(db, email: str) -> User:
    u = User(email=email, hashed_password="x", full_name="Taker")
    db.add(u)
    await db.flush()
    return u


async def _dose(db, user_id: int, name: str, days_ago: int = 0) -> None:
    db.add(MedicationDoseLog(
        user_id=user_id, medication_name=name, dose_amount=1, dose_unit="mg",
        log_date=date.today() - timedelta(days=days_ago),
    ))


@pytest.mark.asyncio
async def test_history_is_offered_even_with_no_prescriptions(db):
    """The exact production shape: logs but no prescription rows."""
    user = await _user(db, "logs-only@example.com")
    for i in range(5):
        await _dose(db, user.id, "Calcium carbonate", days_ago=i)
    await db.flush()

    rows = await frequently_logged_medications(25, user, db)
    assert [r["name"] for r in rows] == ["Calcium carbonate"]
    assert rows[0]["times_logged"] == 5


@pytest.mark.asyncio
async def test_the_same_drug_is_not_offered_twice(db):
    """"Calcium Carbonate" and "Calcium carbonate" are one drug, not two."""
    user = await _user(db, "casing@example.com")
    await _dose(db, user.id, "Calcium Carbonate")
    await _dose(db, user.id, "Calcium carbonate", days_ago=1)
    await db.flush()

    rows = await frequently_logged_medications(25, user, db)
    assert len(rows) == 1, rows
    assert rows[0]["times_logged"] == 2


@pytest.mark.asyncio
async def test_most_recent_comes_first(db):
    """What you took yesterday beats something logged often but long stopped."""
    user = await _user(db, "recency@example.com")
    for i in range(20):
        await _dose(db, user.id, "Old Drug", days_ago=400 + i)
    await _dose(db, user.id, "New Drug", days_ago=0)
    await db.flush()

    rows = await frequently_logged_medications(25, user, db)
    assert rows[0]["name"] == "New Drug", rows


@pytest.mark.asyncio
async def test_regularly_logged_becomes_a_prescription(db):
    """A patient logging a drug 489 times is taking it — stop asking them to retype it."""
    user = await _user(db, "promote@example.com")
    for i in range(5):
        await _dose(db, user.id, "Calcium carbonate", days_ago=i)
    await db.flush()

    result = await promote_logged_medications(3, user, db)
    assert [c["name"] for c in result["created"]] == ["Calcium carbonate"]

    meds = (await db.execute(
        select(Medication).where(Medication.user_id == user.id)
    )).scalars().all()
    assert len(meds) == 1
    assert meds[0].is_active is True
    assert "your own logs" in (meds[0].notes or "")


@pytest.mark.asyncio
async def test_a_one_off_typo_is_not_promoted(db):
    """"Calcium Calcitriol" was logged ONCE against Calcium carbonate's 489.

    A prescription is a clinical statement; one mistyped dose log must not
    silently become one.
    """
    user = await _user(db, "typo@example.com")
    for i in range(5):
        await _dose(db, user.id, "Calcium carbonate", days_ago=i)
    await _dose(db, user.id, "Calcium Calcitriol", days_ago=2)
    await db.flush()

    result = await promote_logged_medications(3, user, db)
    assert [c["name"] for c in result["created"]] == ["Calcium carbonate"]


@pytest.mark.asyncio
async def test_promotion_is_idempotent(db):
    """Running it twice must not duplicate the regimen."""
    user = await _user(db, "idempotent@example.com")
    for i in range(4):
        await _dose(db, user.id, "Folic Acid", days_ago=i)
    await db.flush()

    assert len((await promote_logged_medications(3, user, db))["created"]) == 1
    assert len((await promote_logged_medications(3, user, db))["created"]) == 0


@pytest.mark.asyncio
async def test_an_existing_prescription_is_matched_case_insensitively(db):
    user = await _user(db, "existing@example.com")
    db.add(Medication(user_id=user.id, name="CALCIUM CARBONATE", is_active=True))
    for i in range(4):
        await _dose(db, user.id, "Calcium carbonate", days_ago=i)
    await db.flush()

    assert (await promote_logged_medications(3, user, db))["created"] == []
