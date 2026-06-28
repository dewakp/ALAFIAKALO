"""Re-estimate existing nutrition logs + resolve medication dose-log nutrients.

Why: the food nutrient estimator was fixed (head-noun matching, raw-form
preference, USDA POST, curated water/coffee/egg, " and "/newline meal splitting,
food-aware portion weights). Existing rows still hold the old (often grossly
wrong) values, and medication dose logs were never nutrient-resolved.

This script:
  • Meals  — re-runs estimate_meal_nutrients(food_name) for every NutritionLog and
             overwrites the nutrient columns + extended_nutrients (food_name,
             serving_size, timing, weights, identity are preserved).
  • Meds   — runs lookup_med_nutrients(name, dose, unit) for every
             MedicationDoseLog and sets nutrients_contributed / nutrients_resolved.

Dry-run by default (computes + reports impact, writes nothing). Pass --apply to
persist. Commits in batches; one bad row never aborts the run.

    docker compose exec backend python -m scripts.reestimate_logs           # dry run
    docker compose exec backend python -m scripts.reestimate_logs --apply
    docker compose exec backend python -m scripts.reestimate_logs --apply --meals-only
    docker compose exec backend python -m scripts.reestimate_logs --apply --meds-only
"""
import asyncio
import sys

from sqlalchemy import select

from app.core.database import async_session
from app.core.nutrition_data import DB_COLUMN_KEYS
from app.models.nutrition import NutritionLog
from app.models.med_nutrient import MedicationDoseLog
from app.services.nutrient_estimator import estimate_meal_nutrients
from app.services.med_nutrient_service import lookup_med_nutrients

_BATCH = 50


async def reestimate_meals(apply: bool) -> None:
    print("\n=== MEALS — re-estimating nutrition_logs ===")
    async with async_session() as db:
        ids = (await db.execute(select(NutritionLog.id).order_by(NutritionLog.id))).scalars().all()
    print(f"{len(ids)} nutrition logs to process")

    changed = errors = skipped = 0
    big_drops: list[tuple] = []
    for i, log_id in enumerate(ids, 1):
        # Whole body guarded: a slow AI fallback (timeout) or a commit error on one
        # row must never stall or abort the run.
        try:
            async with async_session() as db:
                log = await db.get(NutritionLog, log_id)
                if log is None or not (log.food_name or "").strip():
                    continue
                old_cal = log.calories
                result = await asyncio.wait_for(
                    estimate_meal_nutrients(db, log.food_name), timeout=90)
                agg = result.get("aggregate_nutrients") or {}
                if not agg:
                    skipped += 1
                    continue
                new_cal = agg.get("calories")
                # Overwrite nutrient columns (absent → None, clearing stale data).
                for key in DB_COLUMN_KEYS:
                    setattr(log, key, agg.get(key))
                extended = {k: v for k, v in agg.items() if k not in DB_COLUMN_KEYS}
                log.extended_nutrients = extended or None
                if old_cal and new_cal is not None and old_cal - new_cal >= 200:
                    big_drops.append((log_id, old_cal, new_cal, (log.food_name or "")[:45]))
                changed += 1
                if apply:
                    await db.commit()
        except (Exception, asyncio.TimeoutError) as exc:  # noqa: BLE001
            errors += 1
            print(f"  ! log {log_id}: {type(exc).__name__}: {str(exc)[:80]}", flush=True)
            continue
        if i % _BATCH == 0:
            print(f"  …{i}/{len(ids)} processed (updated={changed} err={errors})", flush=True)

    print(f"meals: updated={changed} skipped={skipped} errors={errors} "
          f"({'APPLIED' if apply else 'dry-run'})", flush=True)
    if big_drops:
        print("  largest corrections (old → new kcal):")
        for lid, old, new, name in sorted(big_drops, key=lambda x: x[1] - x[2], reverse=True)[:12]:
            print(f"    #{lid}: {old:.0f} → {new:.0f}   {name!r}")


async def resolve_meds(apply: bool) -> None:
    print("\n=== MEDS — resolving medication_dose_logs ===")
    async with async_session() as db:
        ids = (await db.execute(select(MedicationDoseLog.id).order_by(MedicationDoseLog.id))).scalars().all()
    print(f"{len(ids)} dose logs to process")

    resolved = contributed = errors = 0
    for i, dose_id in enumerate(ids, 1):
        async with async_session() as db:
            dose = await db.get(MedicationDoseLog, dose_id)
            if dose is None:
                continue
            try:
                res = await lookup_med_nutrients(
                    db, dose.medication_name, dose.dose_amount, dose.dose_unit)
            except Exception as exc:  # noqa: BLE001
                errors += 1
                print(f"  ! dose {dose_id} ({dose.medication_name}): {type(exc).__name__}: {str(exc)[:70]}")
                continue
            nutrients = res.get("nutrients") or {}
            dose.med_profile_id = res.get("profile_id")
            dose.nutrients_contributed = nutrients or None
            dose.nutrients_resolved = bool(nutrients)
            resolved += 1
            if nutrients:
                contributed += 1
            if apply:
                await db.commit()
        if i % _BATCH == 0:
            print(f"  …{i}/{len(ids)} processed")

    print(f"meds: processed={resolved} with-contribution={contributed} errors={errors} "
          f"({'APPLIED' if apply else 'dry-run'})")


async def main() -> None:
    apply = "--apply" in sys.argv
    meals_only = "--meals-only" in sys.argv
    meds_only = "--meds-only" in sys.argv
    print(f"reestimate_logs — {'APPLY (writing)' if apply else 'DRY RUN (no writes)'}")
    if not meds_only:
        await reestimate_meals(apply)
    if not meals_only:
        await resolve_meds(apply)
    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
