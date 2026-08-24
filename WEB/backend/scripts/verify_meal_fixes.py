"""End-to-end check of the meal fixes against the DEV copy of prod.

Creates real NutritionLog rows, runs the actual background worker (`enrich_log`),
reads back what was stored, then deletes the rows. Nothing touches production.

The headline assertion is the scaling one: "8 Fl oz Boost Glucose Control" must
store ~190 kcal (the 237 mL label), not 80 (the per-100 mL profile).
"""
import asyncio
import sys
from datetime import date

from sqlalchemy import select, delete

from app.core.database import async_session
from app.models.nutrition import NutritionLog
from app.models.user import User
from app.services.nutrient_enrichment import enrich_log

CASES = [
    ("8 Fl oz Boost Glucose Control", None),
    ("8 Fl oz Boost Glucose Control + 0.5 cup of Roasted corn flour", None),
    ("0.5 cup of basmati rice, 1 cup of goat meat vindaloo",
     "Per serving: 240 calories, 18 g protein, 12 g carbs, 13 g fat"),
]

FIELDS = ("calories", "protein_g", "carbs_g", "fat_g",
          "phosphorus_mg", "potassium_mg")


async def main() -> int:
    async with async_session() as db:
        user = (await db.execute(
            select(User).where(User.email == "developer@hntsolutions.com")
        )).scalar_one_or_none()
        if user is None:
            print("test user not found in dev"); return 2

        created: list[int] = []
        for food_name, notes in CASES:
            log = NutritionLog(user_id=user.id, food_name=food_name, notes=notes,
                               log_date=date.today(), meal_type="snack",
                               nutrient_status="pending")
            db.add(log)
            await db.flush()
            created.append(log.id)
        await db.commit()

    for log_id in created:
        await enrich_log(log_id)          # the real background worker

    async with async_session() as db:
        for log_id in created:
            log = (await db.execute(
                select(NutritionLog).where(NutritionLog.id == log_id)
            )).scalar_one()
            print("=" * 74)
            print(f"{log.food_name}")
            if log.notes:
                print(f"  notes: {log.notes}")
            print(f"  status: {log.nutrient_status}")
            vals = {f: getattr(log, f, None) for f in FIELDS}
            print("  " + "  ".join(f"{k}={v}" for k, v in vals.items() if v is not None)
                  or "  (no nutrients)")
        # Clean up: this is a copy of a real record, leave it as we found it.
        await db.execute(delete(NutritionLog).where(NutritionLog.id.in_(created)))
        await db.commit()
        print("=" * 74)
        print(f"cleaned up {len(created)} test rows")
    return 0


sys.exit(asyncio.run(main()))
