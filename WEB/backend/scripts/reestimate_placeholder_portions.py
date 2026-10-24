# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""Re-estimate meals whose items carried the parser's 100 g placeholder.

Operator choice C (2026-10-23): an item with no usable weight takes the
resolved food's own USDA portion, else an ASSUMED ordinary serving labelled as
one, else "weight unknown". Meals estimated before that kept 100 g for every
such item — 72% of logged items state no weight.

SCOPE: meals whose figures the ESTIMATOR wrote (`nutrient_status` done/failed)
and that contain at least one placeholder item. Meals whose figures arrived
with them (`skipped`: imports, labels, typed values) are never touched.

DRY RUN BY DEFAULT: every meal is recomputed with the live code in a rolled-back
session; nothing is written. The report gives before/after per meal and per
day. `--apply` re-estimates through the live writer (`enrich_log`), journalled
so an interrupted run never strands a meal empty.

    python scripts/reestimate_placeholder_portions.py --out /audit
    python scripts/reestimate_placeholder_portions.py --out /audit --apply /audit/placeholder_plan_<stamp>.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.core.database import async_session  # noqa: E402
from app.models.nutrition import NutritionLog  # noqa: E402
from app.models.user import User  # noqa: E402

KEYS = ("calories", "protein_g", "fat_g", "carbs_g", "potassium_mg", "phosphorus_mg", "sodium_mg")


async def plan(out: Path) -> Path:
    from app.services import nutrient_estimator as ne
    from app.services.meal_parser import parse_meal_text

    async with async_session() as db:
        logs = (await db.execute(select(NutritionLog).where(
            NutritionLog.nutrient_status.in_(("done", "failed"))).order_by(NutritionLog.id))).scalars().all()
        users = {u.id: u for u in (await db.execute(select(User))).scalars()}
        meals = []
        for log in logs:
            try:
                comps = parse_meal_text(log.food_name or "")
            except Exception:  # noqa: BLE001
                continue
            n_ph = sum(1 for c in comps if ne._weight_is_placeholder(c.qty_text))
            if n_ph:
                meals.append({"id": log.id, "user_id": log.user_id, "log_date": str(log.log_date),
                              "food_name": log.food_name, "status": log.nutrient_status,
                              "placeholders": n_ph, "items": len(comps),
                              "before": {k: getattr(log, k) for k in KEYS}})
    print(f"{len(logs)} estimator-owned meals; {len(meals)} contain a placeholder item")

    sem = asyncio.Semaphore(int(os.environ.get("REESTIMATE_CONCURRENCY", "2")))

    async def one(m):
        u = users.get(m["user_id"])
        async with sem, async_session() as db:
            try:
                r = await ne.estimate_meal_nutrients(
                    db, m["food_name"] or "", country=getattr(u, "country", None),
                    preferred_units=getattr(u, "preferred_units", None), locale=getattr(u, "locale", None))
                agg = r.get("aggregate_nutrients") or {}
                m["after"] = {k: agg.get(k) for k in KEYS}
                m["portions"] = [c.get("qty_text") for c in r.get("components") or []]
                m["excluded"] = r.get("excluded_components") or []
            except Exception as exc:  # noqa: BLE001
                m["after"], m["error"] = None, type(exc).__name__
            finally:
                await db.rollback()

    await asyncio.gather(*(one(m) for m in meals))

    days = defaultdict(lambda: {"before": 0.0, "after": 0.0, "meals": 0})
    for m in meals:
        if not m.get("after"):
            continue
        d = days[(m["user_id"], m["log_date"])]
        d["before"] += float(m["before"]["calories"] or 0)
        d["after"] += float(m["after"]["calories"] or 0)
        d["meals"] += 1
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = out / f"placeholder_plan_{stamp}.json"
    path.write_text(json.dumps({"meals": meals, "days": [
        {"user_id": k[0], "date": k[1], **v} for k, v in sorted(days.items())]}, indent=1, default=str))

    ok = [m for m in meals if m.get("after")]
    b = sum(float(m["before"]["calories"] or 0) for m in ok)
    a = sum(float(m["after"]["calories"] or 0) for m in ok)
    print(f"recomputed {len(ok)}/{len(meals)} ({len(meals) - len(ok)} errored)")
    print(f"total kcal across those meals: {b:,.0f} -> {a:,.0f}")
    print(f"assumed portions used: {sum(sum(1 for p in m.get('portions') or [] if (p or '').startswith('assumed')) for m in ok)}")
    print(f"USDA portions used:    {sum(sum(1 for p in m.get('portions') or [] if 'USDA' in (p or '')) for m in ok)}")
    print(f"items weight unknown:  {sum(len(m.get('excluded') or []) for m in ok)}")
    print(f"DRY RUN — nothing written. Plan: {path.name}")
    return path


async def apply(plan_path: Path, out: Path, pace: float) -> None:
    from app.core.nutrition_data import DB_COLUMN_KEYS
    from app.services.nutrient_enrichment import enrich_log

    meals = [m for m in json.loads(plan_path.read_text())["meals"] if m.get("after")]
    journal = out / "placeholder_journal.jsonl"
    cleared = {}
    if journal.exists():
        for line in journal.read_text().splitlines():
            x = json.loads(line)
            cleared[x["id"]] = x["before"]
    done = 0
    for i, m in enumerate(meals, 1):
        async with async_session() as db:
            row = (await db.execute(select(NutritionLog).where(NutritionLog.id == m["id"]))).scalar_one_or_none()
            resuming = row is not None and m["id"] in cleared and row.calories is None
            if row is None or (not resuming and row.calories != m["before"]["calories"]):
                print(f"  [{i}/{len(meals)}] {m['id']} SKIPPED — changed since the plan")
                continue
            if not resuming:
                before = {k: getattr(row, k) for k in DB_COLUMN_KEYS if hasattr(row, k)}
                with journal.open("a") as fh:
                    fh.write(json.dumps({"id": m["id"], "before": before}, default=str) + "\n")
            for k in DB_COLUMN_KEYS:
                if hasattr(row, k):
                    setattr(row, k, None)
            row.extended_nutrients = None
            row.nutrient_status = "pending"
            await db.commit()
        await enrich_log(m["id"])
        done += 1
        if i % 25 == 0:
            print(f"  re-estimated {i}/{len(meals)}", flush=True)
        await asyncio.sleep(pace)
    print(f"re-estimated {done} meals")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--apply", type=Path, help="execute a saved dry-run plan")
    ap.add_argument("--pace", type=float, default=2.0)
    a = ap.parse_args()
    if a.apply:
        asyncio.run(apply(a.apply, a.out, a.pace))
    else:
        asyncio.run(plan(a.out))


if __name__ == "__main__":
    main()
