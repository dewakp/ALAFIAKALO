"""add telehealth tables

Revision ID: d3e4f5a6b7c8
Revises: c2a3b4d5e6f7
Create Date: 2026-02-15 04:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "d3e4f5a6b7c8"
down_revision = "c2a3b4d5e6f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── telehealth_sessions ──────────────────────────────────────
    op.create_table(
        "telehealth_sessions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("session_code", sa.String(36), unique=True, nullable=False, index=True),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("session_type", sa.String(20), nullable=False, server_default="video"),
        sa.Column("status", sa.String(20), nullable=False, server_default="scheduled", index=True),

        sa.Column("scheduled_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scheduled_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actual_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actual_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=True),

        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("provider_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True, index=True),

        sa.Column("reason_for_visit", sa.Text(), nullable=True),
        sa.Column("chief_complaint", sa.Text(), nullable=True),
        sa.Column("specialty", sa.String(100), nullable=True),
        sa.Column("priority", sa.String(20), nullable=True),

        sa.Column("linked_calendar_event_id", sa.Integer(), nullable=True),
        sa.Column("linked_condition_id", sa.Integer(), nullable=True),

        sa.Column("recording_enabled", sa.Boolean(), server_default="false"),
        sa.Column("transcription_enabled", sa.Boolean(), server_default="true"),
        sa.Column("screen_sharing_enabled", sa.Boolean(), server_default="true"),
        sa.Column("chat_enabled", sa.Boolean(), server_default="true"),
        sa.Column("waiting_room_enabled", sa.Boolean(), server_default="true"),

        sa.Column("connection_quality", sa.String(20), nullable=True),
        sa.Column("patient_satisfaction", sa.Integer(), nullable=True),

        sa.Column("cancellation_reason", sa.Text(), nullable=True),
        sa.Column("cancelled_by_id", sa.Integer(), nullable=True),

        sa.Column("follow_up_needed", sa.Boolean(), server_default="false"),
        sa.Column("follow_up_notes", sa.Text(), nullable=True),
        sa.Column("follow_up_date", sa.Date(), nullable=True),

        sa.Column("metadata_json", sa.Text(), nullable=True),

        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── session_participants ─────────────────────────────────────
    op.create_table(
        "session_participants",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("telehealth_sessions.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("role", sa.String(20), nullable=False, server_default="patient"),
        sa.Column("status", sa.String(20), nullable=False, server_default="invited"),

        sa.Column("joined_waiting_room_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("admitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),

        sa.Column("device_type", sa.String(50), nullable=True),
        sa.Column("connection_quality", sa.String(20), nullable=True),
        sa.Column("camera_enabled", sa.Boolean(), server_default="true"),
        sa.Column("microphone_enabled", sa.Boolean(), server_default="true"),

        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),

        sa.UniqueConstraint("session_id", "user_id", name="uq_session_participant"),
    )

    # ── session_notes ────────────────────────────────────────────
    op.create_table(
        "session_notes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("telehealth_sessions.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("author_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("note_type", sa.String(30), nullable=False, server_default="general"),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("diagnosis_codes", sa.Text(), nullable=True),
        sa.Column("procedure_codes", sa.Text(), nullable=True),
        sa.Column("is_private", sa.Boolean(), server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── session_recordings ───────────────────────────────────────
    op.create_table(
        "session_recordings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("telehealth_sessions.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("recording_type", sa.String(20), nullable=False, server_default="full"),
        sa.Column("storage_path", sa.Text(), nullable=True),
        sa.Column("storage_url", sa.Text(), nullable=True),
        sa.Column("file_size_bytes", sa.Integer(), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("mime_type", sa.String(50), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="recording"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── session_transcripts ──────────────────────────────────────
    op.create_table(
        "session_transcripts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("telehealth_sessions.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("speaker_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("language", sa.String(10), server_default="en"),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("start_offset_ms", sa.Integer(), nullable=True),
        sa.Column("end_offset_ms", sa.Integer(), nullable=True),
        sa.Column("sequence_number", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_ai_generated", sa.Boolean(), server_default="true"),
        sa.Column("is_reviewed", sa.Boolean(), server_default="false"),
        sa.Column("reviewed_content", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── session_signals ──────────────────────────────────────────
    op.create_table(
        "session_signals",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("telehealth_sessions.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("from_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("to_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("signal_type", sa.String(30), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("is_consumed", sa.Boolean(), server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── provider_availability ────────────────────────────────────
    op.create_table(
        "provider_availability",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("provider_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("day_of_week", sa.Integer(), nullable=True),
        sa.Column("specific_date", sa.Date(), nullable=True),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="available"),
        sa.Column("session_types", sa.String(100), nullable=True),
        sa.Column("slot_duration_minutes", sa.Integer(), server_default="30"),
        sa.Column("max_patients_per_slot", sa.Integer(), server_default="1"),
        sa.Column("is_recurring", sa.Boolean(), server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("provider_availability")
    op.drop_table("session_signals")
    op.drop_table("session_transcripts")
    op.drop_table("session_recordings")
    op.drop_table("session_notes")
    op.drop_table("session_participants")
    op.drop_table("telehealth_sessions")
