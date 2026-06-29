"""Link clinicians to the places they practice from.

NPPES gives each clinician a practice address. Clinicians who share an address
practice from the same place — so we dedup those addresses into `facilities`
(type 'practice'), link each clinician via `physician_facilities`, and anchor the
clinician's map coordinates to that facility. Co-located physicians then share one
real pin with a roster, instead of an overlapping cloud of identical points.

Coordinates start at the ZIP centroid (offline) and can be upgraded to the exact
street location via `geocode_practice_facilities` (bounded, Nominatim).
"""
from __future__ import annotations

import asyncio
import hashlib
import re
from datetime import datetime, timezone

from sqlalchemy import select, func, exists
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.physicians import Physician, EntityType
from app.models.facilities import Facility, PhysicianFacility, FacilityType
from app.services import geocoding

PRACTICE_SOURCE = "nppes_practice"


def _now():
    return datetime.now(timezone.utc)


def _addr_key(p) -> str | None:
    parts = [p.address_line1, p.city, p.state_province, p.postal_code]
    norm = "|".join(re.sub(r"\s+", " ", (x or "").strip().lower()) for x in parts)
    return norm if (p.address_line1 and (p.city or p.postal_code)) else None


async def link_practice_locations(db: AsyncSession, *, batch: int = 4000) -> dict:
    """Group a batch of un-linked clinicians by practice address into facilities + links."""
    rows = (await db.execute(
        select(Physician).where(
            Physician.entity_type == EntityType.clinician.value,
            Physician.address_line1.isnot(None),
            ~exists(select(PhysicianFacility.id).where(
                PhysicianFacility.physician_id == Physician.id)),
        ).limit(batch)
    )).scalars().all()

    groups: dict[str, list[Physician]] = {}
    for p in rows:
        key = _addr_key(p)
        if key:
            groups.setdefault(key, []).append(p)

    facilities_created, links_created = 0, 0
    for key, plist in groups.items():
        uid = hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
        fac = (await db.execute(
            select(Facility).where(Facility.source == PRACTICE_SOURCE,
                                   Facility.source_uid == uid))).scalars().first()
        if fac is None:
            first = plist[0]
            fac = Facility(
                name=(first.facility_name or first.address_line1 or "Medical practice")[:300],
                facility_type=FacilityType.facility.value,
                address_line1=first.address_line1, city=first.city,
                state_province=first.state_province, postal_code=first.postal_code,
                country=first.country, latitude=first.latitude, longitude=first.longitude,
                location_precision=first.location_precision,
                source=PRACTICE_SOURCE, source_uid=uid, is_active=True,
                created_at=_now(), updated_at=_now(),
            )
            db.add(fac)
            await db.flush()
            facilities_created += 1
        for p in plist:
            db.add(PhysicianFacility(
                physician_id=p.id, facility_id=fac.id, is_primary=True,
                relationship_type="practices_at", source="nppes", created_at=_now()))
            links_created += 1
            # Anchor the clinician to the practice location's coordinates.
            if fac.latitude is not None:
                p.latitude, p.longitude = fac.latitude, fac.longitude
                p.location_precision = fac.location_precision
    await db.flush()

    remaining = (await db.execute(
        select(func.count()).select_from(Physician).where(
            Physician.entity_type == EntityType.clinician.value,
            Physician.address_line1.isnot(None),
            ~exists(select(PhysicianFacility.id).where(
                PhysicianFacility.physician_id == Physician.id)),
        ))).scalar() or 0
    return {"processed": len(rows), "facilities_created": facilities_created,
            "links_created": links_created, "remaining_unlinked": remaining}


async def geocode_practice_facilities(db: AsyncSession, *, limit: int = 25) -> dict:
    """Upgrade practice-facility coordinates from ZIP centroid to exact street
    location via Nominatim (rate-limited ~1 req/s), and move linked clinicians too."""
    facs = (await db.execute(
        select(Facility).where(
            Facility.source == PRACTICE_SOURCE,
            (Facility.location_precision != "exact") | (Facility.location_precision.is_(None)),
            Facility.address_line1.isnot(None),
        ).limit(limit)
    )).scalars().all()

    upgraded = 0
    for fac in facs:
        addr = ", ".join(x for x in [fac.address_line1, fac.city, fac.state_province,
                                     fac.postal_code, fac.country] if x)
        try:
            results = await geocoding.geocode_address(addr, limit=1)
        except Exception:
            results = []
        if results:
            lat, lon = results[0]["latitude"], results[0]["longitude"]
            fac.latitude, fac.longitude, fac.location_precision = lat, lon, "exact"
            fac.updated_at = _now()
            links = (await db.execute(select(PhysicianFacility.physician_id).where(
                PhysicianFacility.facility_id == fac.id))).scalars().all()
            if links:
                for p in (await db.execute(select(Physician).where(
                        Physician.id.in_(links)))).scalars().all():
                    p.latitude, p.longitude, p.location_precision = lat, lon, "exact"
            upgraded += 1
        await asyncio.sleep(1.1)  # be polite to Nominatim
    await db.flush()
    return {"scanned": len(facs), "geocoded_exact": upgraded}
