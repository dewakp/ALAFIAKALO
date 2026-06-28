"""Re-mint ALAFIA users' System Identifiers with the CANONICAL 6IGMA algorithm.

Part of Prompt 1.2 (ALAFIA⇄FlowSheet alignment). Legacy ALAFIA SIDs used
RND93+SHA-512; the canonical algorithm (shared with FlowSheet) is
RND157+SHA-256. This script re-mints any user whose `system_id` is missing or
does not verify under the canonical scheme, and writes an `old_sid → new_sid`
map so external references can be reconciled.

SAFE BY DEFAULT: dry-run unless `--apply` is passed.

    # preview what would change
    python -m scripts.remint_canonical_sids
    # actually write new SIDs + map file
    python -m scripts.remint_canonical_sids --apply

Idempotent: users already carrying a valid canonical SID are skipped.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from app.core.database import async_session
from app.models.user import User
from app.models.system_id import SystemIdLog
from app.services import canonical_sid

MAP_PATH = Path(__file__).with_name("sid_remint_map.json")


def _split_name(full_name: str | None) -> tuple[str, str]:
    parts = (full_name or "").strip().split()
    if not parts:
        return ("X", "X")
    if len(parts) == 1:
        return (parts[0], "X")
    return (parts[0], parts[-1])


async def main(apply: bool) -> None:
    remint_map: dict[str, dict] = {}
    skipped = 0

    async with async_session() as db:
        users = (await db.execute(select(User))).scalars().all()
        print(f"scanning {len(users)} users…")

        for u in users:
            # Skip users already on a valid canonical SID.
            if u.system_id and canonical_sid.verify_sid(u.system_id):
                skipped += 1
                continue

            first, last = _split_name(u.full_name)
            sex = u.gender_at_birth or u.gender
            created = u.created_at or datetime.now(timezone.utc)
            new_sid = canonical_sid.generate_sid(first, last, u.date_of_birth, sex, created)

            remint_map[str(u.id)] = {
                "email": u.email,
                "old_sid": (u.system_id or None),
                "new_sid": new_sid,
            }

            if apply:
                u.system_id = new_sid
                segs = canonical_sid.segments_for_log(first, last, u.date_of_birth, sex, created)
                db.add(SystemIdLog(user_id=u.id, system_id=new_sid, **segs))

        if apply:
            await db.commit()

    MAP_PATH.write_text(json.dumps(remint_map, indent=2, default=str))
    action = "RE-MINTED" if apply else "WOULD re-mint (dry-run)"
    print(f"{action}: {len(remint_map)} users · skipped (already canonical): {skipped}")
    print(f"old→new map written to {MAP_PATH}")
    if not apply:
        print("Re-run with --apply to persist new SIDs.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="persist new SIDs (otherwise dry-run)")
    args = ap.parse_args()
    asyncio.run(main(args.apply))
