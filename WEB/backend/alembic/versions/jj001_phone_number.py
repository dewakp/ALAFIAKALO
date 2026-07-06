"""Add users.phone_number for phone (OTP) sign-in.

Phone-auth users arrive via Firebase phone verification and may have no email;
the E.164 number becomes their account handle.
"""

from alembic import op
import sqlalchemy as sa

revision = "jj001_phone_number"
down_revision = "ii001_flagged_estimates"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("phone_number", sa.String(30), nullable=True))
    op.create_index("ix_users_phone_number", "users", ["phone_number"], unique=True)


def downgrade():
    op.drop_index("ix_users_phone_number", table_name="users")
    op.drop_column("users", "phone_number")
