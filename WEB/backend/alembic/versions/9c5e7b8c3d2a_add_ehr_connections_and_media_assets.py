"""add ehr connections and media assets

Revision ID: 9c5e7b8c3d2a
Revises: 8f23b3395540
Create Date: 2026-02-14 03:20:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "9c5e7b8c3d2a"
down_revision = "8f23b3395540"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("insurance_id", sa.String(length=100), nullable=True))
    op.add_column("users", sa.Column("insurance_provider", sa.String(length=100), nullable=True))
    op.add_column("users", sa.Column("insurance_country", sa.String(length=100), nullable=True))

    op.create_table(
        "ehr_connections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("fhir_base_url", sa.Text(), nullable=True),
        sa.Column("patient_id", sa.String(length=100), nullable=True),
        sa.Column("scopes", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ehr_connections_id"), "ehr_connections", ["id"], unique=False)
    op.create_index(op.f("ix_ehr_connections_user_id"), "ehr_connections", ["user_id"], unique=False)
    op.create_index(op.f("ix_ehr_connections_provider"), "ehr_connections", ["provider"], unique=False)
    op.create_index(op.f("ix_ehr_connections_status"), "ehr_connections", ["status"], unique=False)

    op.create_table(
        "media_assets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("content_type", sa.String(length=100), nullable=True),
        sa.Column("file_name", sa.String(length=255), nullable=True),
        sa.Column("file_size_bytes", sa.Integer(), nullable=True),
        sa.Column("image_base64", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_media_assets_id"), "media_assets", ["id"], unique=False)
    op.create_index(op.f("ix_media_assets_user_id"), "media_assets", ["user_id"], unique=False)
    op.create_index(op.f("ix_media_assets_category"), "media_assets", ["category"], unique=False)
    op.create_index(op.f("ix_media_assets_captured_at"), "media_assets", ["captured_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_media_assets_captured_at"), table_name="media_assets")
    op.drop_index(op.f("ix_media_assets_category"), table_name="media_assets")
    op.drop_index(op.f("ix_media_assets_user_id"), table_name="media_assets")
    op.drop_index(op.f("ix_media_assets_id"), table_name="media_assets")
    op.drop_table("media_assets")

    op.drop_index(op.f("ix_ehr_connections_status"), table_name="ehr_connections")
    op.drop_index(op.f("ix_ehr_connections_provider"), table_name="ehr_connections")
    op.drop_index(op.f("ix_ehr_connections_user_id"), table_name="ehr_connections")
    op.drop_index(op.f("ix_ehr_connections_id"), table_name="ehr_connections")
    op.drop_table("ehr_connections")

    op.drop_column("users", "insurance_country")
    op.drop_column("users", "insurance_provider")
    op.drop_column("users", "insurance_id")
