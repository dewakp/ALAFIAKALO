# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""Resolve every declared allergy term against RxNorm. Dry run by default.

    PYTHONPATH=/app python scripts/resolve_allergy_terms.py            # reports
    PYTHONPATH=/app python scripts/resolve_allergy_terms.py --apply    # writes

WHY A SCRIPT AND NOT A REQUEST. `resolve_term` calls RxNav, and a clinical write
path must never wait on a third party (§3ae). The write path reads
`allergy_term_resolutions` instead — one indexed SELECT — so this is what
populates it. Profile saves also enqueue a resolution in the background, so
this is the backfill and the repair, not the only route.

WHAT IT IS GUARDING AGAINST. The reference profile declares `Penicilin`, and a
dose logged as the correctly-spelled `Penicillin` did not match it, because the
matcher compares words. One missing letter defeated the guard whose entire job
is to catch that.

The DRY RUN still calls RxNorm — the whole point is to show what WOULD be
stored, including the refusals, before anything is written. A dry run that
reported nothing would be §3as's cleanup script that selected nothing and read
as a clean database.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select  # noqa: E402

from app.core.database import async_session  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services import allergy_resolution as ar  # noqa: E402
from app.services.food_safety import profile_list  # noqa: E402


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true",
                    help="write the resolutions (default: report only)")
    ap.add_argument("--user", type=int, default=None,
                    help="restrict to one user id")
    args = ap.parse_args()

    async with async_session() as db:
        stmt = select(User).where(
            User.allergies.isnot(None) | User.food_intolerances.isnot(None))
        if args.user:
            stmt = stmt.where(User.id == args.user)
        users = (await db.execute(stmt)).scalars().all()

        # One term can be declared by several patients, and the resolution is a
        # fact about the WORD — so resolve each distinct term once.
        terms: dict[str, str] = {}
        for u in users:
            for item in (profile_list(u.allergies)
                         + profile_list(u.food_intolerances)):
                key = ar._normalise(item)
                if key:
                    terms.setdefault(key, item)

        print(f"users with declarations : {len(users)}")
        print(f"distinct terms          : {len(terms)}")
        print()

        counts: dict[str, int] = {}
        rows = []
        for key, sample in sorted(terms.items()):
            verdict = await ar.resolve_term(sample)
            counts[verdict.verdict] = counts.get(verdict.verdict, 0) + 1
            rows.append((sample, verdict))
            if args.apply:
                await ar.persist(db, verdict)

        width = max((len(s) for s, _ in rows), default=10)
        print(f"{'declared'.ljust(width)}  verdict      resolved / why")
        print("-" * (width + 50))
        for sample, v in rows:
            detail = v.resolved_name or ""
            if v.verdict == ar.SPELLING:
                detail = f"{v.resolved_name}  (distance {v.edit_distance})"
            elif v.verdict in (ar.REFUSED, ar.UNKNOWN, ar.UNREACHABLE):
                detail = f"{v.resolved_name or '—'} — {v.refused_reason}"
            print(f"{sample.ljust(width)}  {v.verdict:<11}  {detail}")

        print()
        for k in sorted(counts):
            print(f"  {k:<12} {counts[k]}")

        # The REFUSALS are the interesting half: each one is a confident wrong
        # answer that was stopped. "Raw Apples" resolves to "raw sugar" with a
        # HIGHER RxNorm score than the genuine typo fixes.
        refused = [(s, v) for s, v in rows if v.verdict == ar.REFUSED]
        if refused:
            print()
            print("REFUSED (RxNorm proposed something that is not a spelling "
                  "variant — review these):")
            for s, v in refused:
                print(f"  {s!r} -> {v.resolved_name!r}: {v.refused_reason}")

        if args.apply:
            await db.commit()
            print("\nAPPLIED.")
        else:
            print("\nDRY RUN — nothing written. Re-run with --apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
