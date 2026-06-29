"""Global disease surveillance — outward (WHO/CDC) + inward (patient symptoms).

`outward` looks at authoritative sources (WHO GHO globally, CDC NNDSS for the US,
Africa CDC via WHO's AFR region). `inward` aggregates de-identified ALAFIA patient
symptom activity by country. The map colors each country 0-4 by burden; the
drill-down endpoint expands one country across both lenses.
"""
import bisect
import json
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.conditions import SymptomLog
from app.models.community_health import CommunityHealthAlert, CommunityHealthReport
from app.services.iso_countries import resolve_country, ISO2_TO_NAME
from app.services.surveillance_sources import (
    DISEASES, DISEASE_BY_ID, SOURCES,
    fetch_who, fetch_who_series, fetch_cdc,
)
from app.schemas.surveillance import (
    DiseaseInfo, SourceInfo, CountrySignal, GlobalResponse,
    SeriesPoint, SymptomCluster, CountryAlert,
    OutwardDetail, CdcUsDetail, InwardDetail, CountryDetail,
)

router = APIRouter()

_OUTBREAK_CATEGORIES = ("pandemic", "epidemic", "outbreak", "advisory")


def _disease_info(d: dict) -> DiseaseInfo:
    return DiseaseInfo(
        id=d["id"], label=d["label"], icon=d["icon"], category=d["category"],
        who_unit=d["who_unit"], has_cdc=bool(d["cdc"]),
    )


def _quartile_cuts(values: list[float]) -> list[float]:
    """Three cut points (40th/70th/90th pct) splitting positives into 4 buckets."""
    vals = sorted(v for v in values if v and v > 0)
    if not vals:
        return []
    def pct(p: float) -> float:
        return vals[min(len(vals) - 1, int(p * len(vals)))]
    return [pct(0.4), pct(0.7), pct(0.9)]


def _level(value: float | None, cuts: list[float]) -> int:
    if not value or value <= 0:
        return 0
    if not cuts:
        return 1
    return 1 + bisect.bisect_right(cuts, value)


def _fmt(value: float) -> str:
    if value >= 1000:
        return f"{value:,.0f}"
    return f"{value:g}"


# ── Inward aggregation (de-identified) ──────────────────────────────────

async def _inward_by_country(db: AsyncSession, days: int) -> dict[str, dict]:
    """Per-country patient symptom activity, keyed by ISO2. Counts only — no PII."""
    since = date.today() - timedelta(days=days)
    since_dt = datetime(since.year, since.month, since.day, tzinfo=timezone.utc)
    agg: dict[str, dict] = {}

    def bucket(iso2: str) -> dict:
        return agg.setdefault(iso2, {"reports": 0, "affected": 0, "symptom_logs": 0,
                                     "symptoms": {}})

    # Per-user symptom logs joined to the user's country.
    rows = (await db.execute(
        select(User.country, SymptomLog.symptom_name)
        .join(User, User.id == SymptomLog.user_id)
        .where(SymptomLog.log_date >= since)
    )).all()
    for country, symptom in rows:
        iso2 = resolve_country(country)
        if not iso2:
            continue
        b = bucket(iso2)
        b["symptom_logs"] += 1
        if symptom:
            key = symptom.strip().lower()
            b["symptoms"][key] = b["symptoms"].get(key, 0) + 1

    # Crowd-sourced community reports (own country + symptom list).
    reports = (await db.execute(
        select(CommunityHealthReport.country, CommunityHealthReport.symptoms_reported,
               CommunityHealthReport.number_affected)
        .where(CommunityHealthReport.is_active == True,  # noqa: E712
               CommunityHealthReport.created_at >= since_dt)
    )).all()
    for country, symptoms_json, affected in reports:
        iso2 = resolve_country(country)
        if not iso2:
            continue
        b = bucket(iso2)
        b["reports"] += 1
        b["affected"] += int(affected or 0)
        try:
            for s in (json.loads(symptoms_json) if symptoms_json else []):
                key = str(s).strip().lower()
                if key:
                    b["symptoms"][key] = b["symptoms"].get(key, 0) + 1
        except (json.JSONDecodeError, TypeError):
            pass

    for b in agg.values():
        b["total"] = b["symptom_logs"] + b["reports"]
    return agg


# ── Reference endpoints ─────────────────────────────────────────────────

@router.get("/diseases", response_model=list[DiseaseInfo])
async def list_diseases(current_user: User = Depends(get_current_user)):
    """Trackable diseases (each backed by a verified WHO indicator)."""
    return [_disease_info(d) for d in DISEASES]


@router.get("/sources", response_model=list[SourceInfo])
async def list_sources(current_user: User = Depends(get_current_user)):
    """Outward + inward data sources with attribution."""
    return [SourceInfo(**s) for s in SOURCES]


# ── Global map ──────────────────────────────────────────────────────────

@router.get("/global", response_model=GlobalResponse)
async def global_surveillance(
    disease: str = Query("cholera"),
    view: str = Query("both", pattern="^(outward|inward|both)$"),
    region: str | None = Query(None, description="WHO region filter, e.g. Africa"),
    days: int = Query(90, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Per-country signal for the choropleth (outward burden + inward activity)."""
    d = DISEASE_BY_ID.get(disease)
    if not d:
        raise HTTPException(404, f"Unknown disease '{disease}'")

    outward = await fetch_who(d["who"]) if view in ("outward", "both") else []
    inward = await _inward_by_country(db, days) if view in ("inward", "both") else {}

    out_by_iso = {o["iso2"]: o for o in outward}
    if region:
        out_by_iso = {k: v for k, v in out_by_iso.items()
                      if (v.get("region") or "").lower() == region.lower()}

    out_cuts = _quartile_cuts([o["value"] for o in out_by_iso.values()])
    in_cuts = _quartile_cuts([b["total"] for b in inward.values()])

    iso_codes = set(out_by_iso) | set(inward)
    countries: list[CountrySignal] = []
    for iso2 in iso_codes:
        o = out_by_iso.get(iso2)
        inw = inward.get(iso2)
        out_val = o["value"] if o else None
        in_total = inw["total"] if inw else 0

        out_lvl = _level(out_val, out_cuts)
        in_lvl = _level(in_total, in_cuts)
        if view == "outward":
            level = out_lvl
        elif view == "inward":
            level = in_lvl
        else:
            level = max(out_lvl, in_lvl)

        parts = []
        if out_val is not None:
            parts.append(f"{_fmt(out_val)} {d['who_unit']} ({o['year']})")
        if in_total:
            parts.append(f"{in_total} local report{'s' if in_total != 1 else ''}")

        countries.append(CountrySignal(
            iso2=iso2,
            name=(o["name"] if o else ISO2_TO_NAME.get(iso2, iso2)),
            region=(o["region"] if o else None),
            outward=out_val,
            outward_year=(o["year"] if o else None),
            inward=in_total,
            level=level,
            value_label=" · ".join(parts) or "No data",
        ))

    countries.sort(key=lambda c: (c.level, c.outward or 0, c.inward), reverse=True)
    return GlobalResponse(
        disease=_disease_info(d),
        view=view,
        region=region,
        days=days,
        generated_at=datetime.now(timezone.utc).isoformat(),
        countries=countries,
        outward_country_count=len(out_by_iso),
        inward_total=sum(b["total"] for b in inward.values()),
        sources=[SourceInfo(**s) for s in SOURCES],
    )


# ── Country drill-down ──────────────────────────────────────────────────

@router.get("/country/{iso2}", response_model=CountryDetail)
async def country_detail(
    iso2: str,
    disease: str = Query("cholera"),
    days: int = Query(90, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Drill-down for one country: outward series, CDC (US), alerts, inward clusters."""
    iso2 = iso2.upper()
    if iso2 not in ISO2_TO_NAME:
        raise HTTPException(404, f"Unknown country '{iso2}'")
    d = DISEASE_BY_ID.get(disease)
    if not d:
        raise HTTPException(404, f"Unknown disease '{disease}'")

    # Outward: latest value + time series for this country.
    who_rows = await fetch_who(d["who"])
    row = next((r for r in who_rows if r["iso2"] == iso2), None)
    series = []
    if row:
        series = [SeriesPoint(**p) for p in await fetch_who_series(d["who"], row["iso3"])]
    outward = OutwardDetail(
        value=(row["value"] if row else None),
        year=(row["year"] if row else None),
        unit=d["who_unit"],
        source="WHO GHO",
        series=series,
    )

    # CDC (US only).
    cdc_us = None
    if iso2 == "US" and d["cdc"]:
        c = await fetch_cdc(d["cdc"])
        if c:
            cdc_us = CdcUsDetail(total=c["total"], year=c["year"], week=c["week"],
                                 states=c["states"])

    # Stored outbreak/advisory alerts touching this country.
    name = ISO2_TO_NAME.get(iso2, iso2)
    alert_rows = (await db.execute(
        select(CommunityHealthAlert)
        .where(CommunityHealthAlert.is_active == True,  # noqa: E712
               CommunityHealthAlert.category.in_(_OUTBREAK_CATEGORIES))
        .order_by(CommunityHealthAlert.issued_date.desc())
        .limit(50)
    )).scalars().all()
    alerts = []
    for a in alert_rows:
        countries_json = (a.affected_countries or "")
        if a.is_global or iso2 in countries_json or name.lower() in countries_json.lower():
            alerts.append(CountryAlert(
                title=a.title, severity=a.severity, source=a.source,
                disease_name=a.disease_name,
                issued_date=a.issued_date.isoformat() if a.issued_date else None,
                source_url=a.source_url,
            ))
        if len(alerts) >= 10:
            break

    # Inward: this country's symptom activity.
    inward_all = await _inward_by_country(db, days)
    b = inward_all.get(iso2)
    if b:
        top = sorted(b["symptoms"].items(), key=lambda kv: kv[1], reverse=True)[:8]
        inward = InwardDetail(
            report_count=b["reports"], affected=b["affected"],
            symptom_log_count=b["symptom_logs"],
            clusters=[SymptomCluster(name=k.title(), count=v) for k, v in top],
        )
    else:
        inward = InwardDetail()

    return CountryDetail(
        iso2=iso2, name=name,
        region=(row["region"] if row else None),
        disease=_disease_info(d),
        days=days,
        outward=outward,
        cdc_us=cdc_us,
        alerts=alerts,
        inward=inward,
    )
