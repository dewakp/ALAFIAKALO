"""CMS NPPES (National Plan & Provider Enumeration System) adapter.

The NPI Registry API (https://npiregistry.cms.hhs.gov/api/) is a free, key-less
CMS source covering every US clinician — physicians AND nurses, dietitians,
pharmacists, therapists, etc. — keyed by NPI, with taxonomy (specialty) and,
crucially, the state **license number** we gate patient association on.

This module only *fetches + normalizes*; dedup/quarantine/promotion lives in
`clinician_ingest`. We take individuals (NPI-1) only — orgs (NPI-2) aren't clinicians.
"""
from __future__ import annotations

import hashlib

import httpx

NPPES_URL = "https://npiregistry.cms.hhs.gov/api/"
SOURCE = "cms_nppes"

# Taxonomy description keywords -> ClinicianRole value. Checked in order; first hit wins.
_ROLE_RULES: list[tuple[tuple[str, ...], str]] = [
    (("nurse practitioner", "advanced practice"), "nurse_practitioner"),
    (("physician assistant",), "physician_assistant"),
    (("nurse", "nursing", "lpn", "licensed practical"), "nurse"),
    (("dietitian", "dietetic", "nutritionist"), "dietitian"),
    (("pharmac",), "pharmacist"),
    (("physical therap", "occupational therap", "speech", "respiratory therap",
      "athletic trainer", "rehabilitation"), "therapist"),
    (("psycholog", "counselor", "social work", "behavioral", "mental health",
      "marriage", "addiction"), "mental_health"),
    (("dentist", "dental", "orthodont", "endodont", "periodont"), "dentist"),
    (("optometr",), "optometrist"),
    (("podiatr",), "podiatrist"),
    (("chiropract",), "chiropractor"),
    (("midwif",), "midwife"),
]


def classify_role(taxonomy_desc: str | None) -> str:
    low = (taxonomy_desc or "").lower()
    for keywords, role in _ROLE_RULES:
        if any(k in low for k in keywords):
            return role
    return "physician"  # default: MD/DO medical & surgical specialties


def _primary_taxonomy(result: dict) -> dict:
    taxes = result.get("taxonomies") or []
    return next((t for t in taxes if t.get("primary")), taxes[0] if taxes else {})


def _best_license(result: dict) -> tuple[str | None, str | None]:
    """Return (license_number, license_state): prefer the primary taxonomy, else any."""
    taxes = result.get("taxonomies") or []
    ordered = sorted(taxes, key=lambda t: 0 if t.get("primary") else 1)
    for t in ordered:
        if t.get("license"):
            return t["license"], t.get("state")
    return None, (ordered[0].get("state") if ordered else None)


def _location_address(result: dict) -> dict:
    addrs = result.get("addresses") or []
    return next((a for a in addrs if a.get("address_purpose") == "LOCATION"),
                addrs[0] if addrs else {})


def normalize(result: dict) -> dict | None:
    """NPPES result -> normalized candidate dict, or None for orgs / unusable rows."""
    if result.get("enumeration_type") != "NPI-1":
        return None
    npi = str(result.get("number") or "").strip()
    if not npi:
        return None

    basic = result.get("basic") or {}
    tax = _primary_taxonomy(result)
    lic, lic_state = _best_license(result)
    addr = _location_address(result)

    name_parts = [basic.get("first_name"), basic.get("middle_name"), basic.get("last_name")]
    full_name = " ".join(p for p in name_parts if p).strip().title() or basic.get("name")

    country = addr.get("country_code") or "US"
    if country == "US":
        country = "United States"

    cand = {
        "source": SOURCE,
        "source_uid": npi,
        "npi_number": npi,
        "full_name": full_name,
        "clinician_role": classify_role(tax.get("desc")),
        "specialty": tax.get("desc"),
        "credentials": (basic.get("credential") or "").strip().rstrip(".") or None,
        "license_number": lic,
        "license_state": lic_state,
        "address_line1": addr.get("address_1"),
        "address_line2": addr.get("address_2"),
        "city": (addr.get("city") or "").title() or None,
        "state_province": addr.get("state"),
        "postal_code": (addr.get("postal_code") or "")[:10] or None,
        "country": country,
        "phone": addr.get("telephone_number"),
        "raw_payload": result,
    }
    cand["content_hash"] = content_hash(cand)
    return cand


def content_hash(cand: dict) -> str:
    """Stable hash of the identity-bearing fields, for change detection."""
    key = "|".join(str(cand.get(f) or "") for f in (
        "npi_number", "full_name", "specialty", "license_number",
        "license_state", "address_line1", "city", "state_province", "postal_code"))
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


async def search_nppes(
    *, number: str | None = None, taxonomy_description: str | None = None,
    state: str | None = None, city: str | None = None, first_name: str | None = None,
    last_name: str | None = None, postal_code: str | None = None,
    limit: int = 200, skip: int = 0, enumeration_type: str = "NPI-1",
) -> list[dict]:
    """Query the NPPES API and return raw result rows (caller normalizes)."""
    params = {"version": "2.1", "limit": max(1, min(limit, 200)), "skip": max(0, min(skip, 1000))}
    if number:
        params["number"] = number
    if enumeration_type:
        params["enumeration_type"] = enumeration_type
    if taxonomy_description:
        params["taxonomy_description"] = taxonomy_description
    if state:
        params["state"] = state
    if city:
        params["city"] = city
    if first_name:
        params["first_name"] = first_name
    if last_name:
        params["last_name"] = last_name
    if postal_code:
        params["postal_code"] = postal_code
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(NPPES_URL, params=params)
            r.raise_for_status()
            return r.json().get("results", []) or []
    except (httpx.HTTPError, ValueError):
        return []


async def search_normalized(**kwargs) -> list[dict]:
    """search_nppes + normalize, dropping orgs/unusable rows."""
    return [c for c in (normalize(r) for r in await search_nppes(**kwargs)) if c]
