"""A patient is told when someone else opens their record.

The rules that matter are the ones that are easy to get backwards:

- The patient looking at their OWN chart is not an access event.
- One clinical visit is one notification, not one per HTTP request. A board load
  fans out across several `/patient/{id}/...` routes and every one of them
  authorizes, so without a window the patient gets five alerts for one visit and
  learns to ignore all five.
- The payload has to actually persist. `create_notification` passed
  `metadata=...` to the model, which on a declarative class is the schema's
  MetaData object: it set a junk instance attribute and left the column NULL.
  27 rows on the production database, 0 with metadata, from 12 call sites that
  all thought they were writing one. Recording WHO looked depends on this.
"""

import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.notification_engine import (
    create_notification,
    notify_record_accessed,
)
from app.models.notifications import (
    Notification, NotificationCategory, NotificationPriority,
)
from app.models.user import User


async def _user(db, email: str, name: str = "Test User") -> User:
    u = User(email=email, hashed_password="x", full_name=name)
    db.add(u)
    await db.flush()
    return u


@pytest.mark.asyncio
async def test_metadata_actually_persists(db):
    """The regression the whole feature rests on."""
    user = await _user(db, "meta@example.com")
    note = await create_notification(
        db, user_id=user.id,
        category=NotificationCategory.SYSTEM,
        priority=NotificationPriority.LOW,
        title="t", message="m",
        metadata_dict={"viewer_id": 7},
    )
    await db.flush()

    row = (await db.execute(select(Notification))).scalar_one()
    assert row.extra_data is not None, "metadata was dropped again"
    assert json.loads(row.extra_data) == {"viewer_id": 7}
    assert note is not None


@pytest.mark.asyncio
async def test_a_clinician_opening_a_chart_notifies_the_patient(db):
    patient = await _user(db, "patient@example.com", "Ada Patient")
    clinician = await _user(db, "doc@example.com", "Dr Bola Okafor")

    note = await notify_record_accessed(
        db, patient_id=patient.id, viewer_id=clinician.id,
        viewer_name=clinician.full_name,
    )
    await db.flush()

    assert note is not None
    assert note.user_id == patient.id           # the PATIENT is told, not the viewer
    assert note.category == NotificationCategory.RECORD_ACCESS
    assert "Dr Bola Okafor" in note.message
    assert json.loads(note.extra_data)["viewer_id"] == clinician.id


@pytest.mark.asyncio
async def test_your_own_record_is_not_an_access_event(db):
    """The easiest thing to get wrong, so it is pinned first in the code too."""
    patient = await _user(db, "self@example.com")

    note = await notify_record_accessed(
        db, patient_id=patient.id, viewer_id=patient.id, viewer_name="Ada",
    )
    await db.flush()

    assert note is None
    assert (await db.execute(select(Notification))).scalars().all() == []


@pytest.mark.asyncio
async def test_one_visit_is_one_notification(db):
    """Five requests in a board load must not become five alerts."""
    patient = await _user(db, "p2@example.com")
    clinician = await _user(db, "d2@example.com", "Dr Who")

    for _ in range(5):
        await notify_record_accessed(
            db, patient_id=patient.id, viewer_id=clinician.id,
            viewer_name=clinician.full_name,
        )
        await db.flush()

    rows = (await db.execute(select(Notification))).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_a_later_visit_notifies_again(db):
    """Dedupe is a window, not a permanent mute."""
    patient = await _user(db, "p3@example.com")
    clinician = await _user(db, "d3@example.com", "Dr Who")

    first = await notify_record_accessed(
        db, patient_id=patient.id, viewer_id=clinician.id, viewer_name="Dr Who",
    )
    await db.flush()
    # Age the first one past the window rather than sleeping.
    first.created_at = datetime.now(timezone.utc) - timedelta(hours=3)
    await db.flush()

    second = await notify_record_accessed(
        db, patient_id=patient.id, viewer_id=clinician.id, viewer_name="Dr Who",
    )
    await db.flush()

    assert second is not None
    assert len((await db.execute(select(Notification))).scalars().all()) == 2


@pytest.mark.asyncio
async def test_a_different_viewer_is_a_separate_notification(db):
    """The window is per viewer. Two clinicians are two events."""
    patient = await _user(db, "p4@example.com")
    one = await _user(db, "d4a@example.com", "Dr One")
    two = await _user(db, "d4b@example.com", "Dr Two")

    await notify_record_accessed(db, patient_id=patient.id, viewer_id=one.id, viewer_name="Dr One")
    await db.flush()
    await notify_record_accessed(db, patient_id=patient.id, viewer_id=two.id, viewer_name="Dr Two")
    await db.flush()

    rows = (await db.execute(select(Notification))).scalars().all()
    assert len(rows) == 2
    assert {json.loads(r.extra_data)["viewer_id"] for r in rows} == {one.id, two.id}


@pytest.mark.asyncio
async def test_an_unnamed_viewer_still_reads_honestly(db):
    """Never render an empty name into the sentence."""
    patient = await _user(db, "p5@example.com")
    ghost = await _user(db, "d5@example.com", "")

    note = await notify_record_accessed(
        db, patient_id=patient.id, viewer_id=ghost.id, viewer_name="",
    )
    await db.flush()

    assert note is not None
    assert "  " not in note.message
    assert note.message.startswith("A member of your care team")
