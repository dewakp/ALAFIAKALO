"""users.last_login for the admin console

The admin console reports when each account last signed in. Nothing recorded it
before, so "last login" could not be answered at all.

NULL means "no successful login since this column shipped", which is NOT the same
as "never signed in" — the console labels it accordingly rather than implying the
account is dormant.

Revision ID: dd002_user_last_login
Revises: dd001_food_training_samples
"""

from alembic import op
import sqlalchemy as sa


revision = "dd002_user_last_login"
down_revision = "dd001_food_training_samples"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("last_login", sa.DateTime(timezone=True), nullable=True))
    # Indexed: the console sorts and filters on it (active in 24h / 7d / 30d).
    op.create_index("ix_users_last_login", "users", ["last_login"])


def downgrade() -> None:
    op.drop_index("ix_users_last_login", table_name="users")
    op.drop_column("users", "last_login")
