"""The delivery webhook's boundary.

This endpoint exists because the send path cannot tell us what happened: Resend
answers 200 with a message id for a send it will never transmit, and on
2026-09-23 three such "sent" log lines were reported as proof of delivery for
one bounce and two suppressed addresses.

§3ah paid for these assertions once already, on the payment webhook: 21 of 31
production deliveries were refused at the signature check with no log line and
no row, so two thirds of the traffic vanished with no trace. What must hold:

  * an unsigned, missigned or replayed callback writes NOTHING
  * an endpoint with no secret configured refuses, rather than trusting input
  * a real event is recorded, with the provider's own wording kept
  * a failure event alerts the operator; an ordinary delivery does not
  * a mail outage never fails the webhook — the row is already committed
"""

import base64
import hashlib
import hmac
import json
import time

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models.email_event import EmailEvent

URL = "/api/v1/webhooks/resend"
SECRET = "whsec_" + base64.b64encode(b"alafia-test-signing-key-0123456789").decode()


def _sign(body: bytes, svix_id: str = "msg_test", ts: int | None = None) -> dict:
    """Sign the RAW bytes the way Svix does: `{id}.{timestamp}.{body}`."""
    stamp = str(int(time.time()) if ts is None else ts)
    key = base64.b64decode(SECRET.split("_", 1)[1])
    signed = b"%s.%s.%s" % (svix_id.encode(), stamp.encode(), body)
    sig = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()
    return {"svix-id": svix_id, "svix-timestamp": stamp, "svix-signature": f"v1,{sig}"}


def _bounce(email: str = "jema.akpohor@example.com") -> bytes:
    return json.dumps({
        "type": "email.bounced",
        "created_at": "2026-09-23T10:15:00.000Z",
        "data": {
            "email_id": "re_abc123",
            "to": [email],
            "subject": "Verify your ALAFIA email",
            "bounce": {"type": "Permanent", "subType": "General",
                       "message": "The recipient's address does not exist."},
        },
    }).encode()


@pytest.fixture
def secret(monkeypatch):
    monkeypatch.setattr(settings, "RESEND_WEBHOOK_SECRET", SECRET)


@pytest.fixture
def captured_alerts(monkeypatch):
    sent = []

    async def _fake_send(to, subject, html_body):
        sent.append({"to": to, "subject": subject, "html": html_body})
        return True

    monkeypatch.setattr("app.api.webhooks.send_email", _fake_send)
    return sent


async def _rows(db):
    return (await db.execute(select(EmailEvent))).scalars().all()


# ── Refusals write nothing ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_no_secret_configured_refuses(client, db, monkeypatch):
    """An endpoint that accepts anything is a public writer into our tables."""
    monkeypatch.setattr(settings, "RESEND_WEBHOOK_SECRET", "")
    body = _bounce()
    res = await client.post(URL, content=body, headers=_sign(body))
    assert res.status_code == 400
    assert await _rows(db) == []


@pytest.mark.asyncio
async def test_missing_signature_headers_refuse(client, db, secret):
    res = await client.post(URL, content=_bounce())
    assert res.status_code == 400
    assert await _rows(db) == []


@pytest.mark.asyncio
async def test_wrong_signature_refuses(client, db, secret):
    body = _bounce()
    headers = _sign(body)
    headers["svix-signature"] = "v1," + base64.b64encode(b"x" * 32).decode()
    res = await client.post(URL, content=body, headers=headers)
    assert res.status_code == 400
    assert await _rows(db) == []


@pytest.mark.asyncio
async def test_a_signature_over_different_bytes_refuses(client, db, secret):
    """Re-serialising the body would change key order and whitespace, so the
    handler must verify the bytes it received, not a dict it rebuilt."""
    headers = _sign(_bounce())
    tampered = _bounce(email="attacker@example.com")
    res = await client.post(URL, content=tampered, headers=headers)
    assert res.status_code == 400
    assert await _rows(db) == []


@pytest.mark.asyncio
async def test_replayed_timestamp_refuses(client, db, secret):
    body = _bounce()
    stale = int(time.time()) - (60 * 60)
    res = await client.post(URL, content=body, headers=_sign(body, ts=stale))
    assert res.status_code == 400
    assert await _rows(db) == []


@pytest.mark.asyncio
async def test_signed_but_not_json_refuses(client, db, secret):
    body = b"not json at all"
    res = await client.post(URL, content=body, headers=_sign(body))
    assert res.status_code == 400
    assert await _rows(db) == []


# ── A real event is recorded ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_bounce_is_recorded_with_the_providers_own_wording(
    client, db, secret, captured_alerts,
):
    body = _bounce()
    res = await client.post(URL, content=body, headers=_sign(body))
    assert res.status_code == 200

    rows = await _rows(db)
    assert len(rows) == 1
    row = rows[0]
    assert row.event_type == "email.bounced"
    assert row.recipient == "jema.akpohor@example.com"
    assert row.message_id == "re_abc123"
    assert row.bounce_type == "Permanent"
    assert "does not exist" in row.reason
    assert row.provider == "resend"
    # Verbatim — the columns are a guess about which fields matter, made
    # before the first real incident.
    assert json.loads(row.payload)["data"]["email_id"] == "re_abc123"


@pytest.mark.asyncio
async def test_a_failure_alerts_the_operator(client, db, secret, captured_alerts):
    body = _bounce()
    await client.post(URL, content=body, headers=_sign(body))

    assert len(captured_alerts) == 1
    alert = captured_alerts[0]
    assert "email.bounced" in alert["subject"]
    assert "jema.akpohor@example.com" in alert["subject"]
    # The operator has to know the address is now SUPPRESSED, or the next send
    # returns 200 and goes nowhere and it looks like it worked.
    assert "suppress" in alert["html"].lower()


@pytest.mark.asyncio
async def test_an_ordinary_delivery_is_recorded_and_does_NOT_alert(
    client, db, secret, captured_alerts,
):
    body = json.dumps({
        "type": "email.delivered",
        "created_at": "2026-09-23T10:16:00.000Z",
        "data": {"email_id": "re_ok", "to": ["member@example.com"],
                 "subject": "Welcome"},
    }).encode()
    res = await client.post(URL, content=body, headers=_sign(body))
    assert res.status_code == 200

    rows = await _rows(db)
    assert len(rows) == 1 and rows[0].event_type == "email.delivered"
    # Alerting on every delivery is how an operator learns to ignore the alerts.
    assert captured_alerts == []


@pytest.mark.asyncio
async def test_a_mail_outage_does_not_fail_the_webhook(client, db, secret, monkeypatch):
    """§3ah: a non-2xx over an email problem sends the provider into a
    multi-day retry cascade for an event we have already recorded."""
    async def _boom(**_kw):
        raise RuntimeError("mail provider down")

    monkeypatch.setattr("app.api.webhooks.send_email", _boom)
    body = _bounce()
    res = await client.post(URL, content=body, headers=_sign(body))

    assert res.status_code == 200
    assert len(await _rows(db)) == 1


@pytest.mark.asyncio
async def test_a_rotated_secret_still_verifies(client, db, secret, captured_alerts):
    """The header carries a space-separated list so a secret can be rotated
    without dropping deliveries signed by the old one."""
    body = _bounce()
    headers = _sign(body)
    good = headers["svix-signature"]
    headers["svix-signature"] = f"v1,{base64.b64encode(b'y' * 32).decode()} {good}"

    res = await client.post(URL, content=body, headers=headers)
    assert res.status_code == 200
    assert len(await _rows(db)) == 1
