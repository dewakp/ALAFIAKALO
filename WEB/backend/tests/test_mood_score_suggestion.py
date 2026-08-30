"""A journal entry's mood must come from the entry, not from a default.

The form pre-filled 7/10 — "Good" — and saved that for anyone who wrote their
entry without dragging the slider. An entry reading "exhausted and fatigued"
was therefore recorded as Good, and every trend, summary and clinician view
downstream inherited it. A default is not a measurement.

`POST /mood/suggest-score` reads what the patient actually wrote and PROPOSES a
score with the reason for it (canon 3aj: inference proposes, it never writes) —
the user still presses save, so a wrong read is visible and correctable.
"""

import pytest

from app.models.user import User


async def _user(db, email: str) -> User:
    u = User(email=email, hashed_password="x", full_name="Test User")
    db.add(u)
    await db.flush()
    return u


async def _post(client, db, email, notes):
    from app.core.security import get_current_user
    from app.main import app

    user = await _user(db, email)
    await db.commit()
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        return await client.post("/api/v1/mood/suggest-score", json={"notes": notes})
    finally:
        app.dependency_overrides.clear()


def _answer(monkeypatch, payload):
    import app.services.alafia_model_service as svc

    async def fake(*a, **kw):
        return payload
    monkeypatch.setattr(svc, "alafia_chat", fake)


@pytest.mark.asyncio
async def test_a_low_entry_scores_low(client, db, monkeypatch):
    _answer(monkeypatch, '{"mood_score": 2, "energy_level": 1, '
                         '"rationale": "you wrote exhausted and fatigued"}')
    resp = await _post(client, db, "mood-low@example.com", "exhausted and fatigued")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["available"] is True
    assert body["mood_score"] == 2
    assert body["energy_level"] == 1
    assert "exhausted" in body["rationale"]


@pytest.mark.asyncio
async def test_prose_around_the_json_is_tolerated(client, db, monkeypatch):
    """Models wrap JSON in a fence or a sentence often enough to plan for."""
    _answer(monkeypatch,
            'Sure!\n```json\n{"mood_score": 4, "rationale": "low but coping"}\n```')
    resp = await _post(client, db, "mood-fence@example.com", "a hard day")
    assert resp.status_code == 200
    assert resp.json()["mood_score"] == 4


@pytest.mark.asyncio
async def test_out_of_range_is_clamped(client, db, monkeypatch):
    _answer(monkeypatch, '{"mood_score": 47, "energy_level": -3, "rationale": "x"}')
    resp = await _post(client, db, "mood-clamp@example.com", "fine")
    body = resp.json()
    assert body["mood_score"] == 10
    assert body["energy_level"] == 1


@pytest.mark.asyncio
async def test_an_unreachable_model_does_not_invent_a_score(client, db, monkeypatch):
    """Unavailable is not a number. The slider goes back to the user."""
    import app.services.alafia_model_service as svc

    async def boom(*a, **kw):
        raise RuntimeError("no provider")
    monkeypatch.setattr(svc, "alafia_chat", boom)

    resp = await _post(client, db, "mood-down@example.com", "exhausted")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["available"] is False
    assert body["mood_score"] is None
    assert body["rationale"]


@pytest.mark.asyncio
async def test_unusable_output_does_not_invent_a_score(client, db, monkeypatch):
    _answer(monkeypatch, "I think you seem alright today!")
    resp = await _post(client, db, "mood-junk@example.com", "tired")
    body = resp.json()
    assert body["available"] is False
    assert body["mood_score"] is None


@pytest.mark.asyncio
async def test_an_empty_entry_is_refused(client, db, monkeypatch):
    """Nothing written is nothing to read — never guess from an empty string."""
    resp = await _post(client, db, "mood-empty@example.com", "")
    assert resp.status_code == 422
