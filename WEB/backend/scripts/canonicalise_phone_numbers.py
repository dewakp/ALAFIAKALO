#!/usr/bin/env python3
"""Put every stored phone number into ONE canonical form (E.164).

`users.phone_number` has always carried a UNIQUE index, but the index compares
the literal string. Production stores all of its numbers as bare digits, so
`9712606446` and `+19712606446` are two different values and one person could
hold two accounts without the constraint ever firing. New signups are
canonicalised at the API boundary; this brings the existing rows into line.

**It refuses what it cannot parse, and that is the point.** One production row
holds a 9-digit value on a US account — too short to be a US number. Prefixing
`+1` would put a DIFFERENT person's number into a clinical record. Those rows
are listed for a human to correct, never rewritten (§3am: an unreadable value
is refused, not assumed).

DRY RUN BY DEFAULT. Nothing is written without --apply.

Numbers are never printed in full: the output shows the last four digits only,
because this runs against real patient records.

    # 1. start the proxy (from the repo root)
    #    scripts/db/db_lib.sh provides start_proxy; or run cloud-sql-proxy yourself
    # 2. then, from WEB/:
    docker compose run --rm --no-deps --network host \
      -e DSN="postgresql://alafia:$PROD_DB_PASS@127.0.0.1:5432/alafia" \
      backend python scripts/canonicalise_phone_numbers.py          # dry run
      backend python scripts/canonicalise_phone_numbers.py --apply  # writes
"""

import argparse
import asyncio
import os
import sys

import asyncpg

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.phone import to_e164  # noqa: E402


def mask(number: str | None) -> str:
    """Last four digits only — this is a real patient identifier."""
    if not number:
        return "—"
    return f"••••{number[-4:]}" if len(number) >= 4 else "••••"


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true",
                    help="write the changes (default: dry run)")
    args = ap.parse_args()

    dsn = os.environ.get("DSN")
    if not dsn:
        print("DSN is not set — refusing to guess at a database.", file=sys.stderr)
        return 2

    conn = await asyncpg.connect(dsn)
    try:
        rows = await conn.fetch(
            "SELECT id, phone_number, country FROM users "
            "WHERE phone_number IS NOT NULL AND phone_number <> '' ORDER BY id"
        )

        already, planned, refused = [], [], []
        for r in rows:
            current, country = r["phone_number"], r["country"]
            canonical = to_e164(current, country)
            if canonical is None:
                refused.append((r["id"], current, country))
            elif canonical == current:
                already.append(r["id"])
            else:
                planned.append((r["id"], current, canonical, country))

        print(f"{len(rows)} account(s) hold a phone number\n")
        print(f"  already canonical : {len(already)}")
        print(f"  to canonicalise   : {len(planned)}")
        print(f"  cannot parse      : {len(refused)}\n")

        for uid, current, canonical, country in planned:
            print(f"  id {uid:>5}  [{country or '??'}]  {mask(current)} "
                  f"({len(current)} chars)  ->  {mask(canonical)} (E.164)")

        for uid, current, country in refused:
            print(f"  id {uid:>5}  [{country or '??'}]  {mask(current)} "
                  f"({len(current)} digits)  ->  REFUSED, not a valid number "
                  f"for this country — needs a human")

        if not planned:
            print("\nNothing to write.")
            return 0

        if not args.apply:
            print("\nDRY RUN — re-run with --apply to write these.")
            return 0

        # One statement per row, inside a transaction: if any collides with the
        # unique index (two rows canonicalising to the SAME number), the whole
        # thing rolls back rather than leaving half the table converted.
        async with conn.transaction():
            for uid, _current, canonical, _country in planned:
                await conn.execute(
                    "UPDATE users SET phone_number = $1 WHERE id = $2", canonical, uid
                )
        print(f"\napplied: {len(planned)} row(s) canonicalised.")
        if refused:
            print(f"still needing a human: {len(refused)} row(s).")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
