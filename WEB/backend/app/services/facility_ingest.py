"""Ingest healthcare facilities (places) into the separate `facilities` directory.

Facilities are NOT clinicians and never enter `physicians`. OpenStreetMap is the
current source; the pipeline is source-agnostic (normalized dicts with source +
source_uid), dedups on (source, source_uid), and geocodes (OSM has real coords).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.facilities import Facility, FacilityType
from app.services import osm_source, geo_approx

# OSM amenity → FacilityType.
_TYPE_MAP = {
    "hospital": FacilityType.hospital.value, "clinic": FacilityType.clinic.value,
    "pharmacy": FacilityType.pharmacy.value, "dentist": FacilityType.dental.value,
    "doctors": FacilityType.doctors_office.value,
}


def _now():
    return datetime.now(timezone.utc)


async def _ingest_one(db: AsyncSession, cand: dict) -> str:
    source, uid = cand["source"], cand["source_uid"]
    existing = (await db.execute(
        select(Facility).where(Facility.source == source, Facility.source_uid == uid)
    )).scalars().first()

    lat, lon, precision = geo_approx.resolve(
        latitude=cand.get("latitude"), longitude=cand.get("longitude"),
        postal_code=cand.get("postal_code"), state=cand.get("state_province"),
        country=cand.get("country"))
    ftype = _TYPE_MAP.get(cand.get("facility_type"), FacilityType.facility.value)

    if existing:
        existing.name = cand.get("full_name") or existing.name
        existing.facility_type = ftype
        existing.phone = cand.get("phone") or existing.phone
        existing.latitude, existing.longitude = lat, lon
        existing.location_precision = precision if lat is not None else None
        return "updated"

    db.add(Facility(
        name=cand.get("full_name") or "Unknown facility",
        facility_type=ftype,
        phone=cand.get("phone"),
        website=cand.get("website"),
        address_line1=cand.get("address_line1"),
        city=cand.get("city"), state_province=cand.get("state_province"),
        postal_code=cand.get("postal_code"), country=cand.get("country"),
        latitude=lat, longitude=lon,
        location_precision=precision if lat is not None else None,
        source=source, source_uid=uid, is_active=True,
        created_at=_now(), updated_at=_now(),
    ))
    return "inserted"


async def ingest_osm(db: AsyncSession, lat: float, lon: float, *,
                     radius_km: float = 50, place_type: str = "all") -> dict:
    """Discover OSM healthcare places near a point and upsert them as facilities."""
    cands = await osm_source.discover_normalized(lat, lon, radius_km=radius_km, place_type=place_type)
    counts: dict[str, int] = {"fetched": len(cands)}
    for cand in cands:
        try:
            outcome = await _ingest_one(db, cand)
        except Exception:
            outcome = "error"
        counts[outcome] = counts.get(outcome, 0) + 1
    await db.flush()
    return counts
