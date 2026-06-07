"""Calendar CRUD endpoints."""

from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.notification_engine import notify_calendar_event
from app.models.user import User
from app.models.calendar import CalendarEvent
from app.schemas.calendar import (
    CalendarEventCreate,
    CalendarEventUpdate,
    CalendarEventResponse,
    VALID_CATEGORIES,
    VALID_STATUSES,
    VALID_RECURRENCES,
    VALID_PRIORITIES,
)

router = APIRouter()


@router.get("/", response_model=list[CalendarEventResponse])
async def list_events(
    start_date: date | None = Query(None, description="Filter from this date (inclusive)"),
    end_date: date | None = Query(None, description="Filter until this date (inclusive)"),
    category: str | None = Query(None, description="Filter by category"),
    status: str | None = Query(None, description="Filter by status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List calendar events with optional date-range and category filters."""
    query = select(CalendarEvent).where(CalendarEvent.user_id == current_user.id)

    if start_date:
        query = query.where(CalendarEvent.event_date >= start_date)
    if end_date:
        query = query.where(CalendarEvent.event_date <= end_date)
    if category:
        query = query.where(CalendarEvent.category == category)
    if status:
        query = query.where(CalendarEvent.status == status)

    query = query.order_by(CalendarEvent.event_date, CalendarEvent.start_time).offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/", response_model=CalendarEventResponse, status_code=201)
async def create_event(
    event_in: CalendarEventCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a calendar event."""
    if event_in.category not in VALID_CATEGORIES:
        raise HTTPException(
            422, f"Invalid category '{event_in.category}'. Must be one of: {', '.join(sorted(VALID_CATEGORIES))}"
        )
    if event_in.status not in VALID_STATUSES:
        raise HTTPException(
            422, f"Invalid status '{event_in.status}'. Must be one of: {', '.join(sorted(VALID_STATUSES))}"
        )
    if event_in.recurrence and event_in.recurrence not in VALID_RECURRENCES:
        raise HTTPException(
            422, f"Invalid recurrence '{event_in.recurrence}'. Must be one of: {', '.join(sorted(VALID_RECURRENCES))}"
        )
    if event_in.priority and event_in.priority not in VALID_PRIORITIES:
        raise HTTPException(
            422, f"Invalid priority '{event_in.priority}'. Must be one of: {', '.join(sorted(VALID_PRIORITIES))}"
        )

    event = CalendarEvent(**event_in.model_dump(), user_id=current_user.id)
    db.add(event)
    await db.flush()
    await db.refresh(event)

    # Notification: new calendar event
    await notify_calendar_event(
        db, user_id=current_user.id,
        event_title=event.title,
        event_date=str(event.start_datetime or event.event_date),
        event_id=event.id,
    )

    return event


@router.get("/{event_id}", response_model=CalendarEventResponse)
async def get_event(
    event_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single calendar event."""
    result = await db.execute(
        select(CalendarEvent).where(
            CalendarEvent.id == event_id,
            CalendarEvent.user_id == current_user.id,
        )
    )
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(404, "Calendar event not found")
    return event


@router.patch("/{event_id}", response_model=CalendarEventResponse)
async def update_event(
    event_id: int,
    updates: CalendarEventUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a calendar event."""
    result = await db.execute(
        select(CalendarEvent).where(
            CalendarEvent.id == event_id,
            CalendarEvent.user_id == current_user.id,
        )
    )
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(404, "Calendar event not found")

    changed = updates.model_dump(exclude_unset=True)

    if "category" in changed and changed["category"] not in VALID_CATEGORIES:
        raise HTTPException(422, f"Invalid category. Must be one of: {', '.join(sorted(VALID_CATEGORIES))}")
    if "status" in changed and changed["status"] not in VALID_STATUSES:
        raise HTTPException(422, f"Invalid status. Must be one of: {', '.join(sorted(VALID_STATUSES))}")
    if "recurrence" in changed and changed["recurrence"] and changed["recurrence"] not in VALID_RECURRENCES:
        raise HTTPException(422, f"Invalid recurrence. Must be one of: {', '.join(sorted(VALID_RECURRENCES))}")
    if "priority" in changed and changed["priority"] and changed["priority"] not in VALID_PRIORITIES:
        raise HTTPException(422, f"Invalid priority. Must be one of: {', '.join(sorted(VALID_PRIORITIES))}")

    # If marking as completed, set completed_at automatically
    if changed.get("status") == "completed" and not changed.get("completed_at"):
        changed["completed_at"] = datetime.now(timezone.utc)

    for field, value in changed.items():
        setattr(event, field, value)

    await db.flush()
    await db.refresh(event)
    return event


@router.delete("/{event_id}", status_code=204)
async def delete_event(
    event_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a calendar event."""
    result = await db.execute(
        select(CalendarEvent).where(
            CalendarEvent.id == event_id,
            CalendarEvent.user_id == current_user.id,
        )
    )
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(404, "Calendar event not found")
    await db.delete(event)
    await db.flush()


@router.patch("/{event_id}/complete", response_model=CalendarEventResponse)
async def complete_event(
    event_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Quick-complete a calendar event (mark as completed with timestamp)."""
    result = await db.execute(
        select(CalendarEvent).where(
            CalendarEvent.id == event_id,
            CalendarEvent.user_id == current_user.id,
        )
    )
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(404, "Calendar event not found")

    event.status = "completed"
    event.completed_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(event)
    return event


@router.get("/categories/list")
async def list_categories():
    """Return all valid event categories with display info."""
    category_info = {
        "appointment": {"label": "Appointment", "icon": "stethoscope", "color": "#2196F3"},
        "meal": {"label": "Meal", "icon": "utensils", "color": "#4CAF50"},
        "medication": {"label": "Medication", "icon": "pill", "color": "#FF9800"},
        "exercise": {"label": "Exercise", "icon": "dumbbell", "color": "#E91E63"},
        "meditation": {"label": "Meditation", "icon": "brain", "color": "#9C27B0"},
        "therapy": {"label": "Therapy", "icon": "heart-handshake", "color": "#00BCD4"},
        "lab": {"label": "Lab / Test", "icon": "flask-conical", "color": "#795548"},
        "wellness": {"label": "Wellness", "icon": "sparkles", "color": "#607D8B"},
        "custom": {"label": "Custom", "icon": "calendar", "color": "#9E9E9E"},
    }
    return [{"key": k, **v} for k, v in category_info.items()]
