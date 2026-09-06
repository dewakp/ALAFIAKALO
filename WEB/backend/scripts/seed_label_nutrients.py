"""Teach the estimator a product from its printed LABEL.

A label is the authoritative statement of what is in a food. The estimator
already prefers a learned entry over USDA and AI (§3c, "look it up once,
remember it after"), so writing one here fixes every future log of that product
at once — and the cache is shared, so it fixes it for every patient.

WHY THIS WAS NEEDED. The cache had learned Boost Glucose Control from OCR'd
marketing prose and got it wrong in three ways at once:

    food_name_normalized  "boost glucose control contains"   ← never matches a
                                                                plain log
    protein_g             2.9591                             ← the FAT value,
                                                                copied over it
    potassium/phosphorus  absent entirely                    ← the two figures
                                                                a dialysis
                                                                patient is
                                                                managed on

On one record that product appears with FIFTEEN different nutrient profiles,
from 0 kcal to 558 kcal for the same 8 fl oz carton. A wrong learned entry is
worse than none: it is confident, shared, and silent.

Values are per 100 mL/g, because that is the basis the estimator scales from.
`--dry-run` prints what would be written.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.core.database import async_session  # noqa: E402
from app.models.learned_nutrient import LearnedFoodNutrient  # noqa: E402

# Nestlé BOOST Glucose Control, 8 fl oz carton = 237 mL.
# Only figures the label states in MASS are used. Percent-DV-only micronutrients
# are deliberately left out rather than back-computed: a %DV depends on which
# Daily Value edition is assumed, and a derived number that looks measured is
# how a wrong figure becomes authoritative. Phosphorus is the one exception —
# it is 25% DV with no mass printed, and it is the number a dialysis patient is
# managed on, so it is derived from the FDA DV of 1250 mg and marked as such.
# The estimator scales by GRAMS, not millilitres, so the label figures are
# divided by the serving's MASS. A 237 mL carton of a supplement drink weighs
# ~244.8 g (meal_parser uses 30.6 g/fl oz — these are ~1.03 g/mL, denser than
# water). Storing per-100 mL instead left every value 3.3% high, uniformly:
# 196.3 kcal against a printed 190, and 322.8 mg of phosphorus against 312.5 —
# a basis mismatch, not an estimate error, and invisible without the label.
_SERVING_ML = 237.0
_SERVING_G = 244.8
_LABEL_PER_SERVING = {
    "calories": 190.0,
    "protein_g": 16.0,
    "fat_g": 7.0,
    "saturated_fat_g": 1.0,
    "trans_fat_g": 0.0,
    "carbs_g": 16.0,
    "fiber_g": 3.0,
    "sugar_g": 4.0,
    "cholesterol_mg": 10.0,
    "sodium_mg": 200.0,
    "potassium_mg": 250.0,
    "calcium_mg": 350.0,
    "iron_mg": 4.5,
    "vitamin_d_iu": 480.0,          # 12 mcg × 40 IU/mcg
    "phosphorus_mg": 312.5,         # 25% of the 1250 mg FDA Daily Value
}

PRODUCTS = [
    {
        "name": "Boost Glucose Control",
        "serving_g": _SERVING_G,
        "per_serving": _LABEL_PER_SERVING,
        "aliases": ["boost glucose control", "8 fl oz boost glucose control"],
    },
]


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="write (default: dry run)")
    args = ap.parse_args()

    from app.services.nutrient_estimator import _normalize_food_name

    for product in PRODUCTS:
        per_100 = {k: round(v * 100.0 / product["serving_g"], 4)
                   for k, v in product["per_serving"].items()}
        print(f"\n{product['name']} — per 100 g "
              f"(label serving {product['serving_g']:.1f} g)")
        print("  " + json.dumps(per_100))

        async with async_session() as db:
            for alias in product["aliases"]:
                key = _normalize_food_name(alias)
                existing = (await db.execute(
                    select(LearnedFoodNutrient)
                    .where(LearnedFoodNutrient.food_name_normalized == key)
                )).scalar_one_or_none()
                verb = "update" if existing else "insert"
                print(f"  {verb}: {key!r}")
                if existing:
                    print(f"    was: {json.dumps(existing.nutrients)[:150]}")
                if not args.apply:
                    continue
                if existing:
                    existing.nutrients = per_100
                    existing.serving_weight_g = product["serving_g"]
                    existing.source = "label"
                    existing.confidence = 1.0
                else:
                    db.add(LearnedFoodNutrient(
                        food_name_normalized=key,
                        food_name_original=product["name"],
                        nutrients=per_100,
                        serving_weight_g=product["serving_g"],
                        source="label",
                        confidence=1.0,
                    ))
            if args.apply:
                await db.commit()

    print("\nwritten." if args.apply else "\nDRY RUN — re-run with --apply to write.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
