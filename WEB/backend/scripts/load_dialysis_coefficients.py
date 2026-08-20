#!/usr/bin/env python3
"""Load fitted dialysis coefficients into the database.

`ML/scripts/fit_dialysis_coefficients.py --out coeffs.json` produces the fit;
this puts it where the API can read it.

    docker compose exec -T backend python -m scripts.load_dialysis_coefficients \
        --file /tmp/coeffs.json --email developer@hntsolutions.com

Only a coefficient that beat the naive baseline on held-out bloods is stored as
adopted. The rest are written too, with `beats_baseline=False`, because "we
tried and it did not work" is worth keeping — it stops the same fit being
re-attempted and silently trusted later.

The patient is resolved by email. Hardcoding a row id is how clinical data ends
up attached to the wrong person.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import sys

from sqlalchemy import select

from app.core.database import async_session
from app.models.dialysis_coefficients import DialysisSoluteCoefficient
from app.models.user import User

#: The fit reports urea as "bun"; the model knows it as an analyte name.
ANALYTE_RENAME = {"bun": "urea"}


async def load(path: pathlib.Path, email: str, apply: bool) -> int:
    payload = json.loads(path.read_text())
    results = payload.get("results", [])
    if not results:
        print("No results in the fit file.")
        return 1

    async with async_session() as db:
        user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if user is None:
            print(f"No user with email {email}", file=sys.stderr)
            return 2

        existing = {
            row.analyte: row
            for row in (await db.execute(
                select(DialysisSoluteCoefficient).where(
                    DialysisSoluteCoefficient.user_id == user.id
                )
            )).scalars().all()
        }

        # Where an analyte was fitted more than one way, the hold-out decides.
        best: dict[str, dict] = {}
        for r in results:
            if r.get("alpha") is None:
                continue
            analyte = ANALYTE_RENAME.get(r["analyte"], r["analyte"])
            current = best.get(analyte)
            if current is None or (r.get("holdout_mae") or 9e9) < (current.get("holdout_mae") or 9e9):
                best[analyte] = {**r, "analyte": analyte}

        print(f"{'analyte':12s} {'method':14s} {'alpha':>12s} {'MAE':>8s} {'adopt':>6s}")
        print("-" * 58)
        for analyte, r in sorted(best.items()):
            adopt = bool(r.get("beats_baseline"))
            print(f"{analyte:12s} {r['method']:14s} {r['alpha']:12.6f} "
                  f"{(r.get('holdout_mae') or 0):8.3f} {'YES' if adopt else 'no':>6s}")

            row = existing.get(analyte) or DialysisSoluteCoefficient(
                user_id=user.id, analyte=analyte
            )
            row.alpha = float(r["alpha"])
            row.implied_volume_l = r.get("implied_volume_l")
            row.method = r["method"]
            row.n_fit = int(r.get("n_fit") or 0)
            row.n_holdout = int(r.get("n_holdout") or 0)
            row.holdout_mae = r.get("holdout_mae")
            row.baseline_mae = r.get("baseline_mae")
            row.holdout_bias = r.get("holdout_bias")
            row.beats_baseline = adopt
            if row.id is None:
                db.add(row)

        adopted = sum(1 for r in best.values() if r.get("beats_baseline"))
        print(f"\n{adopted}/{len(best)} adopted for {email}")

        if apply:
            await db.commit()
            print("committed")
        else:
            await db.rollback()
            print("dry run — pass --apply to write")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=pathlib.Path, required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    return asyncio.run(load(args.file, args.email, args.apply))


if __name__ == "__main__":
    raise SystemExit(main())
