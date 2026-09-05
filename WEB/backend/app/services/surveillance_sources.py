"""Disease surveillance — outward source clients (WHO GHO + CDC NNDSS).

Two live, key-free public sources feed the "looking outward" view:

* WHO GHO  (ghoapi.azureedge.net) — per-country (ISO3) indicator values, global.
  Each African country carries ParentLocation == "Africa", so the Africa CDC
  perspective is served from WHO's AFR region rows (Africa CDC has no open API).
* CDC NNDSS (data.cdc.gov, x9gk-5huc) — US notifiable diseases, updated weekly,
  broken down by state (used both for the US signal and the US drill-down).

Results are normalized to a common shape and cached in-process (6 h TTL) so the
map and drill-down endpoints stay snappy and don't hammer the upstreams.
"""
from __future__ import annotations

import re
import time

import httpx

from app.services.iso_countries import ISO3_TO_ISO2, ISO3_TO_NAME

WHO_BASE = "https://ghoapi.azureedge.net/api"
CDC_NNDSS_URL = "https://data.cdc.gov/resource/x9gk-5huc.json"

_CACHE: dict[str, tuple[float, object]] = {}
_TTL = 6 * 3600  # 6 hours


def _cache_get(key: str):
    hit = _CACHE.get(key)
    if hit and (time.time() - hit[0]) < _TTL:
        return hit[1]
    return None


def _cache_set(key: str, value) -> None:
    _CACHE[key] = (time.time(), value)


# ── Disease catalog ─────────────────────────────────────────────────────
# Each disease maps to a verified WHO GHO indicator (global, per-country) and,
# where applicable, one or more CDC NNDSS labels (US, per-state). `cdc` may be
# empty when CDC doesn't track the disease in NNDSS — WHO still covers it.

DISEASES = [
    {"id": "cholera", "label": "Cholera", "icon": "🦠", "category": "Enteric",
     "who": "CHOLERA_0000000001", "who_unit": "reported cases", "cdc": ["Cholera"]},
    {"id": "measles", "label": "Measles", "icon": "🤒", "category": "Vaccine-preventable",
     "who": "WHS3_62", "who_unit": "reported cases",
     "cdc": ["Measles, Imported", "Measles, Indigenous"]},
    {"id": "malaria", "label": "Malaria", "icon": "🦟", "category": "Vector-borne",
     "who": "MALARIA_EST_CASES", "who_unit": "estimated cases", "cdc": ["Malaria"]},
    {"id": "tuberculosis", "label": "Tuberculosis", "icon": "🫁", "category": "Respiratory",
     "who": "MDG_0000000020", "who_unit": "incidence per 100k/yr", "cdc": ["Tuberculosis"]},
    {"id": "pertussis", "label": "Pertussis (whooping cough)", "icon": "😮‍💨",
     "category": "Vaccine-preventable", "who": "WHS3_49", "who_unit": "reported cases",
     "cdc": ["Pertussis"]},
    {"id": "diphtheria", "label": "Diphtheria", "icon": "🦠", "category": "Vaccine-preventable",
     "who": "WHS3_41", "who_unit": "reported cases", "cdc": []},
    {"id": "polio", "label": "Poliomyelitis", "icon": "🦠", "category": "Vaccine-preventable",
     "who": "WHS3_57", "who_unit": "reported cases", "cdc": ["Poliomyelitis, paralytic"]},
]
DISEASE_BY_ID = {d["id"]: d for d in DISEASES}

SOURCES = [
    {"id": "who", "name": "WHO GHO", "full_name": "World Health Organization — Global Health Observatory",
     "scope": "Global (per country)", "url": "https://www.who.int/data/gho"},
    {"id": "cdc", "name": "CDC NNDSS", "full_name": "US CDC — National Notifiable Diseases Surveillance System",
     "scope": "United States (per state, weekly)", "url": "https://www.cdc.gov/nndss/"},
    {"id": "africa_cdc", "name": "Africa CDC", "full_name": "Africa Centres for Disease Control and Prevention",
     "scope": "Africa (via WHO AFR region — no open API)", "url": "https://africacdc.org"},
    {"id": "inward", "name": "ALAFIA patients", "full_name": "Aggregated, de-identified patient symptom reports",
     "scope": "Wherever ALAFIA users are", "url": None},
]

# US state / territory name -> 2-letter code (for the CDC per-state breakdown).
_US_STATE_NAME_TO_CODE = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA",
    "colorado": "CO", "connecticut": "CT", "delaware": "DE", "district of columbia": "DC",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID", "illinois": "IL",
    "indiana": "IN", "iowa": "IA", "kansas": "KS", "kentucky": "KY", "louisiana": "LA",
    "maine": "ME", "maryland": "MD", "massachusetts": "MA", "michigan": "MI", "minnesota": "MN",
    "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR",
    "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC", "south dakota": "SD",
    "tennessee": "TN", "texas": "TX", "utah": "UT", "vermont": "VT", "virginia": "VA",
    "washington": "WA", "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
    "puerto rico": "PR",
}


def _parse_value(row: dict) -> float | None:
    """Extract a numeric value from a WHO GHO row.

    GHO `Value` strings carry confidence intervals and space thousands-separators,
    e.g. "419 332 [283 000-600 000]" or "121.53 [38.41-214.47]".
    """
    nv = row.get("NumericValue")
    if nv is not None:
        try:
            return float(nv)
        except (TypeError, ValueError):
            pass
    raw = row.get("Value")
    if raw is None:
        return None
    s = str(raw).split("[")[0].replace(",", "").replace(" ", "").strip()
    m = re.match(r"-?\d+(?:\.\d+)?", s)
    return float(m.group()) if m else None


async def fetch_who(indicator: str, min_year: int = 2010) -> list[dict]:
    """Latest per-country value for a WHO GHO indicator.

    Returns [{iso2, iso3, name, region, value, year}] keeping, for each country,
    the most recent year (>= min_year) that has a usable numeric value.
    """
    key = f"who:{indicator}:{min_year}"
    cached = _cache_get(key)
    if cached is not None:
        return cached

    params = {
        "$filter": f"SpatialDimType eq 'COUNTRY' and TimeDim ge {min_year}",
        "$select": "SpatialDim,TimeDim,Value,NumericValue,ParentLocation",
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(f"{WHO_BASE}/{indicator}", params=params,
                                  headers={"Accept": "application/json"})
            r.raise_for_status()
            rows = r.json().get("value", [])
    except (httpx.HTTPError, ValueError):
        return _cache_get(key) or []

    latest: dict[str, dict] = {}
    for row in rows:
        iso3 = row.get("SpatialDim")
        iso2 = ISO3_TO_ISO2.get(iso3)
        if not iso2:
            continue
        val = _parse_value(row)
        if val is None:
            continue
        year = int(row.get("TimeDim") or 0)
        cur = latest.get(iso2)
        if cur is None or year > cur["year"]:
            latest[iso2] = {
                "iso2": iso2, "iso3": iso3,
                "name": ISO3_TO_NAME.get(iso3, iso2),
                "region": row.get("ParentLocation"),
                "value": val, "year": year,
            }
    out = list(latest.values())
    _cache_set(key, out)
    return out


async def fetch_who_series(indicator: str, iso3: str, min_year: int = 2000) -> list[dict]:
    """Yearly time series of a WHO GHO indicator for one country (for drill-down)."""
    key = f"who_series:{indicator}:{iso3}:{min_year}"
    cached = _cache_get(key)
    if cached is not None:
        return cached
    params = {
        "$filter": f"SpatialDim eq '{iso3}' and TimeDim ge {min_year}",
        "$select": "TimeDim,Value,NumericValue",
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(f"{WHO_BASE}/{indicator}", params=params,
                                  headers={"Accept": "application/json"})
            r.raise_for_status()
            rows = r.json().get("value", [])
    except (httpx.HTTPError, ValueError):
        return []
    series: dict[int, float] = {}
    for row in rows:
        val = _parse_value(row)
        if val is None:
            continue
        series[int(row.get("TimeDim") or 0)] = val
    out = [{"year": y, "value": series[y]} for y in sorted(series)]
    _cache_set(key, out)
    return out


async def fetch_cdc(labels: list[str]) -> dict | None:
    """Current-week US counts for the given CDC NNDSS labels.

    Returns {total, year, week, states:{CODE:count}} using the cumulative
    year-to-date column (m2) for the most recent reporting week, or None.
    """
    if not labels:
        return None
    key = "cdc:" + "|".join(labels)
    cached = _cache_get(key)
    if cached is not None:
        return cached

    clause = " or ".join(f"label like '%{lab}%'" for lab in labels)
    params = {
        "$where": clause,
        "$order": "sort_order DESC",
        "$limit": 6000,
        "$select": "label,states,location1,location2,year,week,m1,m2",
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(CDC_NNDSS_URL, params=params,
                                  headers={"Accept": "application/json"})
            r.raise_for_status()
            rows = r.json()
    except (httpx.HTTPError, ValueError):
        return None

    if not rows:
        out = {"total": 0.0, "year": None, "week": None, "states": {}}
        _cache_set(key, out)
        return out

    def yw(row: dict) -> tuple[int, int]:
        try:
            return (int(row.get("year") or 0), int(row.get("week") or 0))
        except (TypeError, ValueError):
            return (0, 0)

    max_yw = max(yw(row) for row in rows)
    current = [row for row in rows if yw(row) == max_yw]

    total = 0.0
    states: dict[str, float] = {}
    for row in current:
        loc = (row.get("states") or row.get("location1") or row.get("location2") or "").strip()
        try:
            count = float(row.get("m2")) if row.get("m2") is not None else 0.0
        except (TypeError, ValueError):
            count = 0.0
        if loc.lower() == "total":
            total += count
        code = _US_STATE_NAME_TO_CODE.get(loc.lower())
        if code:
            states[code] = states.get(code, 0.0) + count

    out = {"total": total, "year": max_yw[0], "week": max_yw[1], "states": states}
    _cache_set(key, out)
    return out
