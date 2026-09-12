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
from app.services.flowsheet_drugs import (
    canonical_drug_name,
    parse_drugs_administered,
    summarize_flowsheet_drugs,
)
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

    In centre these are given by staff and so never appear in a dose log the
    patient fills in. On HHD the patient runs at home and self-administers, so
    the same drug CAN land in both sources — that is two records of one event,
    not two doses, and neither source may be dropped on the assumption that the
    other covers it. Omitting this one is why a review of that record concluded
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


@dataclass
class UnifiedMedicationView:
    """One drug, with every source that attests to it folded together.

    The medication picture lives in four places — a prescription, a portal
    import, a dose the patient logged, and a drug written on a treatment
    flowsheet — and until this existed each screen showed a subset and called
    it the list. A patient on Venofer for five years could read "no iron
    prescribed" because the only record of it was flowsheet free text.
    """

    name: str                     # canonical name
    drug_class: str | None
    written_as: list[str]         # every spelling seen, so nothing is hidden
    sources: list[str]            # prescribed | imported | logged | administered
    active: bool
    dose: str | None
    first: str | None
    last: str | None
    days: int                     # distinct days with at least one administration
    by_source: dict[str, int]     # raw record count per source, undeduplicated
    detail: str | None


#: Sources that record an ADMINISTRATION (a dose that happened) rather than an
#: order (a dose that should happen). Only these contribute to `days`.
_ADMINISTRATION_SOURCES = ("logged", "administered")


async def medications_unified(db: AsyncSession, user_id: int, since: date | None = None
                              ) -> list[UnifiedMedicationView]:
    """THE medication list: every source, harmonised, one row per drug.

    Four sources, and a patient's drug can be in any combination of them:

        prescribed    `medications`, entered by the patient or their clinician
        imported      `medications` with a `source` tag — FHIR/portal import
        logged        `medication_dose_logs`, doses the patient recorded
        administered  `therapy_sessions.drugs_administered`, the flowsheet

    Two distinct kinds of duplicate had to die for this to be one record:

    1. NAME. The same drug is written "Venofer" on a flowsheet, "venofer" in a
       dose log and "Iron sucrose" by a FHIR import. Grouping on the raw string
       — or on `lower()`, which is all the screen used to do — reports three
       drugs where the patient is on one. Every source is folded through
       `canonical_drug_name` first.

    2. EVENT. A drug given during a run is written on the flowsheet AND, when
       the patient does not see it on their screen, logged by hand as well.
       That is one administration with two records, and counting records would
       report a double dose that never happened.

    `days` is therefore the count of distinct DAYS on which the drug was given,
    unioned across sources — a number that cannot double-count a day recorded
    twice. It deliberately does not try to be a dose count: two sources
    disagreeing about how many times a drug was given on one day is not
    something this function can resolve, and inventing a total would be a
    guess. The undeduplicated per-source counts stay in `by_source` so the
    discrepancy is visible rather than smoothed away.

    `since=None` means the whole history, on purpose: the question this answers
    is "what is this patient on", and a 90-day window on a thrice-weekly
    therapy answers a different one.
    """
    buckets: dict[str, dict[str, Any]] = {}

    def bucket(raw_name: str) -> dict[str, Any] | None:
        canon, drug_class, recognised = canonical_drug_name(raw_name or "")
        if not canon:
            return None
        # Bucket on a CASE-FOLDED key.
        #
        # `canonical_drug_name` returns an unrecognised name exactly as it was
        # written — correctly, because guessing a drug name is worse than
        # leaving it alone. But bucketing on that string then splits the same
        # drug by capitalisation: this record held "Calcium Carbonate" (422
        # days) and "Calcium carbonate" (5 days) as two medications, which is
        # the precise duplicate this function exists to remove and the one the
        # dose-log grouping was already careful about.
        #
        # The fix is not an alias entry — that only ever covers the drug
        # someone thought of. Folding case covers every drug, including the
        # ones nobody has written down yet.
        key = canon.casefold()
        b = buckets.setdefault(key, {
            "name": canon, "drug_class": drug_class, "written_as": [],
            "sources": [], "active": False, "dose": None,
            "dates": set(), "by_source": {}, "details": [],
            "recognised": recognised,
        })
        # A recognised spelling is authoritative over a raw one: once RxNorm's
        # name for the drug is known, show that rather than whatever the first
        # source happened to type.
        if recognised and not b["recognised"]:
            b["name"] = canon
            b["recognised"] = True
        if drug_class and not b["drug_class"]:
            b["drug_class"] = drug_class
        if raw_name and raw_name not in b["written_as"]:
            b["written_as"].append(raw_name)
        return b

    def note(b: dict[str, Any], source: str) -> None:
        if source not in b["sources"]:
            b["sources"].append(source)
        b["by_source"][source] = b["by_source"].get(source, 0) + 1

    # ── 1 + 2. Prescriptions and portal imports ────────────────────────────
    # Same table; `source` tells them apart. An imported row is a statement by
    # an outside system, not by this patient, and the screen must be able to
    # say which — but both are still this drug.
    for m in (await db.execute(
        select(Medication).where(Medication.user_id == user_id)
    )).scalars().all():
        b = bucket(m.name)
        if b is None:
            continue
        note(b, "imported" if m.source else "prescribed")
        if m.is_active:
            b["active"] = True
        if not b["dose"]:
            b["dose"] = " ".join(x for x in (m.dosage, m.dosage_unit) if x) or None
        if m.source:
            b["details"].append(str(m.source))

    # ── 3. Dose logs — what the patient recorded taking ────────────────────
    stmt = select(
        MedicationDoseLog.medication_name, MedicationDoseLog.log_date,
        MedicationDoseLog.dose_amount, MedicationDoseLog.dose_unit,
    ).where(MedicationDoseLog.user_id == user_id)
    if since:
        stmt = stmt.where(MedicationDoseLog.log_date >= since)
    for name, log_date, amount, unit in (await db.execute(stmt)).all():
        b = bucket(name)
        if b is None:
            continue
        note(b, "logged")
        if log_date:
            b["dates"].add(str(log_date)[:10])
        if not b["dose"] and amount is not None:
            b["dose"] = f"{amount}{' ' + unit if unit else ''}"

    # ── 4. The flowsheet — drugs given during a treatment ──────────────────
    # Not "what the unit gave": on home haemodialysis the patient runs at home
    # and gives these to themselves. The record states the treatment, not the
    # setting, and this must not claim otherwise.
    fstmt = select(TherapySession).where(
        TherapySession.user_id == user_id,
        TherapySession.drugs_administered.isnot(None),
    )
    if since:
        fstmt = fstmt.where(TherapySession.scheduled_date >= since)
    for session in (await db.execute(fstmt)).scalars().all():
        stamp = str(session.scheduled_date)[:10] if session.scheduled_date else None
        for drug in parse_drugs_administered(session.drugs_administered):
            b = bucket(drug.name)
            if b is None:
                continue
            note(b, "administered")
            b["active"] = True
            if stamp:
                b["dates"].add(stamp)
            if drug.dose and not b["dose"]:
                b["dose"] = drug.dose

    out: list[UnifiedMedicationView] = []
    for b in buckets.values():
        dates = sorted(b["dates"])
        given = sum(b["by_source"].get(s, 0) for s in _ADMINISTRATION_SOURCES)
        detail = " · ".join(x for x in (
            b["drug_class"],
            f"{given} record{'s' if given != 1 else ''}" if given else None,
            *dict.fromkeys(b["details"]),
        ) if x) or None
        out.append(UnifiedMedicationView(
            name=b["name"], drug_class=b["drug_class"],
            written_as=b["written_as"], sources=b["sources"],
            active=b["active"], dose=b["dose"],
            first=dates[0] if dates else None,
            last=dates[-1] if dates else None,
            days=len(dates), by_source=b["by_source"], detail=detail,
        ))
    # Most-recently-given first; drugs with no administration date (a
    # prescription never yet taken) sort last but are NOT dropped — "prescribed
    # and never taken" is a clinical fact, not an empty row.
    out.sort(key=lambda v: (v.last or "", v.days), reverse=True)
    return out


@dataclass
class AdministrationView:
    """One administration on one day, from whichever source recorded it."""

    date: str
    name: str                   # canonical
    written_as: str             # the name as that source wrote it
    dose: str | None
    time: str | None            # dose logs carry one; a flowsheet does not
    drug_class: str | None
    sources: list[str]          # logged | administered — both if recorded twice
    dose_log_id: int | None     # set when a dose log backs this row (deletable)


async def administrations_on_day(db: AsyncSession, user_id: int, day: date
                                 ) -> list[AdministrationView]:
    """What was actually given on ONE day — dose logs and flowsheet, merged.

    The day view used to read `medication_dose_logs` alone, so a day whose only
    record was the flowsheet rendered as "No intake logged for this date". That
    is the screen that causes the duplicate: a patient who was given Iron
    sucrose at their treatment, and is told their record for that day is empty,
    logs it by hand. The app then holds two records of one dose and the count
    of what they took is wrong.

    A drug recorded in BOTH sources on the same day is ONE row carrying both
    source tags — not two rows, and not a silent drop of either. Where a dose
    log backs the row its id rides along, because that row stays deletable;
    a flowsheet administration is not this screen's to delete.
    """
    merged: dict[str, AdministrationView] = {}
    day_str = str(day)[:10]

    logs = (await db.execute(
        select(MedicationDoseLog).where(
            MedicationDoseLog.user_id == user_id,
            MedicationDoseLog.log_date == day,
        )
    )).scalars().all()
    for log in logs:
        canon, drug_class, _ = canonical_drug_name(log.medication_name or "")
        if not canon:
            continue
        dose = None
        if log.dose_amount is not None:
            dose = f"{log.dose_amount}{' ' + log.dose_unit if log.dose_unit else ''}"
        merged[canon.lower()] = AdministrationView(
            date=day_str, name=canon, written_as=log.medication_name or canon,
            dose=dose,
            time=str(log.log_time)[:5] if log.log_time else None,
            drug_class=drug_class, sources=["logged"], dose_log_id=log.id,
        )

    sessions = (await db.execute(
        select(TherapySession).where(
            TherapySession.user_id == user_id,
            TherapySession.drugs_administered.isnot(None),
            func.date(TherapySession.scheduled_date) == day,
        )
    )).scalars().all()
    for session in sessions:
        for drug in parse_drugs_administered(session.drugs_administered):
            canon, drug_class, _ = canonical_drug_name(drug.name or "")
            if not canon:
                continue
            key = canon.lower()
            existing = merged.get(key)
            if existing is not None:
                # Same drug, same day, two records — one administration. Tag it
                # with both sources rather than listing it twice.
                if "administered" not in existing.sources:
                    existing.sources.append("administered")
                existing.dose = existing.dose or drug.dose
                existing.drug_class = existing.drug_class or drug_class
                continue
            merged[key] = AdministrationView(
                date=day_str, name=canon, written_as=drug.name or canon,
                dose=drug.dose, time=None, drug_class=drug_class,
                sources=["administered"], dose_log_id=None,
            )

    return sorted(merged.values(), key=lambda a: (a.time or "99:99", a.name))


async def administration_days(db: AsyncSession, user_id: int, since: date | None = None
                              ) -> list[str]:
    """Every date with at least one administration, from any source.

    Feeds the calendar dots. Reading dose logs alone marked treatment days as
    empty on a calendar whose whole job is to say which days have something on
    them.
    """
    stmt = select(func.distinct(MedicationDoseLog.log_date)).where(
        MedicationDoseLog.user_id == user_id)
    if since:
        stmt = stmt.where(MedicationDoseLog.log_date >= since)
    days = {str(d)[:10] for (d,) in (await db.execute(stmt)).all() if d}

    fstmt = select(func.distinct(func.date(TherapySession.scheduled_date))).where(
        TherapySession.user_id == user_id,
        TherapySession.drugs_administered.isnot(None),
    )
    if since:
        fstmt = fstmt.where(TherapySession.scheduled_date >= since)
    days |= {str(d)[:10] for (d,) in (await db.execute(fstmt)).all() if d}
    return sorted(days)


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
