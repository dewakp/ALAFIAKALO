"""Telehealth schemas — request/response DTOs for the telehealth API."""

from datetime import date, time, datetime
from pydantic import BaseModel, Field


# ── Constants ────────────────────────────────────────────────────────

VALID_SESSION_TYPES = {"video", "voice", "chat"}
VALID_SESSION_STATUSES = {
    "scheduled", "waiting", "in_progress", "completed",
    "cancelled", "no_show", "rescheduled",
}
VALID_PARTICIPANT_ROLES = {"patient", "provider", "observer"}
VALID_PARTICIPANT_STATUSES = {"invited", "joined", "left", "disconnected", "rejected"}
VALID_NOTE_TYPES = {"general", "subjective", "objective", "assessment", "plan", "follow_up"}
VALID_PRIORITIES = {"routine", "urgent", "emergency"}
VALID_SIGNAL_TYPES = {"offer", "answer", "ice_candidate", "renegotiate"}


# ── Session ──────────────────────────────────────────────────────────

class SessionCreate(BaseModel):
    title: str | None = None
    session_type: str = "video"
    scheduled_start: datetime
    scheduled_end: datetime | None = None

    provider_id: int | None = None
    reason_for_visit: str | None = None
    chief_complaint: str | None = None
    specialty: str | None = None
    priority: str | None = "routine"

    linked_calendar_event_id: int | None = None
    linked_condition_id: int | None = None

    recording_enabled: bool = False
    transcription_enabled: bool = True
    screen_sharing_enabled: bool = True
    chat_enabled: bool = True
    waiting_room_enabled: bool = True

    metadata_json: str | None = None


class SessionUpdate(BaseModel):
    title: str | None = None
    session_type: str | None = None
    status: str | None = None
    scheduled_start: datetime | None = None
    scheduled_end: datetime | None = None

    provider_id: int | None = None
    reason_for_visit: str | None = None
    chief_complaint: str | None = None
    specialty: str | None = None
    priority: str | None = None

    recording_enabled: bool | None = None
    transcription_enabled: bool | None = None
    screen_sharing_enabled: bool | None = None
    chat_enabled: bool | None = None
    waiting_room_enabled: bool | None = None

    cancellation_reason: str | None = None

    follow_up_needed: bool | None = None
    follow_up_notes: str | None = None
    follow_up_date: date | None = None

    connection_quality: str | None = None
    patient_satisfaction: int | None = Field(None, ge=1, le=5)

    metadata_json: str | None = None


class SessionResponse(BaseModel):
    id: int
    session_code: str
    title: str | None
    session_type: str
    status: str

    scheduled_start: datetime
    scheduled_end: datetime | None
    actual_start: datetime | None
    actual_end: datetime | None
    duration_minutes: int | None

    created_by_id: int
    provider_id: int | None

    reason_for_visit: str | None
    chief_complaint: str | None
    specialty: str | None
    priority: str | None

    linked_calendar_event_id: int | None
    linked_condition_id: int | None

    recording_enabled: bool
    transcription_enabled: bool
    screen_sharing_enabled: bool
    chat_enabled: bool
    waiting_room_enabled: bool

    connection_quality: str | None
    patient_satisfaction: int | None

    cancellation_reason: str | None
    cancelled_by_id: int | None

    follow_up_needed: bool
    follow_up_notes: str | None
    follow_up_date: date | None

    metadata_json: str | None
    created_at: datetime
    updated_at: datetime

    # Nested
    participants: list["ParticipantResponse"] = []

    model_config = {"from_attributes": True}


# ── Participant ──────────────────────────────────────────────────────

class ParticipantAdd(BaseModel):
    user_id: int
    role: str = "patient"


class ParticipantUpdate(BaseModel):
    status: str | None = None
    camera_enabled: bool | None = None
    microphone_enabled: bool | None = None
    device_type: str | None = None
    connection_quality: str | None = None


class ParticipantResponse(BaseModel):
    id: int
    session_id: int
    user_id: int
    role: str
    status: str

    joined_waiting_room_at: datetime | None
    admitted_at: datetime | None
    left_at: datetime | None

    device_type: str | None
    connection_quality: str | None
    camera_enabled: bool
    microphone_enabled: bool

    created_at: datetime

    model_config = {"from_attributes": True}


# ── Notes ────────────────────────────────────────────────────────────

class NoteCreate(BaseModel):
    note_type: str = "general"
    content: str
    diagnosis_codes: str | None = None
    procedure_codes: str | None = None
    is_private: bool = False


class NoteUpdate(BaseModel):
    note_type: str | None = None
    content: str | None = None
    diagnosis_codes: str | None = None
    procedure_codes: str | None = None
    is_private: bool | None = None


class NoteResponse(BaseModel):
    id: int
    session_id: int
    author_id: int
    note_type: str
    content: str
    diagnosis_codes: str | None
    procedure_codes: str | None
    is_private: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Recordings ───────────────────────────────────────────────────────

class RecordingResponse(BaseModel):
    id: int
    session_id: int
    recording_type: str
    storage_path: str | None
    storage_url: str | None
    file_size_bytes: int | None
    duration_seconds: int | None
    mime_type: str | None
    status: str
    started_at: datetime | None
    ended_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class RecordingCreate(BaseModel):
    recording_type: str = "full"


class RecordingUpdate(BaseModel):
    status: str | None = None
    storage_path: str | None = None
    storage_url: str | None = None
    file_size_bytes: int | None = None
    duration_seconds: int | None = None
    mime_type: str | None = None


# ── Transcripts ──────────────────────────────────────────────────────

class TranscriptCreate(BaseModel):
    content: str
    speaker_id: int | None = None
    language: str = "en"
    confidence: float | None = None
    start_offset_ms: int | None = None
    end_offset_ms: int | None = None
    sequence_number: int = 0


class TranscriptResponse(BaseModel):
    id: int
    session_id: int
    speaker_id: int | None
    content: str
    language: str
    confidence: float | None
    start_offset_ms: int | None
    end_offset_ms: int | None
    sequence_number: int
    is_ai_generated: bool
    is_reviewed: bool
    reviewed_content: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Signaling ────────────────────────────────────────────────────────

class SignalCreate(BaseModel):
    to_user_id: int | None = None
    signal_type: str   # offer, answer, ice_candidate, renegotiate
    payload: str       # JSON-encoded SDP or ICE candidate


class SignalResponse(BaseModel):
    id: int
    session_id: int
    from_user_id: int
    to_user_id: int | None
    signal_type: str
    payload: str
    is_consumed: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Provider Availability ────────────────────────────────────────────

class AvailabilityCreate(BaseModel):
    day_of_week: int | None = Field(None, ge=0, le=6)
    specific_date: date | None = None
    start_time: time
    end_time: time
    session_types: str | None = "video,voice,chat"
    slot_duration_minutes: int = 30
    max_patients_per_slot: int = 1
    is_recurring: bool = True


class AvailabilityUpdate(BaseModel):
    day_of_week: int | None = Field(None, ge=0, le=6)
    specific_date: date | None = None
    start_time: time | None = None
    end_time: time | None = None
    status: str | None = None
    session_types: str | None = None
    slot_duration_minutes: int | None = None
    max_patients_per_slot: int | None = None
    is_recurring: bool | None = None


class AvailabilityResponse(BaseModel):
    id: int
    provider_id: int
    day_of_week: int | None
    specific_date: date | None
    start_time: time
    end_time: time
    status: str
    session_types: str | None
    slot_duration_minutes: int
    max_patients_per_slot: int
    is_recurring: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── ICE / TURN server config (returned to clients) ──────────────────

class ICEServerConfig(BaseModel):
    urls: list[str]
    username: str | None = None
    credential: str | None = None


class RTCConfig(BaseModel):
    ice_servers: list[ICEServerConfig]
    session_code: str
    user_id: int
    role: str


# Rebuild to resolve forward references
SessionResponse.model_rebuild()
