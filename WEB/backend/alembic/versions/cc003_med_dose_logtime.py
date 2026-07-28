"""Medication dose-log uniqueness includes log_time.

The unique key on ``medication_dose_logs`` was
``(user_id, log_date, medication_name, dose_amount, dose_unit)`` — it ignored the
time, so logging the same medication+dose twice in one day (morning + evening)
raised a UniqueViolation and the API 500'd. Add ``log_time`` to the key so those
are distinct dose events, while an identical event (same date+time+med+dose) still
dedupes — which the Firebase→PG sync relies on for its ``ON CONFLICT`` upsert.

Idempotent (DROP IF EXISTS + ADD): prod was hotfixed to this shape already, and a
from-scratch DB carries the old (w001) shape — both converge here.
"""

from alembic import op

revision = "cc003_med_dose_logtime"
down_revision = "cc002_reconcile_drift"
branch_labels = None
depends_on = None

_TABLE = "medication_dose_logs"
_NAME = "uq_dose_log_per_user_date_med_dose"
_NEW_COLS = "(user_id, log_date, log_time, medication_name, dose_amount, dose_unit)"
_OLD_COLS = "(user_id, log_date, medication_name, dose_amount, dose_unit)"


def upgrade() -> None:
    op.execute(f"ALTER TABLE {_TABLE} DROP CONSTRAINT IF EXISTS {_NAME}")
    op.execute(f"ALTER TABLE {_TABLE} ADD CONSTRAINT {_NAME} UNIQUE {_NEW_COLS}")


def downgrade() -> None:
    op.execute(f"ALTER TABLE {_TABLE} DROP CONSTRAINT IF EXISTS {_NAME}")
    op.execute(f"ALTER TABLE {_TABLE} ADD CONSTRAINT {_NAME} UNIQUE {_OLD_COLS}")
