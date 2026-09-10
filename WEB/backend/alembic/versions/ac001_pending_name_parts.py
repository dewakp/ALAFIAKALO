"""Carry first/last name through a pending registration.

Additive only (canon §3ao): two nullable columns, no drops. Existing pending
rows keep their `full_name` and simply have no parts — `materialise()` reads
`full_name` for those, which is what it always did.

Revision ID: ac001_pending_name_parts
Revises: ab001_name_parts_and_avatar
"""
from alembic import op
import sqlalchemy as sa

revision = "ac001_pending_name_parts"
down_revision = "ab001_name_parts_and_avatar"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pending_registrations",
                  sa.Column("first_name", sa.String(length=100), nullable=True))
    op.add_column("pending_registrations",
                  sa.Column("last_name", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("pending_registrations", "last_name")
    op.drop_column("pending_registrations", "first_name")
