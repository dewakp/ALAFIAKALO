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

    # Build lookup by test_name
    by_name: dict[str, list[LabResult]] = {}
    for lab in labs:
        name = lab.test_name.strip()
        by_name.setdefault(name, []).append(lab)

    groups = []
    for group_name, test_names in LAB_CHART_GROUPS.items():
        series_list = []
        for tn in test_names:
            matched = by_name.get(tn, [])
            if not matched:
                # Try case-insensitive match
                for key, vals in by_name.items():
                    if key.lower() == tn.lower():
                        matched = vals
                        break
            if matched:
                series_list.append(LabChartSeries(
                    test_name=tn,
                    unit=matched[0].unit,
                    reference_low=matched[0].reference_range_low,
                    reference_high=matched[0].reference_range_high,
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
