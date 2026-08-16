"""Clinician & Social Worker Dashboard endpoints — role-gated patient views."""

import hashlib
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select, desc

from app.api.chronic_conditions import _compute_payload_hash
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.blockchain import BlockRecord
from app.models.chronic_conditions import (
    ClinicalNote,
    FlowsheetStatus,
    IntradialyticReading,
    TherapySession,
)
from app.models.user import User
from app.models.data_sharing import DataGrant, grant_covers
from app.models.vitals import VitalsLog
from app.models.mood import MoodEntry
from app.models.labs import LabResult
from app.models.medications import Medication
from app.models.user_roles import UserRoleAssignment
from app.schemas.wellness import ClinicianDashboardResponse, PatientSummary
from app.services import clinical_sources as sources
from app.services import patient_board as board

logger = logging.getLogger(__name__)

router = APIRouter()


def _lab_dict(lab: LabResult) -> dict:
    """One lab result as the clients render it.

    `is_abnormal` is included because it is the whole point of scanning a list
    of results — without it the dashboard shows numbers a clinician has to
    range-check by eye, and the patient cards cannot flag anything.
    """
    return {
        "name": lab.test_name,
        "value": lab.value_string or (str(lab.value) if lab.value is not None else None),
        "unit": lab.unit,
        "date": str(lab.test_date),
        # Derived when the lab did not flag it — see board.lab_is_abnormal.
        # This column is NULL on every result in this database.
        "is_abnormal": bool(board.lab_is_abnormal(lab)),
    }

CLINICIAN_ROLES = {
    "physician", "surgeon", "nurse_practitioner", "physician_assistant",
    "registered_nurse", "clinical_nurse_specialist", "other_clinician",
}
SW_ROLES = {"social_worker", "clinical_social_worker", "licensed_counselor"}


async def _get_user_role(user_id: int, db: AsyncSession) -> str | None:
    """Get user's primary active role."""
    result = await db.execute(
        select(UserRoleAssignment.role)
        .where(UserRoleAssignment.user_id == user_id, UserRoleAssignment.is_active == True, UserRoleAssignment.is_primary == True)
    )
    row = result.first()
    return row[0] if row else None


async def _get_patients_for_clinician(clinician_id: int, db: AsyncSession) -> list[PatientSummary]:
    """Get all patients who have granted data access to this clinician."""
    # Find users who have granted data access to this clinician
    result = await db.execute(
        select(DataGrant)
        .where(DataGrant.grantee_user_id == clinician_id, DataGrant.is_active == True)
    )
    grants = result.scalars().all()

    # Group grants by owner
    patient_grants: dict[int, list[str]] = {}
    for g in grants:
        patient_grants.setdefault(g.owner_id, []).append(g.data_type)

    patients = []
    for patient_id, permissions in patient_grants.items():
        # Get patient info
        result = await db.execute(select(User).where(User.id == patient_id))
        patient = result.scalar_one_or_none()
        if not patient:
            continue

        summary = PatientSummary(
            user_id=patient.id,
            full_name=patient.full_name,
            email=patient.email,
            permissions=permissions,
        )

        # Get latest vitals if permitted
        if "vitals" in permissions or "all" in permissions:
            result = await db.execute(
                select(VitalsLog).where(VitalsLog.user_id == patient_id).order_by(desc(VitalsLog.created_at)).limit(1)
            )
            vitals = result.scalar_one_or_none()
            if vitals:
                summary.latest_vitals = {
                    "date": str(vitals.log_date),
                    "bp": f"{vitals.blood_pressure_systolic}/{vitals.blood_pressure_diastolic}" if vitals.blood_pressure_systolic else None,
                    "hr": vitals.heart_rate_bpm,
                    "weight_kg": vitals.weight_kg,
                }

        # Get latest mood if permitted
        if "mood" in permissions or "all" in permissions:
            result = await db.execute(
                select(MoodEntry).where(MoodEntry.user_id == patient_id).order_by(desc(MoodEntry.created_at)).limit(1)
            )
            mood = result.scalar_one_or_none()
            if mood:
                summary.latest_mood = {
                    "date": str(mood.entry_date),
                    "score": mood.mood_score,
                }

        # Get latest labs if permitted
        if "labs" in permissions or "all" in permissions:
            result = await db.execute(
                select(LabResult).where(LabResult.user_id == patient_id).order_by(desc(LabResult.test_date)).limit(5)
            )
            labs = result.scalars().all()
            summary.latest_labs = [_lab_dict(l) for l in labs]

        # Get active medications if permitted
        if "medications" in permissions or "all" in permissions:
            result = await db.execute(
                select(Medication).where(Medication.user_id == patient_id, Medication.is_active == True)
            )
            meds = result.scalars().all()
            summary.medications = [m.name for m in meds]

        # Get the active problem list if permitted. `conditions` is a sharable
        # data type and was in the response schema, but nothing ever filled it —
        # so a patient who shared their conditions showed the clinician nothing.
        if "conditions" in permissions or "all" in permissions:
            # Both tables — see app/services/clinical_sources.py.
            summary.conditions = [
                c.name for c in await sources.conditions(db, patient_id, active_only=True)
            ]

        patients.append(summary)

    return patients


@router.get("/", response_model=ClinicianDashboardResponse)
async def get_clinician_dashboard(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get clinician or social worker dashboard with shared patient data."""
    role = await _get_user_role(current_user.id, db)

    # Allow access even without formal role assignment (for demo)
    display_role = role or "clinician"
    if role and role not in CLINICIAN_ROLES and role not in SW_ROLES:
        # Still allow if they have grants
        pass

    patients = await _get_patients_for_clinician(current_user.id, db)

    return ClinicianDashboardResponse(
        role=display_role,
        patient_count=len(patients),
        patients=patients,
    )


@router.get("/patient/{patient_id}", response_model=PatientSummary)
async def get_patient_detail(
    patient_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get detailed patient summary (requires active data grant)."""
    result = await db.execute(
        select(DataGrant)
        .where(
            DataGrant.grantee_user_id == current_user.id,
            DataGrant.owner_id == patient_id,
            DataGrant.is_active == True,
        )
    )
    grants = result.scalars().all()
    if not grants:
        raise HTTPException(status_code=403, detail="No active data grant from this patient")

    permissions = [g.data_type for g in grants]
    result = await db.execute(select(User).where(User.id == patient_id))
    patient = result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    summary = PatientSummary(
        user_id=patient.id, full_name=patient.full_name, email=patient.email,
        permissions=permissions,
    )
    # Populate all permitted data (same logic as above)
    if "vitals" in permissions or "all" in permissions:
        result = await db.execute(
            select(VitalsLog).where(VitalsLog.user_id == patient_id).order_by(desc(VitalsLog.created_at)).limit(1)
        )
        vitals = result.scalar_one_or_none()
        if vitals:
            summary.latest_vitals = {
                "date": str(vitals.log_date),
                "bp": f"{vitals.blood_pressure_systolic}/{vitals.blood_pressure_diastolic}" if vitals.blood_pressure_systolic else None,
                "hr": vitals.heart_rate_bpm, "weight_kg": vitals.weight_kg,
            }
    if "labs" in permissions or "all" in permissions:
        result = await db.execute(
            select(LabResult).where(LabResult.user_id == patient_id).order_by(desc(LabResult.test_date)).limit(10)
        )
        summary.latest_labs = [_lab_dict(l) for l in result.scalars().all()]
    if "medications" in permissions or "all" in permissions:
        result = await db.execute(
            select(Medication).where(Medication.user_id == patient_id, Medication.is_active == True)
        )
        summary.medications = [m.name for m in result.scalars().all()]
    if "conditions" in permissions or "all" in permissions:
        summary.conditions = [
            c.name for c in await sources.conditions(db, patient_id, active_only=True)
        ]
    if "mood" in permissions or "all" in permissions:
        result = await db.execute(
            select(MoodEntry).where(MoodEntry.user_id == patient_id).order_by(desc(MoodEntry.created_at)).limit(1)
        )
        mood = result.scalar_one_or_none()
        if mood:
            summary.latest_mood = {"date": str(mood.entry_date), "score": mood.mood_score}

    return summary


# ── Patient board ────────────────────────────────────────────────────────
#
# Opening a patient gives a board of category cards — latest/summary per
# category plus the patient's current score — and opening a card gives trends
# and the rows behind them. Both routes re-check the grant on every request:
# a patient revoking access must take effect immediately, not at next login.

async def _permissions_for(clinician_id: int, patient_id: int, db: AsyncSession) -> list[str]:
    """The data types this clinician may see for this patient, or 403."""
    grants = (await db.execute(
        select(DataGrant).where(
            DataGrant.grantee_user_id == clinician_id,
            DataGrant.owner_id == patient_id,
            DataGrant.is_active == True,  # noqa: E712
        )
    )).scalars().all()
    if not grants:
        raise HTTPException(status_code=403, detail="No active data grant from this patient")
    return [g.data_type for g in grants]


async def _patient_or_404(patient_id: int, db: AsyncSession) -> User:
    user = (await db.execute(select(User).where(User.id == patient_id))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    return user


@router.get("/patient/{patient_id}/board")
async def get_patient_board(
    patient_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Every shared category as a card, with its latest values."""
    permissions = await _permissions_for(current_user.id, patient_id, db)
    patient = await _patient_or_404(patient_id, db)

    cards = []
    for cat in board.CATEGORIES:
        shared = cat.key in board.ALWAYS_VISIBLE or grant_covers(permissions, cat.key)
        # An unshared category is still listed, so the clinician can see that it
        # exists and was not shared — silently omitting it reads as "no data".
        if not shared:
            cards.append({
                "key": cat.key, "label": cat.label, "icon": cat.icon,
                "shared": False, "items": [], "count": None, "last_updated": None,
                "empty_reason": "Not shared by this patient.",
            })
            continue
        summary = await cat.summarise(db, patient_id)
        cards.append({
            "key": cat.key, "label": cat.label, "icon": cat.icon, "shared": True,
            "items": summary.items, "count": summary.count,
            "last_updated": summary.last_updated, "empty_reason": summary.empty_reason,
        })

    return {
        "patient": {"user_id": patient.id, "full_name": patient.full_name,
                    "email": patient.email},
        "permissions": permissions,
        "cards": cards,
    }


@router.get("/patient/{patient_id}/category/{category_key}")
async def get_patient_category(
    patient_id: int,
    category_key: str,
    # 1825 was a five-year cap on a control labelled "All". On the reference
    # record it returned 1048 of 2005 sessions — the history starts 2013-05-21 —
    # so a physician pressing "All" was shown half the chart and told it was
    # everything. The ceiling is now a century: "All" has to mean all.
    days: int = Query(board.DEFAULT_WINDOW_DAYS, ge=1, le=36500),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Trends and full rows for one category."""
    cat = board.BY_KEY.get(category_key)
    if cat is None:
        raise HTTPException(status_code=404, detail=f"Unknown category: {category_key}")

    permissions = await _permissions_for(current_user.id, patient_id, db)
    if category_key not in board.ALWAYS_VISIBLE and not grant_covers(permissions, category_key):
        raise HTTPException(
            status_code=403, detail=f"This patient has not shared {cat.label.lower()}")

    patient = await _patient_or_404(patient_id, db)
    detail = await cat.detail(db, patient_id, days)
    # Categories that build their own cards keep them; everything else gets the
    # same latest/range pair, so no category is left as a bare table.
    cards = detail.cards or board.default_cards(detail, days)
    return {
        "patient": {"user_id": patient.id, "full_name": patient.full_name},
        "key": cat.key, "label": cat.label, "icon": cat.icon, "days": days,
        "cards": cards,
        "series": detail.series, "columns": detail.columns, "rows": detail.rows,
    }


# ── Therapy sessions: the physician's read of a patient's flowsheet ──────────
#
# `/chronic/therapy-sessions/*` scopes every lookup to `current_user.id`, so a
# physician opening a patient's session got a 404 — including from `/review`,
# the endpoint written FOR physicians. These routes are the clinician-side
# equivalent: same models, same ledger, but the owner is the patient and the
# gate is an active DataGrant covering `dialysis`.

def _reading_dict(r: IntradialyticReading) -> dict:
    """One intradialytic reading — the points behind the session charts.

    The full column set, not a subset: iOS already models this row
    (`NewFeatureModels.IntradialyticReading`) with `session_id` and `user_id`, so
    a trimmed payload fails to decode on the device while working fine in the
    browser. One shape, both clients.

    `reading_time` is emitted as null when it is null. It briefly went out as ""
    to satisfy a non-optional Swift field — which is the same instinct that made
    the importer write 00:00:00: pick a value so the type is happy, and lose the
    fact that nothing was recorded. The clients model it as optional instead.
    """
    return {
        "id": r.id,
        "session_id": r.session_id, "user_id": r.user_id,
        "reading_time": str(r.reading_time)[:5] if r.reading_time else None,
        "reading_number": r.reading_number,
        "systolic_bp": r.systolic_bp, "diastolic_bp": r.diastolic_bp,
        "pulse": r.pulse, "mean_arterial_pressure": r.mean_arterial_pressure,
        "dialysate_rate": r.dialysate_rate,
        "dialysate_volume_remaining": r.dialysate_volume_remaining,
        "uf_rate": r.uf_rate, "uf_volume_removed": r.uf_volume_removed,
        "blood_flow_rate": r.blood_flow_rate,
        "arterial_pressure": r.arterial_pressure, "venous_pressure": r.venous_pressure,
        "effluent_pressure": r.effluent_pressure,
        "access_state": r.access_state, "saline_amount": r.saline_amount,
        "remarks": r.remarks, "created_at": _iso_dt(r.created_at),
    }


async def _therapy_session_for_patient(
    session_id: int, patient_id: int, db: AsyncSession
) -> TherapySession:
    """A session that belongs to THIS patient — never to the caller."""
    session = (await db.execute(
        select(TherapySession).where(
            TherapySession.id == session_id,
            TherapySession.user_id == patient_id,
        )
    )).scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Therapy session not found for this patient")
    return session


async def _require_dialysis_access(clinician_id: int, patient_id: int, db: AsyncSession) -> None:
    permissions = await _permissions_for(clinician_id, patient_id, db)
    if not grant_covers(permissions, "dialysis"):
        raise HTTPException(status_code=403, detail="This patient has not shared therapies")


@router.get("/patient/{patient_id}/therapy-sessions/{session_id}")
async def get_patient_therapy_session(
    patient_id: int,
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """One session in full: the flowsheet, its readings, its notes, its integrity."""
    await _require_dialysis_access(current_user.id, patient_id, db)
    patient = await _patient_or_404(patient_id, db)
    session = await _therapy_session_for_patient(session_id, patient_id, db)

    readings = (await db.execute(
        select(IntradialyticReading)
        .where(IntradialyticReading.session_id == session_id)
        .order_by(IntradialyticReading.reading_time)
    )).scalars().all()
    notes = (await db.execute(
        select(ClinicalNote).where(ClinicalNote.session_id == session_id)
        .order_by(ClinicalNote.created_at)
    )).scalars().all()

    return {
        "patient": {"user_id": patient.id, "full_name": patient.full_name},
        "session": {
            "id": session.id,
            "date": str(session.scheduled_date)[:10],
            "therapy": getattr(session.therapy_type, "value", str(session.therapy_type)),
            "name": session.therapy_name,
            "status": getattr(session.status, "value", str(session.status)),
            "facility_name": session.facility_name,
            "attending_physician": session.attending_physician,
            "attending_nurse": session.attending_nurse,
            "dialysis_access_type": session.dialysis_access_type,
            "duration_minutes": session.duration_minutes,
            "pre_dialysis_weight_kg": session.pre_dialysis_weight_kg,
            "post_dialysis_weight_kg": session.post_dialysis_weight_kg,
            "dry_weight_kg": session.dry_weight_kg,
            "fluid_removed_ml": session.fluid_removed_ml,
            "blood_flow_rate": session.blood_flow_rate,
            "dialysate_flow_rate": session.dialysate_flow_rate,
            "pre_systolic_bp": session.pre_systolic_bp, "pre_diastolic_bp": session.pre_diastolic_bp,
            "post_systolic_bp": session.post_systolic_bp, "post_diastolic_bp": session.post_diastolic_bp,
            "pre_heart_rate": session.pre_heart_rate, "post_heart_rate": session.post_heart_rate,
            "pre_temperature": session.pre_temperature, "post_temperature": session.post_temperature,
            "complications": session.complications,
            "adverse_reactions": session.adverse_reactions,
            "patient_tolerance": session.patient_tolerance,
            "patient_notes": session.patient_notes,
        },
        "readings": [_reading_dict(r) for r in readings],
        "notes": [{"id": n.id, "author_role": n.author_role, "note_type": n.note_type,
                   "note_text": n.note_text, "created_at": _iso_dt(n.created_at)} for n in notes],
        "signoff": _signoff_dict(session),
    }


def _iso_dt(value) -> str | None:
    return value.isoformat() if value is not None else None


def _signoff_dict(session: TherapySession) -> dict:
    """Who has attested to this record, and whether it is still tamper-checkable."""
    return {
        "flowsheet_status": getattr(session.flowsheet_status, "value", session.flowsheet_status),
        "signed_at": _iso_dt(session.signed_at), "signed_by": session.signed_by,
        "countersigned_at": _iso_dt(session.countersigned_at),
        "countersigned_by": session.countersigned_by,
        "reviewed_at": _iso_dt(session.reviewed_at), "reviewed_by": session.reviewed_by,
        "payload_hash": session.payload_hash,
    }


@router.post("/patient/{patient_id}/therapy-sessions/{session_id}/review")
async def review_patient_therapy_session(
    patient_id: int,
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Physician sign-off: the session becomes `reviewed`, hashed and anchored.

    The patient-side `/review` demands the flowsheet already be signed or
    countersigned. Every therapy_session in this database has
    `flowsheet_status = NULL` — 2005 of them — because the lifecycle post-dates
    the imported history, so that precondition would reject all of them. A
    physician attesting "I have read this record" is meaningful whether or not
    the patient ever e-signed it, so the gate here is only that the record is
    not already reviewed or locked. What the patient did sign is reported back
    in `signoff`, so the physician can see what they are attesting on top of.
    """
    await _require_dialysis_access(current_user.id, patient_id, db)
    session = await _therapy_session_for_patient(session_id, patient_id, db)

    current = getattr(session.flowsheet_status, "value", session.flowsheet_status)
    if current == FlowsheetStatus.LOCKED.value:
        raise HTTPException(status_code=409, detail="This flowsheet is locked")
    if current == FlowsheetStatus.REVIEWED.value:
        raise HTTPException(status_code=409, detail="This session has already been reviewed")

    session.flowsheet_status = FlowsheetStatus.REVIEWED
    session.reviewed_at = datetime.utcnow()
    session.reviewed_by = current_user.id
    if not session.payload_hash:
        session.payload_hash = _compute_payload_hash(session)

    # Anchor to the ledger. Best-effort by design: an unreachable chain node must
    # not cost a physician their sign-off, and the row itself is the record.
    try:
        from app.services.blockchain_ledger import BlockchainLedger
        from app.services.blockchain_engine import EventAction
        await BlockchainLedger(db).record_therapy_event(
            action=EventAction.therapy_session_completed,
            data={"event": "FLOWSHEET_REVIEWED", "payload_hash": session.payload_hash,
                  "patient_id": patient_id},
            actor_id=current_user.id,
            entity_id=session.id,
        )
    except Exception:
        logger.warning("Ledger anchoring failed for session %s review", session_id, exc_info=True)

    await db.commit()
    await db.refresh(session)
    return {"id": session.id, "signoff": _signoff_dict(session),
            "message": "Session reviewed"}


@router.get("/patient/{patient_id}/therapy-summary")
async def get_patient_therapy_summary(
    patient_id: int,
    days: int = Query(90, ge=1, le=36500),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Server-computed session tiles — the same numbers the patient's own screen shows.

    The patient's Session Reports tab reads `/chronic/hd-summary`, which counts
    with SQL. Averaging client-side over "whatever rows arrived" makes the tile
    a function of the page size rather than of the record — the shape that once
    reported "200 sessions" for a patient with 730. Counting here keeps the
    physician's tiles and the board card telling the same story.
    """
    await _require_dialysis_access(current_user.id, patient_id, db)
    since = board._window(days)

    agg = (await db.execute(
        select(
            func.count(TherapySession.id),
            func.avg(TherapySession.pre_dialysis_weight_kg),
            func.avg(TherapySession.post_dialysis_weight_kg),
            func.avg(TherapySession.fluid_removed_ml),
            func.avg(TherapySession.duration_minutes),
            func.min(TherapySession.scheduled_date),
            func.max(TherapySession.scheduled_date),
        ).where(
            TherapySession.user_id == patient_id,
            TherapySession.scheduled_date >= since,
        )
    )).one()
    total_all_time = (await db.execute(
        select(func.count(TherapySession.id))
        .where(TherapySession.user_id == patient_id))).scalar() or 0

    def _r(v, places=1):
        return None if v is None else round(float(v), places)

    return {
        "period_days": days,
        "total_sessions": int(agg[0] or 0),
        # Stated separately so a windowed count is never mistaken for the record.
        "total_sessions_all_time": int(total_all_time),
        "avg_pre_weight_kg": _r(agg[1]),
        "avg_post_weight_kg": _r(agg[2]),
        "avg_fluid_removed_ml": _r(agg[3], 0),
        "avg_duration_min": _r(agg[4], 0),
        "earliest_session": str(agg[5])[:10] if agg[5] else None,
        "latest_session": str(agg[6])[:10] if agg[6] else None,
    }


@router.post("/patient/{patient_id}/therapy-sessions/{session_id}/notes")
async def add_patient_therapy_note(
    patient_id: int,
    session_id: int,
    body: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """A physician's note on a session. Append-only, hashed like the patient's.

    `/chronic/therapy-sessions/{id}/notes` is scoped to the caller's own rows, so
    a physician posting to it 404s. Sign-off without the ability to say WHY is
    an attestation with no clinical content.
    """
    await _require_dialysis_access(current_user.id, patient_id, db)
    await _therapy_session_for_patient(session_id, patient_id, db)

    text = (body or {}).get("note_text", "")
    if not isinstance(text, str) or not text.strip():
        raise HTTPException(status_code=422, detail="note_text is required")
    text = text.strip()

    note = ClinicalNote(
        session_id=session_id,
        author_id=current_user.id,
        author_role="physician",
        note_type=(body or {}).get("note_type") or "clinical",
        note_text=text,
        note_hash=hashlib.sha512(text.encode("utf-8")).hexdigest(),
    )
    db.add(note)
    await db.commit()
    await db.refresh(note)
    return {"id": note.id, "author_role": note.author_role, "note_type": note.note_type,
            "note_text": note.note_text, "created_at": _iso_dt(note.created_at)}


@router.get("/patient/{patient_id}/therapy-sessions/{session_id}/integrity")
async def get_patient_therapy_integrity(
    patient_id: int,
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The tamper-evidence behind a session: ledger trail + recomputed hashes.

    A truncated hash printed on screen proves nothing — it is a string the page
    was handed. This re-derives each block's hash from its payload and its
    predecessor, exactly as `verify_chain_integrity` does, and reports whether
    the chain still holds and whether each block reached the chain node.
    """
    await _require_dialysis_access(current_user.id, patient_id, db)
    session = await _therapy_session_for_patient(session_id, patient_id, db)

    blocks = (await db.execute(
        select(BlockRecord)
        .where(BlockRecord.entity_id == session_id,
               BlockRecord.chain_type == "therapy")
        .order_by(BlockRecord.index)
    )).scalars().all()

    trail = []
    for b in blocks:
        payload = (b.data or {})
        trail.append({
            "block_uid": b.block_uid, "index": b.index, "action": b.action,
            "event": payload.get("event"),
            "actor_id": b.actor_id,
            "recorded_at": _iso_dt(b.created_at),
            "hash": b.hash, "previous_hash": b.previous_hash,
            "anchored": b.blockchain_tx_hash is not None,
            "tx_hash": b.blockchain_tx_hash,
            "block_number": b.blockchain_block_num,
        })

    # The stored payload hash must still describe the row as it stands now:
    # if a value changed after sign-off, this is where it shows.
    recomputed = _compute_payload_hash(session)
    return {
        "session_id": session_id,
        "payload_hash": session.payload_hash,
        "payload_hash_recomputed": recomputed,
        "payload_matches": (session.payload_hash == recomputed) if session.payload_hash else None,
        "chain_intact": all(
            trail[i]["previous_hash"] == trail[i - 1]["hash"] for i in range(1, len(trail))
        ) if len(trail) > 1 else (len(trail) == 1 or None),
        "anchored_count": sum(1 for t in trail if t["anchored"]),
        "trail": trail,
    }
