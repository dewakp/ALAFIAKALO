"""Seed the dose history `e2e/medication-intake.spec.js` asserts on. Dev only.

The spec checks that the intake panel proposes a dose "from your last N doses"
— which requires the proof account to HAVE that history. It previously passed
on whatever rows dev had accumulated, so `scripts/db/pull_prod.sh` (which the
canon tells you to run often, and which is the only sanctioned way to fix
parity) silently broke two specs that look like a code regression.

A fixture that depends on incidental data is not a fixture. This makes the
suite reproducible on a freshly pulled dev.

    docker compose exec -T backend python scripts/seed_e2e_medication_history.py \
        uiproof@example.com
"""

import asyncio
import sys
from datetime import date, timedelta

from sqlalchemy import select, delete

from app.core.database import async_session
from app.models.med_nutrient import MedicationDoseLog
from app.models.user import User

EMAIL = sys.argv[1] if len(sys.argv) > 1 else "uiproof@example.com"

#: Calcitriol is dosed in MICROGRAMS. The spec asserts "mcg" precisely because
#: stating this drug in mg is the 1000x error the guard exists to catch.
DOSES = [(0.5, "mcg"), (0.5, "mcg"), (0.5, "mcg")]


async def main() -> None:
    async with async_session() as db:
        user = (await db.execute(
            select(User).where(User.email == EMAIL))).scalar_one_or_none()
        if user is None:
            raise SystemExit(f"no such user: {EMAIL} — run make_proof_user.py first")

        # Idempotent: re-running must not multiply the history the spec counts.
        await db.execute(delete(MedicationDoseLog).where(
            MedicationDoseLog.user_id == user.id,
            MedicationDoseLog.medication_name.ilike("calcitriol"),
        ))

        today = date.today()
        for i, (amount, unit) in enumerate(DOSES):
            db.add(MedicationDoseLog(
                user_id=user.id,
                medication_name="Calcitriol",
                log_date=today - timedelta(days=i + 1),
                dose_amount=amount,
                dose_unit=unit,
            ))
        await db.commit()
        print(f"seeded {len(DOSES)} Calcitriol doses for {EMAIL}")


asyncio.run(main())
