"""Notification engine – creates notifications based on domain events.

Call these helpers from other API endpoints when relevant events occur
(therapy completed, lab anomaly detected, medication conflict, etc.).
"""

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notifications import (
    Notification,
    NotificationCategory,
    NotificationPreference,
    NotificationPriority,
)


async def _is_enabled(db: AsyncSession, user_id: int, category: NotificationCategory) -> bool:
    """Check if the user has notifications enabled for this category."""
    result = await db.execute(
        select(NotificationPreference).where(
            NotificationPreference.user_id == user_id,
            NotificationPreference.category == category,
        )
    )
    pref = result.scalar_one_or_none()
    # Default: enabled if no preference record exists
    return pref.enabled if pref else True


async def create_notification(
    db: AsyncSession,
    *,
    user_id: int,
    category: NotificationCategory,
    priority: NotificationPriority,
    title: str,
    message: str,
    action_url: str | None = None,
    metadata_dict: dict | None = None,
) -> Notification | None:
    """Core helper – creates and persists a notification if enabled."""
    if not await _is_enabled(db, user_id, category):
        return None

    notif = Notification(
        user_id=user_id,
        category=category,
        priority=priority,
        title=title,
        message=message,
        action_url=action_url,
        # `extra_data`, NOT `metadata`. `metadata` is the MetaData object of the
        # whole schema on any declarative class, so the model maps the column as
        # `extra_data = Column("metadata", ...)` (canon 3ai). Passing
        # `metadata=` to the constructor does not raise — hasattr() is true — it
        # just sets a junk attribute on the instance and leaves the column NULL.
        # Every notification ever written dropped its payload this way: 27 rows
        # on this database, 0 with metadata, from 12 call sites that pass it.
        extra_data=json.dumps(metadata_dict) if metadata_dict else None,
    )
    db.add(notif)
    await db.flush()
    return notif



# How long one viewer's look at one patient's chart counts as a single visit.
#
# A clinician opening the board fires several requests — the board, a category,
# a therapy session — and each one passes the same authorization check. Without
# a window the patient would get five notifications for one visit and learn to
# ignore all of them. An hour is a consultation, not a request.
RECORD_ACCESS_WINDOW_MINUTES = 60


async def notify_record_accessed(
    db: AsyncSession,
    *,
    patient_id: int,
    viewer_id: int,
    viewer_name: str | None = None,
    window_minutes: int = RECORD_ACCESS_WINDOW_MINUTES,
) -> Notification | None:
    """Tell a patient that someone else opened their record.

    Returns None when there is nothing to say — the patient looking at their own
    chart, or the same viewer already announced inside the window.
    """
    # Your own record is not an access event. This is the whole point of the
    # feature and the easiest thing to get wrong, so it is the first line.
    if viewer_id == patient_id:
        return None

    since = datetime.now(timezone.utc) - timedelta(minutes=max(1, window_minutes))
    recent = (await db.execute(
        select(Notification).where(
            Notification.user_id == patient_id,
            Notification.category == NotificationCategory.RECORD_ACCESS,
            Notification.created_at >= since,
        )
    )).scalars().all()
    for note in recent:
        try:
            seen = json.loads(note.extra_data or "{}")
        except (ValueError, TypeError):
            seen = {}
        if seen.get("viewer_id") == viewer_id:
            return None

    # The patient granted this person access, so naming them is the point. Fall
    # back to something honest rather than to an empty string.
    who = (viewer_name or "").strip() or "A member of your care team"
    return await create_notification(
        db,
        user_id=patient_id,
        category=NotificationCategory.RECORD_ACCESS,
        priority=NotificationPriority.LOW,
        title="Your record was viewed",
        message=f"{who} opened your health record.",
        action_url="/data-sharing",
        metadata_dict={"viewer_id": viewer_id, "viewer_name": who},
    )


# ── Domain-specific helpers ──────────────────────────────────────────

async def notify_therapy_session_completed(
    db: AsyncSession,
    *,
    user_id: int,
    therapy_type: str,
    session_date: str,
    session_id: int,
    nurse_user_id: int | None = None,
):
    """Notify patient (and nurse if provided) that a therapy session completed."""
    label = therapy_type.replace("_", " ").title()
    # Patient notification
    await create_notification(
        db,
        user_id=user_id,
        category=NotificationCategory.THERAPY_SESSION,
        priority=NotificationPriority.MEDIUM,
        title=f"{label} Session Completed",
        message=f"Your {label} session on {session_date} has been marked as completed.",
        action_url=f"/chronic/therapy-sessions/{session_id}",
        metadata_dict={"therapy_type": therapy_type, "session_id": session_id},
    )
    # Nurse notification (for home HD / PD)
    if nurse_user_id and nurse_user_id != user_id:
        await create_notification(
            db,
            user_id=nurse_user_id,
            category=NotificationCategory.THERAPY_SESSION,
            priority=NotificationPriority.HIGH,
            title=f"Patient {label} Session Completed",
            message=f"A patient's {label} home session on {session_date} has been completed. Please review.",
            action_url=f"/chronic/therapy-sessions/{session_id}",
            metadata_dict={"therapy_type": therapy_type, "session_id": session_id, "patient_user_id": user_id},
        )


async def notify_calendar_event(
    db: AsyncSession,
    *,
    user_id: int,
    event_title: str,
    event_date: str,
    event_id: int,
):
    """Notify user about an upcoming or new calendar event."""
    await create_notification(
        db,
        user_id=user_id,
        category=NotificationCategory.CALENDAR,
        priority=NotificationPriority.LOW,
        title="Calendar Reminder",
        message=f"Upcoming event: {event_title} on {event_date}.",
        action_url=f"/calendar/{event_id}",
        metadata_dict={"event_id": event_id},
    )


async def notify_lab_anomaly(
    db: AsyncSession,
    *,
    user_id: int,
    test_name: str,
    value: str,
    normal_range: str,
    lab_id: int,
):
    """Notify when a lab result falls outside the normal range."""
    await create_notification(
        db,
        user_id=user_id,
        category=NotificationCategory.LAB_ANOMALY,
        priority=NotificationPriority.HIGH,
        title="Lab Result Anomaly Detected",
        message=f"{test_name}: {value} is outside the normal range ({normal_range}). Please consult your provider.",
        action_url=f"/labs/{lab_id}",
        metadata_dict={"test_name": test_name, "value": value, "normal_range": normal_range, "lab_id": lab_id},
    )


async def notify_treatment_anomaly(
    db: AsyncSession,
    *,
    user_id: int,
    description: str,
    session_id: int,
    therapy_type: str,
):
    """Notify when anomalous treatment data is detected (e.g. excessive fluid removal, abnormal vitals)."""
    label = therapy_type.replace("_", " ").title()
    await create_notification(
        db,
        user_id=user_id,
        category=NotificationCategory.TREATMENT_ANOMALY,
        priority=NotificationPriority.URGENT,
        title=f"{label} Treatment Alert",
        message=description,
        action_url=f"/chronic/therapy-sessions/{session_id}",
        metadata_dict={"session_id": session_id, "therapy_type": therapy_type},
    )


async def notify_medication_conflict(
    db: AsyncSession,
    *,
    user_id: int,
    drug_a: str,
    drug_b: str,
    conflict_detail: str,
):
    """Notify the user about a potential drug-drug interaction or conflict."""
    await create_notification(
        db,
        user_id=user_id,
        category=NotificationCategory.MEDICATION_CONFLICT,
        priority=NotificationPriority.URGENT,
        title="Medication Conflict Detected",
        message=f"Potential interaction between {drug_a} and {drug_b}: {conflict_detail}",
        action_url="/medications",
        metadata_dict={"drug_a": drug_a, "drug_b": drug_b, "detail": conflict_detail},
    )


async def notify_nutrition_restriction(
    db: AsyncSession,
    *,
    user_id: int,
    nutrient: str,
    logged_value: str,
    limit_value: str,
    log_id: int,
):
    """Notify when a logged nutrient exceeds the user's dietary restriction."""
    await create_notification(
        db,
        user_id=user_id,
        category=NotificationCategory.NUTRITION_ALERT,
        priority=NotificationPriority.MEDIUM,
        title="Nutrition Limit Exceeded",
        message=f"Your {nutrient} intake ({logged_value}) exceeds your recommended limit ({limit_value}).",
        action_url=f"/nutrition/{log_id}",
        metadata_dict={"nutrient": nutrient, "logged": logged_value, "limit": limit_value, "log_id": log_id},
    )


# ── Pharmacy helpers ─────────────────────────────────────────────────

async def notify_prescription_created(
    db: AsyncSession,
    *,
    user_id: int,
    medication_name: str,
    prescriber_name: str,
    prescription_id: int,
):
    """Notify patient that a new prescription has been created."""
    await create_notification(
        db,
        user_id=user_id,
        category=NotificationCategory.PRESCRIPTION_CREATED,
        priority=NotificationPriority.HIGH,
        title="New Prescription",
        message=f"Dr. {prescriber_name} prescribed {medication_name}. Review the details and schedule.",
        action_url=f"/pharmacy/prescriptions/{prescription_id}",
        metadata_dict={"prescription_id": prescription_id, "medication": medication_name},
    )


async def notify_prescription_ready(
    db: AsyncSession,
    *,
    user_id: int,
    medication_name: str,
    prescription_id: int,
):
    """Notify patient that their prescription is ready for pickup."""
    await create_notification(
        db,
        user_id=user_id,
        category=NotificationCategory.PRESCRIPTION_READY,
        priority=NotificationPriority.MEDIUM,
        title="Prescription Ready",
        message=f"Your prescription for {medication_name} is ready for pickup at the pharmacy.",
        action_url=f"/pharmacy/prescriptions/{prescription_id}",
        metadata_dict={"prescription_id": prescription_id, "medication": medication_name},
    )


async def notify_dispense_complete(
    db: AsyncSession,
    *,
    user_id: int,
    medication_name: str,
    pharmacist_name: str,
    dispense_id: int,
):
    """Notify patient that their medication has been dispensed."""
    await create_notification(
        db,
        user_id=user_id,
        category=NotificationCategory.DISPENSE_COMPLETE,
        priority=NotificationPriority.MEDIUM,
        title="Medication Dispensed",
        message=f"{medication_name} has been dispensed by {pharmacist_name}. Remember to start your schedule.",
        action_url=f"/pharmacy/dispenses/{dispense_id}",
        metadata_dict={"dispense_id": dispense_id, "medication": medication_name},
    )


async def notify_adherence_missed(
    db: AsyncSession,
    *,
    user_id: int,
    medication_name: str,
    scheduled_time: str,
    prescription_id: int,
):
    """Alert patient about a missed medication dose."""
    await create_notification(
        db,
        user_id=user_id,
        category=NotificationCategory.ADHERENCE_ALERT,
        priority=NotificationPriority.HIGH,
        title="Missed Dose Alert",
        message=f"You missed your {medication_name} dose scheduled for {scheduled_time}. Take it as soon as possible or skip if close to next dose.",
        action_url=f"/pharmacy/adherence?prescription_id={prescription_id}",
        metadata_dict={"prescription_id": prescription_id, "medication": medication_name, "scheduled": scheduled_time},
    )


async def notify_refill_reminder(
    db: AsyncSession,
    *,
    user_id: int,
    medication_name: str,
    patient_name: str,
    prescription_id: int,
):
    """Notify prescriber about a refill request or low supply."""
    await create_notification(
        db,
        user_id=user_id,
        category=NotificationCategory.REFILL_REMINDER,
        priority=NotificationPriority.MEDIUM,
        title="Refill Request",
        message=f"{patient_name} has requested a refill for {medication_name}. Please review.",
        action_url=f"/pharmacy/prescriptions/{prescription_id}",
        metadata_dict={"prescription_id": prescription_id, "medication": medication_name, "patient": patient_name},
    )
