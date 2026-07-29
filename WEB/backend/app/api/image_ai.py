"""Image AI & Dosage Verification endpoints.

Food and medication photos run through the real vision pipeline
(ALAFIAModel → local Ollama vision model in dev, OpenAI when configured);
recognized foods are then priced through the believability-guarded nutrient
estimator — the same stack the Nutrition pages use. No fabricated numbers:
when no vision backend can see the image we say so (503) instead of guessing.

Uploads are accepted as EITHER multipart (`file`) or JSON `{"image_base64"}` —
the JSON path exists because some browsers' multipart encoding (Safari) has
proven flaky through proxies.
"""

import base64
import binascii
import json
import logging
import os
import re

import httpx

from app.services.ollama_auth import ollama_auth_headers
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.medications import Medication
from app.schemas.wellness import (
    NutritionFromImageResponse, MedicationFromImageResponse,
    DosageVerificationRequest, DosageVerificationResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


async def _read_image(request: Request, file: UploadFile | None) -> tuple[bytes, str]:
    """Image bytes + content type from multipart `file` or JSON `image_base64`."""
    if file is not None:
        content = await file.read()
        if content:
            return content, file.content_type or "image/jpeg"
    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        body = None
    if isinstance(body, dict) and body.get("image_base64"):
        b64 = body["image_base64"]
        # Tolerate data URLs ("data:image/jpeg;base64,…")
        content_type = "image/jpeg"
        if b64.startswith("data:"):
            header, _, b64 = b64.partition(",")
            content_type = header.split(";")[0][5:] or content_type
        try:
            return base64.b64decode(b64), content_type
        except (binascii.Error, ValueError):
            raise HTTPException(status_code=400, detail="image_base64 is not valid base64")
    raise HTTPException(
        status_code=400,
        detail="No image received — send a multipart 'file' or JSON {\"image_base64\": …}.",
    )

# ── Deterministic Medication Library ────────────────────────
MEDICATION_LIBRARY = {
    "lisinopril": {"name": "Lisinopril", "class": "ACE Inhibitor", "typical_dosage": "10-40 mg/day", "max": 80, "min": 2.5},
    "amlodipine": {"name": "Amlodipine", "class": "Calcium Channel Blocker", "typical_dosage": "2.5-10 mg/day", "max": 10, "min": 2.5},
    "metformin": {"name": "Metformin", "class": "Biguanide", "typical_dosage": "500-2000 mg/day", "max": 2550, "min": 500},
    "atorvastatin": {"name": "Atorvastatin", "class": "Statin", "typical_dosage": "10-80 mg/day", "max": 80, "min": 10},
    "levothyroxine": {"name": "Levothyroxine", "class": "Thyroid Hormone", "typical_dosage": "25-200 mcg/day", "max": 300, "min": 12.5},
    "metoprolol": {"name": "Metoprolol", "class": "Beta Blocker", "typical_dosage": "25-200 mg/day", "max": 400, "min": 12.5},
    "omeprazole": {"name": "Omeprazole", "class": "Proton Pump Inhibitor", "typical_dosage": "20-40 mg/day", "max": 40, "min": 10},
    "losartan": {"name": "Losartan", "class": "ARB", "typical_dosage": "25-100 mg/day", "max": 100, "min": 25},
    "gabapentin": {"name": "Gabapentin", "class": "Anticonvulsant", "typical_dosage": "300-3600 mg/day", "max": 3600, "min": 100},
    "aspirin": {"name": "Aspirin", "class": "NSAID / Antiplatelet", "typical_dosage": "81-325 mg/day", "max": 4000, "min": 81},
    "insulin": {"name": "Insulin", "class": "Antidiabetic", "typical_dosage": "varies by type", "max": 200, "min": 1},
    "prednisone": {"name": "Prednisone", "class": "Corticosteroid", "typical_dosage": "5-60 mg/day", "max": 80, "min": 1},
    "warfarin": {"name": "Warfarin", "class": "Anticoagulant", "typical_dosage": "2-10 mg/day", "max": 15, "min": 0.5},
    "furosemide": {"name": "Furosemide", "class": "Loop Diuretic", "typical_dosage": "20-80 mg/day", "max": 600, "min": 10},
    "sevelamer": {"name": "Sevelamer", "class": "Phosphate Binder", "typical_dosage": "800-3200 mg TID", "max": 14400, "min": 800},
}


async def _vision_ask(image: bytes, prompt: str) -> str:
    """Ask the local vision model a plain question about the photo."""
    model = os.environ.get("OLLAMA_VISION_MODEL", "moondream")
    b64 = base64.b64encode(image).decode("ascii")
    try:
        async with httpx.AsyncClient(timeout=float(os.environ.get("OLLAMA_TIMEOUT", "300"))) as client:
            resp = await client.post(
                f"{settings.OLLAMA_BASE_URL}/api/generate",
                json={"model": model, "prompt": prompt, "images": [b64], "stream": False},
                headers=await ollama_auth_headers(),
            )
            resp.raise_for_status()
            return (resp.json().get("response") or "").strip()
    except Exception as e:
        logger.warning("Vision question failed: %s", e)
        return ""


_FOOD_CAPTION_PROMPT = "What foods are on this plate?"

# Caption lead-ins that aren't food ("The plate contains rice…" → "rice…").
_CAPTION_PREFIXES = re.compile(
    r"^(the (image|photo|picture) (shows|contains|depicts)|the plate (contains|has|holds)|"
    r"this (is|appears to be)|there (is|are))\s*",
    re.IGNORECASE,
)
# Uncertainty qualifiers double-count the same item ("meat, possibly chicken"
# priced as meat AND chicken; "chicken or fish" as chicken AND "or fish") —
# keep the first alternative, drop the qualifier clause.
_CAPTION_QUALIFIERS = re.compile(
    r",?\s*\b(possibly|probably|perhaps|maybe|likely|or)\s+[^,;.]+",
    re.IGNORECASE,
)
# Portion filler that confuses food-name lookups.
_CAPTION_FILLER = re.compile(r"\b(a piece of|a serving of|a plate of|a bowl of|some)\s+", re.IGNORECASE)
# Sentences about the scene, not the food ("A fork is placed next to the plate.").
_CAPTION_SCENE = re.compile(
    r"[^.;]*\b(fork|knife|spoon|napkin|cutlery|glass|cup|table|plate is|plate appears)\b[^.;]*[.;]?",
    re.IGNORECASE,
)

# Parser tokens that are never foods — conjunctions the NLM meal parser can
# leak as components; the AI fallback would happily invent numbers for them.
_NON_FOOD_TOKENS = {
    "and", "or", "with", "the", "a", "an", "of", "on", "in", "it", "its",
    "food", "meal", "dish", "plate", "bowl", "fork", "knife", "spoon",
    "cup", "glass", "napkin", "table", "garnish", "side",
}


def _clean_caption(caption: str) -> str:
    """Reduce a vision caption to a parseable food list."""
    caption = _CAPTION_SCENE.sub("", caption)
    caption = _CAPTION_PREFIXES.sub("", caption)
    caption = _CAPTION_QUALIFIERS.sub("", caption)
    caption = _CAPTION_FILLER.sub("", caption)
    # Conjunction lists parse cleaner as commas ("rice and chicken" → "rice, chicken")
    caption = re.sub(r"\s+\band\b\s+", ", ", caption, flags=re.IGNORECASE)
    caption = re.sub(r",\s*,+", ", ", caption)
    caption = re.sub(r"\s{2,}", " ", caption)
    return caption.strip().rstrip(".").strip(", ")


def _plausible_food_name(name: str) -> bool:
    """True when a parsed component name looks like a single food item, not a
    sentence fragment ("vegetables. there is chicken", "…nutritious meal option…")."""
    core = name.lower().strip(" .,")
    if not core or len(core) < 3 or core in _NON_FOOD_TOKENS:
        return False
    if core.startswith(("or ", "and ", "with ")):
        return False
    if len(core) > 40 or len(core.split()) > 4:
        return False
    # Sentence punctuation / verb chatter never appears in a food name.
    if any(t in core for t in ("(", ")", ". ", " is ", " are ", " which", " can ",
                               " used ", " creates", " these ", " combination")):
        return False
    return True


async def _extract_food_list(caption: str) -> list[str]:
    """Distill a verbose vision caption into distinct food names via the local
    text model. Small vision models ramble; the text model is good at lists."""
    prompt = (
        "From this description of a meal photo, extract ONLY the distinct food "
        "items that are actually IN the meal. Exclude foods mentioned only as "
        "comparisons or alternatives (e.g. 'can be used instead of rice' → no rice). "
        "Respond with JSON exactly like {\"foods\": [\"rice\", \"grilled chicken\"]}. "
        "No commentary, no cookware, no cutlery, each item 1-4 words.\n\n"
        f"Description: {caption}"
    )
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{settings.OLLAMA_BASE_URL}/api/generate",
                json={"model": settings.OLLAMA_MODEL, "prompt": prompt,
                      "stream": False, "format": "json",
                      "options": {"temperature": 0}},
                headers=await ollama_auth_headers(),
            )
            resp.raise_for_status()
            parsed = json.loads((resp.json().get("response") or "").strip())
    except Exception as e:
        logger.warning("Food-list extraction failed: %s", e)
        return []
    foods = parsed.get("foods") if isinstance(parsed, dict) else None
    if not isinstance(foods, list):
        return []
    out, seen = [], set()
    for f in foods:
        name = str(f).strip().strip(".,")
        if _plausible_food_name(name) and name.lower() not in seen:
            seen.add(name.lower())
            out.append(name)
    return out[:8]


async def _vision_food_caption(image: bytes) -> str:
    """Identify foods in the photo: vision caption → text-model list extraction,
    with regex cleanup as the fallback."""
    caption = await _vision_ask(image, _FOOD_CAPTION_PROMPT)
    if not caption:
        return ""
    foods = await _extract_food_list(caption)
    if foods:
        return "; ".join(foods)
    return _clean_caption(caption)


async def _price_description(db: AsyncSession, user: User, description: str) -> tuple[list, dict]:
    """Run a food description through the believability-guarded estimator,
    keeping only plausible food components."""
    from app.services.nutrient_estimator import estimate_meal_nutrients

    food_items, total = [], {"calories": 0.0, "protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0}
    try:
        meal = await estimate_meal_nutrients(
            db, description,
            country=user.country,
            preferred_units=user.preferred_units,
            locale=user.locale,
        )
        for comp in meal.get("components", []):
            name = str(comp.get("food_name") or comp.get("name") or "").strip()
            # Parser leakage guard: sentence fragments, conjunctions and scene
            # words are not foods — drop them rather than price them.
            if not _plausible_food_name(name):
                continue
            n = comp.get("nutrients_scaled") or comp.get("nutrients") or {}
            entry = {
                "name": name,
                "calories": round(float(n.get("calories") or 0), 1),
                "protein_g": round(float(n.get("protein_g") or 0), 1),
                "carbs_g": round(float(n.get("carbs_g") or 0), 1),
                "fat_g": round(float(n.get("fat_g") or 0), 1),
            }
            food_items.append(entry)
            for k in total:
                total[k] += entry[k]
        # Totals from kept components only — the aggregate would re-include
        # anything the leakage guard dropped.
        total = {k: round(v, 1) for k, v in total.items()}
    except Exception as e:
        logger.warning("Nutrient estimation failed for '%s': %s", description[:80], e)
    return food_items, total


@router.post("/nutrition-from-image", response_model=NutritionFromImageResponse)
async def nutrition_from_image(
    request: Request,
    file: UploadFile | None = File(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Identify the food in a photo and estimate its nutrition.

    Order: the user's own labeled photos (visual memory) → vision model →
    believability-guarded nutrient estimator (learned → curated → USDA → AI).
    """
    from app.services import image_learning

    image, content_type = await _read_image(request, file)

    # 1) Visual memory: has the user labeled this (or a very similar) photo?
    learned = await image_learning.find_learned_match(db, current_user.id, image)
    if learned is not None:
        food_items, total = await _price_description(db, current_user, learned.labels)
        if food_items:
            return NutritionFromImageResponse(
                food_items=food_items,
                total_calories=total["calories"],
                total_protein_g=total["protein_g"],
                total_carbs_g=total["carbs_g"],
                total_fat_g=total["fat_g"],
                notes=f"Matched a meal you labeled before: {learned.labels}. "
                      "Estimates only — verify portions for accuracy.",
            )

    if settings.OPENAI_API_KEY:
        os.environ.setdefault("OPENAI_API_KEY", settings.OPENAI_API_KEY)

    from app.services.alafia_model_service import alafia_infer

    # 2) Structured vision (items + portions when the model can do JSON) …
    vision = await alafia_infer("vision", {
        "image_bytes": image,
        "content_type": content_type,
        "task": "food_photo_nutrition",
    })
    data = (vision.get("data") or {}) if vision.get("success") else {}
    items = [i for i in (data.get("items") or []) if isinstance(i, dict) and i.get("name")]

    if items:
        parts = []
        for it in items[:8]:
            name = str(it["name"]).strip()
            portion = str(it.get("portion") or it.get("quantity") or "").strip()
            parts.append(f"{name} ({portion})" if portion else name)
        description = "; ".join(parts)
    else:
        # … caption fallback: small local vision models (moondream) answer a
        # plain question far more reliably than they emit JSON. The caption
        # feeds the NLM meal parser, which extracts the foods.
        description = await _vision_food_caption(image)
        if not description:
            raise HTTPException(
                status_code=503,
                detail=vision.get("error")
                or "The food-recognition model is unavailable right now — try again shortly "
                   "or log the meal by text in Log Food Intake.",
            )

    food_items, total = await _price_description(db, current_user, description)

    # Estimator found nothing → fall back to the vision model's own estimate.
    if not food_items:
        est = data.get("estimated_nutrition") or {}
        food_items = [{
            "name": ", ".join(str(i["name"]) for i in items[:5]) or description[:80],
            "calories": round(float(est.get("calories") or 0), 1),
            "protein_g": round(float(est.get("protein_g") or 0), 1),
            "carbs_g": round(float(est.get("carbs_g") or 0), 1),
            "fat_g": round(float(est.get("fat_g") or 0), 1),
        }]
        total = {k: food_items[0][k] for k in total}

    notes = f"Identified: {description}."
    if data.get("notes"):
        notes += f" {data['notes']}"
    notes += " Estimates only — verify portions for accuracy. Not right? Teach ALAFIA the correct foods."

    return NutritionFromImageResponse(
        food_items=food_items,
        total_calories=total["calories"],
        total_protein_g=total["protein_g"],
        total_carbs_g=total["carbs_g"],
        total_fat_g=total["fat_g"],
        notes=notes,
    )


@router.post("/label", response_model=NutritionFromImageResponse)
async def label_food_image(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Teach ALAFIA: store the user's ground-truth foods for a photo.

    JSON body: {"image_base64": …, "foods": "…"} OR {"image_base64": …,
    "recipe_url": "https://…"} — with a recipe link, the dish is parsed from
    the page's structured recipe data and the photo is tied to it. The label is
    stored as a perceptual hash (no image bytes retained) and the corrected
    meal is priced and returned. Future photos of the same meal are identified
    from this label before any vision model runs.
    """
    from app.services import image_learning

    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        body = None
    if not isinstance(body, dict) or not (body.get("foods") or body.get("recipe_url")):
        raise HTTPException(status_code=400, detail="Provide {image_base64, foods} or {image_base64, recipe_url}.")

    image, _ = await _read_image(request, None)

    if body.get("foods"):
        foods = str(body["foods"]).strip()[:500]
    else:
        # Third input: the photo's ground truth comes from a recipe page.
        # Label with the DISH NAME (prices at serving scale via the curated/
        # learned stores) — the full ingredient list would price the whole pot.
        from app.services.recipe_ingest import RecipeError, fetch_recipe
        try:
            recipe = await fetch_recipe(str(body["recipe_url"]).strip())
        except RecipeError as e:
            raise HTTPException(status_code=422, detail=str(e))
        foods = recipe["name"].strip()[:200]
        named_items, _named_total = await _price_description(db, current_user, foods)
        if not named_items:
            foods = "; ".join(recipe["ingredients"])[:500]

    await image_learning.save_label(db, current_user.id, image, foods)
    food_items, total = await _price_description(db, current_user, foods)
    if not food_items:
        raise HTTPException(
            status_code=422,
            detail="Could not price those foods — check the names and try again.",
        )
    return NutritionFromImageResponse(
        food_items=food_items,
        total_calories=total["calories"],
        total_protein_g=total["protein_g"],
        total_carbs_g=total["carbs_g"],
        total_fat_g=total["fat_g"],
        notes=f"Learned: {foods}. ALAFIA will recognize this meal from photos going forward.",
    )


_MED_LABEL_PROMPT = (
    "You are reading a medication bottle/package label. Extract exactly what is "
    "printed. Respond ONLY with JSON: "
    '{"medication_name": str, "strength": str, "instructions": str, "prescriber": str, "other": str}. '
    "Use empty strings for anything not visible. Do not guess."
)


async def _vision_read_med_label(image: bytes) -> dict | None:
    """Read a medication label with the local Ollama vision model."""
    model = os.environ.get("OLLAMA_VISION_MODEL", "moondream")
    b64 = base64.b64encode(image).decode("ascii")
    try:
        async with httpx.AsyncClient(timeout=float(os.environ.get("OLLAMA_TIMEOUT", "300"))) as client:
            resp = await client.post(
                f"{settings.OLLAMA_BASE_URL}/api/generate",
                json={"model": model, "prompt": _MED_LABEL_PROMPT, "images": [b64],
                      "stream": False, "format": "json"},
                headers=await ollama_auth_headers(),
            )
            resp.raise_for_status()
            raw = (resp.json().get("response") or "").strip()
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else None
    except Exception as e:
        logger.warning("Medication label vision failed: %s", e)
        return None


@router.post("/medication-from-image", response_model=MedicationFromImageResponse)
async def medication_from_image(
    request: Request,
    file: UploadFile | None = File(None),
    current_user: User = Depends(get_current_user),
):
    """Extract medication info from a bottle/label photo via the vision model,
    enriched from the local reference library when the drug is recognized."""
    image, _ = await _read_image(request, file)

    label = await _vision_read_med_label(image)
    name = (label or {}).get("medication_name", "").strip()

    if not name:
        return MedicationFromImageResponse(
            medication_name="Unknown Medication",
            dosage="See label",
            instructions="Could not read the medication label from this image. "
                         "Try a clearer, well-lit photo of the label, or enter details manually.",
            notes="Verify with your pharmacist.",
        )

    fields = []
    for key, med in MEDICATION_LIBRARY.items():
        if key in name.lower():
            fields = [
                {"label": "Drug Class", "value": med["class"]},
                {"label": "Typical Range", "value": med["typical_dosage"]},
            ]
            break
    if label.get("prescriber"):
        fields.append({"label": "Prescriber", "value": label["prescriber"]})

    return MedicationFromImageResponse(
        medication_name=name[:120],
        dosage=(label.get("strength") or "See label")[:120],
        instructions=(label.get("instructions") or "Follow the label directions.")[:500],
        fields=fields,
        notes="Read from the label by AI vision — verify with your pharmacist before acting on it.",
    )


@router.post("/verify-dosage", response_model=DosageVerificationResponse)
async def verify_dosage(
    request: DosageVerificationRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Verify if medication dosage is within typical range and check interactions via AI."""
    med_name = request.medication_name.lower().strip()

    # Extract numeric value from dosage string
    match = re.search(r"(\d+\.?\d*)", request.dosage)
    dosage_value = float(match.group(1)) if match else None

    # Lookup in local reference library
    med_info = None
    for key, info in MEDICATION_LIBRARY.items():
        if key in med_name or med_name in key:
            med_info = info
            break

    # Build base response from deterministic reference
    if med_info and dosage_value is not None:
        if dosage_value > med_info["max"]:
            is_typical = False
            base_feedback = (
                f"{med_info['name']} ({med_info['class']}): typical range is {med_info['typical_dosage']}. "
                f"Your dosage ({request.dosage}) exceeds the typical maximum ({med_info['max']}). "
                f"Consult your prescriber immediately."
            )
            base_precautions = ["Dosage above typical maximum — verify with healthcare provider urgently."]
        elif dosage_value < med_info["min"]:
            is_typical = True  # Could be a starting dose
            base_feedback = (
                f"{med_info['name']} ({med_info['class']}): typical range is {med_info['typical_dosage']}. "
                f"Your dosage ({request.dosage}) is below the typical minimum ({med_info['min']}), "
                f"which may be appropriate as a starting dose."
            )
            base_precautions = ["Dosage below typical minimum — may be a starting dose; verify with prescriber."]
        else:
            is_typical = True
            base_feedback = (
                f"{med_info['name']} ({med_info['class']}): typical range is {med_info['typical_dosage']}. "
                f"Your dosage ({request.dosage}) is within the typical range."
            )
            base_precautions = ["Always follow your prescriber's instructions."]
        typical_range = med_info["typical_dosage"]
    else:
        is_typical = True
        base_feedback = (
            f"'{request.medication_name}' not found in our reference database. "
            f"Consult your pharmacist for dosage verification."
        )
        base_precautions = [
            "Always follow your prescriber's instructions.",
            "Do not adjust dosage without medical advice.",
        ]
        typical_range = None

    # Query patient's other active medications for AI interaction analysis
    med_rows = (await db.execute(
        select(Medication)
        .where(Medication.user_id == current_user.id, Medication.is_active == True)  # noqa: E712
        .limit(20)
    )).scalars().all()

    other_meds = [
        f"{m.name} {m.dosage or ''} {m.dosage_unit or ''} {m.frequency or ''}".strip()
        for m in med_rows
        if m.name.lower() != med_name
    ]

    ai_notes: str | None = None
    if other_meds:
        other_meds_str = "; ".join(other_meds[:15])
        prompt = (
            f"You are a clinical pharmacist. A patient is taking:\n\n"
            f"NEW MEDICATION: {request.medication_name} {request.dosage}\n"
            f"CURRENT MEDICATIONS: {other_meds_str}\n"
            f"PATIENT: {current_user.full_name or 'Patient'}\n\n"
            f"In 2-3 concise sentences, identify any clinically significant drug-drug interactions "
            f"or warnings between the new medication and the current medications. "
            f"If no significant interactions exist, say so briefly. "
            f"Do not give general drug information — focus only on interactions with the listed medications."
        )
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{settings.OLLAMA_BASE_URL}/api/generate",
                    json={"model": settings.OLLAMA_MODEL, "prompt": prompt, "stream": False},
                    headers=await ollama_auth_headers(),
                )
                resp.raise_for_status()
                ai_notes = (resp.json().get("response") or "").strip() or None
        except Exception:
            ai_notes = None

    if ai_notes:
        base_precautions.append(f"AI interaction check: {ai_notes}")

    return DosageVerificationResponse(
        medication_name=med_info["name"] if med_info else request.medication_name,
        dosage=request.dosage,
        is_typical=is_typical,
        feedback=base_feedback,
        typical_range=typical_range,
        precautions=base_precautions,
    )


# ── Elimination photo analysis ───────────────────────────────

_ELIM_PROMPTS = {
    "bowel": (
        "This is a photo of a stool sample for medical tracking. Describe its "
        "consistency (hard lumps, formed, soft, mushy, or liquid), its color, "
        "and whether any blood or mucus is visible."
    ),
    "urination": (
        "This is a photo of a urine sample for medical tracking. Describe its "
        "color (pale yellow, yellow, dark yellow, amber, brown, pink, or red) "
        "and clarity (clear, cloudy, or foamy)."
    ),
    "vomiting": (
        "This is a photo of vomit for medical tracking. Describe its color and "
        "contents, and whether any blood is visible."
    ),
}

# keyword → (bristol_scale, consistency) for stool descriptions
_BRISTOL_KEYWORDS = [
    (("hard lump", "pellet", "hard lumps"), 1, "hard"),
    (("lumpy", "hard",), 2, "hard"),
    (("cracked", "sausage", "formed"), 4, "normal"),
    (("soft blob", "soft",), 5, "soft"),
    (("mushy", "fluffy"), 6, "soft"),
    (("liquid", "watery", "runny"), 7, "watery"),
]

_COLOR_WORDS = ("brown", "black", "red", "green", "yellow", "pale", "amber",
                "pink", "orange", "clear", "dark", "tan", "grey", "gray", "white")


def _extract_elimination(event_type: str, text: str) -> tuple[dict, list[str]]:
    """Keyword-extract structured elimination fields + attention flags from a caption."""
    low = text.lower()
    suggested: dict = {}
    flags: list[str] = []

    color = next((c for c in _COLOR_WORDS if c in low), None)
    if color:
        suggested["color"] = color

    if event_type == "bowel":
        for words, scale, consistency in _BRISTOL_KEYWORDS:
            if any(w in low for w in words):
                suggested["bristol_scale"] = scale
                suggested["consistency"] = consistency
                break
        if "blood" in low and "no blood" not in low and "no visible blood" not in low:
            suggested["blood_present"] = True
            flags.append("Possible blood visible — worth mentioning to your care team.")
        if "mucus" in low and "no mucus" not in low:
            suggested["mucus_present"] = True
        if color in ("black", "red"):
            flags.append(f"{color.capitalize()} stool can indicate bleeding — "
                         "contact your care team if unexpected.")
    elif event_type == "urination":
        if color in ("red", "pink", "brown"):
            flags.append(f"{color.capitalize()} urine can indicate blood — "
                         "contact your care team if unexpected.")
        if "cloudy" in low:
            flags.append("Cloudy urine can accompany infection — monitor for fever or pain.")
    elif event_type == "vomiting":
        if "blood" in low and "no blood" not in low:
            flags.append("Possible blood in vomit — seek medical attention.")
        if "coffee ground" in low or ("dark" in low and "brown" in low):
            flags.append("Dark, coffee-ground appearance can indicate bleeding — seek medical attention.")

    return suggested, flags


@router.post("/elimination-from-image")
async def elimination_from_image(
    request: Request,
    file: UploadFile | None = File(None),
    current_user: User = Depends(get_current_user),
):
    """Analyze an elimination photo (stool / urine / vomit) and suggest log fields.

    `event_type` rides in the JSON body next to `image_base64` (or as a query
    param for multipart). Returns a description, suggested form fields
    (Bristol scale, color, consistency, blood/mucus) and attention flags.
    NOT a diagnosis.
    """
    event_type = (request.query_params.get("event_type") or "").strip().lower()
    if file is None:
        try:
            body = await request.json()
            if isinstance(body, dict):
                event_type = (body.get("event_type") or event_type or "").strip().lower()
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass
    if event_type not in _ELIM_PROMPTS:
        event_type = "bowel"

    image, _ = await _read_image(request, file)
    description = await _vision_ask(image, _ELIM_PROMPTS[event_type])
    if not description:
        raise HTTPException(
            status_code=503,
            detail="The image-analysis model is unavailable right now — try again shortly.",
        )

    suggested, flags = _extract_elimination(event_type, description)
    return {
        "event_type": event_type,
        "description": description,
        "suggested": suggested,
        "flags": flags,
        "disclaimer": "AI visual estimate — not a medical diagnosis. "
                      "Contact your care team about anything concerning.",
    }


# ── Symptom photo analysis ───────────────────────────────────

_SYMPTOM_PROMPT = (
    "This is a photo of a visible medical symptom for health tracking. Describe "
    "what the symptom looks like (for example a rash, swelling, bruise, wound, "
    "redness, hives, blister, or bite) and where on the body it appears."
)

_SYMPTOM_NAMES = (
    "rash", "swelling", "bruise", "bruising", "wound", "redness", "hives",
    "lesion", "blister", "cut", "burn", "bite", "bump", "lump", "discoloration",
    "peeling", "dryness", "acne", "ulcer", "inflammation",
)
_BODY_PARTS = (
    "face", "forehead", "cheek", "eye", "ear", "nose", "lip", "mouth", "neck",
    "shoulder", "chest", "back", "abdomen", "stomach", "arm", "forearm", "elbow",
    "wrist", "hand", "finger", "hip", "thigh", "leg", "knee", "shin", "calf",
    "ankle", "foot", "toe", "scalp", "skin",
)


@router.post("/symptom-from-image")
async def symptom_from_image(
    request: Request,
    file: UploadFile | None = File(None),
    current_user: User = Depends(get_current_user),
):
    """Describe a visible symptom photo and suggest symptom-log fields.

    Returns a description plus suggested symptom_name / body_part to prefill
    the Symptoms form. NOT a diagnosis.
    """
    image, _ = await _read_image(request, file)
    description = await _vision_ask(image, _SYMPTOM_PROMPT)
    if not description:
        raise HTTPException(
            status_code=503,
            detail="The image-analysis model is unavailable right now — try again shortly.",
        )

    low = description.lower()
    name = next((s for s in _SYMPTOM_NAMES if s in low), None)
    body_part = next((b for b in _BODY_PARTS if b in low), None)

    return {
        "description": description,
        "suggested": {
            "symptom_name": (name or "skin change").capitalize(),
            "body_part": body_part,
            "symptom_type": "skin" if name in ("rash", "hives", "blister", "peeling",
                                               "dryness", "acne", "discoloration") else None,
        },
        "disclaimer": "AI visual description — not a medical diagnosis. "
                      "See a clinician for anything concerning or worsening.",
    }
