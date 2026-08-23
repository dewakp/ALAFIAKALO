"""GET /notifications/ 500s on any user who actually has a notification.

`metadata` is reserved on a SQLAlchemy declarative class — it is the `MetaData`
object for the whole schema. The model works around that correctly:

    extra_data = Column("metadata", Text, nullable=True)

…so the DB column keeps its name while the Python attribute is `extra_data`.
`NotificationOut` then declared a plain `metadata: str | None`, and with
`from_attributes=True` Pydantic read `Notification.metadata` — the MetaData
object — which is not a string. One ResponseValidationError per row.

The endpoint therefore returned 200 **only for users with zero notifications**.
On the production account it produced `18 validation errors` and a 500, which
the page reported as "No notifications" until the error state was added. Two
independent faults stacked: the trailing-slash redirect meant the browser never
reached the endpoint, so the 500 underneath it had never once been seen.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.models.notifications import (
    Notification, NotificationCategory, NotificationPriority,
)
from app.schemas.notifications import NotificationOut
from app.models.user import User


async def _user(db, email: str) -> User:
    u = User(email=email, hashed_password="x", full_name="Test User")
    db.add(u)
    await db.flush()
    return u


def _notification(user_id: int, **kw) -> Notification:
    return Notification(
        user_id=user_id,
        category=NotificationCategory.LAB_ANOMALY,
        priority=NotificationPriority.HIGH,
        title="Potassium is high",
        message="K 6.1 mmol/L",
        is_read=False,
        created_at=datetime.now(timezone.utc),
        **kw,
    )


@pytest.mark.asyncio
async def test_a_notification_serialises(db):
    """The regression: this raised ResponseValidationError for every row."""
    user = await _user(db, "notif@example.com")
    db.add(_notification(user.id, extra_data='{"lab_id": 42}'))
    await db.flush()

    row = (await db.execute(select(Notification))).scalar_one()
    out = NotificationOut.model_validate(row)

    assert out.title == "Potassium is high"
    # Read off `extra_data`, not off SQLAlchemy's MetaData object.
    assert out.metadata == '{"lab_id": 42}'
    assert isinstance(out.metadata, str)


@pytest.mark.asyncio
async def test_a_notification_without_metadata_serialises(db):
    user = await _user(db, "notif2@example.com")
    db.add(_notification(user.id))
    await db.flush()

    row = (await db.execute(select(Notification))).scalar_one()
    out = NotificationOut.model_validate(row)
    assert out.metadata is None


@pytest.mark.asyncio
async def test_the_wire_name_stays_metadata(db):
    """The DB column is literally `metadata`; keep the field name clients see."""
    user = await _user(db, "notif3@example.com")
    db.add(_notification(user.id, extra_data="{}"))
    await db.flush()

    row = (await db.execute(select(Notification))).scalar_one()
    dumped = NotificationOut.model_validate(row).model_dump(by_alias=True)
    assert "metadata" in dumped
    assert dumped["metadata"] == "{}"


@pytest.mark.asyncio
async def test_list_endpoint_returns_the_rows(client, db):
    """End to end: the list must 200 for a user who HAS notifications.

    Before the fix this path only ever returned 200 when the list was empty —
    the one case with nothing to validate.
    """
    from app.core.security import get_current_user
    from app.main import app

    user = await _user(db, "notif4@example.com")
    db.add(_notification(user.id, extra_data='{"lab_id": 7}'))
    await db.commit()

    app.dependency_overrides[get_current_user] = lambda: user
    try:
        resp = await client.get("/api/v1/notifications/")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body) == 1
        assert body[0]["title"] == "Potassium is high"
        assert body[0]["metadata"] == '{"lab_id": 7}'
    finally:
        app.dependency_overrides.pop(get_current_user, None)
