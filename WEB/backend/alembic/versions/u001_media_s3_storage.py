"""Add storage_url to media_assets; make image_base64 nullable.

Revision ID: u001_media_s3_storage
Revises: t001_add_system_id_to_users
Create Date: 2026-04-27

"""

from alembic import op
import sqlalchemy as sa

revision = "u001_media_s3_storage"
down_revision = "t001_add_system_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add URL column for external object storage
    op.add_column(
        "media_assets",
        sa.Column("storage_url", sa.String(2048), nullable=True),
    )
    # Make image_base64 nullable so new rows can omit it when using S3
    op.alter_column(
        "media_assets",
        "image_base64",
        existing_type=sa.Text(),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "media_assets",
        "image_base64",
        existing_type=sa.Text(),
        nullable=False,
    )
    op.drop_column("media_assets", "storage_url")
