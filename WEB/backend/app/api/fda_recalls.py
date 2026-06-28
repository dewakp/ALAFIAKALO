"""FDA Food Recalls — proxy to the openFDA enforcement API."""

import re
import httpx
from datetime import date, timedelta
from fastapi import APIRouter, Body, Depends, Query
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.wellness import FDARecallResponse, FDARecallItem

router = APIRouter()

FDA_API_URL = "https://api.fda.gov/food/enforcement.json"        # back-compat alias
FDA_ENDPOINTS = {
    "food": "https://api.fda.gov/food/enforcement.json",
    "drug": "https://api.fda.gov/drug/enforcement.json",
}

# US state/territory codes ↔ names — used to extract coverage from the free-text
# distribution pattern for the map overlay.
_US_STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "DC": "District of Columbia",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois",
    "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana",
    "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
    "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon",
    "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota",
    "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia",
    "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming", "PR": "Puerto Rico",
}
_STATE_NAME_TO_CODE = {name.lower(): code for code, name in _US_STATES.items()}
_NATIONWIDE_HINTS = ("nationwide", "national", "all states", "all 50 states",
                     "throughout the united states", "entire united states", "all u.s.")


def _parse_coverage(distribution: str | None, firm_state: str | None) -> tuple[list[str], bool]:
    """Extract covered US state codes + a nationwide flag from a distribution pattern."""
    text = distribution or ""
    low = text.lower()
    nationwide = any(h in low for h in _NATIONWIDE_HINTS)
    found: set[str] = set()
    for code in re.findall(r"\b([A-Z]{2})\b", text):
        if code in _US_STATES:
            found.add(code)
    for name, code in _STATE_NAME_TO_CODE.items():
        if name in low:
            found.add(code)
    if firm_state:
        fs = firm_state.strip()
        if fs.upper() in _US_STATES:
            found.add(fs.upper())
        elif fs.lower() in _STATE_NAME_TO_CODE:
            found.add(_STATE_NAME_TO_CODE[fs.lower()])
    if nationwide:
        found |= set(_US_STATES.keys())
    return sorted(found), nationwide


# Country-name → ISO-2, for parsing international distribution patterns so the world
# map reflects every region a recall actually reached (recalls often ship abroad).
_COUNTRY_NAME_TO_ISO2 = {
    "united states": "US", "usa": "US", "america": "US", "canada": "CA", "mexico": "MX",
    "united kingdom": "GB", "england": "GB", "scotland": "GB", "wales": "GB", "ireland": "IE",
    "france": "FR", "germany": "DE", "italy": "IT", "spain": "ES", "portugal": "PT",
    "netherlands": "NL", "belgium": "BE", "switzerland": "CH", "austria": "AT", "sweden": "SE",
    "norway": "NO", "denmark": "DK", "finland": "FI", "poland": "PL", "greece": "GR",
    "romania": "RO", "hungary": "HU", "russia": "RU", "ukraine": "UA", "india": "IN",
    "china": "CN", "japan": "JP", "south korea": "KR", "australia": "AU", "new zealand": "NZ",
    "south africa": "ZA", "nigeria": "NG", "ghana": "GH", "kenya": "KE", "egypt": "EG",
    "morocco": "MA", "united arab emirates": "AE", "saudi arabia": "SA", "israel": "IL",
    "turkey": "TR", "indonesia": "ID", "malaysia": "MY", "singapore": "SG", "thailand": "TH",
    "philippines": "PH", "vietnam": "VN", "pakistan": "PK", "bangladesh": "BD", "colombia": "CO",
    "peru": "PE", "argentina": "AR", "chile": "CL", "brazil": "BR", "puerto rico": "PR", "guam": "GU",
}


def _parse_countries(distribution: str | None, source_iso2: str | None) -> list[str]:
    found: set[str] = set()
    if source_iso2:
        found.add(source_iso2)
    low = (distribution or "").lower()
    for name, code in _COUNTRY_NAME_TO_ISO2.items():
        if re.search(r"\b" + re.escape(name) + r"\b", low):
            found.add(code)
    return sorted(found)


def _build_item(item: dict, product_type: str = "food") -> FDARecallItem:
    states, nationwide = _parse_coverage(item.get("distribution_pattern"), item.get("state"))
    countries = _parse_countries(item.get("distribution_pattern"), "US")
    return FDARecallItem(
        product_type=product_type,
        source="openFDA (US)",
        recall_number=item.get("recall_number"),
        reason=item.get("reason_for_recall"),
        status=item.get("status"),
        distribution=item.get("distribution_pattern"),
        product_description=item.get("product_description"),
        recalling_firm=item.get("recalling_firm"),
        recall_initiation_date=item.get("recall_initiation_date"),
        report_date=item.get("report_date"),
        classification=item.get("classification"),
        voluntary_mandated=item.get("voluntary_mandated"),
        city=item.get("city"),
        state=item.get("state"),
        country="US",          # US FDA jurisdiction
        states=states,
        countries=countries,
        nationwide=nationwide,
    )


# ── International sources (graceful: a failing source never breaks the response) ─
_INTL_HEADERS = {"Accept": "application/json", "User-Agent": "ALAFIA/1.0"}


async def _fetch_canada(search: str | None, days: int, limit: int, kinds: list[str]) -> list[FDARecallItem]:
    """Health Canada recalls (food = category '1', health products = '3')."""
    import time as _time
    try:
        async with httpx.AsyncClient(timeout=15.0, headers=_INTL_HEADERS) as c:
            r = await c.get("https://healthycanadians.gc.ca/recall-alert-rappel-avis/api/recent/en")
            r.raise_for_status()
            data = r.json()
    except (httpx.HTTPError, ValueError):
        return []
    # This endpoint is already a curated "recent recalls" feed, so we don't apply
    # the day-window (it would drop everything if the feed's dates differ).
    out: list[FDARecallItem] = []
    for rec in data.get("results", {}).get("ALL", []):
        cats = rec.get("category") or []
        pt = "food" if "1" in cats else "drug" if "3" in cats else None
        if pt is None or pt not in kinds:
            continue
        dp = rec.get("date_published")
        title = rec.get("title", "")
        if search and search.lower() not in title.lower():
            continue
        rd = _time.strftime("%Y%m%d", _time.gmtime(dp)) if dp else None
        out.append(FDARecallItem(
            product_type=pt, source="Health Canada", country="CA",
            recall_number=str(rec.get("recallId")), product_description=title,
            report_date=rd, recall_initiation_date=rd, distribution="Canada",
            countries=["CA"],
            url=f"https://recalls-rappels.canada.ca/en/alert-recall/{rec.get('recallId')}",
        ))
    return out[:limit]


async def _fetch_uk(search: str | None, days: int, limit: int, kinds: list[str]) -> list[FDARecallItem]:
    """UK Food Standards Agency food alerts."""
    if "food" not in kinds:
        return []
    from datetime import datetime
    try:
        async with httpx.AsyncClient(timeout=15.0, headers=_INTL_HEADERS) as c:
            r = await c.get("https://data.food.gov.uk/food-alerts/id",
                            params={"_sort": "-created", "_limit": min(limit * 2, 50)})
            r.raise_for_status()
            data = r.json()
    except (httpx.HTTPError, ValueError):
        return []
    cutoff = date.today() - timedelta(days=days)
    out: list[FDARecallItem] = []
    for it in data.get("items", []):
        created = (it.get("created") or "")[:10]
        try:
            d = datetime.fromisoformat(created).date()
        except ValueError:
            d = None
        if d and d < cutoff:
            continue
        title = it.get("title", "")
        if search and search.lower() not in title.lower():
            continue
        reason = None
        prob = it.get("problem")
        if isinstance(prob, list) and prob:
            reason = prob[0].get("riskStatement")
        rd = created.replace("-", "") if created else None
        out.append(FDARecallItem(
            product_type="food", source="UK FSA", country="GB",
            product_description=title, reason=reason,
            report_date=rd, recall_initiation_date=rd, distribution="United Kingdom",
            countries=["GB"],
            url=it.get("alertURL"),
        ))
    return out[:limit]


async def _query_openfda(url: str, params: dict) -> dict | None:
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, params=params)
            if resp.status_code == 404:   # openFDA returns 404 for "no matches"
                return {"results": [], "meta": {}}
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError:
        return None


def _kinds(kind: str) -> list[str]:
    k = (kind or "both").lower()
    return ["food", "drug"] if k in ("both", "all", "") else [k] if k in FDA_ENDPOINTS else ["food"]


async def _search_one(product_type: str, search: str | None, days: int, limit: int) -> tuple[list[FDARecallItem], int]:
    """Query a single openFDA enforcement endpoint. NOTE: the query uses SPACES for
    AND/TO (the client URL-encodes them) — literal '+' triggers a 500 parse error."""
    params: dict = {"limit": limit, "sort": "report_date:desc"}
    parts = []
    if search:
        parts.append(f'"{search}"')
    start = (date.today() - timedelta(days=days)).strftime("%Y%m%d")
    end = date.today().strftime("%Y%m%d")
    parts.append(f"report_date:[{start} TO {end}]")
    params["search"] = " AND ".join(parts)

    data = await _query_openfda(FDA_ENDPOINTS[product_type], params)
    if data is None:
        return [], 0
    items = [_build_item(it, product_type) for it in data.get("results", [])]
    total = data.get("meta", {}).get("results", {}).get("total", len(items))
    return items, total


@router.get("/", response_model=FDARecallResponse)
async def search_fda_recalls(
    search: str | None = Query(None, description="Search term"),
    days: int = Query(7, ge=1, le=365, description="Number of days back to search"),
    limit: int = Query(20, ge=1, le=100),
    kind: str = Query("both", description="food | drug | both"),
    current_user: User = Depends(get_current_user),
):
    """Search global food and/or drug recalls (US openFDA + Health Canada + UK FSA)."""
    kinds = _kinds(kind)

    sources: list[list[FDARecallItem]] = []
    total = 0

    # US — openFDA food/drug
    for pt in [k for k in kinds if k in ("food", "drug")]:
        items, t = await _search_one(pt, search, days, limit=limit)
        if items:
            items.sort(key=lambda r: r.report_date or "", reverse=True)
            sources.append(items)
        total += t

    # International sources (each guarded — failures degrade gracefully)
    for fetched in (
        await _fetch_canada(search, days, limit, kinds),
        await _fetch_uk(search, days, limit, kinds),
    ):
        if fetched:
            fetched.sort(key=lambda r: r.report_date or "", reverse=True)
            sources.append(fetched)
        total += len(fetched)

    # Round-robin across sources so every country is represented (not just the
    # one with the freshest dates), each source newest-first internally.
    merged: list[FDARecallItem] = []
    i = 0
    while len(merged) < limit and any(i < len(s) for s in sources):
        for s in sources:
            if i < len(s):
                merged.append(s[i])
                if len(merged) >= limit:
                    break
        i += 1
    return FDARecallResponse(total=total, results=merged)


@router.get("/recent", response_model=FDARecallResponse)
async def get_recent_recalls(
    limit: int = Query(10, ge=1, le=50),
    kind: str = Query("both", description="food | drug | both"),
    current_user: User = Depends(get_current_user),
):
    """Most recent FDA food + drug recalls (last 90 days — report_date lags)."""
    return await search_fda_recalls(search=None, days=90, limit=limit, kind=kind, current_user=current_user)


async def _fetch_fda_recalls_for_term(term: str, days: int, limit: int) -> list[FDARecallItem]:
    """Internal helper — query openFDA for a single search term."""
    start = (date.today() - timedelta(days=days)).strftime("%Y%m%d")
    end = date.today().strftime("%Y%m%d")
    params = {
        "limit": limit,
        "sort": "report_date:desc",
        "search": f'"{term}" AND report_date:[{start} TO {end}]',
    }
    data = await _query_openfda(FDA_ENDPOINTS["food"], params)
    if data is None:
        return []
    return [_build_item(item, "food") for item in data.get("results", [])]


@router.post("/check-meal", response_model=FDARecallResponse)
async def check_meal_for_recalls(
    description: str = Body(..., embed=True, description="Free-text meal description"),
    days: int = Query(30, ge=1, le=365, description="Days back to search recalls"),
    current_user: User = Depends(get_current_user),
):
    """Check FDA food recalls for every ingredient parsed from a meal description."""
    from app.services.meal_parser import parse_meal_text

    components = parse_meal_text(description)
    if not components:
        return FDARecallResponse(total=0, results=[])

    all_results: list[FDARecallItem] = []
    seen_ids: set[str] = set()
    for comp in components:
        for item in await _fetch_fda_recalls_for_term(comp.food_name, days, limit=5):
            rid = item.recall_number or item.product_description or ""
            if rid not in seen_ids:
                seen_ids.add(rid)
                all_results.append(item)

    return FDARecallResponse(total=len(all_results), results=all_results)
