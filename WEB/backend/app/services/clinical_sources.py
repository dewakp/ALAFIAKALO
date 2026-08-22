"""Canonical readers for clinical domains backed by MORE THAN ONE table.

Several domains in this schema are split across two tables for historical
reasons. Reading one and calling it the answer is not a style question — it silently
hides clinical facts:

    conditions   `chronic_conditions`  ← the live table (Conditions screen, EHR
                                         import, dialysis/chemo flowsheets)
                 `health_conditions`   ← LEGACY. Zero writers anywhere in the
                                         app; six readers. Any query against it
                                         alone returns nothing, forever.

    medications  `medications`             prescriptions/profile — written by the
                                           EHR/FHIR import and manual entry
                 `medication_dose_logs`    what the patient actually TOOK,
                                           written by the Medications screen

Found in production data on one patient: 0 rows in `health_conditions` against
4 in `chronic_conditions` (including End-Stage Renal Disease, severe, active),
and 2 inactive prescriptions against 921 dose logs. The clinician board showed
"No active conditions" and two stopped drugs; the AI engine, reading only the
legacy table, believed the patient had no conditions at all.

Every caller goes through this module so the board, the AI, diagnostics and the
nutrient goals cannot disagree about what a patient has or takes. A test asserts
these tables are not queried directly anywhere else — see
tests/test_clinical_sources.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.chronic_conditions import ChronicCondition, TherapySession
from app.services.flowsheet_drugs import summarize_flowsheet_drugs
from app.models.conditions import HealthCondition
from app.models.med_nutrient import MedicationDoseLog
from app.models.medications import Medication

# How far back "currently taking" looks. A dose logged inside this window counts
# as part of the current regimen.
CURRENT_MEDICATION_WINDOW_DAYS = 30


def _enum_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(getattr(value, "value", value))


@dataclass
class ConditionView:
    """One condition, from whichever table it came from."""

    name: str
    category: str | None
    severity: str | None
    diagnosed: str | None
    active: bool
    source: str  # "chronic" | "legacy"
    # Diagnosis coding. ICD-11 is what the patient selected in the app; ICD-10
    # is what an EHR/FHIR or document import carried in. Both are surfaced so a
    # clinician can see which system a code came from.
    icd11_code: str | None = None
    icd11_title: str | None = None
    icd10_code: str | None = None

    @property
    def is_severe(self) -> bool:
        return (self.severity or "").lower() in ("severe", "critical")


@dataclass
class MedicationView:
    """One medication — either taken (dose logs) or prescribed (profile)."""

    name: str
    detail: str | None
    last: str | None
    doses: int | None
    source: str  # "taken" | "prescribed"
    active: bool


def _chronic_view(c: ChronicCondition) -> ConditionView:
    return ConditionView(
        name=c.condition_name,
        category=_enum_str(c.category),
        severity=_enum_str(c.severity),
        diagnosed=str(c.diagnosis_date)[:10] if c.diagnosis_date else None,
        active=bool(c.is_active),
        source="chronic",
        icd11_code=c.icd11_code,
        icd11_title=c.icd11_title,
        icd10_code=c.icd10_code,
    )


def _legacy_view(h: HealthCondition) -> ConditionView:
    return ConditionView(
        name=h.condition_name,
        category=h.category,
        severity=h.severity,
        diagnosed=str(h.diagnosis_date) if h.diagnosis_date else None,
        active=h.status in ("active", "managed"),
        source="legacy",
        # The legacy table has no ICD-11 column and never will — it has no
        # writer at all (CLAUDE.md §3aa).
        icd10_code=h.icd10_code,
    )


# ── Conditions ───────────────────────────────────────────────────────────

async def conditions(db: AsyncSession, user_id: int, active_only: bool = False
                     ) -> list[ConditionView]:
    """Every condition for a user, from BOTH tables."""
    chronic = (await db.execute(
        select(ChronicCondition).where(ChronicCondition.user_id == user_id)
        .order_by(ChronicCondition.is_active.desc())
    )).scalars().all()
    legacy = (await db.execute(
        select(HealthCondition).where(HealthCondition.user_id == user_id)
    )).scalars().all()

    out = [_chronic_view(c) for c in chronic] + [_legacy_view(h) for h in legacy]
    return [c for c in out if c.active] if active_only else out


def conditions_sync(db: Session, user_id: int, active_only: bool = False
                    ) -> list[ConditionView]:
    """Synchronous twin, for callers holding a classic Session (ai_engine)."""
    chronic = db.query(ChronicCondition).filter(
        ChronicCondition.user_id == user_id).all()
    legacy = db.query(HealthCondition).filter(
        HealthCondition.user_id == user_id).all()

    out = [_chronic_view(c) for c in chronic] + [_legacy_view(h) for h in legacy]
    return [c for c in out if c.active] if active_only else out


# ── Medications ──────────────────────────────────────────────────────────

async def medications_taken(db: AsyncSession, user_id: int, since: date | None = None
                            ) -> list[MedicationView]:
    """What the patient actually took, most recently taken first.

    Grouped case-insensitively: the same drug arrives as both "Calcium
    Carbonate" and "Calcium carbonate", and two rows misrepresent the regimen.
    """
    since = since or (date.today() - timedelta(days=CURRENT_MEDICATION_WINDOW_DAYS))
    rows = (await db.execute(
        select(
            func.min(MedicationDoseLog.medication_name),
            func.count(MedicationDoseLog.id),
            func.max(MedicationDoseLog.log_date),
        )
        .where(MedicationDoseLog.user_id == user_id, MedicationDoseLog.log_date >= since)
        .group_by(func.lower(MedicationDoseLog.medication_name))
        .order_by(func.max(MedicationDoseLog.log_date).desc(),
                  func.count(MedicationDoseLog.id).desc())
    )).all()
    return [MedicationView(
        name=name,
        detail=f"{doses} dose{'s' if doses != 1 else ''} in this period",
        last=str(last), doses=int(doses), source="taken", active=True,
    ) for name, doses, last in rows]


async def medications_administered(db: AsyncSession, user_id: int, since: date | None = None
                                   ) -> list[MedicationView]:
    """Drugs given DURING dialysis, read off the flowsheet.

    The THIRD medication source. §3aa names two tables; this is the one nobody
    reads, and on a real record it holds a decade of ESA and IV iron:

        Epogene 1,962 sessions · Venofer 1,248 · Doxercalciferol 788
        ...and 0 of them in medication_dose_logs.

    These are administered by the unit, so they can never appear in a dose log
    the patient fills in. Omitting them is why a review of that record concluded
    "no ESA prescribed or taken" while the patient had been on one for years —
    and an ESA on board is the difference between an anaemia being treated and
    one being missed.

    `since=None` means the whole history on purpose: the question here is "what
    is this patient on", and a 90-day window on a thrice-weekly therapy answers
    a different one.
    """
    stmt = select(TherapySession).where(
        TherapySession.user_id == user_id,
        TherapySession.drugs_administered.isnot(None),
    )
    if since:
        stmt = stmt.where(TherapySession.scheduled_date >= since)
    rows = (await db.execute(stmt)).scalars().all()

    return [MedicationView(
        name=e.name,
        detail=" · ".join(x for x in (
            e.drug_class,
            f"latest {e.latest_dose}" if e.latest_dose else None,
            f"{e.sessions} session{'s' if e.sessions != 1 else ''}",
        ) if x),
        last=e.last_seen,
        doses=e.sessions,
        source="administered",
        active=True,
    ) for e in summarize_flowsheet_drugs(rows)]


async def medications_prescribed(db: AsyncSession, user_id: int, active_only: bool = False
                                 ) -> list[MedicationView]:
    """The prescription / profile list (EHR import + manual entry)."""
    stmt = select(Medication).where(Medication.user_id == user_id)
    if active_only:
        stmt = stmt.where(Medication.is_active.is_(True))
    rows = (await db.execute(
        stmt.order_by(Medication.is_active.desc(), Medication.created_at.desc())
    )).scalars().all()
    return [MedicationView(
        name=m.name,
        detail=" ".join(x for x in [m.dosage, m.dosage_unit, m.frequency] if x) or None,
        last=str(m.start_date) if m.start_date else None,
        doses=None, source="prescribed", active=bool(m.is_active),
    ) for m in rows]


async def dose_counts_by_day(db: AsyncSession, user_id: int, since: date) -> list[tuple]:
    """(day, dose count) pairs — the adherence trend.

    Lives here rather than in the caller so `medication_dose_logs` has exactly
    one reader, which is what the drift guard checks.
    """
    return (await db.execute(
        select(MedicationDoseLog.log_date, func.count(MedicationDoseLog.id))
        .where(MedicationDoseLog.user_id == user_id, MedicationDoseLog.log_date >= since)
        .group_by(MedicationDoseLog.log_date)
        .order_by(MedicationDoseLog.log_date)
    )).all()
