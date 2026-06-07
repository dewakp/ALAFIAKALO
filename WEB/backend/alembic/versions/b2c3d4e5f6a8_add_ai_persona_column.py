"""add ai_persona column

Revision ID: b2c3d4e5f6a8
Revises: a1b2c3d4e5f7
Create Date: 2025-06-15 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "b2c3d4e5f6a8"
down_revision = "a1b2c3d4e5f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("ai_persona", sa.String(50), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "ai_persona")
