"""pharmacy tables

Revision ID: c6d7e8f9a0b1
Revises: b5c6d7e8f9a1
Create Date: 2025-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c6d7e8f9a0b1"
down_revision = "b5c6d7e8f9a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Prescriptions ────────────────────────────────────────────
    op.create_table(
        "prescriptions",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("prescriber_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("medication_name", sa.String(255), nullable=False),
        sa.Column("rxnorm_code", sa.String(20), nullable=True),
        sa.Column("dosage", sa.String(100), nullable=True),
        sa.Column("dosage_unit", sa.String(50), nullable=True),
        sa.Column("strength", sa.String(100), nullable=True),
        sa.Column("form", sa.String(50), nullable=True),
        sa.Column("route", sa.String(50), nullable=True),
        sa.Column("frequency", sa.String(100), nullable=True),
        sa.Column("duration_days", sa.Integer(), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=True),
        sa.Column("refills_authorized", sa.Integer(), default=0),
        sa.Column("refills_remaining", sa.Integer(), default=0),
        sa.Column("diagnosis", sa.Text(), nullable=True),
        sa.Column("instructions", sa.Text(), nullable=True),
        sa.Column("pharmacy_notes", sa.Text(), nullable=True),
        sa.Column("substitution_allowed", sa.Boolean(), default=True),
        sa.Column("daw_code", sa.String(10), nullable=True),
        sa.Column("prescribed_date", sa.Date(), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "draft", "active", "filled", "partially_filled",
                "cancelled", "expired", "on_hold",
                name="prescriptionstatus",
            ),
            default="active",
        ),
        sa.Column("is_controlled_substance", sa.Boolean(), default=False),
        sa.Column("dea_schedule", sa.String(10), nullable=True),
        sa.Column("medication_id", sa.Integer(), sa.ForeignKey("medications.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── Dispenses ────────────────────────────────────────────────
    op.create_table(
        "dispenses",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("prescription_id", sa.Integer(), sa.ForeignKey("prescriptions.id"), nullable=False, index=True),
        sa.Column("pharmacist_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("quantity_dispensed", sa.Integer(), nullable=True),
        sa.Column("days_supply", sa.Integer(), nullable=True),
        sa.Column("ndc_code", sa.String(20), nullable=True),
        sa.Column("lot_number", sa.String(50), nullable=True),
        sa.Column("expiration_date", sa.Date(), nullable=True),
        sa.Column("manufacturer", sa.String(255), nullable=True),
        sa.Column("is_generic", sa.Boolean(), default=False),
        sa.Column("drug_utilization_review", sa.Text(), nullable=True),
        sa.Column("clinical_notes", sa.Text(), nullable=True),
        sa.Column("counseling_provided", sa.Boolean(), default=False),
        sa.Column("counseling_notes", sa.Text(), nullable=True),
        sa.Column("interactions_checked", sa.Boolean(), default=False),
        sa.Column("interactions_found", sa.Text(), nullable=True),
        sa.Column("allergy_checked", sa.Boolean(), default=False),
        sa.Column("allergy_alerts", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "pending", "processing", "ready_for_pickup",
                "dispensed", "returned", "cancelled",
                name="dispensestatus",
            ),
            default="pending",
        ),
        sa.Column("dispensed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("picked_up_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── Adherence Logs ───────────────────────────────────────────
    op.create_table(
        "adherence_logs",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("prescription_id", sa.Integer(), sa.ForeignKey("prescriptions.id"), nullable=False, index=True),
        sa.Column("scheduled_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actual_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.Enum("taken", "missed", "skipped", "late", name="adherencestatus"),
            default="taken",
        ),
        sa.Column("dose_taken", sa.String(100), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("side_effects_reported", sa.Text(), nullable=True),
        sa.Column("mood_before", sa.Integer(), nullable=True),
        sa.Column("mood_after", sa.Integer(), nullable=True),
        sa.Column("pain_before", sa.Integer(), nullable=True),
        sa.Column("pain_after", sa.Integer(), nullable=True),
        sa.Column("symptom_change", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── Medication Schedules ─────────────────────────────────────
    op.create_table(
        "medication_schedules",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("prescription_id", sa.Integer(), sa.ForeignKey("prescriptions.id"), nullable=False, index=True),
        sa.Column("time_of_day", sa.String(10), nullable=False),
        sa.Column("days_of_week", sa.String(50), nullable=True),
        sa.Column("dose_label", sa.String(100), nullable=True),
        sa.Column("is_active", sa.Boolean(), default=True),
        sa.Column("reminder_minutes_before", sa.Integer(), default=15),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── Refill Requests ──────────────────────────────────────────
    op.create_table(
        "refill_requests",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("prescription_id", sa.Integer(), sa.ForeignKey("prescriptions.id"), nullable=False, index=True),
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("requested_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("approved_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column(
            "status",
            sa.Enum("requested", "approved", "denied", "filled", name="refillstatus"),
            default="requested",
        ),
        sa.Column("quantity_requested", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("denial_reason", sa.Text(), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("refill_requests")
    op.drop_table("medication_schedules")
    op.drop_table("adherence_logs")
    op.drop_table("dispenses")
    op.drop_table("prescriptions")
    sa.Enum(name="prescriptionstatus").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="dispensestatus").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="adherencestatus").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="refillstatus").drop(op.get_bind(), checkfirst=True)
