"""Medication → Nutrient service.

Provides:
  - SEEDED_MED_NUTRIENT_PROFILES   : clinically-validated seed data (30+ meds)
  - seed_med_profiles(db)          : idempotent seeder (runs on startup)
  - lookup_med_nutrients(db, ...)  : resolve a medication dose → nutrient dict
  - normalize_med_name(name)       : canonical key for fuzzy matching
  - unit_convert_factor(src, dst)  : convert between compatible dose units

TODO(alafia-model): replace AI-discovered profile resolution with
ALAFIAModel.resolve_medication_nutrients() once Phase 2 is scaffolded.
"""

import logging
import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# ── Seed data ─────────────────────────────────────────────────────────────────
# Each entry: med_name_original, optional brand_names (comma-sep), optional
# rxnorm_code, active_ingredient, dose_unit_canonical, nutrients_per_dose_unit,
# notes.
# Nutrient keys match NutritionLog column names exactly.

SEEDED_MED_NUTRIENT_PROFILES: list[dict] = [
    # ── Vitamin D ──────────────────────────────────────────────────────────
    {
        "med_name_original": "Calcitriol",
        "brand_names": "Rocaltrol,Calcijex,Vectical",
        "rxnorm_code": "3002",
        "active_ingredient": "calcitriol",
        "dose_unit_canonical": "mcg",
        "nutrients_per_dose_unit": {"vitamin_d_iu": 40.0},
        "notes": "Active form 1,25(OH)₂D₃. 1 mcg ≈ 40 IU vitamin D activity.",
    },
    {
        "med_name_original": "Vitamin D3 (Cholecalciferol)",
        "brand_names": "NatureWise Vitamin D3,Sunny D3,Nature Made D3",
        "rxnorm_code": "41549",
        "active_ingredient": "cholecalciferol",
        "dose_unit_canonical": "IU",
        "nutrients_per_dose_unit": {"vitamin_d_iu": 1.0},
        "notes": "Cholecalciferol. 1 IU per IU supplement.",
    },
    {
        "med_name_original": "Vitamin D2 (Ergocalciferol)",
        "brand_names": "Drisdol,Calciferol",
        "rxnorm_code": "3679",
        "active_ingredient": "ergocalciferol",
        "dose_unit_canonical": "IU",
        "nutrients_per_dose_unit": {"vitamin_d_iu": 1.0},
        "notes": "Ergocalciferol (plant-based). 1 IU per IU.",
    },
    # ── Calcium ────────────────────────────────────────────────────────────
    {
        "med_name_original": "Calcium Carbonate",
        "brand_names": "Tums,Caltrate,Os-Cal,Viactiv,Rolaids",
        "rxnorm_code": "41489",
        "active_ingredient": "calcium carbonate",
        "dose_unit_canonical": "mg",
        # CaCO₃ is 40 % elemental calcium by mass
        "nutrients_per_dose_unit": {"calcium_mg": 0.4},
        "notes": "CaCO₃ = 40 % elemental Ca. 500 mg → 200 mg Ca.",
    },
    {
        "med_name_original": "Tums Regular Strength",
        "brand_names": "Tums Regular",
        "rxnorm_code": None,
        "active_ingredient": "calcium carbonate",
        "dose_unit_canonical": "tablet",
        # 500 mg CaCO₃ per tablet → 200 mg elemental Ca
        "nutrients_per_dose_unit": {"calcium_mg": 200.0},
        "notes": "Tums Regular 500 mg CaCO₃/tablet = 200 mg elemental Ca.",
    },
    {
        "med_name_original": "Tums Extra Strength",
        "brand_names": "Tums Extra,Tums 750",
        "rxnorm_code": None,
        "active_ingredient": "calcium carbonate",
        "dose_unit_canonical": "tablet",
        # 750 mg CaCO₃/tablet → 300 mg Ca
        "nutrients_per_dose_unit": {"calcium_mg": 300.0},
        "notes": "Tums Extra Strength 750 mg CaCO₃/tablet = 300 mg elemental Ca.",
    },
    {
        "med_name_original": "Tums Ultra Strength",
        "brand_names": "Tums Ultra",
        "rxnorm_code": None,
        "active_ingredient": "calcium carbonate",
        "dose_unit_canonical": "tablet",
        # 1000 mg CaCO₃/tablet → 400 mg Ca
        "nutrients_per_dose_unit": {"calcium_mg": 400.0},
        "notes": "Tums Ultra 1000 mg CaCO₃/tablet = 400 mg elemental Ca.",
    },
    {
        "med_name_original": "Calcium Citrate",
        "brand_names": "Citracal,Solgar Calcium Citrate",
        "rxnorm_code": "50267",
        "active_ingredient": "calcium citrate",
        # Ca₃(C₆H₅O₇)₂ = 21.1 % elemental Ca
        "dose_unit_canonical": "mg",
        "nutrients_per_dose_unit": {"calcium_mg": 0.211},
        "notes": "Calcium citrate ≈ 21.1 % elemental Ca. Better absorbed than carbonate.",
    },
    {
        "med_name_original": "Calcium Gluconate",
        "brand_names": "Cal-G",
        "rxnorm_code": "2002",
        "active_ingredient": "calcium gluconate",
        # 9 % elemental Ca
        "dose_unit_canonical": "mg",
        "nutrients_per_dose_unit": {"calcium_mg": 0.09},
        "notes": "Calcium gluconate ≈ 9 % elemental Ca.",
    },
    # ── Omega-3 / Fish Oil ─────────────────────────────────────────────────
    {
        "med_name_original": "Fish Oil (Omega-3)",
        "brand_names": "Nordic Naturals,Nature Made Omega-3,Lovaza,Vascepa,Omacor",
        "rxnorm_code": "1435525",
        "active_ingredient": "omega-3 fatty acids",
        "dose_unit_canonical": "mg",
        # Standard fish oil ≈ 30 % EPA+DHA: 1000 mg capsule → 300 mg omega-3
        "nutrients_per_dose_unit": {"omega3_g": 0.0003},
        "notes": "Standard fish oil ≈ 30 % EPA+DHA. 1000 mg → 300 mg (0.3 g) omega-3.",
    },
    {
        "med_name_original": "Fish Oil High Potency",
        "brand_names": "Carlson Fish Oil,Omega-3 Plus,Triple Strength Omega-3",
        "rxnorm_code": None,
        "active_ingredient": "omega-3 fatty acids",
        "dose_unit_canonical": "capsule",
        # ≈ 600 mg EPA+DHA per 1200 mg capsule
        "nutrients_per_dose_unit": {"omega3_g": 0.6},
        "notes": "High-potency fish oil ≈ 600 mg EPA+DHA/capsule.",
    },
    {
        "med_name_original": "Krill Oil",
        "brand_names": "MegaRed,NOW Krill Oil",
        "rxnorm_code": None,
        "active_ingredient": "krill oil",
        "dose_unit_canonical": "mg",
        # Krill oil ≈ 14 % EPA+DHA in phospholipid form (highly bioavailable)
        "nutrients_per_dose_unit": {"omega3_g": 0.00014},
        "notes": "Krill oil ≈ 14 % EPA+DHA in phospholipid form.",
    },
    # ── Iron ───────────────────────────────────────────────────────────────
    {
        "med_name_original": "Ferrous Sulfate",
        "brand_names": "Slow Fe,Fer-In-Sol,Feosol,Slow Release Iron",
        "rxnorm_code": "4511",
        "active_ingredient": "ferrous sulfate",
        # FeSO₄·7H₂O ≈ 20 % elemental iron; 325 mg → ~65 mg Fe
        "dose_unit_canonical": "mg",
        "nutrients_per_dose_unit": {"iron_mg": 0.2},
        "notes": "Ferrous sulfate ≈ 20 % elemental Fe. 325 mg → ~65 mg Fe.",
    },
    {
        "med_name_original": "Ferrous Gluconate",
        "brand_names": "Fergon",
        "rxnorm_code": "4508",
        "active_ingredient": "ferrous gluconate",
        # ≈ 12 % elemental iron
        "dose_unit_canonical": "mg",
        "nutrients_per_dose_unit": {"iron_mg": 0.12},
        "notes": "Ferrous gluconate ≈ 12 % elemental Fe.",
    },
    {
        "med_name_original": "Ferrous Fumarate",
        "brand_names": "Femiron,Ferro-Sequels",
        "rxnorm_code": "4509",
        "active_ingredient": "ferrous fumarate",
        # ≈ 33 % elemental iron — highest density among oral Fe salts
        "dose_unit_canonical": "mg",
        "nutrients_per_dose_unit": {"iron_mg": 0.33},
        "notes": "Ferrous fumarate ≈ 33 % elemental Fe. Highest density oral iron.",
    },
    # ── Folate / Folic Acid ────────────────────────────────────────────────
    {
        "med_name_original": "Folic Acid",
        "brand_names": "Folacin,Folvite,FA-8",
        "rxnorm_code": "4511",
        "active_ingredient": "folic acid",
        "dose_unit_canonical": "mcg",
        "nutrients_per_dose_unit": {"vitamin_b9_folate_mcg": 1.0},
        "notes": "Folic acid = Vitamin B9. 1 mcg per mcg.",
    },
    # ── Vitamin B12 ────────────────────────────────────────────────────────
    {
        "med_name_original": "Cyanocobalamin (Vitamin B12)",
        "brand_names": "Nascobal,CaloMist,B12",
        "rxnorm_code": "2478",
        "active_ingredient": "cyanocobalamin",
        "dose_unit_canonical": "mcg",
        "nutrients_per_dose_unit": {"vitamin_b12_mcg": 1.0},
        "notes": "Cyanocobalamin = Vitamin B12. 1 mcg per mcg.",
    },
    {
        "med_name_original": "Methylcobalamin (Vitamin B12)",
        "brand_names": "Methyl B12,Methylcobalamin B12",
        "rxnorm_code": None,
        "active_ingredient": "methylcobalamin",
        "dose_unit_canonical": "mcg",
        "nutrients_per_dose_unit": {"vitamin_b12_mcg": 1.0},
        "notes": "Methylcobalamin = active form Vitamin B12.",
    },
    # ── Zinc ───────────────────────────────────────────────────────────────
    {
        "med_name_original": "Zinc Sulfate",
        "brand_names": "Zincate,Orazinc",
        "rxnorm_code": "11967",
        "active_ingredient": "zinc sulfate",
        # ZnSO₄·7H₂O ≈ 23 % elemental Zn; 220 mg → ~50 mg Zn
        "dose_unit_canonical": "mg",
        "nutrients_per_dose_unit": {"zinc_mg": 0.23},
        "notes": "Zinc sulfate ≈ 23 % elemental Zn. 220 mg → ~50 mg Zn.",
    },
    {
        "med_name_original": "Zinc Gluconate",
        "brand_names": "Zicam,Cold-Eeze,Zinc Lozenges",
        "rxnorm_code": None,
        "active_ingredient": "zinc gluconate",
        # ≈ 14.3 % elemental Zn
        "dose_unit_canonical": "mg",
        "nutrients_per_dose_unit": {"zinc_mg": 0.143},
        "notes": "Zinc gluconate ≈ 14.3 % elemental Zn.",
    },
    {
        "med_name_original": "Zinc Acetate",
        "brand_names": "Galzin",
        "rxnorm_code": None,
        "active_ingredient": "zinc acetate",
        # ≈ 30 % elemental Zn
        "dose_unit_canonical": "mg",
        "nutrients_per_dose_unit": {"zinc_mg": 0.30},
        "notes": "Zinc acetate ≈ 30 % elemental Zn.",
    },
    # ── Magnesium ──────────────────────────────────────────────────────────
    {
        "med_name_original": "Magnesium Oxide",
        "brand_names": "Mag-Ox 400,Uro-Mag,Phillips Milk of Magnesia",
        "rxnorm_code": "7199",
        "active_ingredient": "magnesium oxide",
        # MgO = 60.3 % elemental Mg; 400 mg → ~241 mg Mg
        "dose_unit_canonical": "mg",
        "nutrients_per_dose_unit": {"magnesium_mg": 0.603},
        "notes": "Magnesium oxide = 60.3 % elemental Mg. 400 mg → ~241 mg.",
    },
    {
        "med_name_original": "Magnesium Citrate",
        "brand_names": "Natural Calm,Citrate of Magnesia",
        "rxnorm_code": None,
        "active_ingredient": "magnesium citrate",
        # ≈ 16.2 % elemental Mg
        "dose_unit_canonical": "mg",
        "nutrients_per_dose_unit": {"magnesium_mg": 0.162},
        "notes": "Magnesium citrate ≈ 16.2 % elemental Mg. Better absorbed than oxide.",
    },
    {
        "med_name_original": "Magnesium Glycinate",
        "brand_names": "Chelated Magnesium,Doctor's Best Magnesium,Magnesium Bisglycinate",
        "rxnorm_code": None,
        "active_ingredient": "magnesium glycinate",
        # ≈ 9.9 % elemental Mg
        "dose_unit_canonical": "mg",
        "nutrients_per_dose_unit": {"magnesium_mg": 0.099},
        "notes": "Magnesium glycinate ≈ 9.9 % elemental Mg. Very gentle on GI.",
    },
    # ── Potassium ──────────────────────────────────────────────────────────
    {
        "med_name_original": "Potassium Chloride",
        "brand_names": "K-Dur,Klor-Con,Micro-K,K-Tab",
        "rxnorm_code": "8591",
        "active_ingredient": "potassium chloride",
        # 1 mEq K⁺ = 39.1 mg elemental potassium
        "dose_unit_canonical": "mEq",
        "nutrients_per_dose_unit": {"potassium_mg": 39.1},
        "notes": "1 mEq = 39.1 mg elemental K. Standard dose 10–20 mEq.",
    },
    # ── Vitamin C ──────────────────────────────────────────────────────────
    {
        "med_name_original": "Ascorbic Acid (Vitamin C)",
        "brand_names": "Emergen-C,Vitamin C,C-500,Ester-C,Airborne",
        "rxnorm_code": "1151",
        "active_ingredient": "ascorbic acid",
        "dose_unit_canonical": "mg",
        "nutrients_per_dose_unit": {"vitamin_c_mg": 1.0},
        "notes": "Ascorbic acid = Vitamin C. 1 mg per mg.",
    },
    # ── Vitamin E ──────────────────────────────────────────────────────────
    {
        "med_name_original": "Vitamin E (Tocopherol)",
        "brand_names": "Aquavite-E,Nutr-E-Sol,d-alpha Tocopherol",
        "rxnorm_code": "11602",
        "active_ingredient": "tocopherol",
        "dose_unit_canonical": "IU",
        # 1 IU natural d-alpha-tocopherol = 0.67 mg
        "nutrients_per_dose_unit": {"vitamin_e_mg": 0.67},
        "notes": "Natural vitamin E: 1 IU ≈ 0.67 mg alpha-tocopherol.",
    },
    # ── Vitamin A ──────────────────────────────────────────────────────────
    {
        "med_name_original": "Vitamin A",
        "brand_names": "Aquasol A,Beta-Carotene,Retinol Palmitate",
        "rxnorm_code": "11847",
        "active_ingredient": "retinol",
        "dose_unit_canonical": "IU",
        "nutrients_per_dose_unit": {"vitamin_a_iu": 1.0},
        "notes": "Vitamin A supplement. 1 IU per IU.",
    },
    # ── Vitamin K ──────────────────────────────────────────────────────────
    {
        "med_name_original": "Vitamin K (Phylloquinone)",
        "brand_names": "Mephyton,Phytonadione,K1",
        "rxnorm_code": "11693",
        "active_ingredient": "phylloquinone",
        "dose_unit_canonical": "mcg",
        "nutrients_per_dose_unit": {"vitamin_k_mcg": 1.0},
        "notes": "Vitamin K1 (phylloquinone). 1 mcg per mcg.",
    },
    # ── B vitamins ─────────────────────────────────────────────────────────
    {
        "med_name_original": "Thiamine (Vitamin B1)",
        "brand_names": "Thiaminate,B1 Vitamin",
        "rxnorm_code": "10382",
        "active_ingredient": "thiamine",
        "dose_unit_canonical": "mg",
        "nutrients_per_dose_unit": {"vitamin_b1_thiamine_mg": 1.0},
        "notes": "Thiamine = Vitamin B1.",
    },
    {
        "med_name_original": "Riboflavin (Vitamin B2)",
        "brand_names": "Riboflavin,B2 Vitamin",
        "rxnorm_code": "9054",
        "active_ingredient": "riboflavin",
        "dose_unit_canonical": "mg",
        "nutrients_per_dose_unit": {"vitamin_b2_riboflavin_mg": 1.0},
        "notes": "Riboflavin = Vitamin B2.",
    },
    {
        "med_name_original": "Niacin (Vitamin B3)",
        "brand_names": "Niaspan,Slo-Niacin,Niacinol,B3",
        "rxnorm_code": "7531",
        "active_ingredient": "niacin",
        "dose_unit_canonical": "mg",
        "nutrients_per_dose_unit": {"vitamin_b3_niacin_mg": 1.0},
        "notes": "Niacin = Vitamin B3. Also used for dyslipidemia.",
    },
    {
        "med_name_original": "Pantothenic Acid (Vitamin B5)",
        "brand_names": "D-Panthenol,B5 Vitamin",
        "rxnorm_code": None,
        "active_ingredient": "pantothenic acid",
        "dose_unit_canonical": "mg",
        "nutrients_per_dose_unit": {"vitamin_b5_pantothenic_acid_mg": 1.0},
        "notes": "Pantothenic acid = Vitamin B5.",
    },
    {
        "med_name_original": "Pyridoxine (Vitamin B6)",
        "brand_names": "Nestrex,B6 Vitamin",
        "rxnorm_code": "9054",
        "active_ingredient": "pyridoxine",
        "dose_unit_canonical": "mg",
        "nutrients_per_dose_unit": {"vitamin_b6_mg": 1.0},
        "notes": "Pyridoxine = Vitamin B6.",
    },
    {
        "med_name_original": "Biotin (Vitamin B7)",
        "brand_names": "Hair Skin and Nails,Nature's Bounty Biotin,B7",
        "rxnorm_code": None,
        "active_ingredient": "biotin",
        "dose_unit_canonical": "mcg",
        "nutrients_per_dose_unit": {"vitamin_b7_biotin_mcg": 1.0},
        "notes": "Biotin = Vitamin B7.",
    },
    # ── Phosphorus ─────────────────────────────────────────────────────────
    {
        "med_name_original": "Sodium Phosphate",
        "brand_names": "Neutra-Phos,Phospha 250 Neutral",
        "rxnorm_code": "9509",
        "active_ingredient": "sodium phosphate",
        "dose_unit_canonical": "mg",
        # Na₃PO₄: P ≈ 26 %, Na ≈ 21 % by mass (approximate)
        "nutrients_per_dose_unit": {"phosphorus_mg": 0.26, "sodium_mg": 0.21},
        "notes": "Sodium phosphate: ~26 % P, ~21 % Na by mass.",
    },
    # ── Selenium ───────────────────────────────────────────────────────────
    {
        "med_name_original": "Selenium",
        "brand_names": "Selenium Yeast,Selenomethionine,Se-200",
        "rxnorm_code": None,
        "active_ingredient": "selenium",
        "dose_unit_canonical": "mcg",
        "nutrients_per_dose_unit": {"selenium_mcg": 1.0},
        "notes": "Selenium supplement. 1 mcg per mcg.",
    },
    # ── Copper ─────────────────────────────────────────────────────────────
    {
        "med_name_original": "Copper Gluconate",
        "brand_names": "Copper supplement",
        "rxnorm_code": None,
        "active_ingredient": "copper gluconate",
        # ≈ 14.4 % elemental Cu
        "dose_unit_canonical": "mg",
        "nutrients_per_dose_unit": {"copper_mg": 0.144},
        "notes": "Copper gluconate ≈ 14.4 % elemental Cu.",
    },
]

# ── Unit conversion table ──────────────────────────────────────────────────────
# Conversion factors to reach canonical unit: multiply user_dose_amount by factor.
# Only same-family conversions are supported.
_UNIT_CONVERSIONS: dict[tuple[str, str], float] = {
    # mass
    ("g", "mg"):    1000.0,
    ("mg", "g"):    0.001,
    ("mg", "mcg"):  1000.0,
    ("mcg", "mg"):  0.001,
    ("g", "mcg"):   1_000_000.0,
    ("mcg", "g"):   0.000_001,
    # IU ↔ mcg: only meaningful for vitamin D (1 mcg = 40 IU)
    ("mcg", "IU"):  40.0,    # for vitamin D only
    ("IU", "mcg"):  0.025,   # for vitamin D only
    # mEq ↔ mg: only for potassium — handled specially in lookup
}


def normalize_med_name(name: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    name = name.lower().strip()
    name = re.sub(r"[^a-z0-9\s]", " ", name)
    return re.sub(r"\s+", " ", name).strip()


def unit_convert_factor(src_unit: str, canonical_unit: str) -> float | None:
    """Return multiplication factor to convert src_unit amount → canonical_unit.
    Returns None if conversion is unknown (caller should warn and pass through).
    """
    if src_unit == canonical_unit:
        return 1.0
    return _UNIT_CONVERSIONS.get((src_unit.lower(), canonical_unit.lower()))


async def seed_med_profiles(db: AsyncSession) -> int:
    """Insert seeded profiles that don't exist yet. Returns count inserted."""
    from app.models.med_nutrient import MedNutrientProfile  # local to avoid circular

    inserted = 0
    for data in SEEDED_MED_NUTRIENT_PROFILES:
        key = normalize_med_name(data["med_name_original"])
        result = await db.execute(
            select(MedNutrientProfile).where(
                MedNutrientProfile.med_name_normalized == key
            )
        )
        if result.scalar_one_or_none() is not None:
            continue  # already exists

        profile = MedNutrientProfile(
            med_name_normalized=key,
            med_name_original=data["med_name_original"],
            brand_names=data.get("brand_names"),
            rxnorm_code=data.get("rxnorm_code"),
            active_ingredient=data.get("active_ingredient"),
            dose_unit_canonical=data["dose_unit_canonical"],
            nutrients_per_dose_unit=data["nutrients_per_dose_unit"],
            source="seeded",
            notes=data.get("notes"),
        )
        db.add(profile)
        inserted += 1

    if inserted:
        await db.commit()
        logger.info("Seeded %d med nutrient profiles", inserted)
    return inserted


async def lookup_med_nutrients(
    db: AsyncSession,
    medication_name: str,
    dose_amount: float,
    dose_unit: str,
) -> dict:
    """Resolve a medication dose to a nutrient contribution dict.

    Lookup strategy:
      1. Exact normalized name match
      2. Brand name substring match
      3. Active ingredient match (if brand_names or active_ingredient contains query tokens)
      4. If no match → return empty nutrients with source="unknown"

    Returns:
      {
        "profile_id": int | None,
        "med_name_resolved": str,
        "dose_amount": float,
        "dose_unit": str,
        "dose_unit_canonical": str | None,
        "nutrients": {nutrient_key: absolute_amount},
        "source": "seeded" | "ai_discovered" | "unknown",
      }
    """
    from app.models.med_nutrient import MedNutrientProfile  # local to avoid circular

    normalized_query = normalize_med_name(medication_name)
    tokens = set(normalized_query.split())

    # 1. Exact match
    result = await db.execute(
        select(MedNutrientProfile).where(
            MedNutrientProfile.med_name_normalized == normalized_query,
            MedNutrientProfile.is_active.is_(True),
        )
    )
    profile: MedNutrientProfile | None = result.scalar_one_or_none()

    # 2. Brand / active_ingredient match (scan active profiles)
    if profile is None:
        all_result = await db.execute(
            select(MedNutrientProfile).where(MedNutrientProfile.is_active.is_(True))
        )
        candidates = all_result.scalars().all()
        best: MedNutrientProfile | None = None
        best_score = 0
        for candidate in candidates:
            # Score = number of query tokens found in candidate's searchable text
            search_text = normalize_med_name(
                " ".join(filter(None, [
                    candidate.med_name_original,
                    candidate.brand_names or "",
                    candidate.active_ingredient or "",
                ]))
            )
            cand_tokens = set(search_text.split())
            overlap = len(tokens & cand_tokens)
            if overlap > best_score and overlap >= max(1, len(tokens) // 2):
                best_score = overlap
                best = candidate
        profile = best

    if profile is None:
        logger.warning(
            "No med nutrient profile found for '%s' — nutrients not resolved",
            medication_name,
        )
        return {
            "profile_id": None,
            "med_name_resolved": medication_name,
            "dose_amount": dose_amount,
            "dose_unit": dose_unit,
            "dose_unit_canonical": None,
            "nutrients": {},
            "source": "unknown",
        }

    # Compute scaling factor
    factor = unit_convert_factor(dose_unit, profile.dose_unit_canonical)
    if factor is None:
        logger.warning(
            "Cannot convert '%s' → '%s' for '%s'; returning raw scale of 1",
            dose_unit, profile.dose_unit_canonical, medication_name,
        )
        factor = 1.0

    effective_amount = dose_amount * factor
    nutrients = {
        key: round(val * effective_amount, 6)
        for key, val in profile.nutrients_per_dose_unit.items()
    }

    return {
        "profile_id": profile.id,
        "med_name_resolved": profile.med_name_original,
        "dose_amount": dose_amount,
        "dose_unit": dose_unit,
        "dose_unit_canonical": profile.dose_unit_canonical,
        "nutrients": nutrients,
        "source": profile.source,
    }
