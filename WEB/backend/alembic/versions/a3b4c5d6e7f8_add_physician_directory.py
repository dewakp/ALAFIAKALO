"""add_physician_directory_tables

Revision ID: a3b4c5d6e7f8
Revises: e1f2a3b4c5d6
Create Date: 2026-02-16

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a3b4c5d6e7f8"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── physicians (global directory) ──
    op.create_table(
        "physicians",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        # Identity
        sa.Column("full_name", sa.String(255), nullable=False, index=True),
        sa.Column("specialty", sa.String(100), nullable=False, index=True),
        sa.Column("specialty_category", sa.String(100), nullable=True),
        sa.Column("credentials", sa.String(100), nullable=True),
        sa.Column("npi_number", sa.String(20), unique=True, nullable=True),
        sa.Column("license_number", sa.String(50), nullable=True),
        # Contact
        sa.Column("phone", sa.String(30), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("website", sa.Text(), nullable=True),
        # Location
        sa.Column("address_line1", sa.String(255), nullable=True),
        sa.Column("address_line2", sa.String(255), nullable=True),
        sa.Column("city", sa.String(100), nullable=True, index=True),
        sa.Column("state_province", sa.String(100), nullable=True),
        sa.Column("postal_code", sa.String(20), nullable=True),
        sa.Column("country", sa.String(100), nullable=True, index=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        # Practice Details
        sa.Column("facility_name", sa.String(255), nullable=True),
        sa.Column("accepting_new_patients", sa.Boolean(), nullable=True),
        sa.Column("telehealth_available", sa.Boolean(), nullable=True),
        sa.Column("languages_spoken", sa.Text(), nullable=True),
        sa.Column("operating_hours", sa.Text(), nullable=True),
        sa.Column("insurance_accepted", sa.Text(), nullable=True),
        # Ratings
        sa.Column("average_rating", sa.Float(), nullable=True, server_default="0.0"),
        sa.Column("review_count", sa.Integer(), nullable=False, server_default="0"),
        # Provenance
        sa.Column("source", sa.String(30), nullable=False, server_default="user_contributed"),
        sa.Column("source_id", sa.String(255), nullable=True),
        sa.Column("contributed_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("status", sa.String(20), nullable=False, server_default="unverified"),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_physicians_geo", "physicians", ["latitude", "longitude"])
    op.create_index("ix_physicians_specialty_city", "physicians", ["specialty", "city"])

    # ── saved_physicians (per-user bookmarks) ──
    op.create_table(
        "saved_physicians",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("physician_id", sa.Integer(), sa.ForeignKey("physicians.id", ondelete="CASCADE"), nullable=False),
        sa.Column("nickname", sa.String(100), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_primary_care", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("relationship_type", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "physician_id", name="uq_user_physician"),
    )

    # ── physician_reviews ──
    op.create_table(
        "physician_reviews",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("physician_id", sa.Integer(), sa.ForeignKey("physicians.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("review_text", sa.Text(), nullable=True),
        sa.Column("is_anonymous", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_approved", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("reported", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "physician_id", name="uq_user_physician_review"),
    )
    op.create_index("ix_physician_reviews_physician", "physician_reviews", ["physician_id"])


def downgrade() -> None:
    op.drop_table("physician_reviews")
    op.drop_table("saved_physicians")
    op.drop_table("physicians")
