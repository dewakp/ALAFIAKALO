"""An empty date field is "no date", not a malformed one.

HTML date inputs submit `""` when cleared. `date | None` rejects that with
"Input should be a valid date or datetime, input is too short", so saving a
prescription with no end date failed on every attempt — and the message names a
field the user never filled in, which reads as a bug in the app rather than
something they can act on.

Normalised in the SCHEMA, not the web form: iOS and Android post the same shape.
"""

import pytest
from pydantic import ValidationError

from app.schemas.medications import MedicationCreate, MedicationUpdate


def test_blank_end_date_is_accepted_as_none():
    rx = MedicationCreate(name="Calcium Carbonate", dosage="1000 mg",
                          dosage_unit="mg", frequency="twice daily",
                          start_date="2026-08-24", end_date="")
    assert rx.end_date is None
    assert rx.start_date is not None


def test_blank_start_date_is_accepted_too():
    assert MedicationCreate(name="Calcitriol", start_date="", end_date="").start_date is None


def test_whitespace_only_counts_as_blank():
    assert MedicationCreate(name="Calcitriol", end_date="   ").end_date is None


def test_a_real_date_still_parses():
    rx = MedicationCreate(name="Calcitriol", start_date="2026-01-15", end_date="2026-06-30")
    assert rx.start_date.isoformat() == "2026-01-15"
    assert rx.end_date.isoformat() == "2026-06-30"


def test_a_genuinely_malformed_date_is_still_rejected():
    """Blank is null; garbage is still garbage."""
    with pytest.raises(ValidationError):
        MedicationCreate(name="Calcitriol", end_date="not-a-date")


def test_update_schema_behaves_the_same():
    assert MedicationUpdate(end_date="").end_date is None
    assert MedicationUpdate(start_date="2026-03-01").start_date.isoformat() == "2026-03-01"


@pytest.mark.asyncio
async def test_saving_a_prescription_without_an_end_date(client, db):
    """End to end: the exact payload the web form posts."""
    from app.core.security import get_current_user
    from app.main import app
    from app.models.user import User

    user = User(email="rx@example.com", hashed_password="x", full_name="Rx User")
    db.add(user)
    await db.commit()

    app.dependency_overrides[get_current_user] = lambda: user
    try:
        resp = await client.post("/api/v1/medications/", json={
            "name": "Calcium Carbonate", "dosage": "1000 mg", "dosage_unit": "mg",
            "frequency": "twice daily", "route": "oral",
            "start_date": "2026-08-24", "end_date": "",
            "prescribing_doctor": "", "reason": "Post parathyroid removal",
            "is_active": True,
        })
        assert resp.status_code == 201, resp.text
        assert resp.json()["end_date"] is None
    finally:
        app.dependency_overrides.pop(get_current_user, None)
