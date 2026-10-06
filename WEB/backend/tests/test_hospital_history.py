# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""The canonical reader for hospital stays and surgical procedures.

The design claim under test is that a stay and a procedure are SEPARATE rows
and either can stand alone, so a reader that starts from `hospitalizations`
and walks down to its procedures silently loses every procedure that has no
admission — day-case surgery, and anything recorded years after the fact.

That is not hypothetical. The model exists because a patient said they take
calcium "after removal of parathyroid glands", a parathyroidectomy that appears
nowhere in the database and has no admission attached to it. A reader that
could not return it would reproduce exactly the gap this work was done to
close, so the orphan case is asserted first.

Seeds its own user and rows. Never reads a real record (dev holds real PHI).
"""

from datetime import datetime

import pytest

from app.models.hospitalization import (AdmissionStatus, AdmissionType,
                                        Hospitalization, ProcedureOutcome,
                                        SurgicalProcedure)
from app.models.user import User
from app.services import clinical_sources as sources


async def _seed_user(db, email: str) -> User:
    user = User(email=email, hashed_password="not-a-real-hash",
                full_name="Ada Demo")
    db.add(user)
    await db.flush()
    return user


@pytest.mark.asyncio
async def test_a_procedure_with_no_admission_is_still_returned(db):
    """The orphan case — the half a stay-first reader loses."""
    user = await _seed_user(db, "orphan-procedure@example.test")
    db.add(SurgicalProcedure(
        user_id=user.id,
        name="Parathyroidectomy",
        performed_at=datetime(2019, 6, 11),
        ongoing_effects="Parathyroid glands removed; calcium must be supplemented.",
        hospitalization_id=None,          # the whole point
        source="manual",
    ))
    await db.flush()

    # The stay-first view cannot see it: there is no stay.
    stays = await sources.hospitalizations(db, user.id)
    assert stays == []

    # The procedure reader must.
    procs = await sources.procedures(db, user.id)
    assert [p.name for p in procs] == ["Parathyroidectomy"]
    assert procs[0].admission is None
    assert procs[0].performed == "2019-06-11"


@pytest.mark.asyncio
async def test_nights_are_counted_only_when_both_ends_are_known(db):
    """A stay still in progress has no length — not a length measured to today."""
    user = await _seed_user(db, "nights@example.test")
    db.add_all([
        Hospitalization(
            user_id=user.id,
            admitted_at=datetime(2024, 3, 2, 14, 0),
            discharged_at=datetime(2024, 3, 6, 9, 30),
            facility_name="Montgomery General",
            reason="Fluid overload",
            admission_type=AdmissionType.ELECTIVE,
            status=AdmissionStatus.DISCHARGED,
            source="document",
        ),
        Hospitalization(
            user_id=user.id,
            admitted_at=datetime(2026, 9, 30, 3, 15),
            discharged_at=None,                      # still an inpatient
            facility_name="Montgomery General",
            status=AdmissionStatus.IN_PROGRESS,
            source="manual",
        ),
    ])
    await db.flush()

    stays = await sources.hospitalizations(db, user.id)
    assert [s.admitted for s in stays] == ["2026-09-30", "2024-03-02"]  # newest first

    current, finished = stays
    assert current.nights is None
    assert current.discharged is None
    assert current.status == "in_progress"

    assert finished.nights == 4
    assert finished.discharged == "2024-03-06"
    # `_enum_str` surfaces the enum VALUE. The COLUMN stores the member NAME
    # (`DISCHARGED`) because SQLEnum persists by name — the two differ, and
    # asserting the stored label here would fail against correct code.
    assert finished.status == "discharged"
    assert finished.admission_type == "elective"


@pytest.mark.asyncio
async def test_both_attached_and_standalone_procedures_come_back_together(db):
    """One patient, one of each. `procedures()` is the complete view."""
    user = await _seed_user(db, "both-kinds@example.test")
    stay = Hospitalization(
        user_id=user.id,
        admitted_at=datetime(2024, 3, 2),
        discharged_at=datetime(2024, 3, 6),
        facility_name="Montgomery General",
        status=AdmissionStatus.DISCHARGED,
    )
    db.add(stay)
    await db.flush()

    db.add_all([
        SurgicalProcedure(
            user_id=user.id, hospitalization_id=stay.id,
            name="AV fistula creation",
            code="0JH60XZ", code_system="ICD-10-PCS",
            body_site="Left forearm", laterality="left",
            performed_at=datetime(2024, 3, 3),
            outcome=ProcedureOutcome.SUCCESSFUL,
            surgeon="Dr A. Surgeon",
        ),
        SurgicalProcedure(
            user_id=user.id, hospitalization_id=None,
            name="Parathyroidectomy",
            performed_at=datetime(2019, 6, 11),
            ongoing_effects="Parathyroid glands removed.",
        ),
    ])
    await db.flush()

    procs = await sources.procedures(db, user.id)
    assert [p.name for p in procs] == ["AV fistula creation", "Parathyroidectomy"]

    attached, orphan = procs
    # Through `procedures()` the stay is CONTEXT, so the label names it.
    assert attached.admission == "2024-03-02 — Montgomery General"
    assert attached.code == "0JH60XZ"
    assert attached.code_system == "ICD-10-PCS"
    assert attached.outcome == "successful"
    assert orphan.admission is None

    # Through `hospitalizations()` the stay is already the row you are reading,
    # so the attached procedure carries the date alone — and the orphan is
    # absent, which is why both readers exist.
    stays = await sources.hospitalizations(db, user.id)
    assert len(stays) == 1
    assert [p.name for p in stays[0].procedures] == ["AV fistula creation"]
    assert stays[0].procedures[0].admission == "2024-03-02"


@pytest.mark.asyncio
async def test_an_undated_procedure_sorts_last_and_is_never_dropped(db):
    """An operation with no date is still a fact about the patient."""
    user = await _seed_user(db, "undated@example.test")
    db.add_all([
        SurgicalProcedure(user_id=user.id, name="Appendectomy", performed_at=None),
        SurgicalProcedure(user_id=user.id, name="Cataract surgery",
                          performed_at=datetime(2022, 1, 4)),
    ])
    await db.flush()

    procs = await sources.procedures(db, user.id)
    assert [p.name for p in procs] == ["Cataract surgery", "Appendectomy"]
    assert procs[-1].performed is None


@pytest.mark.asyncio
async def test_only_a_stated_effect_is_a_lasting_effect(db):
    """Never inferred from a procedure name (§0)."""
    user = await _seed_user(db, "effects@example.test")
    db.add_all([
        SurgicalProcedure(
            user_id=user.id, name="Parathyroidectomy",
            performed_at=datetime(2019, 6, 11),
            ongoing_effects="Parathyroid glands removed; calcium supplementation required.",
        ),
        # A procedure that plainly HAS lasting consequences in real life, but
        # the record does not state them. Nothing may be invented for it.
        SurgicalProcedure(user_id=user.id, name="Nephrectomy",
                          performed_at=datetime(2015, 2, 2),
                          ongoing_effects=None),
        # Empty string is not a statement either.
        SurgicalProcedure(user_id=user.id, name="Tonsillectomy",
                          performed_at=datetime(2001, 8, 9),
                          ongoing_effects=""),
    ])
    await db.flush()

    effects = await sources.lasting_surgical_effects(db, user.id)
    assert len(effects) == 1
    assert effects[0] == (
        "Parathyroidectomy (2019-06-11): "
        "Parathyroid glands removed; calcium supplementation required."
    )
    assert not any("Nephrectomy" in e for e in effects)
    assert not any("Tonsillectomy" in e for e in effects)


@pytest.mark.asyncio
async def test_one_patients_history_never_leaks_into_anothers(db):
    """Both readers are scoped by user, like every other clinical reader."""
    mine = await _seed_user(db, "mine@example.test")
    theirs = await _seed_user(db, "theirs@example.test")
    db.add_all([
        SurgicalProcedure(user_id=mine.id, name="Parathyroidectomy",
                          ongoing_effects="Calcium supplementation required."),
        SurgicalProcedure(user_id=theirs.id, name="Cholecystectomy",
                          ongoing_effects="Gallbladder removed."),
    ])
    db.add(Hospitalization(user_id=theirs.id, admitted_at=datetime(2024, 1, 1)))
    await db.flush()

    assert [p.name for p in await sources.procedures(db, mine.id)] == ["Parathyroidectomy"]
    assert await sources.hospitalizations(db, mine.id) == []
    effects = await sources.lasting_surgical_effects(db, mine.id)
    assert len(effects) == 1 and "Parathyroidectomy" in effects[0]
