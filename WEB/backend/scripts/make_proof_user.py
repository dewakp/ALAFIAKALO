"""Create a local account for the e2e specs and prove_ui_contracts.py. Dev only.

Seeds the DATA the specs assert on as well as the account.

`e2e/medication-intake.spec.js` drives the real backend against this user and
expects a dose history to propose from and a stopped prescription to exclude.
Creating only the account left those specs failing on "No previous dose on
record" — which reads as a broken feature rather than a missing fixture, and it
happens every time dev is re-pulled from prod (which replaces the whole
database, this row included).

A suite that cannot reach the thing it tests is not evidence; neither is one
whose fixture quietly disappeared.
"""
import asyncio, sys
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from app.core.database import async_session
from app.core.security import hash_password
from app.models.user import User
from app.models.med_nutrient import MedicationDoseLog
from app.models.medications import Medication

EMAIL, PASSWORD = sys.argv[1], sys.argv[2]

#: Calcitriol is dosed in MICROGRAMS. The spec asserts the proposal says "mcg"
#: — that is the readable-units rule (§3aj), on the one warning whose job is to
#: stop a 1000x error.
DOSE_HISTORY = [("Calcitriol", 0.5, "mcg"), ("Calcium carbonate", 1000.0, "mg")]

#: Stopped in 2017, exactly like the SMART-sandbox EHR rows this guards against.
#: A stopped prescription is not an option for "what am I taking today".
STOPPED = [("Meperidine Hydrochloride 50 MG", "50 mg"), ("Ibuprofen 200 MG", "200 mg")]


async def main():
    async with async_session() as db:
        user = (await db.execute(select(User).where(User.email == EMAIL))).scalar_one_or_none()
        if user:
            user.hashed_password = hash_password(PASSWORD)
            user.is_active = True
        else:
            user = User(email=EMAIL, hashed_password=hash_password(PASSWORD),
                        full_name="UI Proof", first_name="UI", last_name="Proof",
                        is_active=True)
            db.add(user)
        await db.flush()

        existing = (await db.execute(
            select(MedicationDoseLog).where(MedicationDoseLog.user_id == user.id)
        )).scalars().first()
        if existing is None:
            # Three of each: "your last 3 doses" is the provenance the proposal
            # shows, and `promote-logged` is thresholded at 3.
            now = datetime.now(timezone.utc)
            for name, amount, unit in DOSE_HISTORY:
                for days_ago in (0, 1, 2):
                    db.add(MedicationDoseLog(
                        user_id=user.id,
                        medication_name=name,
                        dose_amount=amount,
                        dose_unit=unit,
                        # The column is `log_date`, not `taken_at`. Read off
                        # `\d medication_dose_logs`, not guessed from the name
                        # — §3ag paid for eleven wrong column names once.
                        log_date=(now - timedelta(days=days_ago)).date(),
                    ))

        has_rx = (await db.execute(
            select(Medication).where(Medication.user_id == user.id)
        )).scalars().first()
        if has_rx is None:
            for name, dosage in STOPPED:
                db.add(Medication(
                    user_id=user.id, name=name, dosage=dosage,
                    is_active=False,
                    start_date=date(2017, 1, 1), end_date=date(2017, 6, 1),
                ))

        await db.commit()
    print("ready:", EMAIL)


asyncio.run(main())
