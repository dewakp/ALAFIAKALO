"""The iOS beta request, and what the contact form must never become.

`/contact` had no test of any kind before this one. It is public,
unauthenticated and unpaywalled on purpose (§3d: the people most likely to need
it are the ones who cannot get in), which is exactly why what it REFUSES
matters as much as what it accepts.

The rule underneath all of it: the client sends a topic KEY and never an
address, so no posted field can point this form at a recipient of someone
else's choosing.
"""

import pytest
from sqlalchemy import select

from app.models.contact import ContactSubmission


def _beta(**over) -> dict:
    payload = {
        "topic": "beta_ios",
        "name": "Ada Lovelace",
        "email": "ada@example.com",
        "message": "iOS beta request. Subscribed on the web since March.",
        "website": "",          # honeypot, empty for a real person
    }
    payload.update(over)
    return payload


@pytest.fixture
def mail(monkeypatch):
    """Capture what would be sent, and send nothing."""
    sent: list[dict] = []

    async def _capture(to: str, subject: str, html_body: str) -> bool:
        sent.append({"to": to, "subject": subject, "html": html_body})
        return True

    monkeypatch.setattr("app.api.contact.send_email", _capture)
    return sent


@pytest.mark.asyncio
async def test_a_beta_request_is_recorded_not_merely_emailed(client, db, mail):
    """The ROW is the receipt.

    `alafia.app` publishes DKIM and SPF and has no MX records — it can send and
    cannot receive. A version of this that only emailed would have Resend
    accept the send, report success, and bounce where nobody looks.
    """
    r = await client.post("/api/v1/contact", json=_beta())

    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert body["ok"] is True
    assert body["desk"] == "iOS Beta Request"
    assert body["reference"].startswith("ALF-")

    row = (await db.execute(select(ContactSubmission).where(
        ContactSubmission.reference == body["reference"]))).scalar_one()
    assert row.topic == "beta_ios"
    assert row.email == "ada@example.com"
    assert row.name == "Ada Lovelace"
    assert row.notified_at is not None, "the desk was not told"


@pytest.mark.asyncio
async def test_the_person_who_asked_is_told_we_have_it(client, db, mail):
    """Silence on a volunteer form reads as a dead form."""
    r = await client.post("/api/v1/contact", json=_beta())

    assert r.status_code == 200
    assert "ada@example.com" in [m["to"] for m in mail], (
        "the sender received no acknowledgement"
    )


@pytest.mark.asyncio
async def test_the_acknowledgement_does_not_quote_the_message_back(client, db, mail):
    """A contact form can carry health details, and mail is not a channel we
    control once it leaves (§3d). The acknowledgement confirms arrival and
    gives the reference; it does not repeat what was written."""
    r = await client.post("/api/v1/contact", json=_beta(
        message="iOS beta request. My potassium ran high again this month."))

    assert r.status_code == 200
    to_sender = next(m for m in mail if m["to"] == "ada@example.com")
    assert "potassium" not in to_sender["html"].lower()
    assert r.json()["reference"] in to_sender["html"]


@pytest.mark.asyncio
async def test_other_desks_do_NOT_auto_reply(client, db, mail):
    """Scoped on purpose.

    Someone filing a security disclosure or a deletion request has not asked
    for an automated reply in their inbox, and turning one on for every desk
    would change what four existing desks do to people who never opted in.
    """
    r = await client.post("/api/v1/contact", json=_beta(
        topic="security", message="Found an IDOR on the labs endpoint."))

    assert r.status_code == 200
    assert "ada@example.com" not in [m["to"] for m in mail], (
        "a security disclosure triggered an automated reply"
    )


@pytest.mark.asyncio
async def test_an_unknown_topic_is_refused_never_routed(client, db, mail):
    """An unrecognised key is a client bug or a probe, not a routing decision
    to improvise. Defaulting it to a desk is how a form becomes a relay."""
    r = await client.post("/api/v1/contact", json=_beta(topic="beta_android"))

    assert r.status_code == 422
    assert mail == [], "an unknown topic still sent mail"


@pytest.mark.asyncio
async def test_the_honeypot_is_accepted_and_discarded(client, db, mail):
    """Same 200 as a real message. A bot told it was detected simply retries
    without the field."""
    r = await client.post("/api/v1/contact", json=_beta(website="http://spam.example"))

    assert r.status_code == 200
    assert mail == []
    assert (await db.execute(select(ContactSubmission))).scalars().all() == []


@pytest.mark.asyncio
async def test_a_failed_acknowledgement_does_not_lose_the_request(client, db, monkeypatch):
    """The desk was told and the row exists; only the courtesy note failed.

    `notify_error` answers a different question — whether the DESK was told —
    and writing a sender-side failure into it would make a delivered request
    look unrecorded.
    """
    async def _desk_ok_sender_fails(to: str, subject: str, html_body: str) -> bool:
        return not to.endswith("@example.com")

    monkeypatch.setattr("app.api.contact.send_email", _desk_ok_sender_fails)

    r = await client.post("/api/v1/contact", json=_beta())

    assert r.status_code == 200, "a bounced acknowledgement cost us the request"
    row = (await db.execute(select(ContactSubmission).where(
        ContactSubmission.reference == r.json()["reference"]))).scalar_one()
    assert row.notified_at is not None, "the desk WAS told"
    assert row.notify_error is None


@pytest.mark.asyncio
async def test_an_acknowledgement_that_raises_does_not_fail_the_request(client, db, monkeypatch):
    async def _raises(to: str, subject: str, html_body: str) -> bool:
        if to.endswith("@example.com"):
            raise RuntimeError("smtp exploded")
        return True

    monkeypatch.setattr("app.api.contact.send_email", _raises)

    r = await client.post("/api/v1/contact", json=_beta())
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_the_beta_topic_is_offered_by_the_api(client):
    """The client reads the desk list rather than hardcoding it, so the routing
    table cannot drift between the site and the server."""
    r = await client.get("/api/v1/contact/topics")

    assert r.status_code == 200
    keys = [topic["key"] for topic in r.json()["topics"]]
    assert "beta_ios" in keys
