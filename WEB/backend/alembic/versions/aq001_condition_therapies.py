# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""A patient DECLARES their therapy; the app does not guess it from a keyword.

Operator, 2026-10-13: *"Only PD patients must see PD. Let user add Therapy types
in Condition and profile. Same as other health conditions. use condition to
determine the Therapy switch."*

`patient_surfaces` decided which therapy screens to offer from two things, and
both were wrong for the patient who most needs them:

  1. **Sessions already on record.** Correct evidence, and useless to someone
     starting dialysis next week: they need the flowsheet BEFORE their first
     session, which is exactly when the record holds none.
  2. **A hand-typed keyword dict.** `_CONDITION_HINTS` matched condition text
     against `("peritoneal", " pd ", "capd", "ccpd")` and
     `("hemodialysis", "haemodialysis", "esrd", …)`. That is §3an's forbidden
     shape — *"covers only the condition someone happened to think of, cannot
     say why, has no source, never improves, and goes stale silently"* — and
     it silently decides which clinical screen a patient can reach. A patient
     whose condition reads "ESKD" or "renal replacement therapy" matched
     nothing.

So the therapy becomes a DECLARED fact on the condition it treats, entered the
same way a condition is. `use condition to determine the Therapy switch`,
exactly as asked.

**Why on the CONDITION rather than the user.** A therapy treats something.
Putting it on `users` would say a person "is a hemodialysis patient" with no
statement of what for, and could not express a patient on dialysis for ESRD who
later has chemotherapy for something else. The condition already carries
`current_treatment_plan` as free text — which no query can read — and this is
the structured half of the same fact.

Additive only: one nullable column (§3ao — every `upgrade()` in this project's
history adds and never drops; `--autogenerate` would have proposed dropping
five live tables).

Revision ID: aq001_condition_therapies
Revises: ap001_nutrient_quotas
"""

from alembic import op
import sqlalchemy as sa

revision = "aq001_condition_therapies"
down_revision = "ap001_nutrient_quotas"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Comma-separated `TherapyType` VALUES, matching how this schema already
    # stores small declared sets (`users.allergies` is comma-separated text —
    # §3ag, where `json.loads` on it was one of five stacked faults).
    #
    # Nullable with no server default: NULL means "not stated", which is a
    # different fact from "no therapy" and must stay distinguishable (§3aa).
    # Every one of the 9 existing rows is NULL on purpose — nobody has declared
    # anything yet, and inventing a modality from their condition text is the
    # guess this column exists to replace.
    op.add_column(
        "chronic_conditions",
        sa.Column("therapy_types", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("chronic_conditions", "therapy_types")
