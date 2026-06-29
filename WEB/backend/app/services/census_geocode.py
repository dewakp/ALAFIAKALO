"""Bulk geocode US practice facilities via the free US Census batch geocoder.

The Census geocoder accepts up to 10,000 addresses per request (no key, built for
bulk) — far better than Nominatim (1 req/s) for upgrading practice-facility
coordinates from ZIP centroid to exact street locations. US addresses only, which
matches NPPES. Linked clinicians are moved to the facility's exact location too.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

import httpx
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.facilities import Facility

CENSUS_URL = "https://geocoding.geo.census.gov/geocoder/locations/addressbatch"
PRACTICE_SOURCE = "nppes_practice"


def _now():
    return datetime.now(timezone.utc)


async def bulk_geocode_practices(db: AsyncSession, *, limit: int = 5000) -> dict:
    """Upgrade up to `limit` practice facilities to exact street coordinates."""
    facs = (await db.execute(
        select(Facility).where(
            Facility.source == PRACTICE_SOURCE,
            (Facility.location_precision != "exact") | (Facility.location_precision.is_(None)),
            Facility.address_line1.isnot(None),
            Facility.country.in_(["United States", "US", "USA", None]),
        ).limit(min(limit, 10000))
    )).scalars().all()
    if not facs:
        return {"scanned": 0, "matched": 0, "no_match": 0, "remaining": 0}

    # Build the Census CSV: Unique ID, Street, City, State, ZIP (no header).
    buf = io.StringIO()
    writer = csv.writer(buf)
    by_id = {}
    for f in facs:
        writer.writerow([f.id, f.address_line1 or "", f.city or "",
                         f.state_province or "", (f.postal_code or "")[:5]])
        by_id[str(f.id)] = f

    try:
        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(
                CENSUS_URL,
                files={"addressFile": ("addresses.csv", buf.getvalue(), "text/csv")},
                data={"benchmark": "Public_AR_Current"},
            )
            resp.raise_for_status()
            text = resp.text
    except httpx.HTTPError as exc:
        return {"error": f"Census geocoder unavailable: {exc}", "scanned": len(facs),
                "matched": 0, "no_match": 0}

    matched = 0
    for row in csv.reader(io.StringIO(text)):
        # row: id, input, status, [matchtype, matched_addr, "lon,lat", tigerid, side]
        if len(row) < 6 or row[2] != "Match":
            continue
        fac = by_id.get(row[0])
        if not fac:
            continue
        try:
            lon_str, lat_str = row[5].split(",")
            lat, lon = float(lat_str), float(lon_str)
        except (ValueError, IndexError):
            continue
        fac.latitude, fac.longitude, fac.location_precision = lat, lon, "exact"
        fac.updated_at = _now()
        matched += 1
    await db.flush()

    # Move linked clinicians to their (now exact) practice facility — one bulk UPDATE.
    if matched:
        await db.execute(text("""
            UPDATE physicians p
            SET latitude = f.latitude, longitude = f.longitude, location_precision = 'exact'
            FROM physician_facilities pf
            JOIN facilities f ON f.id = pf.facility_id
            WHERE pf.physician_id = p.id AND pf.is_primary = TRUE
              AND f.source = :src AND f.location_precision = 'exact'
              AND p.location_precision IS DISTINCT FROM 'exact'
        """), {"src": PRACTICE_SOURCE})

    remaining = (await db.execute(
        select(func.count()).select_from(Facility).where(
            Facility.source == PRACTICE_SOURCE,
            (Facility.location_precision != "exact") | (Facility.location_precision.is_(None)),
            Facility.address_line1.isnot(None),
        ))).scalar() or 0
    return {"scanned": len(facs), "matched": matched,
            "no_match": len(facs) - matched, "remaining": remaining}
