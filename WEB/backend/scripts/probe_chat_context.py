"""Print what _fetch_patient_context() actually hands the model for one user.

Read-only. Diagnostic for "the AI doesn't know my weight / my G6PD".
Prints the PROFILE section verbatim and everything else by size only, so a
real record is not dumped wholesale.

    docker compose --profile test run --rm \
      -e DATABASE_URL="postgresql+asyncpg://alafia:alafia@db:5432/alafia" \
      backend-test python scripts/probe_chat_context.py 63
"""
import asyncio
import sys

from sqlalchemy import select

from app.core.database import async_session
from app.models.user import User


async def main(uid: int) -> None:
    from app.api.ai import _fetch_patient_context

    async with async_session() as db:
        user = (await db.execute(select(User).where(User.id == uid))).scalar_one_or_none()
        if user is None:
            print(f"no user {uid}")
            return
        ctx = await _fetch_patient_context(user, db)

    print(f"=== total context: {len(ctx)} chars, {len(ctx.splitlines())} lines ===\n")

    # Section map with sizes — shows what dominates the payload.
    sections: list[tuple[str, int]] = []
    name, count = "(preamble)", 0
    for line in ctx.splitlines():
        if line.startswith("==="):
            sections.append((name, count))
            name, count = line.strip(), 0
        else:
            count += 1
    sections.append((name, count))
    print("--- sections (lines each) ---")
    for n, c in sections:
        print(f"{c:6d}  {n}")

    # The profile block verbatim — this is where weight/age/sex/conditions live.
    print("\n--- PATIENT PROFILE block as sent ---")
    out, on = [], False
    for line in ctx.splitlines():
        if line.startswith("=== PATIENT PROFILE"):
            on = True
        elif on and line.startswith("===") :
            break
        if on:
            out.append(line)
    print("\n".join(out) if out else "!!! NO PROFILE SECTION FOUND !!!")

    # Direct answers to the two complaints.
    print("\n--- DAILY NUTRIENT TARGETS block as sent ---")
    out2, on2 = [], False
    for line in ctx.splitlines():
        if line.startswith("=== DAILY NUTRIENT TARGETS"):
            on2 = True
        elif on2 and line.startswith("==="):
            break
        if on2:
            out2.append(line)
    print("\n".join(out2) if out2 else "!!! NO TARGETS SECTION !!!")

    print("\n--- targeted checks ---")
    for probe in ("Current Weight", "Age ", "Gender", "G6PD", "Allergies",
                  "Chronic Cond", "Food Intol"):
        hits = [l for l in ctx.splitlines() if probe.lower() in l.lower()]
        print(f"{probe:16s}: {'YES  ' + hits[0].strip()[:90] if hits else 'ABSENT'}")


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 63))
