#!/usr/bin/env python3
# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""Drop the cache rows where a BRANDED product is standing in for a real food.

Operator, 2026-10-21, on a foundational error in nutritional analysis with
grapefruit, banana and eba as the examples.

`food_nutrient_cache` is consulted before USDA, so a wrong row is served
forever and a fix to the lookup path changes nothing. Measured after committing
the FNDDS/empty-record ranking fix (04c6474):

    estimate_nutrients("grapefruit")
        -> 45 kcal, 0 g protein, NO potassium, 9.9 g added sugar
           source=mcp_branded_usda  fdc=1930383  serving="222.0 ml"

That is a sweetened 222 ml drink answering for a raw fruit, with 11 hits
against it, while the repaired USDA rung returns `Grapefruit, raw | 42 kcal |
P 0.77 | K 135`. **The source fix is inert until the row is gone.**

**ONLY A PROVABLY WRONG ROW IS DELETED, and the first version of this script
got that wrong.** It deleted wherever the repaired USDA rung could answer at
all, which sounded safe because a cache row is only a derived lookup. The dry
run refuted it on the 13th row:

    unsalted butter   cached 714.0/0.0/None     usda 345/8.2/88

Butter IS ~717 kcal/100 g. USDA's 345 kcal with 8.2 g of protein and 88 mg of
potassium is not butter, so "USDA can answer" would have replaced a CORRECT
row with a wrong one. Deleting good data for a worse replacement is the same
harm as keeping bad data, and §3ab's rule survives the move to a cache table
after all: only the impossible goes.

So a row is superseded only on a contradiction that can be demonstrated:

  1. **Energy outside its own food class's observed range** — judged by
     `plausibility.review` against `food_category_service.reference_energy_range`,
     the system's existing authority, AND the USDA candidate falls inside it.
     This keeps `unsalted butter` (714 is in band for `oil_fat`; USDA's 345 is
     not) and removes `pineapple` at 386 kcal against a fruit band.
  2. **Declared added sugars on one of the three classes WHO NAMES as
     intrinsic** — fresh fruit, vegetables, milk. A Nutrition Facts panel
     declaring ADDED sugars for a food in one of those contradicts the class
     outright. This is what catches `grapefruit`: 45 kcal is unremarkable for a
     fruit, so rule 1 never fires, but 9.9 g of added sugar in a raw grapefruit
     is impossible by definition (`services/free_sugars.py`).

     ⚠️ It uses `WHO_NAMED_INTRINSIC`, not the wider `_INTRINSIC_ONLY`. With
     the wider set the dry run condemned two rows on a MISCLASSIFICATION
     rather than a contradiction — `brioche bread,` resolved to `nut_seed` and
     a whole breakfast string to `lean_meat`, and brioche legitimately
     contains added sugar at a plausible 289 kcal. Rule 2's premise is that
     the class is trustworthy, and it only is for the three WHO actually
     names; a sweetened nut butter or a glazed ham declares added sugars
     without being the wrong record (§3ab: a rule is only valid in the context
     it was measured for).

Nothing patient-authored is touched: this table is a derived lookup, so a
deletion costs a re-derivation on next use and no record is lost.

    # report only (default)
    PYTHONPATH=/app python scripts/purge_superseded_branded_cache.py
    # then, deliberately
    PYTHONPATH=/app python scripts/purge_superseded_branded_cache.py --apply
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from sqlalchemy import delete, select

logging.getLogger("app").setLevel(logging.ERROR)
logging.getLogger("httpx").setLevel(logging.ERROR)


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true",
                    help="delete the superseded rows (default: report only)")
    ap.add_argument("--limit", type=int, default=0,
                    help="examine at most N rows (0 = all)")
    args = ap.parse_args()

    from app.core.database import async_session
    from app.models.food_nutrient_cache import FoodNutrientCache
    from app.services import plausibility
    from app.services.food_category_service import (
        reference_energy_range, resolve_band_category,
    )
    from app.services.free_sugars import WHO_NAMED_INTRINSIC
    from app.services.nutrient_estimator import _has_any_substance, _try_usda

    async with async_session() as db:
        q = select(FoodNutrientCache).where(
            FoodNutrientCache.source == "mcp_branded_usda"
        ).order_by(FoodNutrientCache.hit_count.desc())
        rows = list((await db.execute(q)).scalars().all())
    if args.limit:
        rows = rows[: args.limit]

    print(f"examining {len(rows)} mcp_branded_usda cache rows\n")

    superseded: list[tuple[FoodNutrientCache, dict]] = []
    kept: list[tuple[FoodNutrientCache, str]] = []

    for row in rows:
        name = row.food_name_normalized
        cached_nutrients = row.nutrients or {}

        async with async_session() as db:
            try:
                band, _src = await resolve_band_category(db, name)
                ref_range = await reference_energy_range(db, name)
                await db.commit()
            except Exception:  # noqa: BLE001
                band, ref_range = None, None

        # ── rule 2 first: it needs no network call and no band range ───────
        #
        # WHO: the sugars in fresh fruit, vegetables and milk are INTRINSIC. A
        # panel declaring added sugars for a food in one of those classes is
        # not that food. This is the grapefruit case, and it is invisible to
        # any energy check — 45 kcal is unremarkable for a fruit.
        declared_added = cached_nutrients.get("added_sugars_g")
        contradicts_class = (
            band in WHO_NAMED_INTRINSIC
            and isinstance(declared_added, (int, float))
            and float(declared_added) > 0
        )

        try:
            better = await _try_usda(name)
        except Exception as exc:  # noqa: BLE001
            # An unreachable USDA is not evidence that the cached row is good.
            # Keep it and SAY so — deleting on a network failure would discard
            # rows we never actually compared (§3aj: fail open).
            kept.append((row, f"USDA unreachable: {type(exc).__name__}"))
            continue

        # ⚠️ The nutrients are UNDER "nutrients". Passing `_try_usda`'s wrapper
        # to `_has_any_substance` made every row look unanswerable and the
        # first dry run reported a confident `0 superseded` — a green pass
        # measuring nothing, on a script whose whole job is to decide what to
        # delete (§3av: run the scan, never the arithmetic).
        better_nutrients = (better or {}).get("nutrients") or {}
        if not better_nutrients or not _has_any_substance(better_nutrients):
            kept.append((row, "USDA has no record carrying substance"))
            continue

        # ── rule 1: the class's own observed energy range judges both rows ──
        _c, cached_warn, cached_ok = plausibility.review(
            name, dict(cached_nutrients), category=band, reference_range=ref_range)
        _u, _usda_warn, usda_ok = plausibility.review(
            name, dict(better_nutrients), category=band, reference_range=ref_range)
        energy_refutes = (not cached_ok) and usda_ok

        if not (energy_refutes or contradicts_class):
            kept.append((row, "no demonstrable contradiction in the cached row"))
            continue

        why = ("added sugars declared on an intrinsic-sugar class"
               if contradicts_class else
               "energy outside its food class, where USDA's record is inside")
        superseded.append((row, {
            "band": band or "-",
            "why": why,
            "cached_kcal": cached_nutrients.get("calories"),
            "cached_k": cached_nutrients.get("potassium_mg"),
            "cached_protein": cached_nutrients.get("protein_g"),
            "usda_kcal": better_nutrients.get("calories"),
            "usda_k": better_nutrients.get("potassium_mg"),
            "usda_protein": better_nutrients.get("protein_g"),
            "cached_reason": "; ".join(cached_warn or []) or "-",
        }))

    print(f"SUPERSEDED — the cached row is demonstrably wrong and USDA has a "
          f"record that is not: {len(superseded)}")
    print(f"{'name':26} {'hits':>4} {'band':14} {'cached kcal/P/K':>20} "
          f"{'usda kcal/P/K':>20}  why")
    for row, cmp in superseded[:60]:
        c = f"{cmp['cached_kcal']}/{cmp['cached_protein']}/{cmp['cached_k']}"
        u = f"{cmp['usda_kcal']}/{cmp['usda_protein']}/{cmp['usda_k']}"
        print(f"{row.food_name_normalized[:26]:26} {row.hit_count or 0:>4} "
              f"{cmp['band'][:14]:14} {c:>20} {u:>20}  {cmp['why']}")
    if len(superseded) > 60:
        print(f"  … and {len(superseded) - 60} more")

    # Count the rejects and print them — a pass that drops what it cannot
    # judge, without saying so, hides its own failure (§3av).
    print(f"\nKEPT: {len(kept)}")
    reasons: dict[str, int] = {}
    for _row, why in kept:
        reasons[why] = reasons.get(why, 0) + 1
    for why, n in sorted(reasons.items(), key=lambda kv: -kv[1]):
        print(f"  {n:>4}  {why}")

    if not args.apply:
        print("\nDRY RUN — nothing deleted. Re-run with --apply to delete the "
              f"{len(superseded)} superseded rows.")
        return 0

    if not superseded:
        print("\nNothing to delete.")
        return 0

    ids = [row.id for row, _ in superseded]
    async with async_session() as db:
        await db.execute(delete(FoodNutrientCache).where(
            FoodNutrientCache.id.in_(ids)))
        await db.commit()
        # Read the count back rather than trusting the statement — a
        # destructive script that reports success having matched nothing is
        # worse than one that fails (§3ab).
        left = (await db.execute(select(FoodNutrientCache).where(
            FoodNutrientCache.id.in_(ids)))).scalars().all()
    print(f"\ndeleted {len(ids) - len(left)} of {len(ids)} rows "
          f"({len(left)} still present)")
    print("Each name re-derives through the repaired lookup on next use.")
    return 0 if not left else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
