"""Backfill nutrient approximations for existing nutrition logs.

Usage:
  cd WEB/backend
  ../../.venv/bin/python scripts/backfill_nutrition_approximations.py

Optional flags:
  --limit 200        Process only first N candidate logs
  --dry-run          Compute approximations but do not persist
  --user-id 123      Restrict processing to one user
  --recent-days 30   Restrict processing to logs created in the last N days
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta

from sqlalchemy import or_, select

from app.core.database import async_session
from app.core.nutrition_data import DB_COLUMN_KEYS
from app.models.nutrition import NutritionLog
from app.services.nutrient_estimator import _try_ai, _try_usda


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill nutrient approximations")
    parser.add_argument("--limit", type=int, default=0, help="Max number of logs to process")
    parser.add_argument("--dry-run", action="store_true", help="Do not save updates")
    parser.add_argument("--user-id", type=int, default=0, help="Restrict to one user_id")
    parser.add_argument(
        "--recent-days",
        type=int,
        default=0,
        help="Restrict to logs created in the last N days",
    )
    return parser.parse_args()


async def main() -> None:
    args = _parse_args()

    updated = 0
    unchanged = 0
    no_estimate = 0
    errors = 0
    source_counts: Counter[str] = Counter()
    samples: list[dict] = []

    # Candidate logs: at least one core macro missing.
    missing_macro = or_(
        NutritionLog.calories.is_(None),
        NutritionLog.protein_g.is_(None),
        NutritionLog.carbs_g.is_(None),
        NutritionLog.fat_g.is_(None),
    )

    async with async_session() as db:
        query = select(NutritionLog).where(
            NutritionLog.food_name.is_not(None),
            missing_macro,
        )

        if args.user_id:
            query = query.where(NutritionLog.user_id == args.user_id)

        if args.recent_days and args.recent_days > 0:
            since_dt = datetime.utcnow() - timedelta(days=args.recent_days)
            query = query.where(NutritionLog.created_at >= since_dt)
            query = query.order_by(NutritionLog.created_at.desc())
        else:
            query = query.order_by(NutritionLog.created_at.asc())

        if args.limit and args.limit > 0:
            query = query.limit(args.limit)

        result = await db.execute(query)
        logs = result.scalars().all()

        print(f"Candidates: {len(logs)}")
        if args.recent_days and args.recent_days > 0:
            print(f"Window: last {args.recent_days} days")
        if args.dry_run:
            print("Mode: DRY RUN (no DB writes)")

        for idx, log in enumerate(logs, start=1):
            try:
                # Use USDA -> AI approximation directly for backfill.
                # This avoids cache-table write failures on very long serving-size strings.
                est = await _try_usda(log.food_name)
                if not est:
                    est = await _try_ai(log.food_name, log.serving_size)
                if not est:
                    est = {
                        "source": None,
                        "fdc_id": None,
                        "ai_model": None,
                        "food_name": log.food_name,
                        "serving_size": log.serving_size,
                        "serving_weight_g": None,
                        "confidence": 0.0,
                        "nutrients": {},
                        "cached": False,
                    }
            except Exception as exc:
                await db.rollback()
                errors += 1
                print(f"[{idx}/{len(logs)}] ERROR log_id={log.id}: {exc}")
                continue

            nutrients = est.get("nutrients") or {}
            source = est.get("source") or "none"
            source_counts[source] += 1

            if not nutrients:
                no_estimate += 1
                print(f"[{idx}/{len(logs)}] NO_ESTIMATE log_id={log.id} food='{log.food_name}'")
                continue

            changed = False

            # Fill only missing model columns.
            for key in DB_COLUMN_KEYS:
                if getattr(log, key, None) is None and key in nutrients:
                    setattr(log, key, nutrients[key])
                    changed = True

            # Fill extended nutrients if available.
            extended = log.extended_nutrients or {}
            for key, value in nutrients.items():
                if key not in DB_COLUMN_KEYS and key not in extended:
                    extended[key] = value
                    changed = True
            if extended:
                log.extended_nutrients = extended

            # Persist matched USDA id when available.
            if est.get("fdc_id") and log.fdc_id is None:
                log.fdc_id = est["fdc_id"]
                changed = True

            if changed:
                updated += 1
                if len(samples) < 12:
                    samples.append(
                        {
                            "id": log.id,
                            "food": log.food_name,
                            "source": source,
                            "cached": bool(est.get("cached")),
                            "calories": log.calories,
                            "protein_g": log.protein_g,
                        }
                    )
                print(
                    f"[{idx}/{len(logs)}] UPDATED log_id={log.id} source={source} cached={bool(est.get('cached'))}"
                )
            else:
                unchanged += 1
                print(f"[{idx}/{len(logs)}] UNCHANGED log_id={log.id} source={source}")

            if not args.dry_run and idx % 25 == 0:
                await db.commit()

        if not args.dry_run:
            await db.commit()
        else:
            await db.rollback()

    print("\n=== Backfill Summary ===")
    print(f"Updated logs:   {updated}")
    print(f"Unchanged logs: {unchanged}")
    print(f"No estimate:    {no_estimate}")
    print(f"Errors:         {errors}")
    print("Source counts:")
    for src, count in sorted(source_counts.items(), key=lambda kv: kv[0]):
        print(f"  - {src}: {count}")

    if samples:
        print("\nSample updated rows:")
        for s in samples:
            print(
                f"  id={s['id']} | {s['food']} | src={s['source']} | "
                f"cached={s['cached']} | kcal={s['calories']} | protein={s['protein_g']}"
            )


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
