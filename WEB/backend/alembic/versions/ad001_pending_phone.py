"""Carry a phone number through a pending registration.

Additive only (canon §3ao): one nullable column, no drops.

Why: web registration consolidated onto the two-step flow, and the one-step
form it replaced collected a phone number — which `auth.register` stored as
`users.phone_number` and which the login path looks accounts up by. Without
this column the consolidation would have silently removed phone login for
every new signup.

Revision ID: ad001_pending_phone
Revises: ac001_pending_name_parts
"""
from alembic import op
import sqlalchemy as sa

revision = "ad001_pending_phone"
down_revision = "ac001_pending_name_parts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pending_registrations",
                  sa.Column("phone", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("pending_registrations", "phone")
