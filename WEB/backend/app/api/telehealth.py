"""Telehealth API — sessions, participants, notes, recordings, transcripts, signaling, availability."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, update, delete
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.telehealth import (
    TelehealthSession,
    SessionParticipant,
    SessionNote,
    SessionRecording,
    SessionTranscript,
    SessionSignal,
    ProviderAvailability,
)
from app.schemas.telehealth import (
    SessionCreate, SessionUpdate, SessionResponse,
    ParticipantAdd, ParticipantUpdate, ParticipantResponse,
    NoteCreate, NoteUpdate, NoteResponse,
    RecordingCreate, RecordingUpdate, RecordingResponse,
    TranscriptCreate, TranscriptResponse,
    SignalCreate, SignalResponse,
    AvailabilityCreate, AvailabilityUpdate, AvailabilityResponse,
    RTCConfig, ICEServerConfig,
    VALID_SESSION_TYPES, VALID_SESSION_STATUSES, VALID_PARTICIPANT_ROLES,
    VALID_NOTE_TYPES, VALID_SIGNAL_TYPES, VALID_PRIORITIES,
)

router = APIRouter()


# ═══════════════════════════════════════════════════════════════════════
# SESSIONS
# ═══════════════════════════════════════════════════════════════════════

@router.get("/sessions", response_model=list[SessionResponse])
async def list_sessions(
    status: str | None = Query(None),
    session_type: str | None = Query(None),
    upcoming: bool = Query(False, description="Only sessions in the future"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List telehealth sessions the current user is involved in."""
    # Sessions where user is creator, provider, or participant
    participant_sub = select(SessionParticipant.session_id).where(
        SessionParticipant.user_id == current_user.id
    ).scalar_subquery()

    query = (
        select(TelehealthSession)
        .options(selectinload(TelehealthSession.participants))
        .where(
            or_(
                TelehealthSession.created_by_id == current_user.id,
                TelehealthSession.provider_id == current_user.id,
                TelehealthSession.id.in_(participant_sub),
            )
        )
    )
    if status:
        query = query.where(TelehealthSession.status == status)
    if session_type:
        query = query.where(TelehealthSession.session_type == session_type)
    if upcoming:
        query = query.where(TelehealthSession.scheduled_start >= datetime.now(timezone.utc))

    query = query.order_by(TelehealthSession.scheduled_start.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/sessions", response_model=SessionResponse, status_code=201)
async def create_session(
    body: SessionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new telehealth session."""
    if body.session_type not in VALID_SESSION_TYPES:
        raise HTTPException(400, f"Invalid session_type. Must be one of: {VALID_SESSION_TYPES}")
    if body.priority and body.priority not in VALID_PRIORITIES:
        raise HTTPException(400, f"Invalid priority. Must be one of: {VALID_PRIORITIES}")

    session = TelehealthSession(
        session_code=str(uuid.uuid4()),
        created_by_id=current_user.id,
        **body.model_dump(exclude_none=False),
    )
    db.add(session)
    await db.flush()

    # Auto-add creator as patient participant
    db.add(SessionParticipant(
        session_id=session.id,
        user_id=current_user.id,
        role="patient",
        status="invited",
    ))

    # Auto-add provider if specified
    if body.provider_id and body.provider_id != current_user.id:
        db.add(SessionParticipant(
            session_id=session.id,
            user_id=body.provider_id,
            role="provider",
            status="invited",
        ))

    await db.flush()

    # Reload with participants
    result = await db.execute(
        select(TelehealthSession)
        .options(selectinload(TelehealthSession.participants))
        .where(TelehealthSession.id == session.id)
    )
    return result.scalar_one()


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get session details."""
    session = await _get_session_for_user(session_id, current_user.id, db)
    return session


@router.patch("/sessions/{session_id}", response_model=SessionResponse)
async def update_session(
    session_id: int,
    body: SessionUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a session (status, scheduling, etc.)."""
    session = await _get_session_for_user(session_id, current_user.id, db)

    if body.status and body.status not in VALID_SESSION_STATUSES:
        raise HTTPException(400, f"Invalid status. Must be one of: {VALID_SESSION_STATUSES}")

    updates = body.model_dump(exclude_unset=True)

    # Handle status transitions
    if "status" in updates:
        new_status = updates["status"]
        if new_status == "in_progress" and not session.actual_start:
            session.actual_start = datetime.now(timezone.utc)
        elif new_status in ("completed", "cancelled", "no_show"):
            if not session.actual_end:
                session.actual_end = datetime.now(timezone.utc)
            if session.actual_start and not session.duration_minutes:
                delta = (session.actual_end - session.actual_start).total_seconds()
                session.duration_minutes = max(1, int(delta / 60))
        if new_status == "cancelled":
            session.cancelled_by_id = current_user.id

    for key, val in updates.items():
        setattr(session, key, val)

    await db.flush()
    result = await db.execute(
        select(TelehealthSession)
        .options(selectinload(TelehealthSession.participants))
        .where(TelehealthSession.id == session.id)
    )
    return result.scalar_one()


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a session (only creator can delete, only if not in-progress)."""
    session = await _get_session_for_user(session_id, current_user.id, db)
    if session.created_by_id != current_user.id:
        raise HTTPException(403, "Only the session creator can delete it.")
    if session.status == "in_progress":
        raise HTTPException(400, "Cannot delete an in-progress session. End it first.")
    await db.delete(session)


# ── Session lifecycle shortcuts ──────────────────────────────────────

@router.patch("/sessions/{session_id}/start", response_model=SessionResponse)
async def start_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Start a session (move to in_progress)."""
    session = await _get_session_for_user(session_id, current_user.id, db)
    if session.status not in ("scheduled", "waiting"):
        raise HTTPException(400, f"Cannot start a session with status '{session.status}'.")
    session.status = "in_progress"
    session.actual_start = datetime.now(timezone.utc)
    await db.flush()
    result = await db.execute(
        select(TelehealthSession)
        .options(selectinload(TelehealthSession.participants))
        .where(TelehealthSession.id == session.id)
    )
    return result.scalar_one()


@router.patch("/sessions/{session_id}/end", response_model=SessionResponse)
async def end_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """End a session (move to completed)."""
    session = await _get_session_for_user(session_id, current_user.id, db)
    if session.status != "in_progress":
        raise HTTPException(400, "Session is not in progress.")
    session.status = "completed"
    session.actual_end = datetime.now(timezone.utc)
    if session.actual_start:
        delta = (session.actual_end - session.actual_start).total_seconds()
        session.duration_minutes = max(1, int(delta / 60))
    await db.flush()
    result = await db.execute(
        select(TelehealthSession)
        .options(selectinload(TelehealthSession.participants))
        .where(TelehealthSession.id == session.id)
    )
    return result.scalar_one()


@router.get("/sessions/{session_id}/rtc-config", response_model=RTCConfig)
async def get_rtc_config(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get WebRTC ICE/TURN server config for a session.

    Returns STUN servers by default. In production, add TURN
    credentials dynamically (e.g. from Coturn with shared-secret).
    """
    session = await _get_session_for_user(session_id, current_user.id, db)

    # Determine user role in this session
    result = await db.execute(
        select(SessionParticipant).where(
            SessionParticipant.session_id == session.id,
            SessionParticipant.user_id == current_user.id,
        )
    )
    participant = result.scalar_one_or_none()
    role = participant.role if participant else "patient"

    return RTCConfig(
        ice_servers=[
            ICEServerConfig(urls=["stun:stun.l.google.com:19302"]),
            ICEServerConfig(urls=["stun:stun1.l.google.com:19302"]),
            # In production, add TURN server with ephemeral credentials:
            # ICEServerConfig(
            #     urls=["turn:turn.alafia.com:3478"],
            #     username="generated-username",
            #     credential="generated-credential",
            # ),
        ],
        session_code=session.session_code,
        user_id=current_user.id,
        role=role,
    )


# ═══════════════════════════════════════════════════════════════════════
# PARTICIPANTS
# ═══════════════════════════════════════════════════════════════════════

@router.get("/sessions/{session_id}/participants", response_model=list[ParticipantResponse])
async def list_participants(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_session_for_user(session_id, current_user.id, db)
    result = await db.execute(
        select(SessionParticipant).where(SessionParticipant.session_id == session_id)
    )
    return result.scalars().all()


@router.post("/sessions/{session_id}/participants", response_model=ParticipantResponse, status_code=201)
async def add_participant(
    session_id: int,
    body: ParticipantAdd,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a participant to a session."""
    await _get_session_for_user(session_id, current_user.id, db)
    if body.role not in VALID_PARTICIPANT_ROLES:
        raise HTTPException(400, f"Invalid role. Must be one of: {VALID_PARTICIPANT_ROLES}")

    # Check duplicate
    existing = await db.execute(
        select(SessionParticipant).where(
            SessionParticipant.session_id == session_id,
            SessionParticipant.user_id == body.user_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(400, "User is already a participant in this session.")

    participant = SessionParticipant(
        session_id=session_id,
        user_id=body.user_id,
        role=body.role,
        status="invited",
    )
    db.add(participant)
    await db.flush()
    return participant


@router.patch("/sessions/{session_id}/participants/{user_id}", response_model=ParticipantResponse)
async def update_participant(
    session_id: int,
    user_id: int,
    body: ParticipantUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update participant status (join, leave, toggle cam/mic)."""
    await _get_session_for_user(session_id, current_user.id, db)
    result = await db.execute(
        select(SessionParticipant).where(
            SessionParticipant.session_id == session_id,
            SessionParticipant.user_id == user_id,
        )
    )
    participant = result.scalar_one_or_none()
    if not participant:
        raise HTTPException(404, "Participant not found in this session.")

    updates = body.model_dump(exclude_unset=True)

    # Track timing
    if "status" in updates:
        now = datetime.now(timezone.utc)
        if updates["status"] == "joined":
            if not participant.admitted_at:
                participant.admitted_at = now
        elif updates["status"] in ("left", "disconnected"):
            participant.left_at = now

    for key, val in updates.items():
        setattr(participant, key, val)

    await db.flush()
    return participant


@router.patch("/sessions/{session_id}/join", response_model=ParticipantResponse)
async def join_session(
    session_id: int,
    device_type: str = Query("web"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Current user joins a session (enters waiting room or directly)."""
    session = await _get_session_for_user(session_id, current_user.id, db)

    result = await db.execute(
        select(SessionParticipant).where(
            SessionParticipant.session_id == session_id,
            SessionParticipant.user_id == current_user.id,
        )
    )
    participant = result.scalar_one_or_none()
    if not participant:
        raise HTTPException(403, "You are not a participant in this session.")

    now = datetime.now(timezone.utc)
    participant.device_type = device_type

    if session.waiting_room_enabled and session.status != "in_progress":
        participant.status = "joined"
        participant.joined_waiting_room_at = now
        # Move session to waiting if still scheduled
        if session.status == "scheduled":
            session.status = "waiting"
    else:
        participant.status = "joined"
        participant.admitted_at = now

    await db.flush()
    return participant


@router.patch("/sessions/{session_id}/admit/{user_id}", response_model=ParticipantResponse)
async def admit_participant(
    session_id: int,
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Provider admits a patient from the waiting room."""
    session = await _get_session_for_user(session_id, current_user.id, db)

    result = await db.execute(
        select(SessionParticipant).where(
            SessionParticipant.session_id == session_id,
            SessionParticipant.user_id == user_id,
        )
    )
    participant = result.scalar_one_or_none()
    if not participant:
        raise HTTPException(404, "Participant not found.")

    participant.status = "joined"
    participant.admitted_at = datetime.now(timezone.utc)
    await db.flush()
    return participant


@router.patch("/sessions/{session_id}/leave", response_model=ParticipantResponse)
async def leave_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Current user leaves a session."""
    await _get_session_for_user(session_id, current_user.id, db)

    result = await db.execute(
        select(SessionParticipant).where(
            SessionParticipant.session_id == session_id,
            SessionParticipant.user_id == current_user.id,
        )
    )
    participant = result.scalar_one_or_none()
    if not participant:
        raise HTTPException(404, "Not a participant.")

    participant.status = "left"
    participant.left_at = datetime.now(timezone.utc)
    await db.flush()
    return participant


# ═══════════════════════════════════════════════════════════════════════
# NOTES
# ═══════════════════════════════════════════════════════════════════════

@router.get("/sessions/{session_id}/notes", response_model=list[NoteResponse])
async def list_notes(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_session_for_user(session_id, current_user.id, db)
    query = select(SessionNote).where(SessionNote.session_id == session_id)
    # Non-authors can't see private notes
    query = query.where(
        or_(SessionNote.is_private == False, SessionNote.author_id == current_user.id)
    )
    query = query.order_by(SessionNote.created_at)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/sessions/{session_id}/notes", response_model=NoteResponse, status_code=201)
async def create_note(
    session_id: int,
    body: NoteCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_session_for_user(session_id, current_user.id, db)
    if body.note_type not in VALID_NOTE_TYPES:
        raise HTTPException(400, f"Invalid note_type. Must be one of: {VALID_NOTE_TYPES}")

    note = SessionNote(
        session_id=session_id,
        author_id=current_user.id,
        **body.model_dump(),
    )
    db.add(note)
    await db.flush()
    return note


@router.patch("/sessions/{session_id}/notes/{note_id}", response_model=NoteResponse)
async def update_note(
    session_id: int,
    note_id: int,
    body: NoteUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_session_for_user(session_id, current_user.id, db)
    result = await db.execute(
        select(SessionNote).where(SessionNote.id == note_id, SessionNote.session_id == session_id)
    )
    note = result.scalar_one_or_none()
    if not note:
        raise HTTPException(404, "Note not found.")
    if note.author_id != current_user.id:
        raise HTTPException(403, "Only the author can edit this note.")

    for key, val in body.model_dump(exclude_unset=True).items():
        setattr(note, key, val)
    await db.flush()
    return note


@router.delete("/sessions/{session_id}/notes/{note_id}", status_code=204)
async def delete_note(
    session_id: int,
    note_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_session_for_user(session_id, current_user.id, db)
    result = await db.execute(
        select(SessionNote).where(SessionNote.id == note_id, SessionNote.session_id == session_id)
    )
    note = result.scalar_one_or_none()
    if not note:
        raise HTTPException(404, "Note not found.")
    if note.author_id != current_user.id:
        raise HTTPException(403, "Only the author can delete this note.")
    await db.delete(note)


# ═══════════════════════════════════════════════════════════════════════
# RECORDINGS
# ═══════════════════════════════════════════════════════════════════════

@router.get("/sessions/{session_id}/recordings", response_model=list[RecordingResponse])
async def list_recordings(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_session_for_user(session_id, current_user.id, db)
    result = await db.execute(
        select(SessionRecording).where(SessionRecording.session_id == session_id)
    )
    return result.scalars().all()


@router.post("/sessions/{session_id}/recordings", response_model=RecordingResponse, status_code=201)
async def create_recording(
    session_id: int,
    body: RecordingCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await _get_session_for_user(session_id, current_user.id, db)
    if not session.recording_enabled:
        raise HTTPException(400, "Recording is not enabled for this session.")

    rec = SessionRecording(
        session_id=session_id,
        recording_type=body.recording_type,
        status="recording",
        started_at=datetime.now(timezone.utc),
    )
    db.add(rec)
    await db.flush()
    return rec


@router.patch("/sessions/{session_id}/recordings/{recording_id}", response_model=RecordingResponse)
async def update_recording(
    session_id: int,
    recording_id: int,
    body: RecordingUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_session_for_user(session_id, current_user.id, db)
    result = await db.execute(
        select(SessionRecording).where(
            SessionRecording.id == recording_id,
            SessionRecording.session_id == session_id,
        )
    )
    rec = result.scalar_one_or_none()
    if not rec:
        raise HTTPException(404, "Recording not found.")

    updates = body.model_dump(exclude_unset=True)
    if "status" in updates and updates["status"] in ("ready", "failed"):
        rec.ended_at = datetime.now(timezone.utc)

    for key, val in updates.items():
        setattr(rec, key, val)
    await db.flush()
    return rec


# ═══════════════════════════════════════════════════════════════════════
# TRANSCRIPTS
# ═══════════════════════════════════════════════════════════════════════

@router.get("/sessions/{session_id}/transcripts", response_model=list[TranscriptResponse])
async def list_transcripts(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_session_for_user(session_id, current_user.id, db)
    result = await db.execute(
        select(SessionTranscript)
        .where(SessionTranscript.session_id == session_id)
        .order_by(SessionTranscript.sequence_number)
    )
    return result.scalars().all()


@router.post("/sessions/{session_id}/transcripts", response_model=TranscriptResponse, status_code=201)
async def create_transcript(
    session_id: int,
    body: TranscriptCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a transcript segment (from client-side speech recognition or server-side ASR)."""
    session = await _get_session_for_user(session_id, current_user.id, db)
    if not session.transcription_enabled:
        raise HTTPException(400, "Transcription is not enabled for this session.")

    transcript = SessionTranscript(
        session_id=session_id,
        speaker_id=body.speaker_id or current_user.id,
        **body.model_dump(exclude={"speaker_id"}),
    )
    if body.speaker_id:
        transcript.speaker_id = body.speaker_id
    db.add(transcript)
    await db.flush()
    return transcript


@router.get("/sessions/{session_id}/transcripts/full", response_model=str)
async def get_full_transcript(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the full assembled transcript as plain text."""
    await _get_session_for_user(session_id, current_user.id, db)
    result = await db.execute(
        select(SessionTranscript)
        .where(SessionTranscript.session_id == session_id)
        .order_by(SessionTranscript.sequence_number)
    )
    segments = result.scalars().all()
    lines = [seg.reviewed_content or seg.content for seg in segments]
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════
# SIGNALING  (WebRTC offer/answer/ICE via REST polling fallback)
# ═══════════════════════════════════════════════════════════════════════

@router.post("/sessions/{session_id}/signal", response_model=SignalResponse, status_code=201)
async def send_signal(
    session_id: int,
    body: SignalCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a WebRTC signaling message (offer/answer/ICE candidate)."""
    await _get_session_for_user(session_id, current_user.id, db)
    if body.signal_type not in VALID_SIGNAL_TYPES:
        raise HTTPException(400, f"Invalid signal_type. Must be one of: {VALID_SIGNAL_TYPES}")

    signal = SessionSignal(
        session_id=session_id,
        from_user_id=current_user.id,
        to_user_id=body.to_user_id,
        signal_type=body.signal_type,
        payload=body.payload,
    )
    db.add(signal)
    await db.flush()
    return signal


@router.get("/sessions/{session_id}/signal", response_model=list[SignalResponse])
async def poll_signals(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Poll for unconsumed signals addressed to the current user."""
    await _get_session_for_user(session_id, current_user.id, db)
    result = await db.execute(
        select(SessionSignal).where(
            SessionSignal.session_id == session_id,
            or_(
                SessionSignal.to_user_id == current_user.id,
                SessionSignal.to_user_id.is_(None),
            ),
            SessionSignal.from_user_id != current_user.id,
            SessionSignal.is_consumed == False,
        ).order_by(SessionSignal.created_at)
    )
    signals = result.scalars().all()
    # Mark consumed
    for sig in signals:
        sig.is_consumed = True
    await db.flush()
    return signals


# ═══════════════════════════════════════════════════════════════════════
# PROVIDER AVAILABILITY
# ═══════════════════════════════════════════════════════════════════════

@router.get("/availability", response_model=list[AvailabilityResponse])
async def list_my_availability(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List my availability slots."""
    result = await db.execute(
        select(ProviderAvailability)
        .where(ProviderAvailability.provider_id == current_user.id)
        .order_by(ProviderAvailability.day_of_week, ProviderAvailability.start_time)
    )
    return result.scalars().all()


@router.get("/availability/provider/{provider_id}", response_model=list[AvailabilityResponse])
async def list_provider_availability(
    provider_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """View a provider's availability (for booking)."""
    result = await db.execute(
        select(ProviderAvailability)
        .where(
            ProviderAvailability.provider_id == provider_id,
            ProviderAvailability.status == "available",
        )
        .order_by(ProviderAvailability.day_of_week, ProviderAvailability.start_time)
    )
    return result.scalars().all()


@router.post("/availability", response_model=AvailabilityResponse, status_code=201)
async def create_availability(
    body: AvailabilityCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    slot = ProviderAvailability(
        provider_id=current_user.id,
        **body.model_dump(),
    )
    db.add(slot)
    await db.flush()
    return slot


@router.patch("/availability/{slot_id}", response_model=AvailabilityResponse)
async def update_availability(
    slot_id: int,
    body: AvailabilityUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ProviderAvailability).where(
            ProviderAvailability.id == slot_id,
            ProviderAvailability.provider_id == current_user.id,
        )
    )
    slot = result.scalar_one_or_none()
    if not slot:
        raise HTTPException(404, "Availability slot not found.")

    for key, val in body.model_dump(exclude_unset=True).items():
        setattr(slot, key, val)
    await db.flush()
    return slot


@router.delete("/availability/{slot_id}", status_code=204)
async def delete_availability(
    slot_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ProviderAvailability).where(
            ProviderAvailability.id == slot_id,
            ProviderAvailability.provider_id == current_user.id,
        )
    )
    slot = result.scalar_one_or_none()
    if not slot:
        raise HTTPException(404, "Availability slot not found.")
    await db.delete(slot)


# ═══════════════════════════════════════════════════════════════════════
# SESSION HISTORY / STATS
# ═══════════════════════════════════════════════════════════════════════

@router.get("/sessions/history/summary")
async def session_history_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a summary of the user's telehealth usage."""
    from sqlalchemy import func

    participant_sub = select(SessionParticipant.session_id).where(
        SessionParticipant.user_id == current_user.id
    ).scalar_subquery()

    base = select(TelehealthSession).where(
        or_(
            TelehealthSession.created_by_id == current_user.id,
            TelehealthSession.provider_id == current_user.id,
            TelehealthSession.id.in_(participant_sub),
        )
    )

    # Total counts by status
    all_sessions = await db.execute(base)
    sessions = all_sessions.scalars().all()

    status_counts = {}
    type_counts = {}
    total_minutes = 0
    for s in sessions:
        status_counts[s.status] = status_counts.get(s.status, 0) + 1
        type_counts[s.session_type] = type_counts.get(s.session_type, 0) + 1
        if s.duration_minutes:
            total_minutes += s.duration_minutes

    return {
        "total_sessions": len(sessions),
        "by_status": status_counts,
        "by_type": type_counts,
        "total_minutes": total_minutes,
    }


# ═══════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════

async def _get_session_for_user(
    session_id: int,
    user_id: int,
    db: AsyncSession,
) -> TelehealthSession:
    """Load a session and verify the user has access."""
    result = await db.execute(
        select(TelehealthSession)
        .options(selectinload(TelehealthSession.participants))
        .where(TelehealthSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(404, "Session not found.")

    # Check access: creator, provider, or participant
    if session.created_by_id == user_id or session.provider_id == user_id:
        return session

    participant_ids = [p.user_id for p in session.participants]
    if user_id in participant_ids:
        return session

    raise HTTPException(403, "You do not have access to this session.")
