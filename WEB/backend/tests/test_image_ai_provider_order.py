"""Image AI follows the provider order and never calls a model server directly.

Medication labels, symptom and elimination photos, the meal caption fallback and
the drug-interaction note all posted straight to Ollama's /api/generate. That
made those screens Ollama-ONLY — a cold scale-to-zero GPU in production, and no
answer at all when it was down — while the rule is: local DB, then hosted
providers, then Ollama. Every model call now goes through ALAFIAModel, which
owns that order.
"""

import base64
import io
from pathlib import Path

import pytest
from PIL import Image

from app.core.security import get_current_user
from app.models.medications import Medication
from app.models.user import User

IMAGE_AI = Path(__file__).resolve().parent.parent / "app" / "api" / "image_ai.py"


def _png() -> str:
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), (200, 40, 40)).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


async def _user(db, email):
    user = User(email=email, hashed_password="x", full_name="T")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


def test_image_ai_never_calls_a_model_server_directly():
    source = IMAGE_AI.read_text()
    for direct in ("/api/generate", "/api/chat", "OLLAMA_BASE_URL", "ollama_auth_headers"):
        assert direct not in source, f"image_ai.py still reaches a model server directly: {direct}"


@pytest.fixture
def vision(monkeypatch):
    """Stands in for ALAFIAModel; records every request and answers as told."""
    state = {"calls": [], "fail": None}

    async def fake_infer(modality, payload):
        state["calls"].append((modality, payload))
        if state["fail"]:
            return {"success": False, "error": state["fail"], "data": {}}
        if payload.get("json_mode"):
            return {"success": True, "source": "vision-anthropic:test",
                    "data": {"text": "{}", "json": {"medication_name": "Calcitriol", "strength": "0.25 mcg",
                                                    "instructions": "Take one capsule daily"}}}
        return {"success": True, "source": "vision-anthropic:test",
                "data": {"text": "A red, raised rash on the forearm."}}

    monkeypatch.setattr("app.services.alafia_model_service.alafia_infer", fake_infer)
    return state


async def _post(client, db, path, body, email):
    from app.main import app

    user = await _user(db, email)
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        return await client.post(path, json=body), user
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_a_symptom_photo_is_read_through_the_vision_capability(client, db, vision):
    r, _ = await _post(client, db, "/api/v1/image-ai/symptom-from-image",
                       {"image_base64": _png()}, "sym-order@example.com")
    assert r.status_code == 200, r.text
    assert r.json()["suggested"]["symptom_name"] == "Rash"
    modality, payload = vision["calls"][0]
    assert modality == "vision" and payload["task"] == "image_question"
    assert "symptom" in payload["text"]


@pytest.mark.asyncio
async def test_when_no_provider_answers_the_reason_reaches_the_patient_not_just_unavailable(client, db, vision):
    vision["fail"] = "anthropic vision: ReadTimeout; Ollama vision: ConnectError"
    r, _ = await _post(client, db, "/api/v1/image-ai/elimination-from-image",
                       {"image_base64": _png(), "event_type": "urine"}, "elim-order@example.com")
    assert r.status_code == 503
    assert "ReadTimeout" in r.json()["detail"]


@pytest.mark.asyncio
async def test_a_medication_label_is_read_as_json_through_the_vision_capability(client, db, vision):
    r, _ = await _post(client, db, "/api/v1/image-ai/medication-from-image",
                       {"image_base64": _png()}, "label-order@example.com")
    assert r.status_code == 200, r.text
    assert r.json()["medication_name"] == "Calcitriol"
    assert vision["calls"][0][1]["json_mode"] is True


@pytest.mark.asyncio
async def test_the_interaction_note_comes_from_the_llm_chain(client, db, monkeypatch):
    from app.main import app

    prompts = []

    async def fake_chat(messages, **kwargs):
        prompts.append(messages[0]["content"])
        return "No clinically significant interaction."

    monkeypatch.setattr("app.services.alafia_model_service.alafia_chat", fake_chat)
    user = await _user(db, "dose-order@example.com")
    user.full_name = "Adaeze Okonkwo"
    db.add(Medication(user_id=user.id, name="Calcium carbonate", dosage="1000", dosage_unit="mg", is_active=True))
    await db.commit()
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        r = await client.post("/api/v1/image-ai/verify-dosage",
                              json={"medication_name": "Calcitriol", "dosage": "0.25 mcg"})
    finally:
        app.dependency_overrides.pop(get_current_user, None)
    assert r.status_code == 200, r.text
    assert any("No clinically significant interaction" in p for p in r.json()["precautions"])
    # Drugs, not people: the prompt that leaves carries no patient identity.
    assert "Adaeze" not in prompts[0] and "dose-order@example.com" not in prompts[0]
    assert "Calcium carbonate" in prompts[0]
