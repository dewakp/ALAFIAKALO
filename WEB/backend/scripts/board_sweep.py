"""Run every clinician-board category against EVERY user that holds data.

Verifying the board against a single patient proves almost nothing: it exercises
whichever code paths that one record happens to populate and silently skips the
rest. On this database, checking only user 63 left `lifestyle` (data belongs to a
different user entirely), `fitness` and `pd_sessions` (no rows anywhere) never
executed once.

This calls the summarise/detail functions directly rather than going through the
HTTP API, so it needs no data-sharing grant and mutates nothing.

    docker compose --profile test run --rm backend-test python scripts/board_sweep.py
"""

from __future__ import annotations

import asyncio
import sys
import traceback

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.services import patient_board as board

# Tables that back at least one category, and the column that ties them to a user.
DATA_TABLES = [
    "vitals_logs", "lab_results", "nutrition_logs", "fitness_logs",
    "lifestyle_entries", "symptom_logs", "therapy_sessions", "pd_sessions",
    "mood_entries", "wellness_scores", "ehr_connections",
    "medications", "medication_dose_logs", "chronic_conditions", "health_conditions",
]


async def users_with_data(db: AsyncSession) -> list[int]:
    found: set[int] = set()
    for table in DATA_TABLES:
        try:
            rows = (await db.execute(
                text(f"SELECT DISTINCT user_id FROM {table} WHERE user_id IS NOT NULL")
            )).all()
        except Exception:
            continue  # table absent in this environment
        found.update(r[0] for r in rows)
    return sorted(found)


async def main() -> int:
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    failures: list[str] = []
    exercised: dict[str, int] = {c.key: 0 for c in board.CATEGORIES}
    empty: dict[str, int] = {c.key: 0 for c in board.CATEGORIES}

    async with Session() as db:
        uids = await users_with_data(db)
        print(f"users holding data: {len(uids)} → {uids}\n")

        for uid in uids:
            for cat in board.CATEGORIES:
                for label, fn in (("summary", cat.summarise), ("detail", cat.detail)):
                    try:
                        result = (await fn(db, uid) if label == "summary"
                                  else await fn(db, uid, 3650))
                    except Exception:
                        failures.append(
                            f"user {uid} · {cat.key}.{label}\n"
                            + traceback.format_exc(limit=3)
                        )
                        continue
                    if label == "summary":
                        if result.items:
                            exercised[cat.key] += 1
                        else:
                            empty[cat.key] += 1

    await engine.dispose()

    print(f"{'category':<20} {'users with data':>15} {'users empty':>12}")
    for cat in board.CATEGORIES:
        flag = "  ← NEVER exercised with data" if exercised[cat.key] == 0 else ""
        print(f"{cat.key:<20} {exercised[cat.key]:>15} {empty[cat.key]:>12}{flag}")

    if failures:
        print(f"\n{len(failures)} FAILURES\n" + "\n".join(failures[:10]))
        return 1
    print("\nno exceptions across every category × every user")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
