"""Add the record_access notification category.

Someone other than the patient opening their chart is an event the patient is
entitled to hear about. It rides the existing notification table, so it needs
one new value on the `notificationcategory` enum.

Revision ID: pp001_record_access
Revises: oo001_marketing_opt_out
"""
from typing import Sequence, Union

from alembic import op

revision: str = "pp001_record_access"
down_revision: Union[str, None] = "oo001_marketing_opt_out"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE cannot run inside a transaction block on older
    # servers, and alembic wraps migrations in one. IF NOT EXISTS makes it
    # idempotent; COMMIT first so the ALTER stands on its own.
    op.execute("COMMIT")
    op.execute("ALTER TYPE notificationcategory ADD VALUE IF NOT EXISTS 'record_access'")


def downgrade() -> None:
    # Postgres cannot drop a value from an enum. Removing it would mean
    # rebuilding the type and rewriting every dependent column — far more
    # destructive than the thing being undone. Deliberately a no-op.
    pass
