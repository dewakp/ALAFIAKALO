"""Geocoding & geo-search service — free OpenStreetMap / Nominatim backend.

This module provides:
  - Forward geocoding  (address string → lat/lng)
  - Reverse geocoding  (lat/lng → address)
  - Nearby place search via Overpass API (find clinics/hospitals/pharmacies)
  - Haversine distance computation for DB-level radius filtering

All services are free, no API key required.  Rate-limited to 1 req/s per
Nominatim usage policy — we respect that with an async semaphore.
"""

from __future__ import annotations

import asyncio
import math
from typing import Any

import httpx

# ── Constants ──────────────────────────────────────────────────────

NOMINATIM_URL = "https://nominatim.openstreetmap.org"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "ALAFIA-HealthApp/1.0 (contact@alafia.app)"

# Rate limiter: Nominatim requires max 1 req/s
_nominatim_semaphore = asyncio.Semaphore(1)
_last_request_time: float = 0.0

EARTH_RADIUS_KM = 6371.0


# ── Haversine (pure math — used in SQL & Python) ──────────────────

def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return distance in kilometres between two GPS points."""
    rlat1, rlon1, rlat2, rlon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = rlat2 - rlat1
    dlon = rlon2 - rlon1
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def bounding_box(lat: float, lon: float, radius_km: float) -> tuple[float, float, float, float]:
    """Return (min_lat, max_lat, min_lon, max_lon) bounding box around a point."""
    delta_lat = radius_km / EARTH_RADIUS_KM * (180 / math.pi)
    delta_lon = radius_km / (EARTH_RADIUS_KM * math.cos(math.radians(lat))) * (180 / math.pi)
    return (lat - delta_lat, lat + delta_lat, lon - delta_lon, lon + delta_lon)


# ── Nominatim helpers ─────────────────────────────────────────────

async def _rate_limited_request(client: httpx.AsyncClient, url: str, params: dict) -> Any:
    """Make a rate-limited request to Nominatim (max 1/s)."""
    global _last_request_time
    async with _nominatim_semaphore:
        now = asyncio.get_event_loop().time()
        wait = max(0, 1.0 - (now - _last_request_time))
        if wait > 0:
            await asyncio.sleep(wait)
        resp = await client.get(url, params=params, headers={"User-Agent": USER_AGENT})
        _last_request_time = asyncio.get_event_loop().time()
        resp.raise_for_status()
        return resp.json()


async def geocode_address(address: str, limit: int = 5) -> list[dict]:
    """Forward geocode: address string → list of {lat, lon, display_name, …}.

    Uses the free Nominatim service (OpenStreetMap).
    """
    async with httpx.AsyncClient(timeout=10) as client:
        data = await _rate_limited_request(client, f"{NOMINATIM_URL}/search", {
            "q": address,
            "format": "jsonv2",
            "addressdetails": 1,
            "limit": limit,
        })
    results = []
    for item in data:
        addr = item.get("address", {})
        results.append({
            "display_name": item.get("display_name", ""),
            "latitude": float(item["lat"]),
            "longitude": float(item["lon"]),
            "address_type": item.get("type"),
            "city": addr.get("city") or addr.get("town") or addr.get("village"),
            "state": addr.get("state"),
            "country": addr.get("country"),
            "postal_code": addr.get("postcode"),
        })
    return results


async def reverse_geocode(lat: float, lon: float) -> dict | None:
    """Reverse geocode: lat/lon → address dict.

    Returns None if no result found.
    """
    async with httpx.AsyncClient(timeout=10) as client:
        data = await _rate_limited_request(client, f"{NOMINATIM_URL}/reverse", {
            "lat": lat,
            "lon": lon,
            "format": "jsonv2",
            "addressdetails": 1,
        })
    if "error" in data:
        return None
    addr = data.get("address", {})
    return {
        "display_name": data.get("display_name", ""),
        "latitude": float(data["lat"]),
        "longitude": float(data["lon"]),
        "address_type": data.get("type"),
        "city": addr.get("city") or addr.get("town") or addr.get("village"),
        "state": addr.get("state"),
        "country": addr.get("country"),
        "postal_code": addr.get("postcode"),
    }


# ── Overpass API — discover nearby healthcare places ──────────────

async def search_nearby_healthcare(
    lat: float, lon: float, radius_m: int = 50000, place_type: str = "all"
) -> list[dict]:
    """Search OpenStreetMap for healthcare facilities near a point.

    place_type: 'hospital', 'clinic', 'pharmacy', 'dentist', 'doctors', or 'all'
    radius_m: search radius in metres (default 50 km).
    """
    type_filters = {
        "hospital": '["amenity"="hospital"]',
        "clinic": '["amenity"="clinic"]',
        "pharmacy": '["amenity"="pharmacy"]',
        "dentist": '["amenity"="dentist"]',
        "doctors": '["amenity"="doctors"]',
    }

    if place_type == "all":
        # Overpass union: statements are concatenated inside ( … ); — NOT pipe-separated.
        filters = "\n      ".join(
            f'node["amenity"="{t}"](around:{radius_m},{lat},{lon});'
            for t in type_filters
        )
    else:
        tag = type_filters.get(place_type, '["healthcare"]')
        filters = f'node{tag}(around:{radius_m},{lat},{lon});'

    # Note: the union group MUST be terminated with ");" — Overpass 400s otherwise.
    query = f"""
    [out:json][timeout:25];
    (
      {filters}
    );
    out body 100;
    """

    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(OVERPASS_URL, data={"data": query}, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        data = resp.json()

    results = []
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        el_lat = el.get("lat")
        el_lon = el.get("lon")
        if not el_lat or not el_lon:
            continue
        results.append({
            "osm_id": str(el.get("id", "")),
            "name": tags.get("name", "Unknown"),
            "amenity_type": tags.get("amenity", "healthcare"),
            "latitude": el_lat,
            "longitude": el_lon,
            "phone": tags.get("phone") or tags.get("contact:phone"),
            "website": tags.get("website") or tags.get("contact:website"),
            "address": _build_address(tags),
            "opening_hours": tags.get("opening_hours"),
            "healthcare_specialty": tags.get("healthcare:speciality") or tags.get("healthcare:specialty"),
            "distance_km": round(haversine(lat, lon, el_lat, el_lon), 2),
        })
    results.sort(key=lambda x: x["distance_km"])
    return results


def _build_address(tags: dict) -> str:
    """Build a single address string from OSM tags."""
    parts = []
    for key in ("addr:housenumber", "addr:street", "addr:city", "addr:state", "addr:postcode", "addr:country"):
        val = tags.get(key)
        if val:
            parts.append(val)
    return ", ".join(parts) if parts else ""
