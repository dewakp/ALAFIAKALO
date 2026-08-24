"""Create a local account for scripts/prove_ui_contracts.py. Dev only."""
import asyncio, sys
from sqlalchemy import select
from app.core.database import async_session
from app.core.security import hash_password
from app.models.user import User

EMAIL, PASSWORD = sys.argv[1], sys.argv[2]

async def main():
    async with async_session() as db:
        existing = (await db.execute(select(User).where(User.email == EMAIL))).scalar_one_or_none()
        if existing:
            existing.hashed_password = hash_password(PASSWORD)
            existing.is_active = True
        else:
            db.add(User(email=EMAIL, hashed_password=hash_password(PASSWORD),
                        full_name="UI Proof", is_active=True))
        await db.commit()
    print("ready:", EMAIL)

asyncio.run(main())
