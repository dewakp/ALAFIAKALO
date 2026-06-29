"""Clinician ingestion + dedup worker with license-hold gating.

Pipeline for every discovered/normalized candidate:

  1. Dedup — match against the live directory by NPI, else name + location.
  2. No license  → quarantine (`held_no_license`); NEVER promoted to `physicians`.
  3. License present, unique → insert into `physicians`. Trusted source (CMS) +
     license auto-verifies (patient-associable); otherwise `license_on_record`
     awaiting an admin.
  4. License present, duplicate → record provenance, upgrade verification if the
     new source is better, mark candidate `merged_duplicate`.

Every transition is written to `clinician_verification_log`. Idempotent: a
candidate whose content hash is unchanged is skipped.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session

from app.models.physicians import (
    Physician, ClinicianSourceRecord, ClinicianIngestCandidate,
    ClinicianVerificationLog, VerificationStatus, PhysicianStatus,
    TRUSTED_LICENSE_SOURCES, SPECIALTY_CATEGORIES,
)
from app.services import cms_nppes, geo_approx

# Seed plan: (taxonomy_description, [states]). Covers physicians + the other
# clinician types the directory must hold (nurses, dietitians, …).
DEFAULT_SEED_PLAN: list[tuple[str, list[str]]] = [
    ("Internal Medicine", ["MD", "NY", "CA"]),
    ("Family Medicine", ["MD", "TX"]),
    ("Nephrology", ["MD", "NY", "CA"]),
    ("Registered Nurse", ["MD", "NY"]),
    ("Nurse Practitioner", ["MD", "CA"]),
    ("Dietitian, Registered", ["MD", "NY", "CA"]),
    ("Pharmacist", ["MD"]),
]


def _now():
    return datetime.now(timezone.utc)


def _specialty_category(specialty: str | None) -> str | None:
    if not specialty:
        return None
    for category, specs in SPECIALTY_CATEGORIES.items():
        if specialty in specs:
            return category
    return None


def _log(db: AsyncSession, *, physician_id, action, from_status=None,
         to_status=None, actor_user_id=None, source=None, notes=None):
    db.add(ClinicianVerificationLog(
        physician_id=physician_id, action=action, from_status=from_status,
        to_status=to_status, actor_user_id=actor_user_id, source=source,
        notes=notes, created_at=_now(),
    ))


async def _find_match(db: AsyncSession, cand: dict) -> Physician | None:
    """Dedup: exact NPI first, then name + (postal or city/state)."""
    npi = cand.get("npi_number")
    if npi:
        m = (await db.execute(select(Physician).where(Physician.npi_number == npi))).scalars().first()
        if m:
            return m
    name = (cand.get("full_name") or "").strip()
    if not name:
        return None
    q = select(Physician).where(func.lower(Physician.full_name) == name.lower())
    postal = cand.get("postal_code")
    if postal:
        q = q.where(Physician.postal_code == postal)
    else:
        city, st = cand.get("city"), cand.get("state_province")
        if city:
            q = q.where(func.lower(Physician.city) == city.lower())
        if st:
            q = q.where(Physician.state_province == st)
    return (await db.execute(q)).scalars().first()


async def _upsert_candidate(db: AsyncSession, cand: dict) -> tuple[ClinicianIngestCandidate, bool]:
    """Get-or-create the candidate row. Returns (row, changed)."""
    existing = (await db.execute(
        select(ClinicianIngestCandidate).where(
            ClinicianIngestCandidate.source == cand["source"],
            ClinicianIngestCandidate.source_uid == cand["source_uid"],
        )
    )).scalars().first()
    fields = dict(
        npi_number=cand.get("npi_number"), full_name=cand.get("full_name"),
        clinician_role=cand.get("clinician_role"), specialty=cand.get("specialty"),
        credentials=cand.get("credentials"), license_number=cand.get("license_number"),
        license_state=cand.get("license_state"), city=cand.get("city"),
        state_province=cand.get("state_province"), postal_code=cand.get("postal_code"),
        country=cand.get("country"), phone=cand.get("phone"),
        content_hash=cand.get("content_hash"), raw_payload=cand.get("raw_payload"),
    )
    if existing is None:
        row = ClinicianIngestCandidate(source=cand["source"], source_uid=cand["source_uid"],
                                       status="pending", created_at=_now(), **fields)
        db.add(row)
        return row, True
    changed = existing.content_hash != cand.get("content_hash") or existing.status == "pending"
    for k, v in fields.items():
        setattr(existing, k, v)
    return existing, changed


def _record_provenance(db: AsyncSession, cand: dict, physician_id: int | None):
    db.add(ClinicianSourceRecord(
        physician_id=physician_id, source=cand["source"], source_uid=cand["source_uid"],
        content_hash=cand.get("content_hash"), raw_payload=cand.get("raw_payload"),
        fetched_at=_now(),
    ))


async def ingest_candidate(db: AsyncSession, cand: dict, *, actor_user_id: int | None = None) -> str:
    """Process one normalized clinician candidate. Returns the outcome status.

    Facilities (places) are NOT clinicians — they live in the separate `facilities`
    table (see app/services/facility_ingest.py) and never reach this function.
    """
    row, changed = await _upsert_candidate(db, cand)
    if not changed and row.status in ("inserted", "merged_duplicate", "rejected"):
        return "unchanged"

    has_license = bool((cand.get("license_number") or "").strip())
    source = cand["source"]
    trusted = source in TRUSTED_LICENSE_SOURCES

    match = await _find_match(db, cand)

    # ── Duplicate ──────────────────────────────────────────────────────────
    if match:
        _record_provenance(db, cand, match.id)
        # Upgrade verification if the new source is strictly better.
        if (has_license and trusted and not match.credential_verified
                and match.verification_status != VerificationStatus.rejected.value):
            prev = match.verification_status
            match.verification_status = VerificationStatus.verified.value
            match.credential_verified = True
            match.verified_at = _now()
            match.held_reason = None
            if not match.license_number:
                match.license_number = cand.get("license_number")
                match.license_state = cand.get("license_state")
            _log(db, physician_id=match.id, action="auto_verified", from_status=prev,
                 to_status=match.verification_status, source=source,
                 notes="Upgraded on trusted-source license match")
        row.status = "merged_duplicate"
        row.matched_physician_id = match.id
        row.reason = "Matched existing directory record"
        row.processed_at = _now()
        return "merged_duplicate"

    # ── No license → quarantine (held, never associated with patients) ──────
    if not has_license:
        row.status = "held_no_license"
        row.reason = "No license number on record — held until license confirmed"
        row.matched_physician_id = None
        row.processed_at = _now()
        _log(db, physician_id=None, action="held", to_status=VerificationStatus.quarantined.value,
             source=source, notes=f"{cand.get('full_name')} ({cand.get('source_uid')})")
        return "held_no_license"

    # ── Unique + licensed → insert into the directory ───────────────────────
    if trusted:
        vstatus, verified = VerificationStatus.verified.value, True
    else:
        vstatus, verified = VerificationStatus.license_on_record.value, False

    # Approximate location: real coords if the source has them, else ZIP/state centroid.
    lat, lon, precision = geo_approx.resolve(
        latitude=cand.get("latitude"), longitude=cand.get("longitude"),
        postal_code=cand.get("postal_code"), state=cand.get("state_province"),
        country=cand.get("country"),
    )

    physician = Physician(
        full_name=cand.get("full_name") or "Unknown",
        specialty=cand.get("specialty") or "Unknown",
        specialty_category=_specialty_category(cand.get("specialty")),
        clinician_role=cand.get("clinician_role") or "physician",
        credentials=cand.get("credentials"),
        npi_number=cand.get("npi_number"),
        license_number=cand.get("license_number"),
        license_state=cand.get("license_state"),
        phone=cand.get("phone"),
        address_line1=cand.get("address_line1"),
        address_line2=cand.get("address_line2"),
        city=cand.get("city"),
        state_province=cand.get("state_province"),
        postal_code=cand.get("postal_code"),
        country=cand.get("country"),
        latitude=lat,
        longitude=lon,
        location_precision=precision if lat is not None else None,
        source="imported",
        primary_source=source,
        source_id=cand.get("source_uid"),
        status=PhysicianStatus.active.value,
        verification_status=vstatus,
        credential_verified=verified,
        verified_at=_now() if verified else None,
        is_verified=verified,
    )
    db.add(physician)
    await db.flush()
    _record_provenance(db, cand, physician.id)
    row.status = "inserted"
    row.matched_physician_id = physician.id
    row.reason = None
    row.processed_at = _now()
    _log(db, physician_id=physician.id, action=("auto_verified" if verified else "ingested"),
         to_status=vstatus, source=source,
         notes=("Trusted source + license → auto-verified" if verified else "License on record; awaits admin"))
    return "inserted"


async def ingest_many(db: AsyncSession, candidates: list[dict], *, actor_user_id=None) -> dict:
    counts: dict[str, int] = {}
    for cand in candidates:
        try:
            outcome = await ingest_candidate(db, cand, actor_user_id=actor_user_id)
        except Exception as exc:  # one bad row shouldn't abort the batch
            outcome = "error"
            counts["error_detail"] = str(exc)[:200]
        counts[outcome] = counts.get(outcome, 0) + 1
    await db.flush()
    return counts


async def run_seed(db: AsyncSession, plan: list[tuple[str, list[str]]] | None = None,
                   *, per_query: int = 50, actor_user_id=None) -> dict:
    """Seed the directory from NPPES for a plan of (taxonomy, states)."""
    plan = plan or DEFAULT_SEED_PLAN
    totals: dict[str, int] = {"queries": 0, "fetched": 0}
    for taxonomy, states in plan:
        for state in states:
            cands = await cms_nppes.search_normalized(
                taxonomy_description=taxonomy, state=state, limit=min(per_query, 200))
            totals["queries"] += 1
            totals["fetched"] += len(cands)
            res = await ingest_many(db, cands, actor_user_id=actor_user_id)
            for k, v in res.items():
                if k == "error_detail":
                    totals[k] = v
                else:
                    totals[k] = totals.get(k, 0) + v
    return totals


async def backfill_coords(db: AsyncSession, *, limit: int = 100000) -> dict:
    """Give existing directory rows an approximate location from their ZIP/state."""
    rows = (await db.execute(
        select(Physician).where(Physician.latitude.is_(None)).limit(limit)
    )).scalars().all()
    updated = 0
    for p in rows:
        lat, lon, precision = geo_approx.resolve(
            postal_code=p.postal_code, state=p.state_province, country=p.country)
        if lat is not None:
            p.latitude, p.longitude, p.location_precision = lat, lon, precision
            updated += 1
    await db.flush()
    return {"scanned": len(rows), "geocoded": updated}


# ═══════════════════════════════════════════════════════════════════════
# SCALED BACKGROUND SEED — comprehensive taxonomies × all states, paginated.
# The CMS database holds hundreds of thousands of clinicians; this pages
# through NPPES (skip 0..1000 × limit 200) for every (taxonomy, state).
# Idempotent + resumable: dedup makes re-runs cheap, so a restart just resumes.
# ═══════════════════════════════════════════════════════════════════════

US_STATES = [
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA", "HI", "ID",
    "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO",
    "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA",
    "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "PR",
]

# NUCC taxonomy descriptions (NPPES). Physicians across specialties + other clinicians.
COMPREHENSIVE_TAXONOMIES = [
    "Internal Medicine", "Family Medicine", "Pediatrics", "Obstetrics & Gynecology",
    "Cardiovascular Disease", "Dermatology", "Endocrinology, Diabetes & Metabolism",
    "Gastroenterology", "Nephrology", "Neurology", "Hematology & Oncology",
    "Psychiatry", "Pulmonary Disease", "Rheumatology", "General Surgery",
    "Orthopaedic Surgery", "Anesthesiology", "Emergency Medicine",
    "Diagnostic Radiology", "Ophthalmology", "Urology", "Otolaryngology",
    "Allergy & Immunology", "Infectious Disease", "Geriatric Medicine",
    "Physical Medicine & Rehabilitation", "Nurse Practitioner", "Registered Nurse",
    "Physician Assistant", "Dietitian, Registered", "Pharmacist",
    "Physical Therapist", "Occupational Therapist", "Clinical Psychologist",
    "Social Worker", "Speech-Language Pathologist", "Optometrist", "Podiatrist",
    "Chiropractor", "Dentist",
]

_SEED_STATUS: dict = {
    "running": False, "started_at": None, "finished_at": None,
    "queries_total": 0, "queries_done": 0, "fetched": 0,
    "inserted": 0, "held_no_license": 0, "merged_duplicate": 0, "unchanged": 0,
    "errors": 0, "current": None,
}


def seed_status() -> dict:
    return dict(_SEED_STATUS)


def stop_seed() -> None:
    _SEED_STATUS["running"] = False


async def _run_full_seed(taxonomies: list[str], states: list[str], pages: int):
    st = _SEED_STATUS
    st.update(running=True, started_at=_now().isoformat(), finished_at=None,
              queries_total=len(taxonomies) * len(states), queries_done=0,
              fetched=0, inserted=0, held_no_license=0, merged_duplicate=0,
              unchanged=0, errors=0, current=None)
    try:
        for tax in taxonomies:
            for state in states:
                if not st["running"]:
                    return
                st["current"] = f"{tax} / {state}"
                try:
                    async with async_session() as db:
                        for page in range(pages):
                            cands = await cms_nppes.search_normalized(
                                taxonomy_description=tax, state=state,
                                limit=200, skip=page * 200)
                            if not cands:
                                break
                            st["fetched"] += len(cands)
                            res = await ingest_many(db, cands)
                            for k in ("inserted", "held_no_license", "merged_duplicate", "unchanged"):
                                st[k] += res.get(k, 0)
                            st["errors"] += res.get("error", 0)
                            if len(cands) < 200:
                                break
                        await db.commit()
                except Exception:
                    st["errors"] += 1
                st["queries_done"] += 1
                await asyncio.sleep(0.05)  # be polite to NPPES
    finally:
        st["running"] = False
        st["finished_at"] = _now().isoformat()
        st["current"] = None


def start_background_seed(taxonomies: list[str] | None = None,
                          states: list[str] | None = None, pages: int = 6) -> bool:
    """Kick off the full seed as a background task. Returns False if already running."""
    if _SEED_STATUS["running"]:
        return False
    asyncio.create_task(_run_full_seed(
        taxonomies or COMPREHENSIVE_TAXONOMIES, states or US_STATES, max(1, min(pages, 6))))
    return True


async def reprocess_held(db: AsyncSession, *, limit: int = 200, actor_user_id=None) -> dict:
    """Re-fetch held (no-license) candidates from NPPES; promote any now licensed."""
    held = (await db.execute(
        select(ClinicianIngestCandidate)
        .where(ClinicianIngestCandidate.status == "held_no_license",
               ClinicianIngestCandidate.npi_number.isnot(None))
        .limit(limit)
    )).scalars().all()
    counts: dict[str, int] = {"rechecked": 0}
    for cand_row in held:
        counts["rechecked"] += 1
        rows = await cms_nppes.search_nppes(number=cand_row.npi_number)
        norm = [c for c in (cms_nppes.normalize(r) for r in rows) if c]
        if norm:
            outcome = await ingest_candidate(db, norm[0], actor_user_id=actor_user_id)
            counts[outcome] = counts.get(outcome, 0) + 1
    await db.flush()
    return counts
