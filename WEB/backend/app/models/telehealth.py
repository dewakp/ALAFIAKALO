"""Telehealth models.

Comprehensive telehealth infrastructure supporting:
- Video / voice consultations between patients and providers
- WebRTC signaling (offer, answer, ICE candidates)
- Waiting room management
- Session recording metadata
- Live transcription storage
- Clinical notes per session
- Provider availability schedules
"""

from datetime import datetime, timezone, date, time
import enum

from sqlalchemy import (
    String, Integer, DateTime, Date, Time, ForeignKey, Text, Boolean,
    Float, Enum as SAEnum, UniqueConstraint, Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


# ── Enums ────────────────────────────────────────────────────────────

class SessionType(str, enum.Enum):
    VIDEO = "video"
    VOICE = "voice"
    CHAT = "chat"


class SessionStatus(str, enum.Enum):
    SCHEDULED = "scheduled"
    WAITING = "waiting"        # patient in waiting room
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"
    RESCHEDULED = "rescheduled"


class ParticipantRole(str, enum.Enum):
    PATIENT = "patient"
    PROVIDER = "provider"
    OBSERVER = "observer"      # e.g. family member, interpreter


class ParticipantStatus(str, enum.Enum):
    INVITED = "invited"
    JOINED = "joined"
    LEFT = "left"
    DISCONNECTED = "disconnected"
    REJECTED = "rejected"


class AvailabilityStatus(str, enum.Enum):
    AVAILABLE = "available"
    BOOKED = "booked"
    BLOCKED = "blocked"


class SignalType(str, enum.Enum):
    OFFER = "offer"
    ANSWER = "answer"
    ICE_CANDIDATE = "ice_candidate"
    RENEGOTIATE = "renegotiate"


# ── Telehealth Session ──────────────────────────────────────────────

class TelehealthSession(Base):
    """A single telehealth encounter (video, voice, or chat)."""
    __tablename__ = "telehealth_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Session identity
    session_code: Mapped[str] = mapped_column(
        String(36), unique=True, nullable=False, index=True,
        comment="UUID-style room code for joining"
    )
    title: Mapped[str | None] = mapped_column(String(255))
    session_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default=SessionType.VIDEO.value
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=SessionStatus.SCHEDULED.value, index=True
    )

    # Scheduling
    scheduled_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scheduled_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actual_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actual_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_minutes: Mapped[int | None] = mapped_column(Integer)

    # Owner / creator (usually the patient or a scheduler)
    created_by_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    # Primary provider for the session
    provider_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), index=True
    )

    # Clinical context
    reason_for_visit: Mapped[str | None] = mapped_column(Text)
    chief_complaint: Mapped[str | None] = mapped_column(Text)
    specialty: Mapped[str | None] = mapped_column(String(100))
    priority: Mapped[str | None] = mapped_column(String(20))  # routine, urgent, emergency

    # Linked records
    linked_calendar_event_id: Mapped[int | None] = mapped_column(Integer)
    linked_condition_id: Mapped[int | None] = mapped_column(Integer)

    # Features enabled
    recording_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    transcription_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    screen_sharing_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    chat_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # Waiting room
    waiting_room_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # Quality & metrics
    connection_quality: Mapped[str | None] = mapped_column(String(20))  # excellent, good, fair, poor
    patient_satisfaction: Mapped[int | None] = mapped_column(Integer)   # 1-5

    # Cancellation / no-show
    cancellation_reason: Mapped[str | None] = mapped_column(Text)
    cancelled_by_id: Mapped[int | None] = mapped_column(Integer)

    # Follow-up
    follow_up_needed: Mapped[bool] = mapped_column(Boolean, default=False)
    follow_up_notes: Mapped[str | None] = mapped_column(Text)
    follow_up_date: Mapped[date | None] = mapped_column(Date)

    # Metadata
    metadata_json: Mapped[str | None] = mapped_column(Text)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    creator = relationship("User", foreign_keys=[created_by_id], backref="created_telehealth_sessions")
    provider = relationship("User", foreign_keys=[provider_id], backref="provider_telehealth_sessions")
    participants = relationship("SessionParticipant", back_populates="session", cascade="all, delete-orphan")
    notes = relationship("SessionNote", back_populates="session", cascade="all, delete-orphan")
    recordings = relationship("SessionRecording", back_populates="session", cascade="all, delete-orphan")
    transcripts = relationship("SessionTranscript", back_populates="session", cascade="all, delete-orphan")
    signals = relationship("SessionSignal", back_populates="session", cascade="all, delete-orphan")


# ── Session Participant ─────────────────────────────────────────────

class SessionParticipant(Base):
    """Tracks who joined a session and their role."""
    __tablename__ = "session_participants"
    __table_args__ = (
        UniqueConstraint("session_id", "user_id", name="uq_session_participant"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("telehealth_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )

    role: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ParticipantRole.PATIENT.value
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ParticipantStatus.INVITED.value
    )

    # Waiting room
    joined_waiting_room_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    admitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Connection info
    device_type: Mapped[str | None] = mapped_column(String(50))  # ios, android, web
    connection_quality: Mapped[str | None] = mapped_column(String(20))

    # Permissions
    camera_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    microphone_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    session = relationship("TelehealthSession", back_populates="participants")
    user = relationship("User")


# ── Session Note ────────────────────────────────────────────────────

class SessionNote(Base):
    """Clinical notes created during or after a session."""
    __tablename__ = "session_notes"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("telehealth_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )

    # SOAP notes structure
    note_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="general"
    )  # general, subjective, objective, assessment, plan, follow_up
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Clinical coding
    diagnosis_codes: Mapped[str | None] = mapped_column(Text)  # JSON array of ICD codes
    procedure_codes: Mapped[str | None] = mapped_column(Text)  # JSON array of CPT codes

    is_private: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    session = relationship("TelehealthSession", back_populates="notes")
    author = relationship("User")


# ── Session Recording ───────────────────────────────────────────────

class SessionRecording(Base):
    """Metadata for session recordings (actual media stored externally)."""
    __tablename__ = "session_recordings"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("telehealth_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )

    recording_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="full"
    )  # full, audio_only, screen
    storage_path: Mapped[str | None] = mapped_column(Text)
    storage_url: Mapped[str | None] = mapped_column(Text)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    mime_type: Mapped[str | None] = mapped_column(String(50))

    # Status
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="recording"
    )  # recording, processing, ready, failed, deleted

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    session = relationship("TelehealthSession", back_populates="recordings")


# ── Session Transcript ──────────────────────────────────────────────

class SessionTranscript(Base):
    """Transcription segments from a session."""
    __tablename__ = "session_transcripts"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("telehealth_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    speaker_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    # Transcript content
    content: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(10), default="en")
    confidence: Mapped[float | None] = mapped_column(Float)

    # Timing within session
    start_offset_ms: Mapped[int | None] = mapped_column(Integer)
    end_offset_ms: Mapped[int | None] = mapped_column(Integer)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # AI processing flags
    is_ai_generated: Mapped[bool] = mapped_column(Boolean, default=True)
    is_reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    reviewed_content: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    session = relationship("TelehealthSession", back_populates="transcripts")
    speaker = relationship("User")


# ── WebRTC Signaling ────────────────────────────────────────────────

class SessionSignal(Base):
    """WebRTC signaling messages (offer/answer/ICE) persisted for reliability."""
    __tablename__ = "session_signals"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("telehealth_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    to_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    signal_type: Mapped[str] = mapped_column(String(30), nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)  # JSON-encoded SDP/ICE

    is_consumed: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    session = relationship("TelehealthSession", back_populates="signals")
    sender = relationship("User", foreign_keys=[from_user_id])
    recipient = relationship("User", foreign_keys=[to_user_id])


# ── Provider Availability ───────────────────────────────────────────

class ProviderAvailability(Base):
    """Weekly / one-off availability slots for providers."""
    __tablename__ = "provider_availability"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    provider_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )

    # Slot definition
    day_of_week: Mapped[int | None] = mapped_column(Integer)  # 0=Mon ... 6=Sun (for recurring)
    specific_date: Mapped[date | None] = mapped_column(Date)  # for one-off overrides
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=AvailabilityStatus.AVAILABLE.value
    )

    # Session types accepted
    session_types: Mapped[str | None] = mapped_column(String(100))  # CSV: video,voice,chat
    slot_duration_minutes: Mapped[int] = mapped_column(Integer, default=30)
    max_patients_per_slot: Mapped[int] = mapped_column(Integer, default=1)

    is_recurring: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    provider = relationship("User", backref="availability_slots")
