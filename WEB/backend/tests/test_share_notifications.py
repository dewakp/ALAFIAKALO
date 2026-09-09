"""Sharing a record used to be silent on the side that gained access.

`POST /data-sharing/grants` created the grant and returned it to the OWNER. The
person given access learned nothing — no email, no notification, no entry
anywhere they would look. Someone could hold access to a patient's labs and
never know they had it.

`send_invitation` was worse: despite the name it sent nothing at all, so an
invitation could only be found by someone already logged in and looking for it
— precisely the person who does not need one.
"""

import pytest


@pytest.mark.asyncio
async def test_the_grantee_is_notified_in_app_and_by_email(db, monkeypatch):
    from sqlalchemy import select

    from app.api import data_sharing
    from app.models.data_sharing import DataGrant
    from app.models.notifications import Notification, NotificationCategory
    from app.models.user import User

    owner = User(email="owner@alafia.app", hashed_password="x", full_name="Ada Owner")
    grantee = User(email="doc@clinic.example", hashed_password="x", full_name="Dr Grantee")
    db.add_all([owner, grantee])
    await db.flush()

    sent = {}

    async def _fake_email(to, **kw):
        sent.update({"to": to, **kw})
        return True

    monkeypatch.setattr(data_sharing, "send_record_shared_email", _fake_email)

    grant = DataGrant(owner_id=owner.id, grantee_user_id=grantee.id,
                      data_type="labs", read_access=True, write_access=False)
    db.add(grant)
    await db.flush()

    await data_sharing._announce_share(db, grant, owner)
    await db.flush()

    notes = (await db.execute(
        select(Notification).where(Notification.user_id == grantee.id))).scalars().all()
    assert len(notes) == 1, "the grantee got no notification"
    assert notes[0].category == NotificationCategory.RECORD_SHARED
    assert "Ada Owner" in notes[0].title
    assert notes[0].action_url == "/share-records"

    assert sent["to"] == "doc@clinic.example"
    assert sent["owner_name"] == "Ada Owner"
    assert sent["data_type"] == "labs"


@pytest.mark.asyncio
async def test_a_share_survives_a_mail_outage(db, monkeypatch):
    """§3ah: a non-2xx over an email problem sent Stripe into a multi-day retry
    cascade. A share must not fail because mail is down."""
    from sqlalchemy import select

    from app.api import data_sharing
    from app.models.data_sharing import DataGrant
    from app.models.notifications import Notification
    from app.models.user import User

    owner = User(email="o2@alafia.app", hashed_password="x", full_name="Owner Two")
    grantee = User(email="g2@clinic.example", hashed_password="x", full_name="Grantee Two")
    db.add_all([owner, grantee])
    await db.flush()

    async def _boom(to, **kw):
        raise RuntimeError("resend is down")

    monkeypatch.setattr(data_sharing, "send_record_shared_email", _boom)

    grant = DataGrant(owner_id=owner.id, grantee_user_id=grantee.id,
                      data_type="vitals", read_access=True)
    db.add(grant)
    await db.flush()

    await data_sharing._announce_share(db, grant, owner)   # must not raise
    await db.flush()

    notes = (await db.execute(
        select(Notification).where(Notification.user_id == grantee.id))).scalars().all()
    assert len(notes) == 1, "the in-app notification is independent of email"


@pytest.mark.asyncio
async def test_an_external_grantee_gets_email_with_no_account_to_notify(db, monkeypatch):
    from app.api import data_sharing
    from app.models.data_sharing import DataGrant
    from app.models.user import User

    owner = User(email="o3@alafia.app", hashed_password="x", full_name="Owner Three")
    db.add(owner)
    await db.flush()

    sent = {}

    async def _fake_email(to, **kw):
        sent.update({"to": to, **kw})
        return True

    monkeypatch.setattr(data_sharing, "send_record_shared_email", _fake_email)

    grant = DataGrant(owner_id=owner.id, grantee_user_id=None,
                      grantee_email="outside@example.com",
                      grantee_display_name="Outside Clinician",
                      data_type="medications", read_access=True)
    db.add(grant)
    await db.flush()

    await data_sharing._announce_share(db, grant, owner)
    assert sent["to"] == "outside@example.com"
    assert sent["recipient_name"] == "Outside Clinician"


@pytest.mark.asyncio
async def test_the_email_carries_no_clinical_content():
    """Email is not a channel we control once it leaves. It names WHO and what
    KIND of record — never a value, a result or a diagnosis."""
    from app.services import email as email_mod

    captured = {}

    async def _capture(to, subject, html):
        captured.update({"to": to, "subject": subject, "html": html})
        return True

    original = email_mod.send_email
    email_mod.send_email = _capture
    try:
        await email_mod.send_record_shared_email(
            "doc@clinic.example", owner_name="Ada Owner", data_type="labs",
            recipient_name="Dr Grantee")
    finally:
        email_mod.send_email = original

    html = captured["html"]
    assert "Ada Owner" in html and "labs" in html
    assert "not in this email" in html
    # No numbers that could be a result, and no record payload.
    assert "mmol" not in html and "mg/dL" not in html


@pytest.mark.asyncio
async def test_an_invitation_actually_reaches_the_invitee(db, monkeypatch):
    from sqlalchemy import select

    from app.api import data_sharing
    from app.models.data_sharing import DataShareInvitation
    from app.models.notifications import Notification
    from app.models.user import User

    owner = User(email="o4@alafia.app", hashed_password="x", full_name="Owner Four")
    invitee = User(email="inv@clinic.example", hashed_password="x", full_name="Invited One")
    db.add_all([owner, invitee])
    await db.flush()

    sent = {}

    async def _fake_email(to, **kw):
        sent.update({"to": to, **kw})
        return True

    monkeypatch.setattr(data_sharing, "send_share_invitation_email", _fake_email)

    inv = DataShareInvitation(sender_id=owner.id, recipient_user_id=invitee.id,
                              recipient_email="inv@clinic.example",
                              data_types="labs,vitals", status="pending")
    db.add(inv)
    await db.flush()

    await data_sharing._announce_invitation(db, inv, owner)
    await db.flush()

    notes = (await db.execute(
        select(Notification).where(Notification.user_id == invitee.id))).scalars().all()
    assert len(notes) == 1
    assert "wants to share" in notes[0].title
    assert "until you accept" in notes[0].message, (
        "an invitation must not read as a completed share")
    assert sent["to"] == "inv@clinic.example"
