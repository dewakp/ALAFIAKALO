"""Print the patient block the PLANNER prompts now send, for one user.

Read-only. Proves the planner carries age/sex/weight/targets/dialysis and the
forbidden list, and that it no longer sends the patient's name.

    docker compose --profile test run --rm \
      -e DATABASE_URL="postgresql+asyncpg://alafia:alafia@db:5432/alafia" \
      backend-test python scripts/probe_planner_prompt.py 63
"""
import asyncio
import sys

from sqlalchemy import select

from app.core.database import async_session
from app.models.user import User


async def main(uid: int) -> None:
    from app.api.planners import _gather_planner_context, _patient_block

    async with async_session() as db:
        user = (await db.execute(select(User).where(User.id == uid))).scalar_one_or_none()
        if user is None:
            print(f"no user {uid}")
            return
        ctx = await _gather_planner_context(uid, db)
        block = _patient_block(user, ctx)

    print("=== PATIENT BLOCK sent to the model ===")
    print(block)

    print("\n=== checks ===")
    name = (getattr(user, "full_name", "") or "").strip()
    print(f"forbidden items gathered : {len(ctx.get('forbidden') or [])}")
    print(f"nutrient goals gathered  : {len((ctx.get('goals') or {}).get('goals') or [])}")
    if name:
        leaked = name.lower() in block.lower() or any(
            part.lower() in block.lower() for part in name.split() if len(part) > 2
        )
        print(f"patient NAME in prompt   : {'*** LEAKED ***' if leaked else 'no'}")
    else:
        print("patient NAME in prompt   : (no name on record to leak)")


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 63))
