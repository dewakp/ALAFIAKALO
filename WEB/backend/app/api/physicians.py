"""Physician Directory API.

Endpoints:
  Directory (public-ish):
    GET    /physicians/                     — search / list physicians
    GET    /physicians/{id}                 — get physician detail
    POST   /physicians/                     — contribute a physician
    PATCH  /physicians/{id}                 — update physician (owner / admin)
    DELETE /physicians/{id}                 — delete physician (owner / admin)

  Saved Physicians (per-user):
    GET    /physicians/saved/               — list my saved physicians
    POST   /physicians/saved/               — save (bookmark) a physician
    PATCH  /physicians/saved/{id}           — update notes / relationship
    DELETE /physicians/saved/{id}           — unsave a physician

  Reviews:
    GET    /physicians/{id}/reviews         — reviews for a physician
    POST   /physicians/{id}/reviews         — add review
    PATCH  /physicians/reviews/{id}         — update my review
    DELETE /physicians/reviews/{id}         — delete my review

  Geo / Discovery:
    GET    /physicians/nearby               — radius search (lat/lon)
    GET    /physicians/geocode              — free geocoding (address → coords)
    GET    /physicians/osm-discover         — discover facilities from OSM
    GET    /physicians/specialties          — specialty taxonomy

All geo powered by free OpenStreetMap / Nominatim — no Google, no API keys.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, and_, or_, cast, Float
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.physicians import (
    Physician, SavedPhysician, PhysicianReview,
    PhysicianSource, PhysicianStatus,
    SPECIALTY_CATEGORIES, ALL_SPECIALTIES,
)
from app.schemas.physicians import (
    PhysicianCreate, PhysicianUpdate, PhysicianResponse,
    SavePhysicianRequest, SavedPhysicianUpdate, SavedPhysicianResponse,
    ReviewCreate, ReviewUpdate, ReviewResponse,
    NearbySearchResponse, GeoSearchResult, GeocodingResult,
    SpecialtyCategoryResponse,
)
from app.services.geocoding import (
    geocode_address, reverse_geocode, search_nearby_healthcare,
    haversine, bounding_box,
)

router = APIRouter()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  SPECIALTY TAXONOMY
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/specialties", response_model=SpecialtyCategoryResponse)
async def get_specialties():
    """Return the full specialty taxonomy (categories → specialties)."""
    return SpecialtyCategoryResponse(categories=SPECIALTY_CATEGORIES)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  GEOCODING (free — Nominatim)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/geocode", response_model=list[GeocodingResult])
async def geocode(
    address: str = Query(..., min_length=2, description="Address to geocode"),
    limit: int = Query(5, ge=1, le=10),
    _current_user: User = Depends(get_current_user),
):
    """Forward geocode an address to lat/lon using free Nominatim (OpenStreetMap)."""
    try:
        results = await geocode_address(address, limit=limit)
        return [GeocodingResult(**r) for r in results]
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Geocoding service error: {exc}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  OSM DISCOVERY (Overpass)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/osm-discover")
async def osm_discover(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
    radius_km: float = Query(50, ge=1, le=200, description="Search radius in km"),
    place_type: str = Query("all", description="hospital|clinic|pharmacy|dentist|doctors|all"),
    _current_user: User = Depends(get_current_user),
):
    """Discover healthcare facilities from OpenStreetMap near a GPS point.

    Returns raw OSM data — use POST /physicians/ to add any to the directory.
    """
    try:
        results = await search_nearby_healthcare(lat, lon, radius_m=int(radius_km * 1000), place_type=place_type)
        return {"results": results, "count": len(results), "center": {"lat": lat, "lon": lon}, "radius_km": radius_km}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"OSM discovery error: {exc}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  PHYSICIAN DIRECTORY CRUD
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/", response_model=list[PhysicianResponse])
async def search_physicians(
    q: str | None = Query(None, description="Name search"),
    specialty: str | None = Query(None),
    specialty_category: str | None = Query(None),
    city: str | None = Query(None),
    state_province: str | None = Query(None),
    country: str | None = Query(None),
    accepting_new_patients: bool | None = Query(None),
    telehealth_available: bool | None = Query(None),
    min_rating: float | None = Query(None, ge=0, le=5),
    verified_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Search / list physicians with optional filters."""
    stmt = select(Physician).where(Physician.status != PhysicianStatus.inactive.value)

    if q:
        stmt = stmt.where(Physician.full_name.ilike(f"%{q}%"))
    if specialty:
        stmt = stmt.where(Physician.specialty.ilike(f"%{specialty}%"))
    if specialty_category:
        stmt = stmt.where(Physician.specialty_category == specialty_category)
    if city:
        stmt = stmt.where(Physician.city.ilike(f"%{city}%"))
    if state_province:
        stmt = stmt.where(Physician.state_province.ilike(f"%{state_province}%"))
    if country:
        stmt = stmt.where(Physician.country.ilike(f"%{country}%"))
    if accepting_new_patients is not None:
        stmt = stmt.where(Physician.accepting_new_patients == accepting_new_patients)
    if telehealth_available is not None:
        stmt = stmt.where(Physician.telehealth_available == telehealth_available)
    if min_rating is not None:
        stmt = stmt.where(Physician.average_rating >= min_rating)
    if verified_only:
        stmt = stmt.where(Physician.is_verified == True)  # noqa: E712

    stmt = stmt.order_by(Physician.full_name).offset(offset).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/nearby", response_model=NearbySearchResponse)
async def nearby_physicians(
    lat: float = Query(..., description="Center latitude"),
    lon: float = Query(..., description="Center longitude"),
    radius_km: float = Query(50, ge=1, le=500),
    specialty: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Find physicians within a radius of a GPS point (Haversine)."""
    min_lat, max_lat, min_lon, max_lon = bounding_box(lat, lon, radius_km)

    stmt = select(Physician).where(
        and_(
            Physician.latitude.is_not(None),
            Physician.longitude.is_not(None),
            Physician.latitude >= min_lat,
            Physician.latitude <= max_lat,
            Physician.longitude >= min_lon,
            Physician.longitude <= max_lon,
            Physician.status != PhysicianStatus.inactive.value,
        )
    )
    if specialty:
        stmt = stmt.where(Physician.specialty.ilike(f"%{specialty}%"))

    result = await db.execute(stmt)
    physicians = result.scalars().all()

    # Precise Haversine filter + distance
    geo_results: list[GeoSearchResult] = []
    for p in physicians:
        dist = haversine(lat, lon, p.latitude, p.longitude)
        if dist <= radius_km:
            geo_results.append(GeoSearchResult(
                physician=PhysicianResponse.model_validate(p),
                distance_km=round(dist, 2),
            ))

    geo_results.sort(key=lambda r: r.distance_km or 999)
    total = len(geo_results)
    geo_results = geo_results[:limit]

    return NearbySearchResponse(
        results=geo_results,
        total=total,
        center_lat=lat,
        center_lon=lon,
        radius_km=radius_km,
    )


@router.get("/{physician_id}", response_model=PhysicianResponse)
async def get_physician(
    physician_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single physician by ID."""
    result = await db.execute(select(Physician).where(Physician.id == physician_id))
    physician = result.scalar_one_or_none()
    if not physician:
        raise HTTPException(status_code=404, detail="Physician not found")
    return physician


@router.post("/", response_model=PhysicianResponse, status_code=201)
async def create_physician(
    body: PhysicianCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Contribute a physician to the directory."""
    # Auto-assign specialty category if not provided
    cat = body.specialty_category
    if not cat:
        for category, specs in SPECIALTY_CATEGORIES.items():
            if body.specialty in specs:
                cat = category
                break

    # Auto-geocode if address given but no coordinates
    lat, lon = body.latitude, body.longitude
    if not lat and not lon and body.city:
        parts = [p for p in [body.address_line1, body.city, body.state_province, body.country] if p]
        if parts:
            try:
                geo = await geocode_address(", ".join(parts), limit=1)
                if geo:
                    lat = geo[0]["latitude"]
                    lon = geo[0]["longitude"]
            except Exception:
                pass  # geocoding failure is non-fatal

    physician = Physician(
        **body.model_dump(exclude={"specialty_category", "latitude", "longitude"}),
        specialty_category=cat,
        latitude=lat,
        longitude=lon,
        source=PhysicianSource.user_contributed.value,
        contributed_by_user_id=current_user.id,
        status=PhysicianStatus.unverified.value,
    )
    db.add(physician)
    await db.flush()
    await db.refresh(physician)
    return physician


@router.patch("/{physician_id}", response_model=PhysicianResponse)
async def update_physician(
    physician_id: int,
    body: PhysicianUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a physician (only the contributor or superuser)."""
    result = await db.execute(select(Physician).where(Physician.id == physician_id))
    physician = result.scalar_one_or_none()
    if not physician:
        raise HTTPException(status_code=404, detail="Physician not found")
    if physician.contributed_by_user_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Not allowed")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(physician, field, value)

    await db.flush()
    await db.refresh(physician)
    return physician


@router.delete("/{physician_id}", status_code=204)
async def delete_physician(
    physician_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a physician (only the contributor or superuser)."""
    result = await db.execute(select(Physician).where(Physician.id == physician_id))
    physician = result.scalar_one_or_none()
    if not physician:
        raise HTTPException(status_code=404, detail="Physician not found")
    if physician.contributed_by_user_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Not allowed")
    await db.delete(physician)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  SAVED PHYSICIANS (per-user bookmarks)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/saved/", response_model=list[SavedPhysicianResponse])
async def list_saved(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List my saved (bookmarked) physicians."""
    stmt = (
        select(SavedPhysician)
        .where(SavedPhysician.user_id == current_user.id)
        .options(selectinload(SavedPhysician.physician))
        .order_by(SavedPhysician.created_at.desc())
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("/saved/", response_model=SavedPhysicianResponse, status_code=201)
async def save_physician(
    body: SavePhysicianRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Bookmark a physician to my list."""
    # Verify physician exists
    result = await db.execute(select(Physician).where(Physician.id == body.physician_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Physician not found")

    # Check duplicate
    existing = await db.execute(
        select(SavedPhysician).where(
            SavedPhysician.user_id == current_user.id,
            SavedPhysician.physician_id == body.physician_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Physician already saved")

    # If marking as primary care, unset previous primary
    if body.is_primary_care:
        prev = await db.execute(
            select(SavedPhysician).where(
                SavedPhysician.user_id == current_user.id,
                SavedPhysician.is_primary_care == True,  # noqa: E712
            )
        )
        for sp in prev.scalars().all():
            sp.is_primary_care = False

    saved = SavedPhysician(user_id=current_user.id, **body.model_dump())
    db.add(saved)
    await db.flush()

    # Reload with physician relationship
    stmt = (
        select(SavedPhysician)
        .where(SavedPhysician.id == saved.id)
        .options(selectinload(SavedPhysician.physician))
    )
    result = await db.execute(stmt)
    return result.scalar_one()


@router.patch("/saved/{saved_id}", response_model=SavedPhysicianResponse)
async def update_saved(
    saved_id: int,
    body: SavedPhysicianUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update notes / relationship for a saved physician."""
    result = await db.execute(
        select(SavedPhysician)
        .where(SavedPhysician.id == saved_id, SavedPhysician.user_id == current_user.id)
        .options(selectinload(SavedPhysician.physician))
    )
    saved = result.scalar_one_or_none()
    if not saved:
        raise HTTPException(status_code=404, detail="Saved physician not found")

    changed = body.model_dump(exclude_unset=True)

    # If marking as primary care, unset others
    if changed.get("is_primary_care"):
        prev = await db.execute(
            select(SavedPhysician).where(
                SavedPhysician.user_id == current_user.id,
                SavedPhysician.is_primary_care == True,  # noqa: E712
                SavedPhysician.id != saved_id,
            )
        )
        for sp in prev.scalars().all():
            sp.is_primary_care = False

    for field, value in changed.items():
        setattr(saved, field, value)

    await db.flush()
    await db.refresh(saved)
    return saved


@router.delete("/saved/{saved_id}", status_code=204)
async def unsave_physician(
    saved_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a physician from my saved list."""
    result = await db.execute(
        select(SavedPhysician).where(
            SavedPhysician.id == saved_id,
            SavedPhysician.user_id == current_user.id,
        )
    )
    saved = result.scalar_one_or_none()
    if not saved:
        raise HTTPException(status_code=404, detail="Saved physician not found")
    await db.delete(saved)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  REVIEWS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/{physician_id}/reviews", response_model=list[ReviewResponse])
async def list_reviews(
    physician_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all approved reviews for a physician."""
    result = await db.execute(
        select(PhysicianReview)
        .where(
            PhysicianReview.physician_id == physician_id,
            PhysicianReview.is_approved == True,  # noqa: E712
        )
        .order_by(PhysicianReview.created_at.desc())
    )
    reviews = result.scalars().all()

    # Resolve reviewer names (respecting anonymity)
    reviewer_ids = {r.user_id for r in reviews if not r.is_anonymous}
    names: dict[int, str] = {}
    if reviewer_ids:
        users_result = await db.execute(
            select(User.id, User.full_name).where(User.id.in_(reviewer_ids))
        )
        names = dict(users_result.all())

    out = []
    for r in reviews:
        data = {c.key: getattr(r, c.key) for c in PhysicianReview.__table__.columns}
        data["reviewer_name"] = names.get(r.user_id, "Anonymous") if not r.is_anonymous else "Anonymous"
        out.append(ReviewResponse(**data))
    return out


@router.post("/{physician_id}/reviews", response_model=ReviewResponse, status_code=201)
async def create_review(
    physician_id: int,
    body: ReviewCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a review for a physician (one per user per physician)."""
    # Verify physician exists
    phys_result = await db.execute(select(Physician).where(Physician.id == physician_id))
    physician = phys_result.scalar_one_or_none()
    if not physician:
        raise HTTPException(status_code=404, detail="Physician not found")

    # Check duplicate
    existing = await db.execute(
        select(PhysicianReview).where(
            PhysicianReview.user_id == current_user.id,
            PhysicianReview.physician_id == physician_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="You already reviewed this physician")

    review = PhysicianReview(
        user_id=current_user.id,
        physician_id=physician_id,
        **body.model_dump(),
    )
    db.add(review)
    await db.flush()

    # Update physician aggregate rating
    await _refresh_rating(physician, db)

    data = {c.key: getattr(review, c.key) for c in PhysicianReview.__table__.columns}
    data["reviewer_name"] = "Anonymous" if review.is_anonymous else current_user.full_name
    return ReviewResponse(**data)


@router.patch("/reviews/{review_id}", response_model=ReviewResponse)
async def update_review(
    review_id: int,
    body: ReviewUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update my review."""
    result = await db.execute(
        select(PhysicianReview).where(
            PhysicianReview.id == review_id,
            PhysicianReview.user_id == current_user.id,
        )
    )
    review = result.scalar_one_or_none()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(review, field, value)

    await db.flush()
    await db.refresh(review)

    # Refresh physician rating
    phys_result = await db.execute(select(Physician).where(Physician.id == review.physician_id))
    physician = phys_result.scalar_one_or_none()
    if physician:
        await _refresh_rating(physician, db)

    data = {c.key: getattr(review, c.key) for c in PhysicianReview.__table__.columns}
    data["reviewer_name"] = "Anonymous" if review.is_anonymous else current_user.full_name
    return ReviewResponse(**data)


@router.delete("/reviews/{review_id}", status_code=204)
async def delete_review(
    review_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete my review."""
    result = await db.execute(
        select(PhysicianReview).where(
            PhysicianReview.id == review_id,
            PhysicianReview.user_id == current_user.id,
        )
    )
    review = result.scalar_one_or_none()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    physician_id = review.physician_id
    await db.delete(review)
    await db.flush()

    # Refresh physician rating
    phys_result = await db.execute(select(Physician).where(Physician.id == physician_id))
    physician = phys_result.scalar_one_or_none()
    if physician:
        await _refresh_rating(physician, db)


# ── Helper ─────────────────────────────────────────────────────────

async def _refresh_rating(physician: Physician, db: AsyncSession) -> None:
    """Recompute average rating + count for a physician."""
    result = await db.execute(
        select(
            func.avg(PhysicianReview.rating),
            func.count(PhysicianReview.id),
        ).where(
            PhysicianReview.physician_id == physician.id,
            PhysicianReview.is_approved == True,  # noqa: E712
        )
    )
    avg_rating, count = result.one()
    physician.average_rating = round(float(avg_rating), 2) if avg_rating else 0.0
    physician.review_count = count or 0
