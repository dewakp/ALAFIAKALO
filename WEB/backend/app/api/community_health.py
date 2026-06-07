"""Community Health endpoints — alerts, recalls, guidelines, reports, subscriptions."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_
from datetime import date, timedelta, datetime, timezone
import json

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.community_health import (
    CommunityHealthAlert,
    CommunityHealthReport,
    HealthGuideline,
    UserAlertSubscription,
    AlertReadStatus,
)
from app.schemas.community_health import (
    AlertCreate, AlertUpdate, AlertResponse,
    ReportCreate, ReportResponse,
    GuidelineCreate, GuidelineResponse,
    SubscriptionCreate, SubscriptionResponse,
    CommunityDashboardStats,
    AlertCategoryInfo, AlertSourceInfo,
)

router = APIRouter()


# ── Serialization helpers ──────────────────────────────────────────────

def _json_loads(val: str | None) -> list | None:
    if val is None:
        return None
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return None


def _json_dumps(val: list | None) -> str | None:
    if val is None:
        return None
    return json.dumps(val)


def _alert_to_response(a: CommunityHealthAlert) -> AlertResponse:
    return AlertResponse(
        id=a.id,
        title=a.title,
        summary=a.summary,
        description=a.description,
        category=a.category,
        severity=a.severity,
        source=a.source,
        source_url=a.source_url,
        source_reference_id=a.source_reference_id,
        affected_countries=_json_loads(a.affected_countries),
        affected_regions=_json_loads(a.affected_regions),
        is_global=a.is_global,
        issued_date=a.issued_date,
        effective_date=a.effective_date,
        expiry_date=a.expiry_date,
        product_name=a.product_name,
        product_type=a.product_type,
        manufacturer=a.manufacturer,
        lot_numbers=_json_loads(a.lot_numbers),
        reason_for_recall=a.reason_for_recall,
        recall_class=a.recall_class,
        disease_name=a.disease_name,
        pathogen=a.pathogen,
        confirmed_cases=a.confirmed_cases,
        deaths=a.deaths,
        recommended_actions=_json_loads(a.recommended_actions),
        target_population=_json_loads(a.target_population),
        is_active=a.is_active,
        is_resolved=a.is_resolved,
        resolution_date=a.resolution_date,
        resolution_notes=a.resolution_notes,
        tags=_json_loads(a.tags),
        created_at=a.created_at,
        updated_at=a.updated_at,
    )


# ═══════════════════════════════════════════════════════════════════════
# REFERENCE DATA — categories, sources
# ═══════════════════════════════════════════════════════════════════════

ALERT_CATEGORIES = [
    AlertCategoryInfo(id="pandemic", name="Pandemic", description="Global disease pandemics", icon="🦠"),
    AlertCategoryInfo(id="epidemic", name="Epidemic", description="Regional disease epidemics", icon="🏥"),
    AlertCategoryInfo(id="outbreak", name="Outbreak", description="Localized disease outbreaks", icon="⚠️"),
    AlertCategoryInfo(id="recall_drug", name="Drug Recall", description="Pharmaceutical recalls from FDA/EMA/etc.", icon="💊"),
    AlertCategoryInfo(id="recall_food", name="Food Recall", description="Food safety recalls and contamination", icon="🍽️"),
    AlertCategoryInfo(id="recall_device", name="Device Recall", description="Medical device safety recalls", icon="🩺"),
    AlertCategoryInfo(id="advisory", name="Health Advisory", description="Public health advisories & warnings", icon="📢"),
    AlertCategoryInfo(id="poison", name="Poison Alert", description="Poisoning alerts & toxic exposure warnings", icon="☠️"),
    AlertCategoryInfo(id="environmental", name="Environmental", description="Environmental health hazards", icon="🌍"),
    AlertCategoryInfo(id="natural_disaster", name="Natural Disaster", description="Health impacts of natural disasters", icon="🌪️"),
    AlertCategoryInfo(id="vaccination", name="Vaccination", description="Vaccination campaigns & updates", icon="💉"),
    AlertCategoryInfo(id="guideline_update", name="Guideline Update", description="Clinical guideline updates", icon="📋"),
    AlertCategoryInfo(id="travel_health", name="Travel Health", description="Travel health notices & requirements", icon="✈️"),
    AlertCategoryInfo(id="water_safety", name="Water Safety", description="Drinking water contamination alerts", icon="💧"),
    AlertCategoryInfo(id="air_quality", name="Air Quality", description="Air quality warnings & hazards", icon="🌫️"),
]

ALERT_SOURCES = [
    AlertSourceInfo(id="who", name="WHO", full_name="World Health Organization", url="https://www.who.int", country=None),
    AlertSourceInfo(id="cdc", name="CDC", full_name="US Centers for Disease Control and Prevention", url="https://www.cdc.gov", country="US"),
    AlertSourceInfo(id="ecdc", name="ECDC", full_name="European Centre for Disease Prevention and Control", url="https://www.ecdc.europa.eu", country="EU"),
    AlertSourceInfo(id="fda", name="FDA", full_name="US Food & Drug Administration", url="https://www.fda.gov", country="US"),
    AlertSourceInfo(id="ema", name="EMA", full_name="European Medicines Agency", url="https://www.ema.europa.eu", country="EU"),
    AlertSourceInfo(id="health_canada", name="Health Canada", full_name="Health Canada / Santé Canada", url="https://www.canada.ca/en/health-canada.html", country="CA"),
    AlertSourceInfo(id="mhra", name="MHRA", full_name="UK Medicines & Healthcare products Regulatory Agency", url="https://www.gov.uk/government/organisations/mhra", country="UK"),
    AlertSourceInfo(id="tga", name="TGA", full_name="Therapeutic Goods Administration (Australia)", url="https://www.tga.gov.au", country="AU"),
    AlertSourceInfo(id="phac", name="PHAC", full_name="Public Health Agency of Canada", url="https://www.canada.ca/en/public-health.html", country="CA"),
    AlertSourceInfo(id="paho", name="PAHO", full_name="Pan American Health Organization", url="https://www.paho.org", country=None),
    AlertSourceInfo(id="africa_cdc", name="Africa CDC", full_name="Africa Centres for Disease Control and Prevention", url="https://africacdc.org", country=None),
    AlertSourceInfo(id="poison_control", name="Poison Control", full_name="National Poison Control Centers", url="https://www.poison.org", country="US"),
]


@router.get("/categories", response_model=list[AlertCategoryInfo])
async def get_alert_categories():
    """List all alert categories."""
    return ALERT_CATEGORIES


@router.get("/sources", response_model=list[AlertSourceInfo])
async def get_alert_sources():
    """List all authoritative health sources."""
    return ALERT_SOURCES


# ═══════════════════════════════════════════════════════════════════════
# DASHBOARD STATS
# ═══════════════════════════════════════════════════════════════════════

@router.get("/dashboard", response_model=CommunityDashboardStats)
async def get_community_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Comprehensive community health dashboard."""
    now = date.today()
    thirty_days_ago = now - timedelta(days=30)

    # Counts
    base = select(func.count()).select_from(CommunityHealthAlert).where(CommunityHealthAlert.is_active == True)

    total_active = (await db.execute(base)).scalar() or 0
    critical = (await db.execute(base.where(CommunityHealthAlert.severity == "critical"))).scalar() or 0

    recall_cats = ("recall_drug", "recall_food", "recall_device")
    active_recalls = (await db.execute(base.where(CommunityHealthAlert.category.in_(recall_cats)))).scalar() or 0

    outbreak_cats = ("pandemic", "epidemic", "outbreak")
    active_outbreaks = (await db.execute(base.where(CommunityHealthAlert.category.in_(outbreak_cats)))).scalar() or 0

    active_advisories = (await db.execute(base.where(CommunityHealthAlert.category == "advisory"))).scalar() or 0
    active_poison = (await db.execute(base.where(CommunityHealthAlert.category == "poison"))).scalar() or 0

    total_guidelines = (await db.execute(
        select(func.count()).select_from(HealthGuideline).where(HealthGuideline.is_current == True)
    )).scalar() or 0

    user_reports = (await db.execute(
        select(func.count()).select_from(CommunityHealthReport)
        .where(CommunityHealthReport.user_id == current_user.id)
        .where(CommunityHealthReport.created_at >= datetime(thirty_days_ago.year, thirty_days_ago.month, thirty_days_ago.day, tzinfo=timezone.utc))
    )).scalar() or 0

    # Unread & bookmarked
    read_ids_q = select(AlertReadStatus.alert_id).where(
        AlertReadStatus.user_id == current_user.id,
        AlertReadStatus.is_read == True,
    )
    read_ids = (await db.execute(read_ids_q)).scalars().all()

    unread_count = total_active - len(set(read_ids))
    if unread_count < 0:
        unread_count = 0

    bookmarked = (await db.execute(
        select(func.count()).select_from(AlertReadStatus)
        .where(AlertReadStatus.user_id == current_user.id, AlertReadStatus.is_bookmarked == True)
    )).scalar() or 0

    # Latest items
    latest_outbreaks_q = (
        select(CommunityHealthAlert)
        .where(CommunityHealthAlert.is_active == True, CommunityHealthAlert.category.in_(outbreak_cats))
        .order_by(CommunityHealthAlert.issued_date.desc())
        .limit(5)
    )
    outbreaks = (await db.execute(latest_outbreaks_q)).scalars().all()

    latest_recalls_q = (
        select(CommunityHealthAlert)
        .where(CommunityHealthAlert.is_active == True, CommunityHealthAlert.category.in_(recall_cats))
        .order_by(CommunityHealthAlert.issued_date.desc())
        .limit(5)
    )
    recalls = (await db.execute(latest_recalls_q)).scalars().all()

    latest_advisories_q = (
        select(CommunityHealthAlert)
        .where(CommunityHealthAlert.is_active == True, CommunityHealthAlert.category == "advisory")
        .order_by(CommunityHealthAlert.issued_date.desc())
        .limit(5)
    )
    advisories = (await db.execute(latest_advisories_q)).scalars().all()

    return CommunityDashboardStats(
        total_active_alerts=total_active,
        critical_alerts=critical,
        active_recalls=active_recalls,
        active_outbreaks=active_outbreaks,
        active_advisories=active_advisories,
        active_poison_alerts=active_poison,
        total_guidelines=total_guidelines,
        user_reports_30d=user_reports,
        unread_alerts=unread_count,
        bookmarked_alerts=bookmarked,
        latest_outbreaks=[_alert_to_response(a) for a in outbreaks],
        latest_recalls=[_alert_to_response(a) for a in recalls],
        latest_advisories=[_alert_to_response(a) for a in advisories],
    )


# ═══════════════════════════════════════════════════════════════════════
# ALERTS / RECALLS / ADVISORIES
# ═══════════════════════════════════════════════════════════════════════

@router.get("/alerts", response_model=list[AlertResponse])
async def list_alerts(
    category: str | None = None,
    source: str | None = None,
    severity: str | None = None,
    country: str | None = None,
    active_only: bool = True,
    search: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List community health alerts with filtering."""
    q = select(CommunityHealthAlert)
    if active_only:
        q = q.where(CommunityHealthAlert.is_active == True)
    if category:
        q = q.where(CommunityHealthAlert.category == category)
    if source:
        q = q.where(CommunityHealthAlert.source == source)
    if severity:
        q = q.where(CommunityHealthAlert.severity == severity)
    if country:
        q = q.where(or_(
            CommunityHealthAlert.is_global == True,
            CommunityHealthAlert.affected_countries.contains(country),
        ))
    if search:
        q = q.where(or_(
            CommunityHealthAlert.title.ilike(f"%{search}%"),
            CommunityHealthAlert.summary.ilike(f"%{search}%"),
            CommunityHealthAlert.disease_name.ilike(f"%{search}%"),
            CommunityHealthAlert.product_name.ilike(f"%{search}%"),
        ))
    q = q.order_by(CommunityHealthAlert.issued_date.desc()).offset(skip).limit(limit)
    result = await db.execute(q)
    return [_alert_to_response(a) for a in result.scalars().all()]


@router.get("/alerts/{alert_id}", response_model=AlertResponse)
async def get_alert(
    alert_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a single alert and mark as read."""
    result = await db.execute(select(CommunityHealthAlert).where(CommunityHealthAlert.id == alert_id))
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    # Mark as read
    existing = (await db.execute(
        select(AlertReadStatus).where(
            AlertReadStatus.user_id == current_user.id,
            AlertReadStatus.alert_id == alert_id,
        )
    )).scalar_one_or_none()
    if not existing:
        db.add(AlertReadStatus(user_id=current_user.id, alert_id=alert_id, is_read=True))
    elif not existing.is_read:
        existing.is_read = True

    return _alert_to_response(alert)


@router.post("/alerts", response_model=AlertResponse)
async def create_alert(
    data: AlertCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a community health alert (admin/system use)."""
    alert = CommunityHealthAlert(
        title=data.title,
        summary=data.summary,
        description=data.description,
        category=data.category,
        severity=data.severity,
        source=data.source,
        source_url=data.source_url,
        source_reference_id=data.source_reference_id,
        affected_countries=_json_dumps(data.affected_countries),
        affected_regions=_json_dumps(data.affected_regions),
        is_global=data.is_global,
        issued_date=data.issued_date,
        effective_date=data.effective_date,
        expiry_date=data.expiry_date,
        product_name=data.product_name,
        product_type=data.product_type,
        manufacturer=data.manufacturer,
        lot_numbers=_json_dumps(data.lot_numbers),
        reason_for_recall=data.reason_for_recall,
        recall_class=data.recall_class,
        disease_name=data.disease_name,
        pathogen=data.pathogen,
        confirmed_cases=data.confirmed_cases,
        deaths=data.deaths,
        recommended_actions=_json_dumps(data.recommended_actions),
        target_population=_json_dumps(data.target_population),
        tags=_json_dumps(data.tags),
    )
    db.add(alert)
    await db.flush()
    await db.refresh(alert)
    return _alert_to_response(alert)


@router.put("/alerts/{alert_id}", response_model=AlertResponse)
async def update_alert(
    alert_id: int,
    data: AlertUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update an existing alert."""
    result = await db.execute(select(CommunityHealthAlert).where(CommunityHealthAlert.id == alert_id))
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(alert, field, value)

    await db.flush()
    await db.refresh(alert)
    return _alert_to_response(alert)


@router.post("/alerts/{alert_id}/bookmark")
async def toggle_bookmark(
    alert_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Bookmark/unbookmark an alert."""
    existing = (await db.execute(
        select(AlertReadStatus).where(
            AlertReadStatus.user_id == current_user.id,
            AlertReadStatus.alert_id == alert_id,
        )
    )).scalar_one_or_none()

    if existing:
        existing.is_bookmarked = not existing.is_bookmarked
        return {"bookmarked": existing.is_bookmarked}
    else:
        db.add(AlertReadStatus(user_id=current_user.id, alert_id=alert_id, is_read=True, is_bookmarked=True))
        return {"bookmarked": True}


# ═══════════════════════════════════════════════════════════════════════
# COMMUNITY HEALTH REPORTS (crowd-sourced)
# ═══════════════════════════════════════════════════════════════════════

@router.get("/reports", response_model=list[ReportResponse])
async def list_reports(
    report_type: str | None = None,
    country: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List community health reports (own + verified public)."""
    q = select(CommunityHealthReport).where(
        or_(
            CommunityHealthReport.user_id == current_user.id,
            CommunityHealthReport.is_verified == True,
        )
    )
    if report_type:
        q = q.where(CommunityHealthReport.report_type == report_type)
    if country:
        q = q.where(CommunityHealthReport.country == country)
    q = q.order_by(CommunityHealthReport.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(q)
    reports = result.scalars().all()
    return [_report_to_response(r) for r in reports]


@router.post("/reports", response_model=ReportResponse)
async def create_report(
    data: ReportCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Submit a community health report."""
    report = CommunityHealthReport(
        user_id=current_user.id,
        report_type=data.report_type,
        title=data.title,
        description=data.description,
        latitude=data.latitude,
        longitude=data.longitude,
        location_name=data.location_name,
        country=data.country,
        region=data.region,
        symptoms_reported=_json_dumps(data.symptoms_reported),
        number_affected=data.number_affected,
        onset_date=data.onset_date,
        product_involved=data.product_involved,
        severity=data.severity,
    )
    db.add(report)
    await db.flush()
    await db.refresh(report)
    return _report_to_response(report)


@router.delete("/reports/{report_id}")
async def delete_report(
    report_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete own community report."""
    result = await db.execute(
        select(CommunityHealthReport).where(
            CommunityHealthReport.id == report_id,
            CommunityHealthReport.user_id == current_user.id,
        )
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    await db.delete(report)
    return {"detail": "Report deleted"}


def _report_to_response(r: CommunityHealthReport) -> ReportResponse:
    return ReportResponse(
        id=r.id,
        user_id=r.user_id,
        report_type=r.report_type,
        title=r.title,
        description=r.description,
        latitude=r.latitude,
        longitude=r.longitude,
        location_name=r.location_name,
        country=r.country,
        region=r.region,
        symptoms_reported=_json_loads(r.symptoms_reported),
        number_affected=r.number_affected,
        onset_date=r.onset_date,
        product_involved=r.product_involved,
        severity=r.severity,
        is_verified=r.is_verified,
        is_active=r.is_active,
        created_at=r.created_at,
    )


# ═══════════════════════════════════════════════════════════════════════
# HEALTH GUIDELINES
# ═══════════════════════════════════════════════════════════════════════

@router.get("/guidelines", response_model=list[GuidelineResponse])
async def list_guidelines(
    category: str | None = None,
    source: str | None = None,
    search: str | None = None,
    current_only: bool = True,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List health guidelines from WHO/CDC/etc."""
    q = select(HealthGuideline)
    if current_only:
        q = q.where(HealthGuideline.is_current == True)
    if category:
        q = q.where(HealthGuideline.category == category)
    if source:
        q = q.where(HealthGuideline.source == source)
    if search:
        q = q.where(or_(
            HealthGuideline.title.ilike(f"%{search}%"),
            HealthGuideline.summary.ilike(f"%{search}%"),
        ))
    q = q.order_by(HealthGuideline.effective_date.desc().nullslast()).offset(skip).limit(limit)
    result = await db.execute(q)
    return [_guideline_to_response(g) for g in result.scalars().all()]


@router.post("/guidelines", response_model=GuidelineResponse)
async def create_guideline(
    data: GuidelineCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Add a health guideline (admin/system use)."""
    guideline = HealthGuideline(
        title=data.title,
        summary=data.summary,
        full_text=data.full_text,
        category=data.category,
        source=data.source,
        source_url=data.source_url,
        version=data.version,
        effective_date=data.effective_date,
        target_population=_json_dumps(data.target_population),
        applicable_countries=_json_dumps(data.applicable_countries),
        applicable_conditions=_json_dumps(data.applicable_conditions),
        recommendations=_json_dumps(data.recommendations),
        tags=_json_dumps(data.tags),
    )
    db.add(guideline)
    await db.flush()
    await db.refresh(guideline)
    return _guideline_to_response(guideline)


@router.get("/guidelines/{guideline_id}", response_model=GuidelineResponse)
async def get_guideline(
    guideline_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a single guideline."""
    result = await db.execute(select(HealthGuideline).where(HealthGuideline.id == guideline_id))
    guideline = result.scalar_one_or_none()
    if not guideline:
        raise HTTPException(status_code=404, detail="Guideline not found")
    return _guideline_to_response(guideline)


def _guideline_to_response(g: HealthGuideline) -> GuidelineResponse:
    return GuidelineResponse(
        id=g.id,
        title=g.title,
        summary=g.summary,
        full_text=g.full_text,
        category=g.category,
        source=g.source,
        source_url=g.source_url,
        version=g.version,
        effective_date=g.effective_date,
        superseded_date=g.superseded_date,
        is_current=g.is_current,
        target_population=_json_loads(g.target_population),
        applicable_countries=_json_loads(g.applicable_countries),
        applicable_conditions=_json_loads(g.applicable_conditions),
        recommendations=_json_loads(g.recommendations),
        tags=_json_loads(g.tags),
        created_at=g.created_at,
    )


# ═══════════════════════════════════════════════════════════════════════
# USER ALERT SUBSCRIPTIONS
# ═══════════════════════════════════════════════════════════════════════

@router.get("/subscriptions", response_model=SubscriptionResponse | None)
async def get_subscription(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get alert subscription preferences."""
    result = await db.execute(
        select(UserAlertSubscription).where(UserAlertSubscription.user_id == current_user.id)
    )
    sub = result.scalar_one_or_none()
    if not sub:
        return None
    return _sub_to_response(sub)


@router.put("/subscriptions", response_model=SubscriptionResponse)
async def upsert_subscription(
    data: SubscriptionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create or update alert subscription preferences."""
    result = await db.execute(
        select(UserAlertSubscription).where(UserAlertSubscription.user_id == current_user.id)
    )
    sub = result.scalar_one_or_none()

    if sub:
        sub.categories = _json_dumps(data.categories)
        sub.sources = _json_dumps(data.sources)
        sub.countries = _json_dumps(data.countries)
        sub.severities = _json_dumps(data.severities)
        sub.push_enabled = data.push_enabled
        sub.email_enabled = data.email_enabled
        sub.sms_enabled = data.sms_enabled
    else:
        sub = UserAlertSubscription(
            user_id=current_user.id,
            categories=_json_dumps(data.categories),
            sources=_json_dumps(data.sources),
            countries=_json_dumps(data.countries),
            severities=_json_dumps(data.severities),
            push_enabled=data.push_enabled,
            email_enabled=data.email_enabled,
            sms_enabled=data.sms_enabled,
        )
        db.add(sub)

    await db.flush()
    await db.refresh(sub)
    return _sub_to_response(sub)


def _sub_to_response(s: UserAlertSubscription) -> SubscriptionResponse:
    return SubscriptionResponse(
        id=s.id,
        user_id=s.user_id,
        categories=_json_loads(s.categories),
        sources=_json_loads(s.sources),
        countries=_json_loads(s.countries),
        severities=_json_loads(s.severities),
        push_enabled=s.push_enabled,
        email_enabled=s.email_enabled,
        sms_enabled=s.sms_enabled,
        created_at=s.created_at,
    )


# ═══════════════════════════════════════════════════════════════════════
# SEED DATA — pre-populate with real-world alerts & guidelines
# ═══════════════════════════════════════════════════════════════════════

@router.post("/seed")
async def seed_community_data(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Seed database with sample WHO/CDC/FDA alerts & guidelines."""
    # Check if already seeded
    count = (await db.execute(select(func.count()).select_from(CommunityHealthAlert))).scalar()
    if count > 0:
        return {"detail": f"Already seeded ({count} alerts exist)"}

    alerts_data = [
        # Pandemics / Outbreaks
        AlertCreate(
            title="WHO: Mpox (Clade I) — Public Health Emergency",
            summary="WHO declared mpox clade I outbreak a PHEIC. Enhanced surveillance recommended in all countries.",
            category="pandemic", severity="high", source="who",
            source_url="https://www.who.int/emergencies/diseases/mpox",
            is_global=True, issued_date=date(2024, 8, 14),
            disease_name="Mpox (clade I)", pathogen="Monkeypox virus",
            confirmed_cases=38000, deaths=1500,
            recommended_actions=["Monitor for symptoms", "Vaccination for high-risk groups", "Isolate confirmed cases"],
            tags=["mpox", "monkeypox", "PHEIC"],
        ),
        AlertCreate(
            title="WHO: Avian Influenza A(H5N1) — Increased Human Cases",
            summary="Rising H5N1 detections in dairy cattle and poultry. Sporadic human cases reported.",
            category="outbreak", severity="high", source="who",
            source_url="https://www.who.int/emergencies/diseases/avian-influenza",
            is_global=True, issued_date=date(2025, 1, 10),
            disease_name="Avian Influenza A(H5N1)", pathogen="H5N1 Influenza A",
            confirmed_cases=950, deaths=52,
            recommended_actions=["Avoid contact with sick birds", "Report dead poultry", "PPE for farm workers"],
            tags=["H5N1", "bird flu", "avian influenza"],
        ),
        AlertCreate(
            title="CDC: Measles Outbreak — Multi-State Alert",
            summary="Measles cases confirmed in 12 US states linked to declining childhood vaccination rates.",
            category="outbreak", severity="high", source="cdc",
            source_url="https://www.cdc.gov/measles/",
            affected_countries=["US"], issued_date=date(2025, 2, 1),
            disease_name="Measles", pathogen="Measles virus",
            confirmed_cases=372,
            recommended_actions=["Verify MMR vaccination status", "Isolate suspected cases", "Post-exposure prophylaxis within 72h"],
            tags=["measles", "MMR", "vaccination"],
        ),

        # Drug Recalls
        AlertCreate(
            title="FDA: Voluntary Recall of Metformin HCl Extended-Release Tablets",
            summary="Several lots recalled due to NDMA (N-Nitrosodimethylamine) impurity above acceptable limits.",
            category="recall_drug", severity="moderate", source="fda",
            source_url="https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts",
            affected_countries=["US"], issued_date=date(2025, 1, 15),
            product_name="Metformin HCl ER 500mg/750mg/1000mg", product_type="drug",
            manufacturer="Various Generic Manufacturers",
            lot_numbers=["MET2024-A1", "MET2024-B3", "MET2024-C5"],
            reason_for_recall="NDMA impurity above acceptable daily intake limit",
            recall_class="II",
            recommended_actions=["Check lot numbers", "Contact pharmacy for replacement", "Do not stop medication without consulting doctor"],
            tags=["metformin", "NDMA", "diabetes"],
        ),
        AlertCreate(
            title="EMA: Safety Signal — Ozempic (Semaglutide) Thyroid Monitoring",
            summary="EMA recommends enhanced thyroid monitoring for patients on GLP-1 agonists following post-market signals.",
            category="advisory", severity="moderate", source="ema",
            source_url="https://www.ema.europa.eu/en/medicines",
            affected_countries=["EU"], issued_date=date(2025, 1, 28),
            product_name="Semaglutide (Ozempic/Wegovy)", product_type="drug",
            recommended_actions=["Regular thyroid function tests", "Report thyroid symptoms", "Monitor for neck lumps"],
            tags=["semaglutide", "ozempic", "GLP-1", "thyroid"],
        ),
        AlertCreate(
            title="Health Canada: Recall of Contaminated Eye Drops",
            summary="Multiple brands of over-the-counter eye drops recalled due to bacterial contamination (Pseudomonas aeruginosa).",
            category="recall_drug", severity="high", source="health_canada",
            source_url="https://recalls-rappels.canada.ca/en",
            affected_countries=["CA"], issued_date=date(2025, 2, 5),
            product_name="Various OTC Artificial Tears", product_type="drug",
            manufacturer="Global Pharma Healthcare",
            reason_for_recall="Bacterial contamination — risk of serious eye infection",
            recall_class="I",
            recommended_actions=["Stop use immediately", "Check product list", "Seek medical attention if symptoms"],
            tags=["eye drops", "contamination", "pseudomonas"],
        ),

        # Food Recalls
        AlertCreate(
            title="FDA: Recall of Ready-to-Eat Salads — Listeria Risk",
            summary="Nationwide recall of pre-packaged salads due to potential Listeria monocytogenes contamination.",
            category="recall_food", severity="high", source="fda",
            affected_countries=["US"], issued_date=date(2025, 2, 8),
            product_name="FreshCo Ready-to-Eat Garden Salads", product_type="food",
            manufacturer="FreshCo Foods Inc.",
            lot_numbers=["SAL-2025-0201", "SAL-2025-0205", "SAL-2025-0208"],
            reason_for_recall="Potential Listeria monocytogenes contamination",
            recall_class="I",
            recommended_actions=["Do not consume", "Discard or return for refund", "Monitor for fever, muscle aches, diarrhea"],
            tags=["listeria", "salad", "food safety"],
        ),

        # Poison / Environmental
        AlertCreate(
            title="Poison Control: Warning — Laundry Pod Ingestion in Children",
            summary="Surge in pediatric poisoning cases from liquid laundry detergent pods. Keep out of children's reach.",
            category="poison", severity="high", source="poison_control",
            source_url="https://www.poison.org/articles/laundry-detergent-pods",
            is_global=True, issued_date=date(2025, 1, 20),
            recommended_actions=["Store pods in locked cabinet", "Call Poison Control: 1-800-222-1222", "Seek ER if ingested"],
            target_population=["Parents", "Caregivers", "Pediatric"],
            tags=["poison", "laundry pods", "pediatric", "children"],
        ),
        AlertCreate(
            title="EPA/CDC: Elevated Lead Levels in Municipal Water — Flint Follow-up",
            summary="Continued monitoring advisory for communities with aging water infrastructure. Test your water.",
            category="water_safety", severity="moderate", source="cdc",
            affected_countries=["US"], issued_date=date(2025, 1, 5),
            recommended_actions=["Test home water", "Use certified filters", "Contact local water authority"],
            tags=["lead", "water safety", "contamination"],
        ),

        # Travel Health
        AlertCreate(
            title="CDC: Travel Health Notice — Dengue in Southeast Asia",
            summary="Increased dengue transmission in Thailand, Vietnam, Philippines. Use mosquito prevention measures.",
            category="travel_health", severity="moderate", source="cdc",
            source_url="https://wwwnc.cdc.gov/travel/notices",
            affected_countries=["TH", "VN", "PH"], issued_date=date(2025, 2, 1),
            disease_name="Dengue Fever", pathogen="Dengue virus",
            recommended_actions=["Use EPA-registered insect repellent", "Wear long sleeves", "Sleep under mosquito nets"],
            tags=["dengue", "travel", "mosquito", "southeast asia"],
        ),
    ]

    guidelines_data = [
        GuidelineCreate(
            title="WHO: COVID-19 Vaccination — Updated 2025 Guidance",
            summary="Updated recommendations for COVID-19 vaccination including booster schedules for high-risk groups.",
            category="vaccination", source="who",
            source_url="https://www.who.int/publications/i/item/WHO-2019-nCoV-vaccines-SAGE-recommendation",
            version="2025.1", effective_date=date(2025, 1, 1),
            target_population=["Healthcare workers", "Elderly 65+", "Immunocompromised", "Pregnant women"],
            recommendations=[
                "Primary series for all adults and children 6mo+",
                "Annual booster for high-risk groups",
                "Updated formulation targeting current variants",
                "Co-administration with influenza vaccine acceptable",
            ],
            tags=["COVID-19", "vaccination", "booster"],
        ),
        GuidelineCreate(
            title="CDC: Childhood Immunization Schedule 2025",
            summary="Recommended immunization schedule for children and adolescents aged 18 years or younger.",
            category="vaccination", source="cdc",
            source_url="https://www.cdc.gov/vaccines/schedules/",
            version="2025", effective_date=date(2025, 2, 1),
            applicable_countries=["US"],
            recommendations=[
                "HepB: Birth, 1-2mo, 6-18mo",
                "DTaP: 2mo, 4mo, 6mo, 15-18mo, 4-6yr",
                "IPV: 2mo, 4mo, 6-18mo, 4-6yr",
                "MMR: 12-15mo, 4-6yr",
                "Varicella: 12-15mo, 4-6yr",
                "HPV: 11-12yr (2–3 dose series)",
            ],
            tags=["childhood", "immunization", "schedule"],
        ),
        GuidelineCreate(
            title="WHO: Hand Hygiene in Healthcare Settings",
            summary="Evidence-based guidelines for hand hygiene to prevent healthcare-associated infections.",
            category="infection_prevention", source="who",
            source_url="https://www.who.int/publications/i/item/9789241597906",
            version="2.0", effective_date=date(2024, 5, 5),
            target_population=["Healthcare workers", "Hospital staff"],
            recommendations=[
                "5 Moments for Hand Hygiene",
                "Alcohol-based hand rub as preferred method",
                "Soap and water when hands visibly soiled",
                "Minimum 20 seconds hand washing duration",
            ],
            tags=["hand hygiene", "infection control", "HAI"],
        ),
        GuidelineCreate(
            title="CDC: Antimicrobial Resistance — Prescribing Guidelines",
            summary="Guidelines to combat antimicrobial resistance through appropriate antibiotic prescribing.",
            category="antimicrobial", source="cdc",
            source_url="https://www.cdc.gov/antibiotic-use/",
            version="2025.1", effective_date=date(2025, 1, 15),
            recommendations=[
                "Avoid antibiotics for viral infections",
                "Use narrow-spectrum when possible",
                "Complete full prescribed course",
                "Regular antibiogram review",
                "Consider antibiotic stewardship programs",
            ],
            tags=["AMR", "antibiotics", "stewardship"],
        ),
        GuidelineCreate(
            title="WHO: Non-Communicable Disease Prevention",
            summary="Global action plan for prevention and control of NCDs: cardiovascular, cancer, diabetes, chronic respiratory.",
            category="ncd", source="who",
            source_url="https://www.who.int/publications/i/item/9789241506236",
            version="2025", effective_date=date(2025, 1, 1),
            recommendations=[
                "Reduce tobacco use by 30%",
                "Reduce salt intake to <5g/day",
                "Reduce physical inactivity by 15%",
                "Screen for cervical, breast, colorectal cancer",
                "Ensure essential NCD medicines availability",
            ],
            tags=["NCD", "cardiovascular", "cancer", "diabetes"],
        ),
        GuidelineCreate(
            title="Health Canada: Cannabis Health Effects Advisory",
            summary="Evidence-based guidance on health effects of cannabis use with harm reduction recommendations.",
            category="other", source="health_canada",
            source_url="https://www.canada.ca/en/health-canada/services/drugs-medication/cannabis.html",
            version="2024.2", effective_date=date(2024, 10, 1),
            applicable_countries=["CA"],
            recommendations=[
                "Delay use until after age 25",
                "Choose lower-THC products",
                "Avoid smoking — consider edibles or vaporization",
                "Do not drive while impaired",
                "Avoid during pregnancy/breastfeeding",
            ],
            tags=["cannabis", "harm reduction"],
        ),
    ]

    # Insert alerts
    for a_data in alerts_data:
        alert = CommunityHealthAlert(
            title=a_data.title,
            summary=a_data.summary,
            description=a_data.description,
            category=a_data.category,
            severity=a_data.severity,
            source=a_data.source,
            source_url=a_data.source_url,
            source_reference_id=a_data.source_reference_id,
            affected_countries=_json_dumps(a_data.affected_countries),
            affected_regions=_json_dumps(a_data.affected_regions),
            is_global=a_data.is_global,
            issued_date=a_data.issued_date,
            effective_date=a_data.effective_date,
            expiry_date=a_data.expiry_date,
            product_name=a_data.product_name,
            product_type=a_data.product_type,
            manufacturer=a_data.manufacturer,
            lot_numbers=_json_dumps(a_data.lot_numbers),
            reason_for_recall=a_data.reason_for_recall,
            recall_class=a_data.recall_class,
            disease_name=a_data.disease_name,
            pathogen=a_data.pathogen,
            confirmed_cases=a_data.confirmed_cases,
            deaths=a_data.deaths,
            recommended_actions=_json_dumps(a_data.recommended_actions),
            target_population=_json_dumps(a_data.target_population),
            tags=_json_dumps(a_data.tags),
        )
        db.add(alert)

    # Insert guidelines
    for g_data in guidelines_data:
        guideline = HealthGuideline(
            title=g_data.title,
            summary=g_data.summary,
            full_text=g_data.full_text,
            category=g_data.category,
            source=g_data.source,
            source_url=g_data.source_url,
            version=g_data.version,
            effective_date=g_data.effective_date,
            target_population=_json_dumps(g_data.target_population),
            applicable_countries=_json_dumps(g_data.applicable_countries),
            applicable_conditions=_json_dumps(g_data.applicable_conditions),
            recommendations=_json_dumps(g_data.recommendations),
            tags=_json_dumps(g_data.tags),
        )
        db.add(guideline)

    return {"detail": f"Seeded {len(alerts_data)} alerts and {len(guidelines_data)} guidelines"}
