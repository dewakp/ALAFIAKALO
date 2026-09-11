"""Saline given during a session, and the machine's own recorded time.

Additive only (canon §3ao): two nullable columns, no drops.

**Saline is fluid the session PUTS BACK.** A litre of saline for an
intradialytic hypotension episode is volume returned to the patient, so
`fluid_removed_ml` on its own overstates what actually came off. Net fluid
removal is what the dry weight is judged against, and a session that removed
2,500 mL while giving 500 mL of saline removed 2,000 mL net — recorded as 2,500
it reads as a patient who tolerated more ultrafiltration than they did.

**The machine's total time is not the wall clock.** It is a specific figure the
machine itself reports, and it excludes the periods it was not dialysing —
alarms, pauses, a line reconnection. The summary's automated duration is
`actual_end_time - actual_start_time`, which is a different number and always
the larger one. Kt/V is computed from TIME ON DIALYSIS, so using the wall clock
overstates the dose delivered. Both are kept, separately, because they answer
different questions and neither can be derived from the other.

Revision ID: ae001_saline_machine_time  (<=32 chars: alembic_version.version_num is varchar(32))
Revises: ad001_pending_phone
"""
from alembic import op
import sqlalchemy as sa

revision = "ae001_saline_machine_time"
down_revision = "ad001_pending_phone"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("therapy_sessions",
                  sa.Column("saline_added_ml", sa.Float(), nullable=True))
    op.add_column("therapy_sessions",
                  sa.Column("machine_total_time_minutes", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("therapy_sessions", "machine_total_time_minutes")
    op.drop_column("therapy_sessions", "saline_added_ml")
