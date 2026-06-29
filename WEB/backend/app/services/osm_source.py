"""OpenStreetMap (Overpass) source adapter — a non-CMS, global discovery source.

OSM yields healthcare *places* (clinics, practices, pharmacies) with real
coordinates but no license. Routed through the same ingestion pipeline, these
land in quarantine (`held_no_license`) until a license is confirmed — exactly the
safety behavior we want for a non-authoritative source. The ingest pipeline is
source-agnostic: any adapter just emits normalized candidate dicts carrying a
`source` field, so adding further sources (state boards, NPPES bulk file, …)
means writing another small adapter like this one.
"""
from __future__ import annotations

from app.services.geocoding import search_nearby_healthcare
from app.services import cms_nppes  # reuse content_hash

SOURCE = "osm"

# OSM amenity → our coarse clinician_role (these are facilities; role is best-effort).
_AMENITY_ROLE = {
    "pharmacy": "pharmacist", "dentist": "dentist", "doctors": "physician",
    "clinic": "physician", "hospital": "physician",
}


def normalize(el: dict) -> dict | None:
    osm_id = el.get("osm_id")
    name = el.get("name")
    if not osm_id or not name or name == "Unknown":
        return None
    cand = {
        "source": SOURCE,
        "source_uid": str(osm_id),
        "npi_number": None,
        "full_name": name,
        "clinician_role": _AMENITY_ROLE.get(el.get("amenity_type"), "other"),
        "specialty": el.get("healthcare_specialty") or (el.get("amenity_type") or "").title() or None,
        "credentials": None,
        "license_number": None,        # OSM has none → record is held until licensed
        "license_state": None,
        "address_line1": el.get("address") or None,
        "city": None,
        "state_province": None,
        "postal_code": None,
        "country": None,               # unknown from a bare node; point map uses coords
        "phone": el.get("phone"),
        "latitude": el.get("latitude"),
        "longitude": el.get("longitude"),
        "raw_payload": el,
    }
    cand["content_hash"] = cms_nppes.content_hash(cand)
    return cand


async def discover_normalized(lat: float, lon: float, *, radius_km: float = 50,
                              place_type: str = "all") -> list[dict]:
    """Discover healthcare places near a point and normalize them to candidates."""
    raw = await search_nearby_healthcare(lat, lon, radius_m=int(radius_km * 1000),
                                         place_type=place_type)
    return [c for c in (normalize(el) for el in raw) if c]
