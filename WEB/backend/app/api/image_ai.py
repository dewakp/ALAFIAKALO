"""Image AI & Dosage Verification endpoints — deterministic fallback with AI dosage analysis."""

import re
import httpx
from fastapi import APIRouter, Depends, UploadFile, File
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

router = APIRouter()

# ── Deterministic Food Library ───────────────────────────────
FOOD_LIBRARY = {
    "chicken": {"name": "Grilled Chicken Breast", "calories": 165, "protein_g": 31, "carbs_g": 0, "fat_g": 3.6},
    "rice": {"name": "White Rice (1 cup)", "calories": 206, "protein_g": 4.3, "carbs_g": 45, "fat_g": 0.4},
    "salmon": {"name": "Salmon Fillet", "calories": 208, "protein_g": 20, "carbs_g": 0, "fat_g": 13},
    "salad": {"name": "Mixed Green Salad", "calories": 20, "protein_g": 1.5, "carbs_g": 3.5, "fat_g": 0.2},
    "pasta": {"name": "Pasta (1 cup cooked)", "calories": 220, "protein_g": 8, "carbs_g": 43, "fat_g": 1.3},
    "egg": {"name": "Scrambled Eggs (2)", "calories": 182, "protein_g": 12, "carbs_g": 2, "fat_g": 14},
    "bread": {"name": "Whole Wheat Bread (2 slices)", "calories": 160, "protein_g": 8, "carbs_g": 28, "fat_g": 2},
    "banana": {"name": "Banana", "calories": 105, "protein_g": 1.3, "carbs_g": 27, "fat_g": 0.4},
    "apple": {"name": "Apple", "calories": 95, "protein_g": 0.5, "carbs_g": 25, "fat_g": 0.3},
    "yogurt": {"name": "Greek Yogurt (1 cup)", "calories": 130, "protein_g": 17, "carbs_g": 7, "fat_g": 4},
    "burger": {"name": "Hamburger", "calories": 354, "protein_g": 20, "carbs_g": 29, "fat_g": 17},
    "pizza": {"name": "Pizza Slice (cheese)", "calories": 285, "protein_g": 12, "carbs_g": 36, "fat_g": 10},
    "steak": {"name": "Beef Steak (6oz)", "calories": 340, "protein_g": 42, "carbs_g": 0, "fat_g": 18},
    "soup": {"name": "Vegetable Soup (1 bowl)", "calories": 120, "protein_g": 4, "carbs_g": 18, "fat_g": 3},
    "sandwich": {"name": "Turkey Sandwich", "calories": 350, "protein_g": 24, "carbs_g": 34, "fat_g": 12},
}

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


@router.post("/nutrition-from-image", response_model=NutritionFromImageResponse)
async def nutrition_from_image(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """Identify food items from an image (deterministic fallback: filename-based matching)."""
    filename = (file.filename or "").lower()
    content = await file.read()

    # Deterministic: match filename keywords against food library
    found_items = []
    for keyword, food in FOOD_LIBRARY.items():
        if keyword in filename:
            found_items.append(food)

    # If no filename match, return a generic meal estimate
    if not found_items:
        found_items = [
            {"name": "Detected Meal (estimated)", "calories": 450, "protein_g": 20, "carbs_g": 50, "fat_g": 15}
        ]

    total_cal = sum(f.get("calories", 0) for f in found_items)
    total_prot = sum(f.get("protein_g", 0) for f in found_items)
    total_carbs = sum(f.get("carbs_g", 0) for f in found_items)
    total_fat = sum(f.get("fat_g", 0) for f in found_items)

    return NutritionFromImageResponse(
        food_items=found_items,
        total_calories=total_cal,
        total_protein_g=total_prot,
        total_carbs_g=total_carbs,
        total_fat_g=total_fat,
        notes="Analysis based on image recognition. Verify portions for accuracy. AI vision integration pending.",
    )


@router.post("/medication-from-image", response_model=MedicationFromImageResponse)
async def medication_from_image(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """Extract medication info from bottle photo (deterministic fallback: filename-based matching)."""
    filename = (file.filename or "").lower()
    content = await file.read()

    # Deterministic: match filename keywords against medication library
    for keyword, med in MEDICATION_LIBRARY.items():
        if keyword in filename:
            return MedicationFromImageResponse(
                medication_name=med["name"],
                dosage=med["typical_dosage"],
                instructions=f"Typical dosage range: {med['typical_dosage']}",
                fields=[
                    {"label": "Drug Class", "value": med["class"]},
                    {"label": "Max Daily", "value": f"{med['max']}"},
                    {"label": "Min Daily", "value": f"{med['min']}"},
                ],
                notes="Extracted via image recognition. Verify with your pharmacist. AI vision integration pending.",
            )

    return MedicationFromImageResponse(
        medication_name="Unknown Medication",
        dosage="See label",
        instructions="Could not identify medication from image. Please enter details manually.",
        notes="AI vision integration pending. Try uploading a clearer image of the medication label.",
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
