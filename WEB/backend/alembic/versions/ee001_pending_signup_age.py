"""Capture date of birth and country on a pending signup, for the age gate.

An account holder must be an adult by their own jurisdiction's standard (see
app/core/age_policy.py). The two-step flow needs the date of birth at
/signup/start so the check happens BEFORE the verification email is sent and
before any payment is taken — refusing someone after they have paid means a
refund and a bad first impression.

Both columns are nullable: rows already in flight when this ships have no date
of birth, and backfilling one would be inventing data. `materialise()` runs the
same age assertion, so an in-flight row without a date of birth cannot quietly
become an account.

Revision ID: ee001_pending_signup_age
Revises: dd004_nutrient_status
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "ee001_pending_signup_age"
down_revision: Union[str, None] = "dd004_nutrient_status"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "pending_registrations",
        sa.Column("date_of_birth", sa.String(length=10), nullable=True),
    )
    op.add_column(
        "pending_registrations",
        sa.Column("country", sa.String(length=2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("pending_registrations", "country")
    op.drop_column("pending_registrations", "date_of_birth")
