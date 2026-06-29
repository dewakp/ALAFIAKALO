"""Clinician directory — ingestion (CMS seed + search worker), admin verification,
and the global map overlay. Mounted under the existing `/physicians` prefix.

Patient association is gated elsewhere (saved_physicians) on `credential_verified`;
this module produces verified records and the data that drives the drill-down map.
"""
import bisect
from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.physicians import (
    Physician, ClinicianIngestCandidate, ClinicianVerificationLog,
    VerificationStatus, PhysicianStatus,
)
from app.services import clinician_ingest, cms_nppes, osm_source
from app.services.iso_countries import resolve_country, ISO2_TO_NAME

router = APIRouter()


def _require_admin(user: User):
    if not getattr(user, "is_superuser", False):
        raise HTTPException(403, "Administrator privileges required")


def _now():
    return datetime.now(timezone.utc)


# ── Response models ─────────────────────────────────────────────────────

class MapCountry(BaseModel):
    iso2: str
    name: str
    count: int
    level: int


class DirectoryMap(BaseModel):
    total_verified: int
    by_role: dict[str, int]
    countries: list[MapCountry]
    generated_at: str


class MapPoint(BaseModel):
    id: int
    full_name: str
    clinician_role: str
    specialty: str | None = None
    city: str | None = None
    state_province: str | None = None
    latitude: float
    longitude: float
    location_precision: str | None = None
    credential_verified: bool


class DirectoryClinician(BaseModel):
    id: int
    full_name: str
    clinician_role: str
    specialty: str | None = None
    credentials: str | None = None
    city: str | None = None
    state_province: str | None = None
    country: str | None = None
    verification_status: str
    credential_verified: bool
    primary_source: str | None = None
    npi_number: str | None = None


def _levelize(counts: list[int]) -> list[int]:
    vals = sorted(v for v in counts if v > 0)
    if not vals:
        return []
    def pct(p):
        return vals[min(len(vals) - 1, int(p * len(vals)))]
    return [pct(0.4), pct(0.7), pct(0.9)]


def _level(v: int, cuts: list[int]) -> int:
    if v <= 0:
        return 0
    return 1 + bisect.bisect_right(cuts, v) if cuts else 1


# ═══════════════════════════════════════════════════════════════════════
# GLOBAL MAP OVERLAY (verified directory only)
# ═══════════════════════════════════════════════════════════════════════

@router.get("/directory/map", response_model=DirectoryMap)
async def directory_map(
    role: str | None = Query(None, description="Filter by clinician_role"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Verified clinicians aggregated by country, for the drill-down choropleth."""
    q = select(Physician.country, Physician.clinician_role).where(
        Physician.credential_verified == True,  # noqa: E712
        Physician.status == PhysicianStatus.active.value,
    )
    if role:
        q = q.where(Physician.clinician_role == role)
    rows = (await db.execute(q)).all()

    per_country: dict[str, int] = {}
    by_role: dict[str, int] = {}
    for country, crole in rows:
        iso2 = resolve_country(country)
        if iso2:
            per_country[iso2] = per_country.get(iso2, 0) + 1
        by_role[crole] = by_role.get(crole, 0) + 1

    cuts = _levelize(list(per_country.values()))
    countries = [
        MapCountry(iso2=iso2, name=ISO2_TO_NAME.get(iso2, iso2), count=n, level=_level(n, cuts))
        for iso2, n in sorted(per_country.items(), key=lambda kv: kv[1], reverse=True)
    ]
    return DirectoryMap(
        total_verified=len(rows), by_role=by_role, countries=countries,
        generated_at=_now().isoformat(),
    )


@router.get("/directory/points", response_model=list[MapPoint])
async def directory_points(
    role: str | None = Query(None),
    bbox: str | None = Query(None, description="minLat,minLon,maxLat,maxLon"),
    verified_only: bool = Query(True),
    limit: int = Query(1000, ge=1, le=5000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Directory clinicians with coordinates, for the point map (approx or exact)."""
    q = select(Physician).where(Physician.latitude.isnot(None), Physician.longitude.isnot(None))
    if verified_only:
        q = q.where(Physician.credential_verified == True)  # noqa: E712
    if role:
        q = q.where(Physician.clinician_role == role)
    if bbox:
        try:
            mnla, mnlo, mxla, mxlo = (float(x) for x in bbox.split(","))
            q = q.where(Physician.latitude >= mnla, Physician.latitude <= mxla,
                        Physician.longitude >= mnlo, Physician.longitude <= mxlo)
        except ValueError:
            raise HTTPException(422, "bbox must be 'minLat,minLon,maxLat,maxLon'")
    rows = (await db.execute(q.limit(limit))).scalars().all()
    return [MapPoint(
        id=r.id, full_name=r.full_name, clinician_role=r.clinician_role,
        specialty=r.specialty, city=r.city, state_province=r.state_province,
        latitude=r.latitude, longitude=r.longitude,
        location_precision=r.location_precision, credential_verified=r.credential_verified,
    ) for r in rows]


@router.get("/directory/country/{iso2}", response_model=list[DirectoryClinician])
async def directory_country(
    iso2: str,
    role: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Verified clinicians in one country (drill-down list)."""
    iso2 = iso2.upper()
    q = select(Physician).where(
        Physician.credential_verified == True,  # noqa: E712
        Physician.status == PhysicianStatus.active.value,
    )
    if role:
        q = q.where(Physician.clinician_role == role)
    rows = (await db.execute(q.limit(2000))).scalars().all()
    out = [r for r in rows if resolve_country(r.country) == iso2][:limit]
    return [DirectoryClinician(
        id=r.id, full_name=r.full_name, clinician_role=r.clinician_role,
        specialty=r.specialty, credentials=r.credentials, city=r.city,
        state_province=r.state_province, country=r.country,
        verification_status=r.verification_status, credential_verified=r.credential_verified,
        primary_source=r.primary_source, npi_number=r.npi_number,
    ) for r in out]


# ═══════════════════════════════════════════════════════════════════════
# ADMIN — ingestion + verification
# ═══════════════════════════════════════════════════════════════════════

@router.post("/admin/ingest/seed")
async def admin_seed(
    per_query: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Seed the directory from CMS NPPES using the default plan (admin)."""
    _require_admin(current_user)
    return await clinician_ingest.run_seed(db, per_query=per_query, actor_user_id=current_user.id)


@router.post("/admin/ingest/search")
async def admin_ingest_search(
    taxonomy_description: str | None = Query(None),
    state: str | None = Query(None),
    city: str | None = Query(None),
    last_name: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Run one NPPES search and ingest unique, licensed results (admin)."""
    _require_admin(current_user)
    cands = await cms_nppes.search_normalized(
        taxonomy_description=taxonomy_description, state=state, city=city,
        last_name=last_name, limit=limit)
    counts = await clinician_ingest.ingest_many(db, cands, actor_user_id=current_user.id)
    return {"fetched": len(cands), **counts}


@router.post("/admin/ingest/seed-all")
async def admin_seed_all(
    pages: int = Query(6, ge=1, le=6, description="NPPES pages per (taxonomy,state); 200 each"),
    current_user: User = Depends(get_current_user),
):
    """Kick off the full background seed across all specialties × states (admin).

    The CMS database holds hundreds of thousands of clinicians; this pages NPPES
    comprehensively in the background. Poll /admin/ingest/status. Idempotent.
    """
    _require_admin(current_user)
    started = clinician_ingest.start_background_seed(pages=pages)
    return {"started": started, "already_running": not started,
            "status": clinician_ingest.seed_status()}


@router.get("/admin/ingest/status")
async def admin_seed_status(current_user: User = Depends(get_current_user)):
    """Progress of the background seed (admin)."""
    _require_admin(current_user)
    return clinician_ingest.seed_status()


@router.post("/admin/ingest/stop")
async def admin_seed_stop(current_user: User = Depends(get_current_user)):
    """Request the background seed to stop after the current query (admin)."""
    _require_admin(current_user)
    clinician_ingest.stop_seed()
    return {"stopping": True}


@router.post("/admin/ingest/osm")
async def admin_ingest_osm(
    lat: float = Query(...), lon: float = Query(...),
    radius_km: float = Query(50, ge=1, le=200),
    place_type: str = Query("all"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Discover + ingest healthcare places from OpenStreetMap near a point (admin).

    A non-CMS source: lacking licenses, these land in quarantine until confirmed.
    """
    _require_admin(current_user)
    cands = await osm_source.discover_normalized(lat, lon, radius_km=radius_km, place_type=place_type)
    counts = await clinician_ingest.ingest_many(db, cands, actor_user_id=current_user.id)
    return {"source": "osm", "fetched": len(cands), **counts}


@router.post("/admin/backfill-coords")
async def admin_backfill_coords(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Give existing directory rows an approximate location from ZIP/state (admin)."""
    _require_admin(current_user)
    return await clinician_ingest.backfill_coords(db)


@router.post("/admin/ingest/reprocess-held")
async def admin_reprocess_held(
    limit: int = Query(200, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Re-check quarantined (no-license) candidates; promote any now licensed (admin)."""
    _require_admin(current_user)
    return await clinician_ingest.reprocess_held(db, limit=limit, actor_user_id=current_user.id)


@router.get("/admin/candidates")
async def admin_candidates(
    status: str | None = Query(None, description="held_no_license | inserted | merged_duplicate | pending"),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List ingestion candidates (incl. the quarantine queue) (admin)."""
    _require_admin(current_user)
    q = select(ClinicianIngestCandidate).order_by(ClinicianIngestCandidate.created_at.desc())
    if status:
        q = q.where(ClinicianIngestCandidate.status == status)
    rows = (await db.execute(q.limit(limit))).scalars().all()
    return [{
        "id": r.id, "source": r.source, "source_uid": r.source_uid,
        "full_name": r.full_name, "clinician_role": r.clinician_role,
        "specialty": r.specialty, "license_number": r.license_number,
        "license_state": r.license_state, "city": r.city, "state_province": r.state_province,
        "country": r.country, "status": r.status, "reason": r.reason,
        "matched_physician_id": r.matched_physician_id,
    } for r in rows]


@router.get("/admin/stats")
async def admin_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Directory + ingestion counts by verification status / role / candidate status (admin)."""
    _require_admin(current_user)

    async def grouped(col):
        rows = (await db.execute(select(col, func.count()).group_by(col))).all()
        return {str(k): v for k, v in rows}

    return {
        "by_verification_status": await grouped(Physician.verification_status),
        "by_role": await grouped(Physician.clinician_role),
        "candidates_by_status": await grouped(ClinicianIngestCandidate.status),
        "verified_total": (await db.execute(
            select(func.count()).select_from(Physician).where(Physician.credential_verified == True)  # noqa: E712
        )).scalar() or 0,
    }


@router.post("/{physician_id}/verify")
async def verify_clinician(
    physician_id: int,
    action: str = Body(..., embed=True, description="verify | reject"),
    notes: str | None = Body(None, embed=True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Admin verifies or rejects a clinician's license (the manual gate)."""
    _require_admin(current_user)
    p = (await db.execute(select(Physician).where(Physician.id == physician_id))).scalars().first()
    if not p:
        raise HTTPException(404, "Clinician not found")
    if action not in ("verify", "reject"):
        raise HTTPException(422, "action must be 'verify' or 'reject'")

    prev = p.verification_status
    if action == "verify":
        if not (p.license_number or "").strip():
            raise HTTPException(400, "Cannot verify a clinician with no license on record")
        p.verification_status = VerificationStatus.verified.value
        p.credential_verified = True
        p.is_verified = True
        p.verified_at = _now()
        p.verified_by_user_id = current_user.id
        p.held_reason = None
    else:
        p.verification_status = VerificationStatus.rejected.value
        p.credential_verified = False
        p.is_verified = False
        p.verified_by_user_id = current_user.id
        p.verified_at = _now()
    p.verification_notes = notes

    db.add(ClinicianVerificationLog(
        physician_id=p.id, action=f"admin_{action}", from_status=prev,
        to_status=p.verification_status, actor_user_id=current_user.id,
        source=p.primary_source, notes=notes, created_at=_now(),
    ))
    return {"id": p.id, "verification_status": p.verification_status,
            "credential_verified": p.credential_verified}
