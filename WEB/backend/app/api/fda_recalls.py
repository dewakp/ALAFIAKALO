"""FDA Food Recalls — proxy to openFDA enforcement API."""

import httpx
from datetime import date, timedelta
from fastapi import APIRouter, Body, Depends, Query
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.wellness import FDARecallResponse, FDARecallItem

router = APIRouter()

FDA_API_URL = "https://api.fda.gov/food/enforcement.json"


@router.get("/", response_model=FDARecallResponse)
async def search_fda_recalls(
    search: str | None = Query(None, description="Search term for food recalls"),
    days: int = Query(7, ge=1, le=365, description="Number of days back to search"),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
):
    """Search FDA food enforcement/recall database."""
    params = {"limit": limit}

    # Build search query
    search_parts = []
    if search:
        search_parts.append(f'"{search}"')

    # Date range
    start_date = (date.today() - timedelta(days=days)).strftime("%Y%m%d")
    end_date = date.today().strftime("%Y%m%d")
    search_parts.append(f"report_date:[{start_date}+TO+{end_date}]")

    if search_parts:
        params["search"] = "+AND+".join(search_parts)

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(FDA_API_URL, params=params)
            if response.status_code == 404:
                return FDARecallResponse(total=0, results=[])
            response.raise_for_status()
            data = response.json()

        results = []
        for item in data.get("results", []):
            results.append(FDARecallItem(
                recall_number=item.get("recall_number"),
                reason=item.get("reason_for_recall"),
                status=item.get("status"),
                distribution=item.get("distribution_pattern"),
                product_description=item.get("product_description"),
                recalling_firm=item.get("recalling_firm"),
                recall_initiation_date=item.get("recall_initiation_date"),
                classification=item.get("classification"),
                voluntary_mandated=item.get("voluntary_mandated"),
            ))

        return FDARecallResponse(
            total=data.get("meta", {}).get("results", {}).get("total", len(results)),
            results=results,
        )
    except httpx.HTTPError:
        return FDARecallResponse(total=0, results=[])


@router.get("/recent", response_model=FDARecallResponse)
async def get_recent_recalls(
    limit: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
):
    """Get most recent FDA food recalls (last 7 days)."""
    return await search_fda_recalls(search=None, days=7, limit=limit, current_user=current_user)


async def _fetch_fda_recalls_for_term(
    term: str,
    days: int,
    limit: int,
) -> list[FDARecallItem]:
    """Internal helper — query openFDA for a single search term."""
    params: dict = {"limit": limit}
    start = (date.today() - timedelta(days=days)).strftime("%Y%m%d")
    end = date.today().strftime("%Y%m%d")
    params["search"] = f'"{term}"+AND+report_date:[{start}+TO+{end}]'
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(FDA_API_URL, params=params)
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            data = resp.json()
        return [
            FDARecallItem(
                recall_number=item.get("recall_number"),
                reason=item.get("reason_for_recall"),
                status=item.get("status"),
                distribution=item.get("distribution_pattern"),
                product_description=item.get("product_description"),
                recalling_firm=item.get("recalling_firm"),
                recall_initiation_date=item.get("recall_initiation_date"),
                classification=item.get("classification"),
                voluntary_mandated=item.get("voluntary_mandated"),
            )
            for item in data.get("results", [])
        ]
    except httpx.HTTPError:
        return []


@router.post("/check-meal", response_model=FDARecallResponse)
async def check_meal_for_recalls(
    description: str = Body(..., embed=True, description="Free-text meal description"),
    days: int = Query(30, ge=1, le=365, description="Days back to search recalls"),
    current_user: User = Depends(get_current_user),
):
    """Check FDA food recalls for every ingredient parsed from a meal description.

    Uses the NLM meal parser to extract individual food items from the
    free-text description, then queries openFDA for each item and de-duplicates
    results by recall number.

    Example body: ``{"description": "1.5 cup beef suya(peanut butter, pepper), garri, whole milk"}``
    """
    from app.services.meal_parser import parse_meal_text

    components = parse_meal_text(description)
    if not components:
        return FDARecallResponse(total=0, results=[])

    all_results: list[FDARecallItem] = []
    seen_ids: set[str] = set()

    for comp in components:
        items = await _fetch_fda_recalls_for_term(comp.food_name, days, limit=5)
        for item in items:
            rid = item.recall_number or item.product_description or ""
            if rid not in seen_ids:
                seen_ids.add(rid)
                all_results.append(item)

    return FDARecallResponse(total=len(all_results), results=all_results)
