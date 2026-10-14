# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""A therapy is a SWITCH over a comprehensive list, not a set of present items.

Operator, 2026-10-14: *"hard-coded enum for therapy will need a comprehensive
list with items zeroed out (no impact) when not present (like a switch) and a
mechanism for compounded therapies. current model lacks comprehensive list and
does not include switch mechanism."*

Both faults are real and measured.

**The list was curated, not comprehensive.** `THERAPY_CODE_SURFACE` held **10**
hand-picked ICD-11 codes while the WHO branch it was picked from holds **31** —
every one already in the bundled catalog. Picking ten of thirty-one is the same
act as typing them, one step removed: it covers the therapies someone happened
to think of (§3an), and a patient on apheresis, cardiac rehabilitation or
palliative care could not say so.

**A set cannot hold a zero.** `therapy_types` was comma-separated membership,
so a code was present or absent and ABSENT MEANT TWO THINGS AT ONCE: "not
receiving this" and "nobody ever asked". That is §3at's checkbox, exactly —
*"A checkbox cannot record three states, and thrill/bruit has three… 'absent',
the finding that needs to shout, was indistinguishable from a box nobody had
touched."* Here the collapsed states are the patient's whole therapy picture.

Three states, and the row is what separates them:

    no row                  never asked          -> unknown
    receiving = false       explicitly not on it -> a measured ZERO, no impact
    receiving = true        undergoing it        -> contributes

A zero that was stated is evidence. It is what lets a therapy axis have the
same dimensions for every patient — most of them zero — instead of a
variable-length list that no two records can be compared across.

**`regimen` is the compounding mechanism.** Therapies given together as one
treatment share a regimen label, so "HD + ESA + IV iron" is one statement
rather than three unrelated switches, and a reader can tell a combination from
a coincidence. ⚠️ **Which combinations have clinical MEANING is not decided
here** — naming an interaction is a clinical claim, and inventing one is what
§3an forbids. This records what the patient says is given together; it asserts
nothing about the effect.

Additive only (§3ao): one new table, and `chronic_conditions.therapy_types`
stays exactly where it is so nothing that reads it breaks mid-deploy.

Revision ID: ar001_therapy_switch
Revises: aq001_condition_therapies
"""

from alembic import op
import sqlalchemy as sa

revision = "ar001_therapy_switch"
down_revision = "aq001_condition_therapies"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "condition_therapies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("condition_id", sa.Integer(),
                  sa.ForeignKey("chronic_conditions.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        # The ICD-11 code. Verified against the bundled MMS linearization on the
        # way in — §3ad, the catalog is the authority.
        sa.Column("therapy_code", sa.String(length=16), nullable=False),
        # THE SWITCH. NOT NULL on purpose: a row exists only when someone
        # answered, so the column never has to carry "unknown" as a third value
        # — the absence of the row carries it. A nullable boolean here would
        # recreate the tri-state confusion one level down (§3at).
        sa.Column("receiving", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
        # Compounding: therapies sharing a label are given as ONE treatment.
        sa.Column("regimen", sa.String(length=120), nullable=True),
        sa.Column("started_on", sa.Date(), nullable=True),
        sa.Column("ended_on", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    # One statement per therapy per condition. Without this an edit could leave
    # a `receiving=true` row beside a `receiving=false` one for the same code,
    # and whichever was read first would win — the arbitrary-order failure that
    # §3ax's duplicate analyte spellings already cost this codebase once.
    op.create_unique_constraint(
        "uq_condition_therapy", "condition_therapies",
        ["condition_id", "therapy_code"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_condition_therapy", "condition_therapies",
                       type_="unique")
    op.drop_table("condition_therapies")
