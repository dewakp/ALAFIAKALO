"""A delete button that could never succeed.

The endpoint refused EVERY delete with a flat 403 — "Medication entries cannot
be deleted" — and the web client had no catch, so the rejection vanished and the
row just sat there. The button looked broken because it was: nothing it could do
would work.

What the rule protects is the clinical record. A prescription with doses logged
against it is part of the patient's history. One with none is a catalog entry —
the EHR import creates them, and this account's only two are 2017 sandbox rows
with zero doses attached.
"""

from datetime import date

import pytest
from sqlalchemy import select

from app.models.med_nutrient import MedicationDoseLog
from app.models.medications import Medication
from app.models.user import User


async def _user(db, email: str) -> User:
    u = User(email=email, hashed_password="x", full_name="Rx User")
    db.add(u)
    await db.flush()
    return u


def _auth(app, user):
    from app.core.security import get_current_user
    app.dependency_overrides[get_current_user] = lambda: user


@pytest.mark.asyncio
async def test_a_prescription_with_no_doses_can_be_deleted(client, db):
    from app.main import app

    user = await _user(db, "del1@example.com")
    med = Medication(user_id=user.id, name="Ibuprofen 200 MG Oral Tablet", is_active=False)
    db.add(med)
    await db.commit()

    _auth(app, user)
    try:
        resp = await client.delete(f"/api/v1/medications/{med.id}")
        assert resp.status_code == 204, resp.text
    finally:
        app.dependency_overrides.clear()

    assert (await db.execute(
        select(Medication).where(Medication.id == med.id)
    )).scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_a_prescription_with_recorded_doses_is_protected(client, db):
    """The case the rule is actually for — and it says how many, and what to do."""
    from app.main import app

    user = await _user(db, "del2@example.com")
    med = Medication(user_id=user.id, name="Calcitriol", is_active=True)
    db.add(med)
    await db.flush()
    db.add(MedicationDoseLog(
        user_id=user.id, medication_id=med.id, medication_name="Calcitriol",
        log_date=date.today(), dose_amount=0.5, dose_unit="mcg",
    ))
    await db.commit()

    _auth(app, user)
    try:
        resp = await client.delete(f"/api/v1/medications/{med.id}")
        assert resp.status_code == 409, resp.text
        assert "1 recorded dose" in resp.json()["detail"]
        assert "inactive" in resp.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()

    assert (await db.execute(
        select(Medication).where(Medication.id == med.id)
    )).scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_another_users_prescription_is_not_deletable(client, db):
    from app.main import app

    owner = await _user(db, "owner@example.com")
    other = await _user(db, "other@example.com")
    med = Medication(user_id=owner.id, name="Calcitriol", is_active=True)
    db.add(med)
    await db.commit()

    _auth(app, other)
    try:
        resp = await client.delete(f"/api/v1/medications/{med.id}")
        assert resp.status_code == 404, resp.text
    finally:
        app.dependency_overrides.clear()
