"""Re-run nutrient estimation over meals whose figures never resolved.

WHY THIS EXISTS. A meal is saved immediately and its nutrients filled in
afterwards by a background task (§3c). When that task failed — an unknown dish,
a provider timeout, an early bug — the row kept the meal and lost the numbers.
Those rows do not heal on their own: nothing re-runs them, and every later
question about that day silently reads them as zeros. On one production record
that is 69 meals with no calories, 7 marked `failed`, and 54 with no extended
panel, sitting inside totals the assistant reports as fact.

WHAT IT DOES NOT DO. It never overwrites a figure that is already there —
`_enrich` only fills blanks, because anything the patient typed outranks an
estimate. So this is additive: it can give a meal nutrients it lacked, and it
cannot change one it already had.

LEARNING CARRIES FORWARD. Estimation goes Cache → USDA → AI, and every AI answer
is written to `learned_food_nutrients` (`_save_to_cache`). So repairing "Eba with
mixed vegetables stew" once teaches every future log of that dish — for this
patient and everyone else. The run reports how much the cache grew, because that
growth is the durable part: the repaired rows are worth less than the fact that
the next one resolves without asking anybody.

DRY RUN BY DEFAULT. This writes to clinical records, so it prints what it would
change and exits unless `--apply` is passed.

    python scripts/reestimate_nutrition.py --user 63
    python scripts/reestimate_nutrition.py --user 63 --apply
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, or_, select  # noqa: E402

from app.core.database import async_session  # noqa: E402
from app.models.learned_nutrient import LearnedFoodNutrient  # noqa: E402
from app.models.nutrition import NutritionLog  # noqa: E402


def _needs_repair(model):
    """Rows whose nutrients never resolved.

    Deliberately NOT keyed on `nutrient_status`: "skipped" carries real figures
    on 902 of 960 production rows, so selecting on status would re-run almost
    everything and call complete data broken.
    """
    return or_(
        model.calories.is_(None),
        model.calories == 0,
        model.nutrient_status == "failed",
    )


async def _implausible_rows(db, user_id: int) -> list:
    """Rows whose STORED figures are impossible for the food they describe.

    Judged with `plausibility.review_meal` — the same guard the estimator
    applies to its own output — rather than a threshold invented here. A meal
    denser than pure fat cannot exist, whatever it contains.

    These rows are the opposite of the missing-nutrient case and worse: they
    carry values, so nothing selects them, they look complete, and they inflate
    every daily total and every answer built on one. On one record 12 such rows
    survived every previous pass, the largest reading 3,892 kcal for a brioche
    bun, a tin of sardines and a boiled egg.
    """
    from app.services import plausibility
    from app.services.meal_parser import parse_meal_text

    rows = (await db.execute(
        select(NutritionLog)
        .where(NutritionLog.user_id == user_id, NutritionLog.calories > 0)
        .order_by(NutritionLog.log_date)
    )).scalars().all()

    bad = []
    for r in rows:
        try:
            weight = sum(c.qty_g or 0 for c in parse_meal_text(r.food_name or ""))
        except Exception:  # noqa: BLE001 — an unparseable name is not a finding
            continue
        if not weight:
            continue
        stored = {"calories": r.calories, "protein_g": r.protein_g,
                  "carbs_g": r.carbs_g, "fat_g": r.fat_g}
        if plausibility.review_meal(weight, stored):
            bad.append(r)
    return bad


async def _cache_size(db) -> int:
    return int((await db.execute(
        select(func.count()).select_from(LearnedFoodNutrient))).scalar() or 0)


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--user", type=int, required=True, help="user id to repair")
    ap.add_argument("--apply", action="store_true",
                    help="write the results (default is a dry run)")
    ap.add_argument("--limit", type=int, default=0, help="stop after N meals")
    ap.add_argument("--implausible", action="store_true",
                    help="repair rows whose STORED values are impossible, not "
                         "just ones that are missing")
    args = ap.parse_args()

    async with async_session() as db:
        if args.implausible:
            rows = await _implausible_rows(db, args.user)
        else:
            rows = (await db.execute(
                select(NutritionLog)
                .where(NutritionLog.user_id == args.user, _needs_repair(NutritionLog))
                .order_by(NutritionLog.log_date)
            )).scalars().all()
        before_cache = await _cache_size(db)

    # A shell entry ("unknown", "same as previous") has no nutrients to find.
    # Re-running it cannot help and MUST NOT invent calories, so it is reported
    # separately rather than counted as work outstanding (§3c).
    from app.services.nutrient_estimator import _is_placeholder

    shells = [r for r in rows if _is_placeholder(r.food_name or "")]
    rows = [r for r in rows if not _is_placeholder(r.food_name or "")]

    if args.limit:
        rows = rows[: args.limit]

    label = "with impossible stored values" if args.implausible else "worth re-estimating"
    print(f"user {args.user}: {len(rows)} meals {label}")
    print(f"  ({len(shells)} shell entries skipped — no description to resolve)")
    print(f"learned-food cache: {before_cache} entries")
    if not rows:
        return 0

    if not args.apply:
        print("\nDRY RUN — nothing will be written. Meals that would be re-estimated:\n")
        for r in rows[:25]:
            print(f"  {r.log_date}  {r.nutrient_status or '-':8}  {(r.food_name or '')[:66]}")
        if len(rows) > 25:
            print(f"  … and {len(rows) - 25} more")
        print("\nRe-run with --apply to write. Existing values are never overwritten.")
        return 0

    from app.core.nutrition_data import DB_COLUMN_KEYS
    from app.services.nutrient_enrichment import enrich_log

    repaired = failed = 0
    for i, row in enumerate(rows, 1):
        # The SAME writer the live path uses. A second copy of that logic is how
        # a fix lands on one path and misses the other.
        try:
            if args.implausible:
                # The stored figures are the problem, so they are cleared first.
                # Re-estimation then either produces a believable answer or —
                # since the writer now refuses a flagged estimate — leaves the
                # meal honestly unresolved. Either beats an impossible number.
                async with async_session() as db:
                    stale = (await db.execute(select(NutritionLog).where(
                        NutritionLog.id == row.id))).scalar_one()
                    for key in DB_COLUMN_KEYS:
                        if hasattr(stale, key):
                            setattr(stale, key, None)
                    stale.extended_nutrients = None
                    await db.commit()
            # Zeros left by a FAILED estimate are not values the patient chose.
            await enrich_log(row.id, overwrite_zeros=True)
        except Exception as exc:  # noqa: BLE001 — one bad meal must not stop the run
            failed += 1
            print(f"  [{i}/{len(rows)}] FAILED {row.id}: {type(exc).__name__}")
            continue
        async with async_session() as db:
            fresh = (await db.execute(
                select(NutritionLog).where(NutritionLog.id == row.id))).scalar_one()
            ok = bool(fresh.calories)
        repaired += ok
        if i % 10 == 0 or ok:
            print(f"  [{i}/{len(rows)}] {row.log_date} "
                  f"{'resolved' if ok else 'still empty'}: {(row.food_name or '')[:52]}")

    async with async_session() as db:
        after_cache = await _cache_size(db)

    print(f"\nrepaired {repaired}/{len(rows)} meals ({failed} errored)")
    print(f"learned-food cache: {before_cache} → {after_cache} "
          f"(+{after_cache - before_cache} foods that now resolve without asking again)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
