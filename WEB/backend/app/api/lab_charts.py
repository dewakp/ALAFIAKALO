"""Lab Comparison Charts — aggregation endpoints for trend visualization."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import date

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.labs import LabResult
from app.schemas.wellness import LabChartGroup, LabChartSeries, LabChartPoint, LAB_CHART_GROUPS
from app.services.docparse.dictionaries import analyte_key, preferred_name

router = APIRouter()


@router.get("/groups", response_model=list[LabChartGroup])
async def get_lab_chart_groups(
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return lab results organized into 7 chart groups for trend visualization."""
    query = select(LabResult).where(LabResult.user_id == current_user.id)
    if start_date:
        query = query.where(LabResult.test_date >= start_date)
    if end_date:
        query = query.where(LabResult.test_date <= end_date)
    query = query.order_by(LabResult.test_date.asc())
    result = await db.execute(query)
    labs = result.scalars().all()

    # Grouped by analyte, not by the stored wording. One patient's alkaline
    # phosphatase is "ALP" until July 2025 and "Alk Phos" after; matched raw, the
    # chart drew only the spelling this group list happened to name.
    by_analyte: dict[str, list[LabResult]] = {}
    for lab in labs:
        by_analyte.setdefault(analyte_key(lab.test_name), []).append(lab)

    groups = []
    for group_name, test_names in LAB_CHART_GROUPS.items():
        series_list = []
        charted: set[str] = set()
        for tn in test_names:
            key = analyte_key(tn)
            matched = by_analyte.get(key)
            if not matched or key in charted:
                continue
            charted.add(key)
            # Spellings come from different report formats, so describe the
            # series by the most recent report that states a unit and a range.
            ranged = next((m for m in reversed(matched)
                           if m.reference_range_low is not None or m.reference_range_high is not None),
                          matched[-1])
            series_list.append(LabChartSeries(
                test_name=preferred_name([m.test_name for m in matched], fallback=tn),
                unit=next((m.unit for m in reversed(matched) if m.unit), None),
                reference_low=ranged.reference_range_low,
                reference_high=ranged.reference_range_high,
                data=[LabChartPoint(date=str(m.test_date), value=m.value) for m in matched if m.value is not None],
            ))
        if series_list:
            groups.append(LabChartGroup(group_name=group_name, series=series_list))
    return groups


@router.get("/tests")
async def list_available_tests(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List distinct test names available for this user."""
    result = await db.execute(
        select(LabResult.test_name, func.count(LabResult.id))
        .where(LabResult.user_id == current_user.id)
        .group_by(LabResult.test_name)
        .order_by(LabResult.test_name)
    )
    return [{"test_name": row[0], "count": row[1]} for row in result.all()]


@router.get("/test/{test_name}", response_model=LabChartSeries)
async def get_single_test_trend(
    test_name: str,
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get trend data for a single lab test."""
    query = (
        select(LabResult)
        .where(LabResult.user_id == current_user.id, LabResult.test_name == test_name)
        .order_by(LabResult.test_date.asc())
    )
    if start_date:
        query = query.where(LabResult.test_date >= start_date)
    if end_date:
        query = query.where(LabResult.test_date <= end_date)
    result = await db.execute(query)
    labs = result.scalars().all()
    return LabChartSeries(
        test_name=test_name,
        unit=labs[0].unit if labs else None,
        reference_low=labs[0].reference_range_low if labs else None,
        reference_high=labs[0].reference_range_high if labs else None,
        data=[LabChartPoint(date=str(l.test_date), value=l.value) for l in labs if l.value is not None],
    )
