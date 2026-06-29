"""clinician directory — extend physicians + provenance/quarantine/audit tables

Revision ID: ee001_clinician_directory
Revises: dd001_learned_food_nutrients
Create Date: 2026-06-28
"""
import sqlalchemy as sa
from alembic import op

revision = "ee001_clinician_directory"
down_revision = "dd001_learned_food_nutrients"
branch_labels = None
depends_on = None


def upgrade():
    # ── Extend physicians with clinician-type + license-verification workflow ──
    op.add_column("physicians", sa.Column("clinician_role", sa.String(40), nullable=False, server_default="physician"))
    op.add_column("physicians", sa.Column("license_state", sa.String(50), nullable=True))
    op.add_column("physicians", sa.Column("primary_source", sa.String(40), nullable=True))
    op.add_column("physicians", sa.Column("verification_status", sa.String(30), nullable=False, server_default="quarantined"))
    op.add_column("physicians", sa.Column("credential_verified", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("physicians", sa.Column("verified_by_user_id", sa.Integer(), nullable=True))
    op.add_column("physicians", sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("physicians", sa.Column("verification_notes", sa.Text(), nullable=True))
    op.add_column("physicians", sa.Column("held_reason", sa.String(80), nullable=True))
    op.create_foreign_key(
        "fk_physicians_verified_by", "physicians", "users",
        ["verified_by_user_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_physicians_clinician_role", "physicians", ["clinician_role"])
    op.create_index("ix_physicians_primary_source", "physicians", ["primary_source"])
    op.create_index("ix_physicians_verification_status", "physicians", ["verification_status"])
    op.create_index("ix_physicians_credential_verified", "physicians", ["credential_verified"])

    # Existing rows: treat as already-in-directory but NOT patient-associable until verified.
    op.execute("UPDATE physicians SET verification_status = 'license_on_record' "
               "WHERE license_number IS NOT NULL AND license_number <> ''")

    # ── Provenance ────────────────────────────────────────────────────────
    op.create_table(
        "clinician_source_records",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("physician_id", sa.Integer(), sa.ForeignKey("physicians.id", ondelete="CASCADE"), nullable=True),
        sa.Column("source", sa.String(40), nullable=False),
        sa.Column("source_uid", sa.String(64), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("source", "source_uid", name="uq_clinician_source_uid"),
    )
    op.create_index("ix_clinician_source_records_uid", "clinician_source_records", ["source", "source_uid"])
    op.create_index("ix_clinician_source_records_physician", "clinician_source_records", ["physician_id"])

    # ── Quarantine / dedup queue ──────────────────────────────────────────
    op.create_table(
        "clinician_ingest_candidates",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source", sa.String(40), nullable=False),
        sa.Column("source_uid", sa.String(64), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("npi_number", sa.String(20), nullable=True),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("clinician_role", sa.String(40), nullable=True),
        sa.Column("specialty", sa.String(150), nullable=True),
        sa.Column("credentials", sa.String(100), nullable=True),
        sa.Column("license_number", sa.String(50), nullable=True),
        sa.Column("license_state", sa.String(50), nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("state_province", sa.String(100), nullable=True),
        sa.Column("postal_code", sa.String(20), nullable=True),
        sa.Column("country", sa.String(100), nullable=True),
        sa.Column("phone", sa.String(30), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("reason", sa.String(255), nullable=True),
        sa.Column("matched_physician_id", sa.Integer(), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_clinician_candidates_source_uid", "clinician_ingest_candidates", ["source", "source_uid"])
    op.create_index("ix_clinician_candidates_status", "clinician_ingest_candidates", ["status"])
    op.create_index("ix_clinician_candidates_npi", "clinician_ingest_candidates", ["npi_number"])

    # ── Audit ─────────────────────────────────────────────────────────────
    op.create_table(
        "clinician_verification_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("physician_id", sa.Integer(), sa.ForeignKey("physicians.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("from_status", sa.String(30), nullable=True),
        sa.Column("to_status", sa.String(30), nullable=True),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source", sa.String(40), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_clinician_verification_log_physician", "clinician_verification_log", ["physician_id"])


def downgrade():
    op.drop_table("clinician_verification_log")
    op.drop_table("clinician_ingest_candidates")
    op.drop_table("clinician_source_records")
    for ix in ("ix_physicians_credential_verified", "ix_physicians_verification_status",
               "ix_physicians_primary_source", "ix_physicians_clinician_role"):
        op.drop_index(ix, table_name="physicians")
    op.drop_constraint("fk_physicians_verified_by", "physicians", type_="foreignkey")
    for col in ("held_reason", "verification_notes", "verified_at", "verified_by_user_id",
                "credential_verified", "verification_status", "primary_source",
                "license_state", "clinician_role"):
        op.drop_column("physicians", col)
