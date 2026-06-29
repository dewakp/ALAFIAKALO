"""Facility directory API — places (hospitals, clinics, pharmacies, …).

Separate from clinicians (`/physicians`): a facility is a place, never a licensed
individual and never a patient's clinician. `physician_facilities` links the two
("a clinician practices at a facility").
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.facilities import Facility, PhysicianFacility
from app.models.physicians import Physician
from app.services import facility_ingest, practice_linking, census_geocode

router = APIRouter()


def _require_admin(user: User):
    if not getattr(user, "is_superuser", False):
        raise HTTPException(403, "Administrator privileges required")


class FacilityOut(BaseModel):
    id: int
    name: str
    facility_type: str
    phone: str | None = None
    website: str | None = None
    address_line1: str | None = None
    city: str | None = None
    state_province: str | None = None
    postal_code: str | None = None
    country: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    location_precision: str | None = None
    source: str | None = None

    model_config = {"from_attributes": True}


class FacilityPoint(BaseModel):
    id: int
    name: str
    facility_type: str
    city: str | None = None
    state_province: str | None = None
    latitude: float
    longitude: float
    location_precision: str | None = None
    clinician_count: int = 0


async def _clinician_counts(db: AsyncSession, facility_ids: list[int]) -> dict[int, int]:
    if not facility_ids:
        return {}
    rows = (await db.execute(
        select(PhysicianFacility.facility_id, func.count())
        .where(PhysicianFacility.facility_id.in_(facility_ids))
        .group_by(PhysicianFacility.facility_id))).all()
    return {fid: n for fid, n in rows}


@router.get("/", response_model=list[FacilityOut])
async def list_facilities(
    q: str | None = Query(None, description="Name search"),
    facility_type: str | None = Query(None),
    city: str | None = Query(None),
    country: str | None = Query(None),
    limit: int = Query(10, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Search / list facilities (paginated)."""
    stmt = select(Facility).where(Facility.is_active == True)  # noqa: E712
    if q:
        stmt = stmt.where(Facility.name.ilike(f"%{q}%"))
    if facility_type:
        stmt = stmt.where(Facility.facility_type == facility_type)
    if city:
        stmt = stmt.where(Facility.city.ilike(f"%{city}%"))
    if country:
        stmt = stmt.where(Facility.country.ilike(f"%{country}%"))
    stmt = stmt.order_by(Facility.name).offset(offset).limit(limit)
    return (await db.execute(stmt)).scalars().all()


@router.get("/points", response_model=list[FacilityPoint])
async def facility_points(
    facility_type: str | None = Query(None),
    bbox: str | None = Query(None, description="minLat,minLon,maxLat,maxLon"),
    limit: int = Query(1000, ge=1, le=5000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Facility map points."""
    q = select(Facility).where(
        Facility.is_active == True,  # noqa: E712
        Facility.latitude.isnot(None), Facility.longitude.isnot(None))
    if facility_type:
        q = q.where(Facility.facility_type == facility_type)
    if bbox:
        try:
            mnla, mnlo, mxla, mxlo = (float(x) for x in bbox.split(","))
            q = q.where(Facility.latitude >= mnla, Facility.latitude <= mxla,
                        Facility.longitude >= mnlo, Facility.longitude <= mxlo)
        except ValueError:
            raise HTTPException(422, "bbox must be 'minLat,minLon,maxLat,maxLon'")
    rows = (await db.execute(q.limit(limit))).scalars().all()
    counts = await _clinician_counts(db, [r.id for r in rows])
    return [FacilityPoint(
        id=r.id, name=r.name, facility_type=r.facility_type, city=r.city,
        state_province=r.state_province, latitude=r.latitude, longitude=r.longitude,
        location_precision=r.location_precision, clinician_count=counts.get(r.id, 0)) for r in rows]


@router.get("/stats")
async def facility_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    total = (await db.execute(select(func.count()).select_from(Facility))).scalar() or 0
    by_type = {str(k): v for k, v in (await db.execute(
        select(Facility.facility_type, func.count()).group_by(Facility.facility_type))).all()}
    return {"total": total, "by_type": by_type}


@router.get("/{facility_id}/clinicians")
async def facility_clinicians(
    facility_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """The roster of clinicians who practice at a facility."""
    rows = (await db.execute(
        select(Physician).join(PhysicianFacility, PhysicianFacility.physician_id == Physician.id)
        .where(PhysicianFacility.facility_id == facility_id)
        .order_by(Physician.full_name).limit(500))).scalars().all()
    return [{
        "id": p.id, "full_name": p.full_name, "clinician_role": p.clinician_role,
        "specialty": p.specialty, "credentials": p.credentials,
        "credential_verified": p.credential_verified,
    } for p in rows]


@router.post("/admin/link-practices")
async def admin_link_practices(
    batch: int = Query(4000, ge=100, le=20000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Group clinicians by practice address into facilities + links (admin)."""
    _require_admin(current_user)
    return await practice_linking.link_practice_locations(db, batch=batch)


@router.post("/admin/geocode-practices")
async def admin_geocode_practices(
    limit: int = Query(5000, ge=1, le=10000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upgrade practice-facility coords ZIP centroid → exact street, in bulk via the
    free US Census batch geocoder (admin). Returns matched / remaining counts."""
    _require_admin(current_user)
    return await census_geocode.bulk_geocode_practices(db, limit=limit)


@router.get("/{facility_id}", response_model=FacilityOut)
async def get_facility(
    facility_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    f = (await db.execute(select(Facility).where(Facility.id == facility_id))).scalars().first()
    if not f:
        raise HTTPException(404, "Facility not found")
    return f


@router.post("/discover-here")
async def discover_here(
    lat: float = Query(...), lon: float = Query(...),
    radius_km: float = Query(10, ge=1, le=50),
    place_type: str = Query("all"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """On-demand: discover OSM healthcare facilities for the current map area and
    add them to the shared facility directory. Any signed-in user (OSM is public,
    deduped, idempotent)."""
    return await facility_ingest.ingest_osm(db, lat, lon, radius_km=radius_km, place_type=place_type)


@router.post("/admin/ingest-osm")
async def admin_ingest_osm(
    lat: float = Query(...), lon: float = Query(...),
    radius_km: float = Query(50, ge=1, le=200),
    place_type: str = Query("all"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Discover + ingest OpenStreetMap healthcare facilities near a point (admin)."""
    _require_admin(current_user)
    return await facility_ingest.ingest_osm(db, lat, lon, radius_km=radius_km, place_type=place_type)
