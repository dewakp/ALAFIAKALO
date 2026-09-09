"""Tell the person a record was shared WITH that it happened.

Sharing was silent. `POST /data-sharing/grants` created the grant and returned
it to the owner; the grantee learned nothing — no email, no notification, no
entry anywhere they would look. Someone could be given access to a patient's
labs and never know they had it.

Adds one value to the `notificationcategory` enum. `RECORD_ACCESS` already
exists but means the opposite direction — the patient's own view of who opened
their chart — so reusing it would put "your record was shared with you" in the
patient's access log.

ADD VALUE IF NOT EXISTS is safe to re-run, and Postgres 12+ permits it inside a
transaction as long as the value is not USED in the same transaction (it is
not — this migration only declares it).

There is no downgrade: Postgres cannot drop an enum value, and rewriting the
type to remove one would rewrite every notification row. Leaving an unused
value costs nothing.

Revision ID: zz001_record_shared_notification
Revises: yy001_ai_interaction_saved
"""

from alembic import op

revision = "zz001_record_shared_notification"
down_revision = "yy001_ai_interaction_saved"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE notificationcategory ADD VALUE IF NOT EXISTS 'record_shared'")


def downgrade() -> None:
    # Deliberately a no-op — see the module docstring.
    pass
