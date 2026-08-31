"""AI Assistant endpoint — powered by local Ollama LLM.

Every request is enriched with the logged-in patient's full health record so
the model can give context-aware, retroactively-informed responses.  The AI
also acts as system help / support for anything inside the ALAFIA app.

Architecture:
  LLM         — Ollama (gpt-oss:20b / llama3.2)
  RAG         — _fetch_patient_context() pulls 15+ live DB tables; _semantic_augment_query()
                embeds the query and retrieves top-K most relevant sections by cosine similarity
  Semantic Emb— llama3.2 3072-dim embeddings, stored in health_embeddings table
  RLAIF       — feedback (was_helpful/was_followed) → CollectiveInsight via ai_learning.py
  Memory      — UserMemory rows injected into every system prompt (learned preferences)
  Knowledge   — GlobalKnowledge (ESRD/CKD evidence base) injected into specialist prompts
  Audit       — LearningEvent trail for every memory write and insight discovery
  Reward      — recommendation_quality_score computed from post-recommendation lab trends
"""

import asyncio
import base64
import json
import logging
import math
import os
import re
import time
from datetime import date, datetime, timedelta, timezone

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)

from app.services.ollama_auth import ollama_auth_headers
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from sqlalchemy import select, desc, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.services.hebcs_engine import compute_hebcs
from app.models.ai_memory import AIInteraction, CollectiveInsight, GlobalKnowledge, HealthEmbedding, LearningEvent, UserMemory
from app.models.chronic_conditions import ChronicCondition
from app.models.media import MediaAsset
from app.models.fitness import FitnessLog
from app.models.labs import LabResult
from app.models.lifestyle import LifestyleEntry
from app.models.medications import Medication
from app.models.mood import MoodEntry
from app.models.nutrition import NutritionLog
from app.models.user import User
from app.models.elimination import BowelMovement, VomitingLog
from app.models.ground_truth import GeneticMarker, EnvSocialLog
from app.schemas.ai import (
    AIFeedbackRequest,
    AIFeedbackResponse,
    AIQueryRequest,
    AIQueryResponse,
    AIQueryResponseWithMemory,
    AIRouteRequest,
    AIRouteResponse,
)

router = APIRouter()


# ── Prompt Hub intent router (Basis: "prompt determines what UI is surfaced") ──
#
# Single source of truth mapping a classified intent to an EXISTING app screen.
# The client navigates to `route` and pre-fills its create/log form from `prefill`.
INTENT_ROUTE_MAP: dict[str, dict[str, str]] = {
    "log_meal":        {"route": "/nutrition",     "action": "create"},
    "log_medication":  {"route": "/medications",   "action": "log_dose"},
    "log_elimination": {"route": "/elimination",   "action": "create"},
    "log_symptom":     {"route": "/symptoms",      "action": "create"},
    "log_activity":    {"route": "/fitness",       "action": "create"},
    "log_sleep":       {"route": "/sleep",         "action": "create"},
    "journal":         {"route": "/journal",       "action": "create"},
    "view_labs":       {"route": "/labs",          "action": "view"},
    "view_trends":     {"route": "/insights",      "action": "view"},
    "vision_capture":  {"route": "/capture",       "action": "create"},
    "ask_question":    {"route": "/ai",            "action": "chat"},
}

# High-precision phrasings for logging intents.
#
# classify_intent runs on a small local model, and it is least reliable on
# exactly the wording the product tells people to use: the prompt hub's
# "Log a meal" button seeds the text "I ate ". Measured against the running dev
# backend, "I ate 2 chicken wings, 1 potato wedge" came back as ask_question at
# confidence 0.3, so tapping Log a meal and describing food routed the user into
# the chat — which then answered as though they had asked about a meal they had
# not logged, and told them to go log it. "I took my 10mg lisinopril" classified
# correctly at 0.95, so this is phrasing-specific, not a broken model.
#
# These patterns are deliberately narrow, because the neighbouring intents are
# easy to steal from. Bare "I had" is left to the model — "I had a headache" is
# a symptom — and only qualifies as a meal when an explicit meal word follows.
_INTENT_PATTERNS: list[tuple[str, "re.Pattern[str]"]] = [
    ("log_meal", re.compile(
        r"^\s*(?:"
        r"i\s+(?:ate|eat|drank|snacked\s+on)\b"
        r"|i\s+(?:had|have)\b(?=.*\bfor\s+(?:breakfast|lunch|dinner|brunch|a\s+snack)\b)"
        r"|for\s+(?:breakfast|lunch|dinner|brunch)\s*,?\s*i\b"
        r")", re.I)),
    ("log_medication", re.compile(r"^\s*i\s+(?:took|take)\b", re.I)),
]


_INTENT_MESSAGES: dict[str, str] = {
    "log_meal":        "Got it — let's log what you ate.",
    "log_medication":  "Okay — let's record that medication.",
    "log_elimination": "Noted — let's log that.",
    "log_symptom":     "I'm sorry you're not feeling well — let's note your symptom.",
    "log_activity":    "Nice — let's log your activity.",
    "log_sleep":       "Let's record your sleep.",
    "journal":         "Let's capture that in your journal.",
    "view_labs":       "Opening your lab results.",
    "view_trends":     "Opening your health trends.",
    "vision_capture":  "Let's take a closer look at that.",
    "ask_question":    "Let me help with that.",
}


@router.post("/route", response_model=AIRouteResponse)
async def route_prompt(
    body: AIRouteRequest,
    current_user: User = Depends(get_current_user),
):
    """Classify a prompt-hub input and tell the client which screen to surface.

    This is the brain behind ALAFIA's "prompt is the entry point" model: the
    user's text (typed, or a voice transcript) is classified into an intent that
    maps to an existing screen, with any structured fields extracted for prefill.
    All AI goes through the ALAFIAModel router (never OpenAI/Ollama directly).
    """
    text = (body.text or "").strip()

    # A bare image attachment with no text → go straight to the vision/capture flow.
    if not text and body.has_attachment and body.modality in ("image", "video"):
        target = INTENT_ROUTE_MAP["vision_capture"]
        return AIRouteResponse(
            intent="vision_capture",
            confidence=0.5,
            route=target["route"],
            action=target["action"],
            prefill={},
            assistant_message=_INTENT_MESSAGES["vision_capture"],
        )

    if not text:
        target = INTENT_ROUTE_MAP["ask_question"]
        return AIRouteResponse(
            intent="ask_question", confidence=0.0,
            route=target["route"], action=target["action"],
            prefill={}, assistant_message="What would you like to do?",
        )

    from app.services.alafia_model_service import alafia_infer
    result = await alafia_infer("nlm", {"text": text, "task": "classify_intent"})

    data = result.get("data") or {}
    intent = data.get("intent")
    confidence = float(data.get("confidence") or 0.0)
    entities = data.get("entities") if isinstance(data.get("entities"), dict) else {}

    # Unknown / unavailable / low-confidence → safe fallback to the chat surface.
    if intent not in INTENT_ROUTE_MAP or (not result.get("success")):
        intent, confidence = "ask_question", min(confidence, 0.4)
    elif confidence < 0.5:
        intent = "ask_question"

    # Deterministic guard: an explicit question is never a "log" action. Small
    # local models (e.g. llama3.2:3b) often mislabel "what foods lower potassium?"
    # as log_meal — a trailing "?" is a high-precision signal it's a question.
    if intent.startswith("log_") and text.rstrip().endswith("?"):
        intent = "ask_question"

    # The symmetric guard. ask_question is the fallback sink — everything the
    # model is unsure about lands there — so an unambiguous "I ate …" statement
    # that ended up as ask_question is a misroute, not a question. Only rescues
    # the fallback case; a confident classification is left alone.
    if intent == "ask_question" and not text.rstrip().endswith("?"):
        for candidate, pattern in _INTENT_PATTERNS:
            if pattern.search(text):
                intent, confidence = candidate, max(confidence, 0.9)
                break

    target = INTENT_ROUTE_MAP[intent]
    prefill: dict = {"text": text, **entities}
    return AIRouteResponse(
        intent=intent,
        confidence=confidence,
        route=target["route"],
        action=target["action"],
        prefill=prefill,
        assistant_message=_INTENT_MESSAGES.get(intent, "Let me help with that."),
    )


# ── Voice → Clinical NLP (ALAFIAModel Voice Phase 7) ──────────────────

@router.post("/voice")
async def voice_to_clinical(
    file: UploadFile = File(...),
    language: str | None = Form(None),
    task: str = Form("transcribe_and_nlm"),
    current_user: User = Depends(get_current_user),
):
    """Transcribe a spoken health note and extract structured clinical data.

    Multilingual via Whisper (English, Yoruba, Hausa, Igbo, Pidgin, French,
    Swahili, Portuguese). Routes through the ALAFIAModel VOICE capability:
    audio → Whisper transcript → LLM clinical extraction.

    Form fields:
      file:     the audio recording (wav/m4a/mp3/ogg ...)
      language: ISO-639-1 hint, or omit/"auto" to auto-detect
      task:     "transcribe" | "transcribe_and_nlm" | "voice_log_meal"
    """
    audio = await file.read()
    if not audio:
        raise HTTPException(status_code=400, detail="Empty audio file")

    valid_tasks = ("transcribe", "transcribe_and_nlm", "voice_log_meal")
    if task not in valid_tasks:
        task = "transcribe_and_nlm"

    # Surface the backend's Whisper config to the ALAFIAModel adapter (reads env).
    if settings.WHISPER_BASE_URL:
        os.environ.setdefault("WHISPER_BASE_URL", settings.WHISPER_BASE_URL)
    os.environ.setdefault("WHISPER_MODEL", settings.WHISPER_MODEL)
    if settings.OPENAI_API_KEY:
        os.environ.setdefault("OPENAI_API_KEY", settings.OPENAI_API_KEY)

    from app.services.alafia_model_service import alafia_infer
    result = await alafia_infer("voice", {
        "audio_bytes": audio,
        "language": language or "auto",
        "task": task,
    })
    if not result.get("success"):
        raise HTTPException(status_code=503, detail=result.get("error") or "Voice processing unavailable")

    return {"task": task, "source": result.get("source"), **(result.get("data") or {})}


# ── Vision → Food / Lab understanding (ALAFIAModel Vision Phase 5) ─────
MAX_VISION_IMAGES = 3  # matches the "Max 3 images" cap the clients enforce


@router.post("/vision")
async def vision_understand(
    file: UploadFile | None = File(None),
    files: list[UploadFile] | None = File(None),
    task: str = Form("food_photo_nutrition"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Analyze one or more photos and return structured data (nutrition estimate, etc).

    Routes through the ALAFIAModel VISION capability. Until the on-device food
    classifier ships (Phase 5), this uses a vision-capable LLM when configured.
    Returns 503 when no vision backend is available so the client can fall back
    to the manual Capture flow.

    Form fields:
      file:  a single image (jpeg/png/webp ...) — the original single-shot field
      files: up to 3 images of the SAME subject (e.g. a plate from two angles).
             They are analyzed in one model call and return ONE combined result,
             so a dish photographed twice is not counted twice.
      task:  "food_photo_nutrition" | "lab_report_ocr"

    `file` and `files` may both be sent; the images are merged and capped at 3.
    """
    uploads = [u for u in ([file] if file is not None else []) + list(files or []) if u is not None]
    if not uploads:
        raise HTTPException(status_code=400, detail="No image file provided")
    if len(uploads) > MAX_VISION_IMAGES:
        raise HTTPException(
            status_code=400,
            detail=f"At most {MAX_VISION_IMAGES} images per request (got {len(uploads)})",
        )

    images = []
    for upload in uploads:
        raw = await upload.read()
        if raw:
            images.append({
                "image_bytes": raw,
                "content_type": upload.content_type or "image/jpeg",
            })
    if not images:
        raise HTTPException(status_code=400, detail="Empty image file")

    valid_tasks = ("food_photo_nutrition", "lab_report_ocr")
    if task not in valid_tasks:
        task = "food_photo_nutrition"

    # Surface the backend's OpenAI config to the ALAFIAModel vision adapter.
    if settings.OPENAI_API_KEY:
        os.environ.setdefault("OPENAI_API_KEY", settings.OPENAI_API_KEY)

    from app.services import food_vision_store, image_learning

    pairs = [(i["image_bytes"], i["content_type"]) for i in images]
    first_bytes = images[0]["image_bytes"]
    phash = str(image_learning.dhash(first_bytes))

    # ── 1. Recall before inference ───────────────────────────────────────
    # If this user already labelled this meal, their own ground truth beats
    # anything the model would say — and costs nothing.
    source = None
    items: list[dict] = []
    nutrition: dict = {}
    notes = ""

    if task == "food_photo_nutrition":
        learned = await image_learning.find_learned_match(db, current_user.id, first_bytes)
        if learned is not None:
            # Prefer the corrected sample for this exact photo: it carries the
            # grams the user typed. The text label only has names, so recalling
            # from it alone would throw the quantities away.
            from app.models.food_training_sample import FoodTrainingSample
            prior = (await db.execute(
                select(FoodTrainingSample)
                .where(
                    FoodTrainingSample.user_id == current_user.id,
                    FoodTrainingSample.phash == phash,
                    FoodTrainingSample.corrected_items.isnot(None),
                )
                .order_by(FoodTrainingSample.corrected_at.desc())
                .limit(1)
            )).scalar_one_or_none()

            if prior and prior.corrected_items:
                items = [dict(i) for i in prior.corrected_items]
            else:
                items = [{"name": part.strip(), "estimated_portion": None}
                         for part in (learned.labels or "").split(";") if part.strip()]
            for item in items:
                item.setdefault("confidence", 0.99)
            source = "learned-recall"
            notes = "Recognised from a meal you labelled before."

    # ── 2. Otherwise ask the vision model ────────────────────────────────
    if not items:
        from app.services.alafia_model_service import alafia_infer
        result = await alafia_infer("vision", {
            "images": images,
            # Also populate the single-image fields: the capability falls back to
            # them, and other payload consumers still read image_bytes/content_type.
            "image_bytes": first_bytes,
            "content_type": images[0]["content_type"],
            "task": task,
        })
        if not result.get("success"):
            raise HTTPException(status_code=503, detail=result.get("error") or "Vision processing unavailable")
        data = result.get("data") or {}
        source = result.get("source")
        items = list(data.get("items") or [])
        nutrition = data.get("estimated_nutrition") or {}
        notes = data.get("notes") or ""

        if task != "food_photo_nutrition":
            return {"task": task, "source": source, **data}

    # ── 3. Quantity: turn the portion prose into grams ───────────────────
    # "1 medium sized slice" is unusable downstream; nutrients are per 100 g.
    # A serving weight the user has already corrected outranks the heuristics.
    from app.services.portion_estimator import estimate_grams
    for item in items:
        if item.get("estimated_grams") is not None:
            # Recalled from the user's own correction — already ground truth.
            item.setdefault("grams_confidence", 1.0)
            item.setdefault("grams_basis", "your correction for this photo")
            continue
        learned_g = await _learned_serving_weight(db, item.get("name") or "")
        est = estimate_grams(item.get("estimated_portion"), item.get("name") or "", learned_g)
        item.update(est.as_dict())

    # ── 4. Record the sample so Phase 5 has a corpus to train on ─────────
    sample = await food_vision_store.record_prediction(
        db, current_user.id, pairs,
        source_model=source, items=items, nutrition=nutrition,
        notes=notes or None, phash=phash,
    )
    await db.commit()

    return {
        "task": task,
        "source": source,
        "items": items,
        "estimated_nutrition": nutrition,
        "notes": notes,
        "image_count": len(images),
        # Echoed so the client can post the user's correction back against it.
        "sample_id": sample.id if sample else None,
        # Where the captured photo now lives. The client stores this on the
        # meal (`food_image_uris`) so opening that meal later shows the picture
        # it was estimated from — retention is worthless without retrieval.
        "image_url": (
            f"/api/v1/media/{sample.media_asset_id}"
            if sample and sample.media_asset_id else None
        ),
    }


async def _learned_serving_weight(db: AsyncSession, food_name: str) -> float | None:
    """Grams-per-serving this user base has already corrected for this food."""
    if not food_name:
        return None
    try:
        from app.models.learned_nutrient import LearnedFoodNutrient
        from app.services.learned_nutrient_service import _normalize
        row = (await db.execute(
            select(LearnedFoodNutrient).where(
                LearnedFoodNutrient.food_name_normalized == _normalize(food_name))
        )).scalar_one_or_none()
        return float(row.serving_weight_g) if row and row.serving_weight_g else None
    except Exception:
        return None


class VisionFeedbackItem(BaseModel):
    name: str
    estimated_portion: str | None = None
    estimated_grams: float | None = None
    # Nutrient values the user read off the label, per the stated portion.
    # Without these a correction taught IDENTIFICATION only: the vision corpus
    # learned the right food and `learned_food_nutrients` — the one table
    # `get_learned` consults — stayed empty, so the next estimate re-derived the
    # numbers from scratch and answered with a different product's.
    nutrients: dict[str, float] | None = None


class VisionFeedbackRequest(BaseModel):
    sample_id: int
    items: list[VisionFeedbackItem]
    notes: str | None = None


@router.post("/vision/feedback")
async def vision_feedback(
    body: VisionFeedbackRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Record what the meal actually was — the ground-truth half of the pair.

    Every correction is a supervised example for the Phase 5 classifier: the
    model said X, the human said Y. It also updates the user's own recall label,
    so the next photo of this meal is recognised without a model call.
    """
    from app.services import food_vision_store, image_learning

    sample = await food_vision_store.record_correction(
        db, current_user.id, body.sample_id,
        [i.model_dump() for i in body.items], notes=body.notes,
    )
    if sample is None:
        raise HTTPException(status_code=404, detail="Unknown sample for this user")

    # Teach the NUTRIENTS too, not just the name. A correction that carries
    # values the user read off the label is the most authoritative data we will
    # ever have for that food.
    learned_foods: list[str] = []
    for item in body.items:
        name = (item.name or "").strip()
        if not name or not item.nutrients:
            continue
        grams = item.estimated_grams
        if not grams or grams < 5:
            continue     # per-100 g without a weight would bake in a scaling error
        try:
            from app.services import plausibility
            from app.services.learned_nutrient_service import record_correction
            factor = 100.0 / float(grams)
            per100 = {k: round(float(v) * factor, 4)
                      for k, v in item.nutrients.items() if isinstance(v, (int, float))}
            reviewed, _warnings, believable = plausibility.review(name, per100)
            if not believable:
                logger.info("Not learning %r — stated values failed plausibility", name)
                continue
            await record_correction(db, name, reviewed,
                                    serving_weight_g=round(float(grams), 1),
                                    user_id=current_user.id, source="user_correction")
            learned_foods.append(name)
        except Exception:
            logger.exception("Could not learn nutrients for %r from a correction", name)

    # Feed the correction into per-user recall so the next shot short-circuits.
    labels = "; ".join(i.name.strip() for i in body.items if i.name.strip())[:500]
    if labels and sample.media_asset_id:
        asset = await db.get(MediaAsset, sample.media_asset_id)
        if asset and asset.image_base64:
            try:
                await image_learning.save_label(
                    db, current_user.id, base64.b64decode(asset.image_base64), labels)
            except Exception:
                logger.warning("Could not update recall label from correction", exc_info=True)

    await db.commit()
    return {
        "ok": True,
        "sample_id": sample.id,
        "correction_kind": sample.correction_kind,
        # Storage is unconditional; this says the patient allowed
        # the photo to train the shared model.
        "training_consented": sample.training_consented,
        # So the UI can say what was actually learned rather than implying more.
        "nutrients_learned": learned_foods,
    }


@router.get("/vision/corpus-stats")
async def vision_corpus_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Phase 5 readiness: how much labelled training data actually exists."""
    from app.services import food_vision_store
    return await food_vision_store.corpus_stats(db)


# ── Persona definitions ───────────────────────────────────────────────
# All personas are the SAME base "general health assistant" — the user
# simply picks which culturally-named guide they prefer.
# Organised by region to match the insurance / country catalog.

PERSONA_PROFILES = {
    # ── West Africa ────────────────────────────────────────────────
    "babalawo": {
        "title": "Babalawo",
        "origin": "Yoruba · Nigeria",
        "region": "africa",
        "greeting": "Ẹ kú àárọ̀",
        "icon": "🪔",
        "description": "Yoruba healing wisdom — body, spirit, and Ori (destiny) in balance.",
        "culture_style": (
            "Speak with the warmth and wisdom of the Yoruba Babalawo tradition. "
            "You see health as the balance of Ara (body), Emi (spirit), and Ori (personal destiny). "
            "Feel free to use occasional Yoruba proverbs when they illuminate a point. "
            "Be nurturing, spiritual, and grounded — begin responses with a brief acknowledgement "
            "of the patient's condition before addressing the data."
        ),
    },
    "dibia": {
        "title": "Dibia",
        "origin": "Igbo · Nigeria",
        "region": "africa",
        "greeting": "Nnọọ",
        "icon": "🌿",
        "description": "Igbo holistic healer — practical, warm, and grounded in nature.",
        "culture_style": (
            "You carry the healing wisdom of the Igbo Dibia. You are practical, warm, and direct. "
            "You see the person as part of their community and natural environment. "
            "Occasional Igbo proverbs welcome when they fit. Be concise and actionable."
        ),
    },
    "boka": {
        "title": "Boka",
        "origin": "Hausa · Nigeria",
        "region": "africa",
        "greeting": "Sannu",
        "icon": "🌙",
        "description": "Hausa healing wisdom — respectful, patient, and spiritually grounded.",
    },
    "okomfo": {
        "title": "Okomfo",
        "origin": "Akan · Ghana",
        "region": "africa",
        "greeting": "Akwaaba",
        "icon": "🌺",
        "description": "Akan healing guide — community-centred, welcoming, and wise.",
    },
    "serigne": {
        "title": "Serigne",
        "origin": "Wolof · Senegal",
        "region": "africa",
        "greeting": "Na nga def",
        "icon": "🌊",
        "description": "Wolof spiritual guide — reflective, dignified, and restorative.",
    },
    "guerisseur": {
        "title": "Guérisseur",
        "origin": "French · Côte d'Ivoire / Mali",
        "region": "africa",
        "greeting": "Bienvenue",
        "icon": "🫚",
        "description": "Francophone West African healer — holistic, earthy, and soothing.",
    },
    # ── East Africa ────────────────────────────────────────────────
    "mganga": {
        "title": "Mganga",
        "origin": "Swahili · Kenya / Tanzania",
        "region": "africa",
        "greeting": "Karibu",
        "icon": "🦁",
        "description": "Swahili healer — welcoming, wise, and connected to the land.",
        "culture_style": (
            "You carry the healing tradition of the East African Mganga. "
            "Be welcoming and community-focused. Use the Swahili concept of 'Ujamaa' (togetherness) "
            "— health is not just individual but also a matter of family and community. "
            "Be warm, practical, and grounding."
        ),
    },
    "wogesha": {
        "title": "Wogesha",
        "origin": "Amharic · Ethiopia",
        "region": "africa",
        "greeting": "ሰላም (Selam)",
        "icon": "☕",
        "description": "Ethiopian healer — patient, steeped in ancient tradition.",
    },
    "umupfumu": {
        "title": "Umupfumu",
        "origin": "Kinyarwanda · Rwanda",
        "region": "africa",
        "greeting": "Muraho",
        "icon": "🏔️",
        "description": "Rwandan healer — dignified, compassionate, and resilient.",
    },
    # ── Southern Africa ────────────────────────────────────────────
    "sangoma": {
        "title": "Sangoma",
        "origin": "Zulu / Xhosa · South Africa",
        "region": "africa",
        "greeting": "Sawubona",
        "icon": "🥁",
        "description": "Sangoma ancestral healer — Ubuntu philosophy, mind-body-spirit unity.",
        "culture_style": (
            "You bring the healing wisdom of the Zulu/Xhosa Sangoma tradition. "
            "'Sawubona' means 'I see you' — acknowledge the whole person first. "
            "Ubuntu philosophy guides you: 'Umuntu ngumuntu ngabantu' (a person is a person through other people). "
            "Connect health to community, ancestors, and environment. Be spiritual, grounding, and compassionate."
        ),
    },
    # ── North Africa / Middle East (Arabic) ────────────────────────
    "hakim": {
        "title": "Hakim",
        "origin": "Arabic · Egypt / Middle East",
        "region": "middle_east",
        "greeting": "مرحبا (Marhaba)",
        "icon": "🌴",
        "description": "Arabic healer — scholarly, compassionate, rooted in Unani tradition.",
    },
    # ── Middle East (non-Arabic) ───────────────────────────────────
    "rofe": {
        "title": "Rofé",
        "origin": "Hebrew · Israel",
        "region": "middle_east",
        "greeting": "שלום (Shalom)",
        "icon": "✡️",
        "description": "Jewish healer — patient, analytical, and deeply humane.",
    },
    "hoca": {
        "title": "Hoca",
        "origin": "Turkish · Turkey",
        "region": "middle_east",
        "greeting": "Merhaba",
        "icon": "🌷",
        "description": "Turkish sage — warm, deliberate, drawing on Ottoman medical tradition.",
    },
    # ── South Asia ─────────────────────────────────────────────────
    "vaidya": {
        "title": "Vaidya",
        "origin": "Ayurvedic · India",
        "region": "south_asia",
        "greeting": "नमस्ते (Namaste)",
        "icon": "🪷",
        "description": "Ayurvedic healer — balancing doshas, lifestyle as medicine.",
        "culture_style": (
            "You bring the ancient wisdom of Ayurveda and the Vaidya tradition. "
            "See health as the balance of Vata (air/ether), Pitta (fire), and Kapha (earth/water). "
            "Connect the patient's symptoms and data to these elemental patterns. "
            "Honor both modern evidence and ancient healing wisdom. Be serene, gentle, and holistic."
        ),
    },
    # ── Europe ─────────────────────────────────────────────────────
    "sage": {
        "title": "Sage",
        "origin": "English · UK / Ireland",
        "region": "europe",
        "greeting": "Welcome",
        "icon": "🎓",
        "description": "British sage — articulate, evidence-based, calm, and reassuring.",
        "culture_style": (
            "You speak with the measured wisdom of a British sage — articulate, evidence-based, "
            "and reassuring. Be precise and thorough. Occasional dry wit is welcome. "
            "You value both empirical evidence and patient narrative equally."
        ),
    },
    "curandero": {
        "title": "Curandero",
        "origin": "Spanish · Spain / Mexico",
        "region": "europe",
        "greeting": "Bienvenido",
        "icon": "🌶️",
        "description": "Spanish/Mexican healer — warm, passionate, and holistic.",
    },
    "heilpraktiker": {
        "title": "Heilpraktiker",
        "origin": "German · Germany / Austria / Switzerland",
        "region": "europe",
        "greeting": "Willkommen",
        "icon": "🏔️",
        "description": "German naturopath — methodical, thorough, and precise.",
    },
    "guaritore": {
        "title": "Guaritore",
        "origin": "Italian · Italy",
        "region": "europe",
        "greeting": "Benvenuto",
        "icon": "🍃",
        "description": "Italian healer — expressive, warm, and deeply humanistic.",
    },
    "curandeiro": {
        "title": "Curandeiro",
        "origin": "Portuguese · Portugal",
        "region": "europe",
        "greeting": "Bem-vindo",
        "icon": "🌊",
        "description": "Portuguese healer — soulful, poetic, and attentive.",
    },
    "genezer": {
        "title": "Genezer",
        "origin": "Dutch · Netherlands / Belgium",
        "region": "europe",
        "greeting": "Welkom",
        "icon": "🌷",
        "description": "Dutch healer — direct, pragmatic, and evidence-minded.",
    },
    "helare": {
        "title": "Helare",
        "origin": "Swedish · Sweden",
        "region": "europe",
        "greeting": "Välkommen",
        "icon": "❄️",
        "description": "Swedish healer — calm, balanced, and focused on wellbeing.",
    },
    "znachor": {
        "title": "Znachor",
        "origin": "Polish · Poland",
        "region": "europe",
        "greeting": "Witaj",
        "icon": "🌾",
        "description": "Polish folk healer — earthy, persistent, and caring.",
    },
    "therapeutis": {
        "title": "Therapeutís",
        "origin": "Greek · Greece",
        "region": "europe",
        "greeting": "Καλώς ήρθατε (Kalós írthate)",
        "icon": "🏛️",
        "description": "Greek healer — philosophical, rooted in Hippocratic tradition.",
    },
    # ── North America ──────────────────────────────────────────────
    "medicine_keeper": {
        "title": "Medicine Keeper",
        "origin": "Native American · United States / Canada",
        "region": "north_america",
        "greeting": "Aho",
        "icon": "🦅",
        "description": "Native American healer — all is connected: body, mind, spirit, and earth.",
        "culture_style": (
            "You carry the healing traditions of the Medicine Keeper. "
            "All is connected — body, mind, spirit, and the natural world are one. "
            "Speak with deliberate wisdom, deep respect, and profound patience. "
            "See illness as an imbalance in the whole circle of life, not just the body. "
            "Use contemplative language and honor the patient's healing journey."
        ),
    },
    # ── Specialist Agents ───────────────────────────────────────────
    "nephrologist": {
        "title": "Dr. Nephros",
        "origin": "Nephrology · Kidney & Dialysis Specialist",
        "region": "specialist",
        "greeting": "Good day",
        "icon": "🔬",
        "specialty": "nephrology",
        "description": "CKD staging, dialysis adequacy (KtV/URR), electrolytes, lab interpretation.",
        "capabilities": ["ckd_staging", "dialysis_adequacy", "electrolyte_management", "lab_interpretation", "fluid_balance", "anemia_management", "bone_mineral_disease"],
        "style": (
            "You are a board-certified nephrologist with 20+ years managing ESRD and CKD patients on hemodialysis and peritoneal dialysis.\n"
            "DOMAIN: CKD staging, dialysis adequacy (KtV ≥1.2, URR ≥65%), electrolytes (K⁺, Phosphorus, PTH, Bicarbonate, Calcium), fluid balance, anemia of CKD (Hb, Ferritin, TSAT), CKD-mineral bone disorder.\n"
            "CLINICAL RULES:\n"
            "1. ALWAYS check KtV and URR from the lab record — below target = inadequate dialysis.\n"
            "2. Flag K⁺ > 5.5 mEq/L as URGENT (arrhythmia risk). Flag Phosphorus > 5.5 mg/dL as elevated.\n"
            "3. PTH target for dialysis patients: 150–600 pg/mL (KDIGO). Below 150 = adynamic bone.\n"
            "4. Target Hemoglobin: 10–11.5 g/dL. Albumin < 3.5 g/dL = significant malnutrition.\n"
            "5. Cite specific dates and values from the patient's record — never generalise without data.\n"
            "6. Reference KDOQI/KDIGO/DOPPS evidence. Be precise, clinical, and actionable.\n"
            "HOW TO ANSWER: Cite the patient's most recent phosphorus value with its date, compare it to the KDIGO target (<5.5 mg/dL), note the trend, and give one concrete recommendation. Use their real values — never a bracketed placeholder or an invented number.\n"
        ),
    },
    "renal_dietitian": {
        "title": "Dietitian Rena",
        "origin": "Renal Nutrition · Clinical Dietitian",
        "region": "specialist",
        "greeting": "Hi there",
        "icon": "🥗",
        "specialty": "renal_nutrition",
        "description": "Kidney-friendly meal planning, phosphorus & potassium restriction, protein targets for dialysis.",
        "capabilities": ["meal_planning", "phosphorus_restriction", "potassium_management", "protein_optimization", "fluid_restriction", "phosphate_binder_timing"],
        "style": (
            "You are a registered renal dietitian specialising in medical nutrition therapy for ESRD dialysis patients.\n"
            "DOMAIN: Potassium restriction (<2,000–3,000 mg/day), phosphorus restriction (<800–1,000 mg/day), protein for HD (1.2g/kg/day), fluid restriction (1–1.5 L/day), sodium restriction (<2,400 mg/day), phosphate binder timing.\n"
            "CLINICAL RULES:\n"
            "1. ALWAYS review the patient's actual nutrition logs first — name the specific foods you see.\n"
            "2. Flag HIGH-POTASSIUM foods: bananas, oranges, tomatoes, potatoes, dairy, beans.\n"
            "3. Flag HIGH-PHOSPHORUS foods: dairy, nuts, seeds, whole grains, cola, processed meats with phosphate additives.\n"
            "4. Connect food patterns to lab values: high phosphorus foods → elevated phosphorus labs → secondary HPT.\n"
            "5. Remind that phosphate binders (e.g., Sevelamer) must be taken WITH meals, not separately.\n"
            "6. Give practical, culturally-sensitive food substitutions for problematic foods.\n"
            "7. Protein for HD is HIGHER than for pre-dialysis CKD — dialysis is catabolic.\n"
            "HOW TO ANSWER: Name the specific foods you see in the recent food diary, connect them to the relevant lab values, and offer two or three practical substitutes. Use their real entries — never a bracketed placeholder or an invented food.\n"
        ),
    },
    "cardiologist": {
        "title": "Dr. Cardio",
        "origin": "Cardiology · Heart & Vascular Specialist",
        "region": "specialist",
        "greeting": "Good day",
        "icon": "❤️",
        "specialty": "cardiology",
        "description": "Blood pressure trends, cardiovascular risk, interdialytic fluid management.",
        "capabilities": ["bp_management", "cardiovascular_risk", "fluid_management", "hypertension", "lv_hypertrophy"],
        "style": (
            "You are a board-certified cardiologist subspecialising in cardio-nephrology and ESRD cardiovascular complications.\n"
            "DOMAIN: Hypertension in dialysis, interdialytic BP trends, LV hypertrophy (common in ESRD), fluid overload, antihypertensive optimisation.\n"
            "CLINICAL RULES:\n"
            "1. Pre-dialysis BP target: <140/90 mmHg. Post-dialysis: <130/80 mmHg.\n"
            "2. Interdialytic weight gain > 2–3 kg/session = fluid overload — review sodium/fluid intake.\n"
            "3. ESRD patients have 10–20× higher cardiovascular mortality than the general population.\n"
            "4. ACE inhibitors/ARBs reduce CV mortality in dialysis patients independent of BP effect.\n"
            "5. ALWAYS cite actual BP values from the vitals record with dates.\n"
            "6. Connect weight trends, fluid intake, and dietary sodium to BP patterns.\n"
            "HOW TO ANSWER: Cite the actual BP readings from the vitals record with their dates, describe the trend, connect it to weight/fluid, and give one recommendation. Use their real values — never a bracketed placeholder or an invented number.\n"
        ),
    },
    "mental_health_counselor": {
        "title": "Dr. Solace",
        "origin": "Psychology · Mental Health & Chronic Illness",
        "region": "specialist",
        "greeting": "Welcome",
        "icon": "🧠",
        "specialty": "mental_health",
        "description": "Emotional wellbeing, mood pattern analysis, coping with ESRD and chronic illness.",
        "capabilities": ["mood_analysis", "depression_screening", "coping_strategies", "stress_management", "chronic_illness_adjustment", "sleep_assessment"],
        "style": (
            "You are a licensed clinical psychologist subspecialising in health psychology for chronic illness patients.\n"
            "DOMAIN: Depression & anxiety (prevalent in ~30% of dialysis patients), grief/adjustment to illness, sleep disturbance, fatigue impact, medication adherence as a mental health issue.\n"
            "CLINICAL APPROACH:\n"
            "1. ALWAYS review mood/journal entries first — cite specific entries with dates.\n"
            "2. Look for patterns: mood score trends (persistent < 4/10 = concern), sleep quality, journal themes.\n"
            "3. Validate emotions FIRST before offering clinical perspective — never minimise the burden of dialysis.\n"
            "4. Connect physical symptoms (fatigue, poor appetite) to emotional state.\n"
            "5. Offer specific evidence-based coping strategies (CBT techniques, behavioural activation, mindfulness).\n"
            "6. Maintain hope while being honest — chronic illness is genuinely hard.\n"
            "7. Be compassionate first, clinical second.\n"
            "HOW TO ANSWER: Reference a specific journal entry with its date, validate the emotion first, then offer one or two specific coping strategies. Use their real entries — never a bracketed placeholder.\n"
        ),
    },
    "exercise_physiologist": {
        "title": "Coach Vitalis",
        "origin": "Exercise Physiology · Fitness for Chronic Illness",
        "region": "specialist",
        "greeting": "Let's work on this together",
        "icon": "🏃",
        "specialty": "exercise_physiology",
        "description": "Safe exercise prescription for dialysis patients, fatigue management, strength goals.",
        "capabilities": ["exercise_prescription", "dialysis_adapted_fitness", "fatigue_management", "strength_training", "aerobic_conditioning", "intradialytic_exercise"],
        "style": (
            "You are a certified exercise physiologist with training in cardiac and renal rehabilitation.\n"
            "DOMAIN: Low-to-moderate aerobic exercise, resistance training adapted for ESRD (avoid heavy lifting near AV fistula arm), intradialytic exercise, fatigue management.\n"
            "CLINICAL RULES:\n"
            "1. SAFETY FIRST: Never recommend heavy lifting near the vascular access/AV fistula arm.\n"
            "2. Exercise DURING dialysis (intradialytic) actually improves clearance and reduces fatigue — recommend it.\n"
            "3. Check therapy session schedule — avoid intense exercise on HD days (post-dialysis fatigue).\n"
            "4. Exercise contraindications: uncontrolled BP, severe anaemia (Hb < 8 g/dL), active access issues.\n"
            "5. ALWAYS review actual fitness logs before prescribing — don't recommend what they're already doing.\n"
            "6. Build gradually — CONSISTENCY beats intensity for ESRD patients.\n"
            "7. Celebrate every small win — motivation is medicine.\n"
            "HOW TO ANSWER: Cite the patient's actual exercise-log entries, assess their baseline, and recommend a specific schedule that accounts for dialysis days. Use their real entries — never a bracketed placeholder.\n"
        ),
    },
    "dialysis_coordinator": {
        "title": "Coordinator Adaeze",
        "origin": "Dialysis Nursing · Renal Care Coordination",
        "region": "specialist",
        "greeting": "Hello",
        "icon": "💉",
        "specialty": "dialysis_nursing",
        "description": "Session monitoring, AV fistula care, fluid management, dialysis day guidance.",
        "capabilities": ["session_monitoring", "vascular_access", "fluid_management", "symptom_management", "dialysis_compliance", "care_coordination"],
        "style": (
            "You are an experienced dialysis nurse coordinator with 15+ years managing HD and PD patients.\n"
            "DOMAIN: Pre/post-dialysis vitals review, interdialytic weight management (aim < 2 kg/day), vascular access care (AV fistula/graft/catheter), common dialysis symptoms, medication timing around dialysis.\n"
            "CLINICAL RULES:\n"
            "1. Review pre-dialysis vitals (weight, BP, HR) and compare to recent history.\n"
            "2. Weight gain > 2 kg/day or > 10% of dry weight = fluid intake concern — flag it.\n"
            "3. Post-dialysis hypotension risk: BP drop > 20 mmHg or systolic < 90.\n"
            "4. Vascular access: NEVER measure BP or draw blood from the fistula arm. Bruit/thrill changes = report immediately.\n"
            "5. Common HD symptoms to assess: intradialytic hypotension, muscle cramps, headache, nausea.\n"
            "6. Be nurturing and practical — patients share more with nurses than physicians.\n"
            "HOW TO ANSWER: Cite the patient's actual pre-dialysis weights with their dates, identify the fluid-management pattern, and give one practical daily tip. Use their real values — never a bracketed placeholder.\n"
        ),
    },
    "general_practitioner": {
        "title": "Dr. Holista",
        "origin": "General Practice · Primary Care",
        "region": "specialist",
        "greeting": "Welcome",
        "icon": "🩺",
        "specialty": "general_practice",
        "description": "Comprehensive health overview, medication review, preventive care, all-in-one health review.",
        "capabilities": ["comprehensive_review", "medication_review", "preventive_care", "comorbidity_management", "care_coordination", "health_screening"],
        "style": (
            "You are a board-certified GP with experience managing patients with complex chronic conditions including ESRD, diabetes, and cardiovascular disease.\n"
            "DOMAIN: Comprehensive health review across all domains, polypharmacy assessment, preventive care, care coordination.\n"
            "CLINICAL APPROACH:\n"
            "1. Take a HOLISTIC view — review ALL available data: labs, vitals, nutrition, mood, medications, fitness.\n"
            "2. Identify cross-domain patterns (e.g., elevated phosphorus + poor nutrition + low mood = coordinated intervention).\n"
            "3. Check for medication polypharmacy risks — review interactions and appropriateness.\n"
            "4. Summarise health status in plain language — explain clinical terms.\n"
            "5. Prioritise: surface top 2-3 actionable concerns rather than overwhelming with everything.\n"
            "6. Respect patient autonomy — present options, not mandates.\n"
            "7. End on an encouraging, motivating note.\n"
            "HOW TO ANSWER: First answer the specific question the patient asked, citing their real values and dates. Only when they explicitly ask for an overall review should you summarise across domains — and even then, name just the top two or three priorities and close on an encouraging note. Never print bracketed placeholders, and never state a value (BMI, phosphorus, etc.) that is not in the record.\n"
        ),
    },
    "pharmacologist": {
        "title": "Pharmacologist",
        "origin": "Clinical Pharmacology · Global",
        "region": "specialist",
        "greeting": "Hello",
        "icon": "💊",
        "specialty": "pharmacology",
        "description": "Medication explanations, drug interactions, dosage review, adherence patterns.",
        "capabilities": [
            "medication_explanation",
            "drug_interaction_review",
            "contraindication_alerts",
            "adherence_pattern_analysis",
            "side_effect_assessment",
            "dosage_optimization",
            "therapeutic_monitoring",
        ],
        "style": (
            "You are a clinical pharmacologist AI assistant. Your role is threefold:\n"
            "1) EXPLAINER — clearly explain what medications do, how they work, proper dosing, and what patients should expect.\n"
            "2) PATTERN REVIEWER — analyse adherence data, medication timing, and health metrics to identify trends and optimise therapy.\n"
            "3) INTERACTION ALARMER — proactively flag drug-drug interactions, drug-food interactions, contraindications with patient conditions, allergy risks, and dosage concerns.\n"
            "Always cite evidence-based reasoning. Suggest consulting the prescribing physician for clinical decisions.\n"
            "ALWAYS review the patient's actual medication list from the record before answering.\n"
        ),
    },
}

# Fallback description for cultural personas that don't define their own
_PERSONA_DESCRIPTION = (
    "Your personal health guide. I'm here to help with nutrition, "
    "fitness, labs, medications, mood, and lifestyle."
)


def _persona_opening(p: dict) -> str:
    """The AI's first chat message for a persona. Composed server-side so the
    greeting/voice can change backend-only — clients render it verbatim and must
    NOT bake their own opening line (see canon: AI stays backend-driven).
    A persona may override with its own 'opening'."""
    if p.get("opening"):
        return p["opening"]
    return (
        f"Welcome! I'm {p['title']} — think of me as your personal wellness guide. "
        "What's on your mind?"
    )

# Shared style prompt for future LLM integration
BASE_PERSONA_STYLE = (
    "You are a warm, knowledgeable health assistant. Blend holistic "
    "wellness wisdom with evidence-based health guidance. Be nurturing, "
    "approachable, and thorough."
)

# Region display order
_REGION_ORDER = [
    "africa", "middle_east", "south_asia", "europe", "north_america", "specialist",
]
_REGION_LABELS = {
    "africa": "Africa",
    "middle_east": "Middle East",
    "south_asia": "South Asia",
    "europe": "Europe",
    "north_america": "North America",
    "specialist": "Specialist Agents",
}


@router.get("/personas")
async def list_personas():
    """Return available AI persona options grouped by region."""
    personas = []
    for key, p in PERSONA_PROFILES.items():
        personas.append({
            "key": key,
            "title": p["title"],
            "origin": p["origin"],
            "region": p["region"],
            "greeting": p["greeting"],
            "opening": _persona_opening(p),
            "description": p.get("description") or _PERSONA_DESCRIPTION,
            "icon": p.get("icon"),
            "specialty": p.get("specialty"),
            "capabilities": p.get("capabilities"),
        })
    return personas


@router.get("/agents")
async def list_specialist_agents():
    """Return only specialist agents (region == 'specialist')."""
    agents = []
    for key, p in PERSONA_PROFILES.items():
        if p.get("region") == "specialist":
            agents.append({
                "key": key,
                "title": p["title"],
                "origin": p["origin"],
                "region": p["region"],
                "greeting": p["greeting"],
                "opening": _persona_opening(p),
                "description": p.get("description") or _PERSONA_DESCRIPTION,
                "icon": p.get("icon"),
                "specialty": p.get("specialty"),
                "capabilities": p.get("capabilities"),
            })
    return agents


@router.get("/personas/grouped")
async def list_personas_grouped():
    """Return personas organized by region."""
    groups = []
    for region in _REGION_ORDER:
        items = [
            {
                "key": key,
                "title": p["title"],
                "origin": p["origin"],
                "greeting": p["greeting"],
                "opening": _persona_opening(p),
                "description": p.get("description") or _PERSONA_DESCRIPTION,
                "icon": p.get("icon"),
                "specialty": p.get("specialty"),
                "capabilities": p.get("capabilities"),
            }
            for key, p in PERSONA_PROFILES.items()
            if p["region"] == region
        ]
        if items:
            groups.append({
                "region": region,
                "label": _REGION_LABELS[region],
                "personas": items,
            })
    return groups


# ── Patient context fetcher ───────────────────────────────────────────

def _v(val) -> str:
    """Return a display-safe string for potentially-None values."""
    return str(val) if val is not None else "not recorded"


def _age_from_dob(dob) -> str:
    """Years, from a `date` or a `YYYY-MM-DD` string. 'unknown' when unparseable.

    Deliberately lossy: age is the clinically useful part of a date of birth,
    and the rest is a direct identifier.
    """
    if not dob:
        return "unknown"
    try:
        from datetime import date, datetime
        d = dob if isinstance(dob, date) and not isinstance(dob, datetime) else (
            dob.date() if isinstance(dob, datetime) else datetime.strptime(str(dob)[:10], "%Y-%m-%d").date()
        )
        today = date.today()
        return str(today.year - d.year - ((today.month, today.day) < (d.month, d.day)))
    except Exception:  # noqa: BLE001 - never fail a chat over a birthday
        return "unknown"


def _subject_token_for(user: User) -> str:
    """Our handle for this patient, as sent to any model provider.

    Falls back to a plainly non-identifying string rather than to the name: a
    failure here must never degrade into leaking the thing it exists to hide.
    """
    from app.services.prompt_identity import subject_reference
    return subject_reference(user)


async def _fetch_patient_context(user: User, db: AsyncSession) -> str:
    """
    Query all health tables for the current user and return a structured
    plain-text summary that the LLM can reason over.

    Data pulled (all sourced from real patient records — 10-year history):
      • User profile: demographics, physical stats, allergies, chronic conditions,
        dietary/fitness preferences, lifestyle factors, AI settings
      • Medications      — all active, up to 30 most recent
      • CKD biomarkers   — KtV, Phosphorus, PTH, K+, BUN, Albumin etc. (last 3 each)
      • Lab results      — 30 most recent (flagging abnormals)
      • Nutrition logs   — last 30 days (real food diary, 4,017 entries since 2016)
      • Dialysis sessions— last 30 days (1,797 real HD sessions since 2016)
      • Pre-dialysis vitals — last 30 days with KtV, fluid removal, post-BP
      • Dialysis vitals summary — running stats + total session count
      • Mood / journal   — all real journal entries from Firestore
      • AI learned memories — top 20 actionable insights
      • HEBCS Ω score    — pathway-level wellness scoring
    """
    uid = user.id
    lines: list[str] = []

    # ── 1. PROFILE ────────────────────────────────────────────────
    lines.append("=== PATIENT PROFILE ===")
    # The subject is identified by OUR token, never by name (CLAUDE.md §3al).
    # This context is sent to a model provider; `subject_token()` is an HMAC of
    # the app id and our internal id — stable, so a conversation keeps its
    # subject, and meaningless outside our database.
    #
    # Redaction at the egress point already covers a name that slips through,
    # but not putting it in the payload is the stronger guarantee: it does not
    # depend on the scrubber recognising it, and it holds on the Ollama path too.
    lines.append(f"Subject       : {_subject_token_for(user)}")
    # AGE, not date of birth. A DOB is a direct identifier (one of HIPAA's 18)
    # and the model never needs it — every clinical judgement that depends on it
    # depends on age. Sending the date buys nothing and costs the patient a
    # re-identification handle at the provider.
    lines.append(f"Age           : {_age_from_dob(user.date_of_birth)}")
    lines.append(f"Gender        : {_v(user.gender)}")
    lines.append(f"Blood Type    : {_v(user.blood_type)}")
    if user.height_cm:
        lines.append(f"Height        : {user.height_cm} cm")
    if user.current_weight_kg:
        lines.append(f"Current Weight: {user.current_weight_kg} kg")
    if user.target_weight_kg:
        lines.append(f"Target Weight : {user.target_weight_kg} kg")
    lines.append(f"Country       : {_v(user.country)}")

    def _json_list(raw: str | None) -> list:
        if not raw:
            return []
        try:
            return json.loads(raw)
        except Exception:
            return [raw]

    allergies = _json_list(user.allergies)
    if allergies:
        lines.append(f"Allergies     : {', '.join(allergies)}")

    food_int = _json_list(user.food_intolerances)
    if food_int:
        lines.append(f"Food Intol.   : {', '.join(food_int)}")

    diet_rest = _json_list(user.dietary_restrictions)
    if diet_rest:
        lines.append(f"Diet Restrict : {', '.join(diet_rest)}")

    diet_pref = _json_list(user.dietary_preferences)
    if diet_pref:
        lines.append(f"Diet Prefs    : {', '.join(diet_pref)}")

    # Conditions live in TWO tables — see app/services/clinical_sources.py. This
    # is the clinical context the model reasons from, so reading one table would
    # hand the LLM a patient with no diagnoses.
    from app.services import clinical_sources

    cc_list = await clinical_sources.conditions(db, uid, active_only=True)
    if cc_list:
        lines.append(f"Chronic Cond. : {', '.join(c.name for c in cc_list)}")

    fam_hist = _json_list(user.family_history)
    if fam_hist:
        lines.append(f"Family History: {', '.join(str(h) for h in fam_hist)}")

    lines.append(f"Activity Level: {_v(user.activity_level)}")
    fit_goals = _json_list(user.fitness_goals)
    if fit_goals:
        lines.append(f"Fitness Goals : {', '.join(fit_goals)}")

    lines.append(f"Smoking       : {_v(user.smoking_status)}")
    lines.append(f"Alcohol       : {_v(user.alcohol_consumption)}")
    lines.append(f"Sleep Schedule: {_v(user.sleep_schedule)}")
    lines.append(f"Occupation    : {_v(user.occupation)}")
    lines.append(f"Stress Level  : {_v(user.stress_level)}")
    lines.append("")

    # ── 1aa. FOODS THIS PATIENT MUST NEVER BE OFFERED ─────────────
    #
    # The Allergies line above was already here and was not enough: a
    # production plan for a patient whose profile reads "Raw Apples, Raw
    # Berries" opened with "1 small apple" and closed by recommending apples
    # again. An allergy listed among fifteen other profile fields reads as
    # background; stated as a prohibition with its reason, it is an
    # instruction. This block also carries contraindications implied by a
    # DIAGNOSIS rather than by an allergy row — fava beans in G6PD deficiency.
    #
    # Unlike the planner, a prose answer cannot be filtered after the fact, so
    # here this is a prompt-level control only. `app/services/food_safety.py`
    # is the single place that decides what is forbidden, for both surfaces.
    try:
        from app.services import food_safety
        forbidden = food_safety.forbidden_for(user, cc_list)
        block = food_safety.prompt_block(forbidden)
        if block:
            lines.append("=== FOODS THIS PATIENT MUST NEVER BE OFFERED ===")
            lines.append(block)
            lines.append("")
    except Exception:  # noqa: BLE001 - never fail a chat over the guard
        logger.warning("food safety block unavailable", exc_info=True)

    # ── 1a. THIS PATIENT'S NUTRIENT LIMITS AND TARGETS ────────────
    #
    # Without these the model INVENTS them, and it invents them wrong in a
    # specific, dangerous way: it reaches for a SERUM reference value and
    # presents it as a DIETARY limit. A production answer capped potassium at
    # "4.8" — that is a serum figure in mmol/L; the dietary limit for this
    # patient is on the order of 2,000-3,000 mg/day. An earlier answer from the
    # local 20B model was ~10x too strict the same way.
    #
    # 4.8 exists nowhere in this codebase or the database: HEBCS bands
    # potassium 3.5-5.5 and the stored lab reference ranges are 3.5-5.5 and
    # 3.5-5.1. It was fabricated. The fix is not prompt scolding — it is giving
    # the model the numbers we already compute, from the same
    # `compute_goals` the Nutrition screen and the health score use (KDOQI 2020
    # for CKD). Canon 3c: if a lookup is wrong, fix what blocks the lookup.
    try:
        from app.services.nutrient_goals_service import compute_goals
        goals_payload = compute_goals(
            date_of_birth=str(user.date_of_birth) if user.date_of_birth else None,
            sex=user.gender,
            height_cm=user.height_cm,
            current_weight_kg=user.current_weight_kg,
            target_weight_kg=user.target_weight_kg,
            activity_level=user.activity_level,
            conditions=cc_list,
        )
        goal_rows = goals_payload.get("goals") or []
        if goal_rows:
            lines.append("=== DAILY NUTRIENT TARGETS AND LIMITS (authoritative) ===")
            lines.append("These are computed for THIS patient from their biology and")
            lines.append("conditions. Use these exact figures. Do not substitute a")
            lines.append("remembered guideline, and never quote a SERUM reference range")
            lines.append("(mmol/L, mEq/L) as if it were a dietary intake limit.")
            for g in goal_rows:
                kind = "max/day" if g.get("kind") == "limit" else "aim/day"
                lines.append(
                    f"  • {g.get('name') or g.get('key')}: "
                    f"{g.get('goal')} {g.get('unit') or ''} ({kind})".rstrip())
            if goals_payload.get("energy_kcal"):
                lines.append(f"  • Energy: {goals_payload['energy_kcal']} kcal (aim/day)")
            if not goals_payload.get("profile_complete"):
                # Say so rather than letting a default read as a prescription.
                lines.append("  NOTE: the profile is incomplete, so these are")
                lines.append("  reference-adult defaults, not personalised figures.")
            lines.append("")
    except Exception:
        logger.warning("Could not compute nutrient goals for AI context", exc_info=True)

    # ── 2. MEDICATIONS ────────────────────────────────────────────
    med_q = await db.execute(
        select(Medication)
        .where(Medication.user_id == uid)
        .order_by(desc(Medication.start_date), desc(Medication.id))
        .limit(30)
    )
    meds = med_q.scalars().all()
    if meds:
        lines.append("=== MEDICATIONS (active & recent) ===")
        for m in meds:
            status = "active" if m.is_active else "discontinued"
            dose = f"{m.dosage} {m.dosage_unit or ''}".strip() if m.dosage else ""
            parts = [m.name, status]
            if dose:
                parts.append(dose)
            if m.frequency:
                parts.append(m.frequency)
            if m.route:
                parts.append(f"via {m.route}")
            if m.reason:
                parts.append(f"for {m.reason}")
            if m.prescribing_doctor:
                parts.append(f"by {m.prescribing_doctor}")
            lines.append("  • " + " | ".join(parts))
        lines.append("")

    # ── 3. LAB RESULTS ────────────────────────────────────────────
    # 3a. CKD/dialysis key biomarkers — last 3 values each for trend context
    CKD_BIOMARKERS = [
        "KtV (Dialysis Adequacy)", "URR", "URR (Urea Reduction Ratio)",
        "Phosphorus", "PTH (Intact)",
        "Potassium", "BUN", "Creatinine", "Albumin", "Hemoglobin",
        "Bicarbonate", "Calcium", "Sodium", "Ferritin", "Transferrin Saturation",
    ]
    biomarker_rows: dict[str, list] = {}
    for bname in CKD_BIOMARKERS:
        bq = await db.execute(
            select(LabResult)
            .where(LabResult.user_id == uid, LabResult.test_name == bname,
                   LabResult.value.isnot(None))
            .order_by(desc(LabResult.test_date))
            .limit(3)
        )
        rows = bq.scalars().all()
        if rows:
            biomarker_rows[bname] = rows

    if biomarker_rows:
        lines.append("=== KEY CKD/DIALYSIS BIOMARKERS (latest 3 values each) ===")
        for bname, rows in biomarker_rows.items():
            vals = [(f"{r.test_date}: {r.value} {r.unit or ''}".strip() +
                     (" [!]" if r.is_abnormal else "")) for r in rows]
            lines.append(f"  {bname}: {' | '.join(vals)}")
        lines.append("")

    # 3b. Recent labs (most recent 30, for general context)
    lab_q = await db.execute(
        select(LabResult)
        .where(LabResult.user_id == uid)
        .order_by(desc(LabResult.test_date), desc(LabResult.id))
        .limit(30)
    )
    labs = lab_q.scalars().all()
    if labs:
        lines.append("=== LAB RESULTS (30 most recent) ===")
        for l in labs:
            val = f"{l.value} {l.unit or ''}".strip() if l.value is not None else (l.value_string or "N/A")
            flag = " [ABNORMAL]" if l.is_abnormal else ""
            ref = ""
            if l.reference_range_low is not None and l.reference_range_high is not None:
                ref = f" (ref {l.reference_range_low}–{l.reference_range_high} {l.unit or ''})"
            lines.append(f"  {l.test_date} | {l.test_name}: {val}{ref}{flag}")
        lines.append("")

    # ── 4. NUTRITION (last 14 days, capped at 40 entries) ────────
    cutoff_14 = date.today() - timedelta(days=14)
    cutoff_30 = date.today() - timedelta(days=30)
    nut_q = await db.execute(
        select(NutritionLog)
        .where(NutritionLog.user_id == uid, NutritionLog.log_date >= cutoff_14)
        .order_by(desc(NutritionLog.log_date))
        .limit(40)
    )
    nuts = nut_q.scalars().all()
    if nuts:
        lines.append("=== NUTRITION LOGS (last 14 days) ===")
        for n in nuts:
            cal = f"{n.calories:.0f} kcal" if n.calories else ""
            pro = f"P:{n.protein_g:.1f}g" if n.protein_g else ""
            carb = f"C:{n.carbs_g:.1f}g" if hasattr(n, 'carbs_g') and n.carbs_g else ""
            fat  = f"F:{n.fat_g:.1f}g"   if hasattr(n, 'fat_g') and n.fat_g else ""
            macro = " ".join(filter(None, [cal, pro, carb, fat]))
            lines.append(f"  {n.log_date} {n.meal_type}: {n.food_name}{(' — ' + macro) if macro else ''}")
        lines.append("")

    # ── 5. FITNESS LOGS (last 30 days) ────────────────────────────
    fit_q = await db.execute(
        select(FitnessLog)
        .where(FitnessLog.user_id == uid, FitnessLog.log_date >= cutoff_14)
        .order_by(desc(FitnessLog.log_date))
        .limit(20)
    )
    fits = fit_q.scalars().all()
    if fits:
        lines.append("=== FITNESS / EXERCISE LOGS (last 14 days) ===")
        for f in fits:
            parts = [f"{f.log_date}", f.activity_type or "Activity"]
            if f.duration_minutes:
                parts.append(f"{f.duration_minutes} min")
            if f.calories_burned:
                parts.append(f"{f.calories_burned:.0f} kcal burned")
            if f.heart_rate_avg:
                parts.append(f"HR avg {f.heart_rate_avg} bpm")
            if f.intensity:
                parts.append(f"{f.intensity} intensity")
            if f.notes:
                parts.append(f.notes[:100])
            lines.append("  " + " | ".join(parts))
        lines.append("")

    # ── 6. MOOD (all entries — small dataset of real journal entries) ──
    mood_q = await db.execute(
        select(MoodEntry)
        .where(MoodEntry.user_id == uid)
        .order_by(desc(MoodEntry.entry_date))
        .limit(30)
    )
    moods = mood_q.scalars().all()
    if moods:
        lines.append("=== MOOD & JOURNAL ENTRIES ===")
        for m in moods:
            parts = [f"{m.entry_date}", f"mood {m.mood_score}/10"]
            if m.sleep_hours:
                parts.append(f"{m.sleep_hours}h sleep")
            if m.emotions:
                parts.append(f"feeling: {m.emotions}")
            lines.append("  " + " | ".join(parts))
            if m.journal_entry:
                lines.append(f"    Journal: {m.journal_entry[:200]}")
            if m.notes:
                lines.append(f"    Notes  : {m.notes[:150]}")
        lines.append("")

    # ── 6b. ELIMINATION (bowel movements & vomiting — last 60 days) ──
    cutoff_60 = date.today() - timedelta(days=60)
    bm_q = await db.execute(
        select(BowelMovement)
        .where(BowelMovement.user_id == uid, BowelMovement.log_date >= cutoff_60)
        .order_by(desc(BowelMovement.log_date))
        .limit(30)
    )
    bms = bm_q.scalars().all()
    vm_q = await db.execute(
        select(VomitingLog)
        .where(VomitingLog.user_id == uid, VomitingLog.log_date >= cutoff_60)
        .order_by(desc(VomitingLog.log_date))
        .limit(20)
    )
    vms = vm_q.scalars().all()
    if bms or vms:
        lines.append("=== ELIMINATION LOG ====")
        if bms:
            blood_count = sum(1 for b in bms if b.blood_present)
            lines.append(f"  Bowel movements (last 60d): {len(bms)} events")
            if blood_count:
                lines.append(f"  ⚠ Blood present in {blood_count}/{len(bms)} events")
            for b in bms[:10]:
                parts = [str(b.log_date)]
                if b.log_time:
                    parts.append(str(b.log_time)[:5])
                if b.blood_present:
                    parts.append("BLOOD PRESENT")
                if b.bristol_scale:
                    parts.append(f"Bristol {b.bristol_scale}")
                if b.notes:
                    parts.append(b.notes[:80])
                lines.append("  BM: " + " | ".join(parts))
        if vms:
            lines.append(f"  Vomiting episodes (last 60d): {len(vms)} events")
            for v in vms[:10]:
                parts = [str(v.log_date)]
                if v.log_time:
                    parts.append(str(v.log_time)[:5])
                if v.notes:
                    parts.append(v.notes[:80])
                lines.append("  VOMIT: " + " | ".join(parts))
        lines.append("")

    # ── 7. LIFESTYLE / VITALS (pre-dialysis readings, last 30 days) ──
    lfe_q = await db.execute(
        select(LifestyleEntry)
        .where(LifestyleEntry.user_id == uid, LifestyleEntry.entry_date >= cutoff_14)
        .order_by(desc(LifestyleEntry.entry_date))
        .limit(14)
    )
    lfes = lfe_q.scalars().all()
    if lfes:
        lines.append("=== PRE-DIALYSIS VITALS (last 14 days) ===")
        for e in lfes:
            parts = [f"{e.entry_date}"]
            if e.weight_kg:
                parts.append(f"{e.weight_kg} kg")
            if e.blood_pressure_systolic and e.blood_pressure_diastolic:
                parts.append(f"BP {e.blood_pressure_systolic}/{e.blood_pressure_diastolic}")
            if e.resting_heart_rate:
                parts.append(f"HR {e.resting_heart_rate} bpm")
            if e.body_temperature_c:
                parts.append(f"Temp {e.body_temperature_c}°C")
            if e.blood_oxygen_pct:
                parts.append(f"SpO2 {e.blood_oxygen_pct}%")
            if e.notes:
                # Include the rich notes (KtV, fluid removed, post-BP from dialysis session)
                parts.append(e.notes[:100])
            lines.append("  " + " | ".join(parts))
        lines.append("")

        # ── 7a. DIALYSIS CLINICAL SUMMARY (from lifestyle history) ──
        # Compute running stats to give AI a concise trend summary
        weights = [e.weight_kg for e in lfes if e.weight_kg]
        bp_sys  = [e.blood_pressure_systolic for e in lfes
                   if e.blood_pressure_systolic]
        if weights or bp_sys:
            lines.append("=== DIALYSIS VITALS SUMMARY ===")
            if weights:
                avg_w = sum(weights) / len(weights)
                lines.append(f"  Pre-dialysis weight (last 30d): avg {avg_w:.1f} kg, "
                              f"range {min(weights):.1f}–{max(weights):.1f} kg")
            if bp_sys:
                avg_s = sum(bp_sys) / len(bp_sys)
                lines.append(f"  Pre-dialysis BP (last 30d): avg systolic {avg_s:.0f} mmHg, "
                              f"range {min(bp_sys)}–{max(bp_sys)} mmHg")
            # Total session count from lifestyle_entries (each row = one session day)
            hist_q = await db.execute(
                select(LifestyleEntry)
                .where(LifestyleEntry.user_id == uid)
            )
            all_sessions = hist_q.scalars().all()
            if all_sessions:
                lines.append(f"  Total dialysis session days on record: {len(all_sessions)} "
                              f"(since {min(s.entry_date for s in all_sessions)})")
            lines.append("")

    # ── 7b. GROUND TRUTHS: GENETICS + ENVIRONMENT/SOCIAL ──────────
    gm_q = await db.execute(
        select(GeneticMarker).where(GeneticMarker.user_id == uid)
    )
    markers = gm_q.scalars().all()
    if markers:
        lines.append("=== GENETIC GROUND TRUTHS ===")
        for m in markers:
            bits = [m.gene]
            if m.genotype:
                bits.append(f"({m.genotype})")
            if m.associated_condition:
                bits.append(f"— {m.associated_condition}")
            if m.risk_level:
                bits.append(f"[{m.risk_level} risk]")
            lines.append("  " + " ".join(bits))
        lines.append("")

    es_q = await db.execute(
        select(EnvSocialLog)
        .where(EnvSocialLog.user_id == uid)
        .order_by(desc(EnvSocialLog.log_date))
        .limit(1)
    )
    es = es_q.scalar_one_or_none()
    if es:
        parts = []
        if es.location:
            parts.append(f"location {es.location}")
        if es.air_quality_index is not None:
            parts.append(f"AQI {es.air_quality_index}")
        if es.occupation:
            parts.append(f"occupation {es.occupation}")
        if es.work_stress_level is not None:
            parts.append(f"work stress {es.work_stress_level}/10")
        if es.financial_stress_level is not None:
            parts.append(f"financial stress {es.financial_stress_level}/10")
        if es.social_support_level is not None:
            parts.append(f"social support {es.social_support_level}/10")
        if es.major_life_event:
            parts.append(f"recent event: {es.major_life_event[:80]}")
        if parts:
            lines.append("=== ENVIRONMENTAL & SOCIAL FACTORS (latest) ===")
            lines.append("  " + "; ".join(parts))
            lines.append("")

    # ── 8. LEARNED AI MEMORIES (persistent per-user insights) ────
    mem_q = await db.execute(
        select(UserMemory)
        .where(
            UserMemory.user_id == uid,
            UserMemory.is_actionable == True,
            UserMemory.confidence_score >= 0.5,
        )
        .order_by(desc(UserMemory.priority), desc(UserMemory.confidence_score))
        .limit(20)
    )
    memories = mem_q.scalars().all()
    if memories:
        lines.append("=== AI LEARNED PREFERENCES & PATTERNS ===")
        for mem in memories:
            conf = f"{int(mem.confidence_score * 100)}% confidence"
            lines.append(f"  [{mem.category}] {mem.insight_value} ({conf})")
        lines.append("")

    # ── 8b. RLAIF COLLECTIVE PATTERNS (derived from feedback history) ───────
    ci_q = await db.execute(
        select(CollectiveInsight)
        .where(
            CollectiveInsight.is_active == True,
            CollectiveInsight.confidence_level >= 0.4,
        )
        .order_by(desc(CollectiveInsight.confidence_level))
        .limit(5)
    )
    patterns = ci_q.scalars().all()
    # Filter to this user's patterns
    user_patterns = [p for p in patterns if (p.applicable_demographics or {}).get("user_id") == uid]
    if user_patterns:
        lines.append("=== AI LEARNED RESPONSE PATTERNS (from your feedback) ===")
        for pat in user_patterns:
            conf = f"{int(pat.confidence_level * 100)}% confidence"
            lines.append(f"  [{pat.category}] {pat.pattern_description} ({conf})")
        lines.append("")

    # ── 9. HEBCS Ω WELLNESS SCORE ─────────────────────────────────
    try:
        lab_q = await db.execute(
            select(
                LabResult.test_name,
                LabResult.value,
                LabResult.test_date,
            )
            .where(
                LabResult.user_id == uid,
                LabResult.value.isnot(None),
            )
            .order_by(
                LabResult.test_name,
                LabResult.test_date.desc(),
            )
        )
        lab_rows = lab_q.all()
        bv: dict = {}
        seen_t: set = set()
        for tn, val, _ in lab_rows:
            if tn not in seen_t:
                bv[tn] = val
                seen_t.add(tn)
        if bv:
            hd = compute_hebcs(bv)
            lines.append("=== HEBCS Ω WELLNESS SCORE ===")
            lines.append(f"  Overall Ω   : {hd['omega']:.4f}  ({hd['omega_pct']:.1f}% of optimal)")
            lines.append(f"  Data coverage: {hd['data_coverage']:.0%} of expected biomarkers")
            lines.append("  Pathway scores (1.0 = optimal, 0 = critical):")
            for pname, pdata in hd['pathways'].items():
                s = pdata['score']
                flag = " ⚠" if s is not None and s < 0.60 else ""
                lines.append(f"    {pname:<22}: {s if s is not None else 'N/A'}{flag}")
            lines.append("")
    except Exception:
        pass  # Don't block AI if scoring fails

    return "\n".join(lines)


def _build_system_prompt(
    persona: dict | None,
    context_module: str | None,
    user_name: str,
    patient_context: str = "",
    global_knowledge: list[str] | None = None,
) -> str:
    """Build a persona-specific system prompt for Ollama, injecting patient health record
    and optional GlobalKnowledge evidence notes for specialist agents."""
    # Patient record always comes FIRST so the model reads it before any instructions
    patient_block = ""
    if patient_context.strip():
        patient_block = (
            "The following is "
            + user_name
            + "'s complete personal health record, pre-loaded from the ALAFIA database. "
            "Read every section carefully before answering.\n\n"
            "=== START OF " + user_name.upper() + "'S HEALTH RECORD ===\n"
            + patient_context.strip()
            + "\n=== END OF HEALTH RECORD ===\n\n"
        )

    module_note = ""
    if context_module:
        module_note = (
            f"The patient is currently viewing the {context_module.replace('_', ' ')} section. "
            "Lead with insights relevant to that area unless asked otherwise.\n\n"
        )

    # ── Specialist agents: full custom role prompt ─────────────────
    if persona and persona.get("style"):
        specialist_prompt = persona["style"].strip()

        # Inject GlobalKnowledge evidence notes when available
        knowledge_block = ""
        if global_knowledge:
            evidence_lines = "\n".join(f"  • {k}" for k in global_knowledge[:4])
            knowledge_block = (
                f"\n\nEVIDENCE NOTES (cite these when relevant — these are verified clinical guidelines):\n"
                + evidence_lines
                + "\n"
            )

        core_rules = (
            f"\n\nFUNDAMENTAL RULES (apply to every response):\n"
            f"  - ANSWER THE SPECIFIC QUESTION {user_name} ASKED. Respond directly to what they asked — "
            f"do NOT deliver a full multi-section health review unless they explicitly ask for an overall review.\n"
            f"  - You have full access to {user_name}'s complete health record shown above. Use it.\n"
            f"  - ALWAYS cite specific dates and values from the record. Never generalise when data exists.\n"
            f"  - NEVER print bracketed placeholders such as [date], [value], [insert], [trend], or "
            f"[comprehensive summary]. Those are notes to you, not text to output. If you do not have a value, "
            f"omit it or say it is not recorded — do not leave a placeholder and do not invent one.\n"
            f"  - Do NOT fabricate values. Never state a number (BMI, phosphorus, weight, lab result, stress level, "
            f"etc.) unless that exact value appears in the record above.\n"
            f"  - Only describe a lab or vital as high, low, elevated, or abnormal when it falls OUTSIDE the "
            f"reference range shown in the record. If it is within range, call it normal — do not imply concern.\n"
            f"  - FORBIDDEN: Do NOT say 'I cannot access your data' or 'I don't have your records'. The data is above.\n"
            f"  - FORBIDDEN: Do NOT tell {user_name} to check another platform or app when data is here.\n"
            f"  - If something is not in the record, say so plainly — do not fabricate values.\n"
            f"  - Refer to the patient as '{user_name}' or 'you'.\n"
            f"  - Answer in short paragraphs and simple bullet points. NEVER use a markdown table: "
            f"the answer is read in a narrow chat column where a multi-column table cannot fit, and it "
            f"arrives as a wall of pipes and dashes. Put each point on its own line instead.\n"
            f"  - Keep it brief. Lead with the direct answer, then the reasoning — not the reverse."
        )
        return f"{patient_block}{module_note}{specialist_prompt}{knowledge_block}{core_rules}"

    # ── Cultural personas: analyst base + optional cultural flavour ─
    if persona:
        title = persona["title"]
        origin = persona["origin"]
        greeting = persona["greeting"]
        culture = persona.get("culture_style", "")
        persona_intro = (
            f"You are {title}, a personal health data analyst rooted in the "
            f"{origin} healing tradition. Your greeting is '{greeting}'. "
            + (culture.strip() + " " if culture else "")
        )
    else:
        persona_intro = "You are LAFIA, a personal health data analyst for the ALAFIA platform. "

    analyst_instructions = (
        f"{persona_intro}\n"
        f"{module_note}"
        f"Your only job is to read the health record above and answer {user_name}'s questions "
        "based on what is written there. "
        "RULES (must follow every single one):\n"
        f"  - ANSWER THE SPECIFIC QUESTION {user_name} ASKED — do not deliver a full health review unless asked.\n"
        f"  - If {user_name} asks about their meals, read NUTRITION LOGS and report the most recent entry with its date, food name, and meal type.\n"
        f"  - If {user_name} asks about their conditions, read the 'Chronic Cond.' line in PATIENT PROFILE.\n"
        f"  - If {user_name} asks about labs, read LAB RESULTS.\n"
        f"  - If {user_name} asks about medications, read MEDICATIONS.\n"
        "  - NEVER print bracketed placeholders like [date], [value], or [insert]. If you don't have a value, "
        "omit it or say it isn't recorded — never leave or invent a placeholder.\n"
        "  - Do NOT fabricate values. Never state a number that is not written in the record above. Only call a "
        "value high or low when it is outside the reference range shown; otherwise treat it as normal.\n"
        "  - FORBIDDEN: Do NOT say 'I cannot access your data', 'I don't have your records', "
        "or 'I'm a large language model'. The data IS available — it is above.\n"
        "  - FORBIDDEN: Do NOT suggest checking MyChart, asking a doctor, or using another platform when the data is here.\n"
        "  - Always cite the specific date and value from the record.\n"
        "  - Plain text only — no markdown, no bullet points unless listing multiple items.\n"
        f"  - Refer to the patient as '{user_name}' or 'you'."
    )

    return f"{patient_block}{analyst_instructions}"


# keyword → section header to extract from patient_context
_QUERY_SECTION_MAP: list[tuple[list[str], str]] = [
    (["meal", "eat", "food", "nutrition", "diet", "breakfast", "lunch", "dinner", "snack", "drink", "drank", "ate", "consumed"], "NUTRITION LOGS"),
    (["condition", "diagnosis", "disease", "chronic", "illness", "sick", "disorder", "health condition"], "PATIENT PROFILE"),
    (["medication", "medicine", "drug", "prescription", "pill", "tablet", "dose", "drug"], "MEDICATIONS"),
    (["lab", "test", "result", "blood", "creatinine", "potassium", "pth", "phosphorus", "ktv", "hemoglobin", "albumin", "biomarker"], "LAB RESULTS"),
    (["dialysis", "session", "vital", "weight", "blood pressure", "bp", "heart rate", "temperature", "spo2"], "PRE-DIALYSIS VITALS"),
    (["mood", "journal", "feeling", "emotion", "mental"], "MOOD"),
    (["bowel", "stool", "poop", "vomit", "urination", "elimination"], "ELIMINATION"),
    (["score", "wellness", "hebcs", "omega", "pathway"], "HEBCS"),
]


def _augment_query(query: str, patient_context: str, user_name: str) -> str:
    """
    Keyword-based fallback: extract the most relevant section(s) from patient_context
    and prepend them to the user message.  Used when semantic embeddings are not yet ready.
    """
    q_lower = query.lower()
    matched_sections: list[str] = []

    for keywords, section_header in _QUERY_SECTION_MAP:
        if any(kw in q_lower for kw in keywords):
            # Find the section in the context
            idx = patient_context.find(section_header)
            if idx == -1:
                continue
            # Extract from the header to the next "===" section or end
            end_idx = patient_context.find("\n===", idx + len(section_header))
            snippet = patient_context[idx:end_idx].strip() if end_idx != -1 else patient_context[idx:].strip()
            # Cap at 1500 chars per section to stay within context window
            matched_sections.append(snippet[:1500])

    if not matched_sections:
        # No specific match — include profile + first 800 chars of context
        matched_sections.append(patient_context[:1200])

    relevant_data = "\n\n".join(matched_sections)
    return (
        f"--- {user_name}'s relevant health records for this question ---\n"
        f"{relevant_data}\n"
        f"--- end of records ---\n\n"
        f"{query}"
    )


def _assemble_chat_messages(system_prompt: str, history, query: str, augmented_query: str) -> list[dict]:
    """Build the Ollama message list for a chat turn.

    The frontend includes the just-sent user turn in `history`; drop that trailing
    duplicate so the question isn't sent twice (once raw, once augmented). The
    augmented copy — which carries the retrieved health-record snippet — becomes
    the final user turn the model answers.
    """
    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    hist = list(history or [])
    if hist and hist[-1].role == "user" and (hist[-1].content or "").strip() == (query or "").strip():
        hist = hist[:-1]
    for m in hist:
        messages.append({"role": m.role, "content": m.content})
    messages.append({"role": "user", "content": augmented_query})
    return messages


# ── Semantic RAG helpers ───────────────────────────────────────────────────────

def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Pure-Python cosine similarity between two equal-length vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x ** 2 for x in a))
    mag_b = math.sqrt(sum(x ** 2 for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


async def _embed_text(text: str) -> list[float] | None:
    """Embed text using Ollama llama3.2 (3072-dim). Returns None on failure."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{settings.OLLAMA_BASE_URL}/api/embeddings",
                json={"model": "llama3.2:latest", "prompt": text[:2000]},
                headers=await ollama_auth_headers(),
            )
            if resp.status_code == 200:
                return resp.json().get("embedding")
    except Exception:
        pass
    return None


def _split_context_sections(patient_context: str) -> dict[str, str]:
    """Split patient context string into {section_header: section_text} dict."""
    sections: dict[str, str] = {}
    lines = patient_context.split("\n")
    current_key: str | None = None
    current_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("===") and stripped.endswith("===") and len(stripped) > 6:
            if current_key and current_lines:
                sections[current_key] = "\n".join(current_lines).strip()
            current_key = stripped.strip("= ").strip()
            current_lines = []
        elif current_key is not None:
            current_lines.append(line)
    if current_key and current_lines:
        sections[current_key] = "\n".join(current_lines).strip()
    return sections


async def _refresh_patient_embeddings(
    user_id: int,
    patient_context: str,
    db: AsyncSession,
) -> None:
    """
    Background task: split patient context into sections, embed each via llama3.2,
    and upsert into health_embeddings.  Called fire-and-forget after each AI chat.
    """
    sections = _split_context_sections(patient_context)
    for key, text in sections.items():
        if not text.strip():
            continue
        embedding = await _embed_text(text)
        if not embedding:
            continue
        try:
            existing_q = await db.execute(
                select(HealthEmbedding).where(
                    HealthEmbedding.user_id == user_id,
                    HealthEmbedding.chunk_key == key,
                )
            )
            row = existing_q.scalar_one_or_none()
            if row:
                row.chunk_text = text
                row.embedding = embedding
                row.updated_at = datetime.now(timezone.utc)
            else:
                db.add(HealthEmbedding(
                    user_id=user_id,
                    chunk_key=key,
                    chunk_text=text,
                    embedding=embedding,
                    updated_at=datetime.now(timezone.utc),
                ))
        except Exception:
            pass
    try:
        await db.commit()
    except Exception:
        await db.rollback()


async def _semantic_augment_query(
    query: str,
    user_id: int,
    db: AsyncSession,
    patient_context: str,
    top_k: int = 3,
) -> str:
    """
    Semantic RAG: embed the query and retrieve the most semantically similar
    health record sections from health_embeddings.  Falls back to keyword
    matching (_augment_query) if embeddings are not yet populated.
    """
    emb_result = await db.execute(
        select(HealthEmbedding)
        .where(HealthEmbedding.user_id == user_id)
        .order_by(desc(HealthEmbedding.updated_at))
    )
    stored = emb_result.scalars().all()

    if not stored:
        # No embeddings yet — fall back to keyword matching
        return _augment_query(query, patient_context, "")

    query_embedding = await _embed_text(query)
    if not query_embedding:
        return _augment_query(query, patient_context, "")

    scored: list[tuple[float, str, str]] = []
    for row in stored:
        if not row.embedding:
            continue
        try:
            sim = _cosine_similarity(query_embedding, row.embedding)
            scored.append((sim, row.chunk_key, row.chunk_text))
        except Exception:
            continue

    if not scored:
        return _augment_query(query, patient_context, "")

    scored.sort(reverse=True)
    top_sections = scored[:top_k]
    parts = [f"[{key}]\n{text[:1500]}" for _, key, text in top_sections]
    return (
        "RELEVANT HEALTH RECORD SECTIONS (semantic retrieval):\n\n"
        + "\n\n---\n\n".join(parts)
        + f"\n\n---\n\nUser Question: {query}"
    )


@router.post("/chat", response_model=AIQueryResponseWithMemory)
async def ai_chat(
    request: AIQueryRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Non-streaming AI chat — returns full response when complete."""
    persona_key = request.persona or getattr(current_user, "ai_persona", None)
    persona = PERSONA_PROFILES.get(persona_key) if persona_key else None

    patient_context = await _fetch_patient_context(current_user, db)

    # Fetch GlobalKnowledge evidence notes for specialist agents
    domain_knowledge: list[str] = []
    if persona and persona.get("specialty"):
        gk_result = await db.execute(
            select(GlobalKnowledge)
            .where(GlobalKnowledge.domain == persona["specialty"], GlobalKnowledge.is_active == True)
            .order_by(desc(GlobalKnowledge.relevance_score))
            .limit(3)
        )
        for gk in gk_result.scalars().all():
            points = " | ".join((gk.key_points or [])[:3])
            domain_knowledge.append(f"{gk.title} ({gk.source_organization}): {points}")

    system_prompt = _build_system_prompt(
        # NOT the patient's name: this prompt reaches a third-party provider and
        # a second-person reference carries the same weight (§3al). "the patient"
        # rather than a greeting word, because the string is interpolated into
        # rules ("ANSWER THE QUESTION {x} ASKED") as well as into address.
        persona, request.context_module, "the patient",
        patient_context, global_knowledge=domain_knowledge or None,
    )
    model = request.model or settings.OLLAMA_MODEL

    # Semantic RAG: embed query, retrieve top-K most relevant record sections
    augmented_query = await _semantic_augment_query(
        request.query, current_user.id, db, patient_context
    )
    ollama_messages = _assemble_chat_messages(
        system_prompt, request.messages, request.query, augmented_query
    )

    t0 = time.monotonic()
    # Routed through the ALAFIAModel facade (Ollama primary → OpenAI fallback).
    from app.services.alafia_model_service import alafia_chat_detailed, ALAFIAModelError
    try:
        # _detailed so the token count survives to the AIInteraction row below.
        # The plain alafia_chat returns only text, which is why per-user usage
        # read as zero for every interaction ever recorded.
        completion = await alafia_chat_detailed(ollama_messages, model=model, temperature=0.7)
        response_text = (completion.get("text") or "").strip()
    except ALAFIAModelError as exc:
        raise HTTPException(503, f"AI model unavailable: {exc}")

    elapsed_ms = int((time.monotonic() - t0) * 1000)

    # Persist interaction for memory + feedback tracking
    interaction_id: int | None = None
    try:
        interaction = AIInteraction(
            user_id=current_user.id,
            interaction_type="chat",
            category=request.context_module or "general",
            user_request=request.query,
            ai_response=response_text,
            context_used={"persona": persona_key, "module": request.context_module},
            llm_provider=completion.get("provider") or "ollama",
            llm_model=completion.get("model") or model,
            tokens_used=completion.get("tokens_used") or 0,
            response_time_ms=elapsed_ms,
        )
        db.add(interaction)
        await db.commit()
        await db.refresh(interaction)
        interaction_id = interaction.id
    except Exception:
        await db.rollback()  # don't fail the request over memory write

    # Fire-and-forget: refresh semantic embeddings in the background
    asyncio.ensure_future(
        _refresh_patient_embeddings(current_user.id, patient_context, db)
    )

    return AIQueryResponseWithMemory(
        response=response_text,
        module=request.context_module,
        confidence=1.0,
        persona=persona_key,
        interaction_id=interaction_id,
    )


@router.post("/chat/stream")
async def ai_chat_stream(
    request: AIQueryRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Streaming AI chat — returns Server-Sent Events (SSE).

    Each event: `data: {"content": "<token>"}\\n\\n`
    Final event: `data: [DONE]\\n\\n`
    """
    persona_key = request.persona or getattr(current_user, "ai_persona", None)
    persona = PERSONA_PROFILES.get(persona_key) if persona_key else None

    patient_context = await _fetch_patient_context(current_user, db)

    # Fetch GlobalKnowledge for specialist agents
    domain_knowledge: list[str] = []
    if persona and persona.get("specialty"):
        gk_result = await db.execute(
            select(GlobalKnowledge)
            .where(GlobalKnowledge.domain == persona["specialty"], GlobalKnowledge.is_active == True)
            .order_by(desc(GlobalKnowledge.relevance_score))
            .limit(3)
        )
        for gk in gk_result.scalars().all():
            points = " | ".join((gk.key_points or [])[:3])
            domain_knowledge.append(f"{gk.title} ({gk.source_organization}): {points}")

    system_prompt = _build_system_prompt(
        # NOT the patient's name: this prompt reaches a third-party provider and
        # a second-person reference carries the same weight (§3al). "the patient"
        # rather than a greeting word, because the string is interpolated into
        # rules ("ANSWER THE QUESTION {x} ASKED") as well as into address.
        persona, request.context_module, "the patient",
        patient_context, global_knowledge=domain_knowledge or None,
    )
    model = request.model or settings.OLLAMA_MODEL

    # Semantic RAG: embed query and retrieve top-K relevant sections
    augmented_query = await _semantic_augment_query(
        request.query, current_user.id, db, patient_context
    )
    ollama_messages = _assemble_chat_messages(
        system_prompt, request.messages, request.query, augmented_query
    )

    t0 = time.monotonic()
    accumulated: list[str] = []

    # Streams through the ALAFIAModel router, NOT straight to Ollama.
    #
    # This was the one LLM path that bypassed the router, and it cost three
    # things at once: a hosted provider was never used — so APP_REVIEW_RESPONSE.md
    # telling Apple "currently Anthropic … our own servers as fallback" was
    # inverted for the app's main AI surface; the answer came from a 20B local
    # model, which invented a potassium limit 10x too strict; and the payload
    # never passed `privacy.scrub_payload`, the single egress point where a
    # patient stops being a name and becomes `subject_token()`.
    #
    # Order is the router's: hosted first in production, Ollama as the fallback
    # when a provider is unreachable or out of credit.
    async def token_generator():
        try:
            from app.services.alafia_model_service import stream_alafia_chat

            async for token in stream_alafia_chat(ollama_messages, model=model):
                accumulated.append(token)
                yield f"data: {json.dumps({'content': token})}\n\n"

            elapsed_ms = int((time.monotonic() - t0) * 1000)
            full_response = "".join(accumulated)
            try:
                interaction = AIInteraction(
                    user_id=current_user.id,
                    interaction_type="chat_stream",
                    category=request.context_module or "general",
                    user_request=request.query,
                    ai_response=full_response,
                    context_used={"persona": persona_key, "module": request.context_module},
                    llm_provider="router",
                    llm_model=model,
                    response_time_ms=elapsed_ms,
                )
                db.add(interaction)
                await db.commit()
                await db.refresh(interaction)
                yield f"data: {json.dumps({'interaction_id': interaction.id})}\n\n"
            except Exception:
                await db.rollback()
            yield "data: [DONE]\n\n"
            return
        except Exception as exc:
            # Name the exception TYPE: `str(httpx.ReadTimeout(''))` is '', so the
            # likeliest failure would otherwise render as nothing at all (§3ae).
            detail = f"{type(exc).__name__}: {exc}".rstrip(": ")
            logger.error("chat stream failed: %s", detail, exc_info=True)
            yield f"data: {json.dumps({'error': detail})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        token_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/feedback", response_model=AIFeedbackResponse)
async def ai_feedback(
    body: AIFeedbackRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Record user feedback on an AI interaction.

    - Sets was_helpful / was_followed on the saved AIInteraction
    - If helpful and the AI response contains a learnable insight, writes a UserMemory
    """
    result = await db.execute(
        select(AIInteraction).where(
            AIInteraction.id == body.interaction_id,
            AIInteraction.user_id == current_user.id,  # ownership check
        )
    )
    interaction = result.scalar_one_or_none()
    if not interaction:
        raise HTTPException(404, "Interaction not found")

    interaction.was_helpful = body.was_helpful
    interaction.user_feedback = body.user_feedback
    if body.was_followed is not None:
        interaction.was_followed = body.was_followed
    interaction.feedback_received_at = datetime.now(timezone.utc)
    interaction.user_sentiment = "positive" if body.was_helpful else "negative"

    # If positive feedback, write a UserMemory so future responses reflect this preference
    if body.was_helpful and body.user_feedback:
        existing = await db.execute(
            select(UserMemory).where(
                UserMemory.user_id == current_user.id,
                UserMemory.insight_key == f"feedback_{body.interaction_id}",
            )
        )
        if not existing.scalar_one_or_none():
            memory = UserMemory(
                user_id=current_user.id,
                category=interaction.category or "general",
                insight_key=f"feedback_{body.interaction_id}",
                insight_value=(
                    f"User found this response helpful: \"{interaction.ai_response[:200]}\"."
                    + (f" Their note: {body.user_feedback}" if body.user_feedback else "")
                ),
                confidence_score=0.8,
                evidence_count=1,
                is_actionable=True,
                priority=6,
            )
            db.add(memory)

            # LearningEvent audit trail for new memory
            db.add(LearningEvent(
                event_type="insight_discovered",
                intelligence_level="individual",
                user_id=current_user.id,
                description=(
                    f"UserMemory created from feedback on interaction #{body.interaction_id} "
                    f"({interaction.category}): user marked response helpful."
                ),
                data_snapshot={"interaction_id": body.interaction_id, "category": interaction.category},
            ))

    # Outcome reward shaping: if user followed the recommendation, compute quality score
    if body.was_followed:
        from app.api.ai_learning import compute_outcome_reward
        try:
            score = await compute_outcome_reward(body.interaction_id, current_user.id, db)
            if score is not None:
                interaction.recommendation_quality_score = score
        except Exception:
            pass  # reward computation is best-effort

    await db.commit()
    return AIFeedbackResponse(ok=True, interaction_id=body.interaction_id)

