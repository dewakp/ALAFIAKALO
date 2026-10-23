# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""Remove wrong cached food profiles, and re-estimate the meals built on them.

Input is the output of `scripts/audit_food_cache.py` (results.jsonl), so what
is removed is exactly what the audit found, by rules stated here.

A CACHE ROW GOES when ANY of:
  physical   `plausibility.review` says not believable — the rule the estimator
             now enforces before caching (above pure fat, macros over 100 g,
             energy that contradicts its own macros)
  wrong      the model judged the stored profile not credible for the name
  mismatch   the linked USDA/branded record is a DIFFERENT food and the model
             did not call the stored profile credible anyway
  not_food   the name is not a food ("to taste", "1 cup of", "mg of sodium")

Deleting a cache row loses nothing that cannot be re-derived: the next lookup
re-resolves it, now through `food_match_verifier`. Every deleted row is written
to a backup file first regardless.

A MEAL IS RE-ESTIMATED when it reaches a removed key AND its figures came from
the estimator:
  - status `done` / `failed`: enrichment wrote them (it only runs when the meal
    arrived with no calories), so they are estimator output by definition;
  - status `skipped`: the figures ARRIVED with the meal — an import, a label, a
    value somebody typed — so it is re-estimated only when the production meal
    estimator, run cache-only against the unpurged cache, REPRODUCES its stored
    calories. Otherwise it is reported and never touched: the row records no
    provenance, and clearing a patient's own number on a guess is worse than
    the bug being repaired.

DRY RUN BY DEFAULT, and the dry run's saved plan is what `--apply` executes —
so what is written is exactly what was reviewed, and provenance is not
recomputed (that pass alone drew 4,157 USDA 429s). A meal whose stored calories
changed since the plan was made is skipped.

    python scripts/repair_food_cache.py --audit /audit
    python scripts/repair_food_cache.py --audit /audit --apply /audit/repair_plan_<stamp>.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, select, text  # noqa: E402

from app.core.database import async_session  # noqa: E402
from app.models.food_nutrient_cache import FoodNutrientCache  # noqa: E402
from app.models.nutrition import NutritionLog  # noqa: E402


def _norm(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def purge_plan(results: list[dict]) -> dict[str, dict]:
    from app.services import plausibility

    plan: dict[str, dict] = {}
    for r in results:
        if not r["id"].startswith("cache:"):
            continue
        j = r.get("llm") or {}
        reasons = []
        if not plausibility.review(r["name"], r["nutrients"])[2]:
            reasons.append("physical")
        if j.get("verdict") == "wrong":
            reasons.append("wrong")
        if j.get("match") == "different_food" and j.get("verdict") != "ok":
            reasons.append("mismatch")
        if j.get("name_kind") == "not_food":
            reasons.append("not_food")
        if reasons:
            plan[_norm(r["name"])] = {
                "id": int(r["id"].split(":")[1]), "reasons": reasons,
                "source": r["source"], "kcal": r["nutrients"].get("calories"),
                "matched": (r.get("usda") or {}).get("description"),
                "why": j.get("reason")}
    return plan


async def affected_meals(plan: dict[str, dict]) -> list[dict]:
    """Meals whose description or any parsed component is a purged key, with
    a provenance verdict computed against the CURRENT (unpurged) cache."""
    from app.services import nutrient_estimator as ne
    from app.services.meal_parser import parse_meal_text

    async with async_session() as db:
        rows = (await db.execute(select(NutritionLog).order_by(NutritionLog.id))).scalars().all()
        meals = [{"id": r.id, "user_id": r.user_id, "log_date": str(r.log_date),
                  "food_name": r.food_name, "status": r.nutrient_status,
                  "calories": r.calories, "fat_g": r.fat_g, "protein_g": r.protein_g}
                 for r in rows]

    hit = []
    for m in meals:
        keys = {_norm(m["food_name"])}
        try:
            keys |= {_norm(c.food_name) for c in parse_meal_text(m["food_name"] or "")}
        except Exception:  # noqa: BLE001 — an unparseable name is not a finding
            pass
        via = sorted(k for k in keys if k in plan)
        if via:
            hit.append({**m, "via": via})

    # Cache-only recompute: every network tier is a miss, nothing is written.
    saved = (ne._try_usda, ne._try_mcp_branded, ne._try_ai)

    async def _miss(*a, **k):
        return None

    ne._try_usda = ne._try_mcp_branded = ne._try_ai = _miss
    # Each recompute still resolves category bands against USDA (~6 s a meal),
    # and meals are independent — so they run concurrently, bounded.
    sem = asyncio.Semaphore(8)

    async def _one(m: dict) -> None:
        async with sem, async_session() as db:
            try:
                est = await ne.estimate_meal_nutrients(db, m["food_name"] or "")
                kcal = (est.get("aggregate_nutrients") or {}).get("calories")
            except Exception:  # noqa: BLE001
                kcal = None
            finally:
                await db.rollback()
        s = m["calories"]
        m["cache_only_kcal"] = kcal
        m["provenance"] = ("unknown" if s is None or kcal is None else
                           "derived" if abs(float(s) - float(kcal)) <= max(5.0, 0.03 * float(s))
                           else "other")

    try:
        await asyncio.gather(*(_one(m) for m in hit))
    finally:
        ne._try_usda, ne._try_mcp_branded, ne._try_ai = saved
    return hit


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--audit", required=True, help="directory holding results.jsonl")
    ap.add_argument("--apply", metavar="PLAN", help="execute a saved dry-run plan")
    ap.add_argument("--pace", type=float, default=6.0,
                    help="seconds between foods/meals on --apply. USDA allows 3,600 "
                         "requests an hour per key and one food lookup makes ~5 of them "
                         "(search, branded, category, energy range), so 6 s keeps under it")
    args = ap.parse_args()
    d = Path(args.audit)

    if args.apply:
        saved = json.loads(Path(args.apply).read_text())
        plan, meals = saved["purge"], saved["meals"]
    else:
        results = [json.loads(line) for line in (d / "results.jsonl").read_text().splitlines()]
        plan = purge_plan(results)
        meals = await affected_meals(plan)
    prov = Counter((m["status"], m["provenance"]) for m in meals)
    derived = [m for m in meals
               if m["status"] in ("done", "failed") or m["provenance"] == "derived"]

    print(f"cache rows to remove: {len(plan)}  by reason "
          f"{dict(Counter(x for p in plan.values() for x in p['reasons']))}")
    print(f"meals reaching a removed key: {len(meals)}")
    for k, n in sorted(prov.items()):
        print(f"   status={k[0]:8} provenance={k[1]:8} {n}")
    print(f"meals to re-estimate (estimator output, or reproduced from the cache): {len(derived)}")
    print(f"meals left untouched (figures arrived with the meal): {len(meals) - len(derived)}")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if not args.apply:
        out = d / f"repair_plan_{stamp}.json"
        out.write_text(json.dumps({"purge": plan, "meals": meals}, indent=1, default=str))
        (d / f"untouched_{stamp}.json").write_text(json.dumps(
            [m for m in meals if m not in derived], indent=1, default=str))
        print(f"\nDRY RUN — nothing written. Plan: {out.name}")
        return 0

    # 1. Back up, then remove, the cache rows.
    # By id AND name: the plan was made on a copy, and a row replaced since
    # then under the same id must not be deleted on the strength of its
    # predecessor's audit.
    ids = [p["id"] for p in plan.values()]
    names = [k for k in plan]
    match = "id = any(:ids) and food_name_normalized = any(:names)"
    async with async_session() as db:
        backup = (await db.execute(text(
            f"select row_to_json(c) from food_nutrient_cache c where {match}"),
            {"ids": ids, "names": names})).scalars().all()
        (d / f"cache_backup_{stamp}.json").write_text(json.dumps(backup, default=str))
        n = (await db.execute(delete(FoodNutrientCache).where(
            FoodNutrientCache.id.in_(ids),
            FoodNutrientCache.food_name_normalized.in_(names)))).rowcount
        await db.commit()
    print(f"removed {n} cache rows (backup: cache_backup_{stamp}.json)")

    # 2. Warm the cache: resolve every food the selected meals contain, ONE AT
    #    A TIME, through the live lookup — now verified. An answer given while
    #    an authority was unavailable is not cached (§3bj), so a rate-limited
    #    food is retried after a pause instead of being written into a meal.
    from app.core.nutrition_data import DB_COLUMN_KEYS
    from app.services import nutrient_estimator as ne
    from app.services.meal_parser import parse_meal_text
    from app.services.nutrient_enrichment import enrich_log

    foods = []
    for m in derived:
        try:
            names = [c.food_name for c in parse_meal_text(m["food_name"] or "")]
        except Exception:  # noqa: BLE001
            names = []
        for n in names or [m["food_name"] or ""]:
            if n and _norm(n) not in {_norm(f) for f in foods}:
                foods.append(n)

    async def _resolved(name: str) -> bool:
        async with async_session() as db:
            got = (await db.execute(text(
                "select 1 from food_nutrient_cache where food_name_normalized = :n "
                "union all select 1 from learned_food_nutrients where food_name_normalized = :n"),
                {"n": _norm(name)})).first()
        return got is not None

    # A food that is not cached afterwards was answered while an authority
    # was unavailable (USDA 429, a model outage): that answer is deliberately
    # not cached. USDA's own Retry-After on an exhausted key is ~7 minutes, so
    # the wait is minutes, not seconds — up to 20 of them before giving up.
    print(f"\nwarming {len(foods)} distinct foods")
    unresolved = []
    for i, name in enumerate(foods, 1):
        for attempt in range(10):
            if await _resolved(name) or ne._curated_lookup(name) or ne._is_placeholder(name):
                break
            async with async_session() as db:
                try:
                    await ne.estimate_nutrients(db, name)
                    await db.commit()
                except Exception as exc:  # noqa: BLE001
                    await db.rollback()
                    print(f"  {name!r}: {type(exc).__name__}")
            if await _resolved(name):
                break
            print(f"  {name!r} not resolved (attempt {attempt + 1}) — an authority was "
                  f"unavailable; waiting 120 s", flush=True)
            await asyncio.sleep(120)
        else:
            unresolved.append(name)
        if i % 25 == 0:
            print(f"  warmed {i}/{len(foods)} ({len(unresolved)} unresolved)")
        await asyncio.sleep(args.pace)
    print(f"warm: {len(foods) - len(unresolved)} resolved, {len(unresolved)} unresolved")

    # 3. Re-estimate the selected meals through the live writer. A JOURNAL is
    #    written before a meal is cleared, so an interrupted run never strands a
    #    meal empty: a rerun recognises its own cleared rows and finishes them.
    journal = d / "repair_journal.jsonl"
    cleared = {}
    if journal.exists():
        for line in journal.read_text().splitlines():
            x = json.loads(line)
            cleared[x["id"]] = x["before"]

    # A meal containing a food that never resolved is DEFERRED, not estimated
    # around the gap: re-estimating it now would write an uncached fallback
    # into the record — the degraded answer the lookup refuses to keep.
    unresolved_n = {_norm(u) for u in unresolved}

    def _blocked(m: dict) -> bool:
        try:
            names = [c.food_name for c in parse_meal_text(m["food_name"] or "")]
        except Exception:  # noqa: BLE001
            names = []
        return any(_norm(n) in unresolved_n for n in (names or [m["food_name"] or ""]))

    deferred = [m for m in derived if _blocked(m)]
    derived = [m for m in derived if not _blocked(m)]
    if deferred:
        print(f"deferred {len(deferred)} meals containing an unresolved food — rerun later")

    report = []
    for i, m in enumerate(derived, 1):
        if i > 1:
            await asyncio.sleep(args.pace)
        async with async_session() as db:
            row = (await db.execute(select(NutritionLog).where(NutritionLog.id == m["id"]))).scalar_one_or_none()
            resuming = row is not None and m["id"] in cleared and row.calories is None
            if row is None or (not resuming and row.calories != m["calories"]
                               and not (row.calories is None and m["calories"] is None)):
                print(f"  [{i}/{len(derived)}] {m['id']} SKIPPED — changed since the plan")
                continue
            if resuming:
                before = cleared[m["id"]]
            else:
                before = {k: getattr(row, k) for k in DB_COLUMN_KEYS if hasattr(row, k)}
                with journal.open("a") as fh:
                    fh.write(json.dumps({"id": m["id"], "before": before}, default=str) + "\n")
            for k in before:
                setattr(row, k, None)
            row.extended_nutrients = None
            row.nutrient_status = "pending"
            await db.commit()
        try:
            await enrich_log(m["id"])
        except Exception as exc:  # noqa: BLE001 — one meal must not stop the run
            print(f"  [{i}/{len(derived)}] {m['id']} FAILED {type(exc).__name__}")
        async with async_session() as db:
            row = (await db.execute(select(NutritionLog).where(NutritionLog.id == m["id"]))).scalar_one()
            after = {k: getattr(row, k) for k in before}
            status = row.nutrient_status
        report.append({"id": m["id"], "user_id": m["user_id"], "log_date": m["log_date"],
                       "food_name": m["food_name"], "status_after": status,
                       "before": before, "after": after})
        print(f"  [{i}/{len(derived)}] {m['log_date']} {status:7} "
              f"{before.get('calories')} -> {after.get('calories')} kcal  {(m['food_name'] or '')[:50]}")

    (d / f"repair_report_{stamp}.json").write_text(json.dumps(
        {"unresolved_foods": unresolved, "deferred_meals": [m["id"] for m in deferred],
         "meals": report}, indent=1, default=str))
    print(f"\nre-estimated {len(report)} meals (report: repair_report_{stamp}.json)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
