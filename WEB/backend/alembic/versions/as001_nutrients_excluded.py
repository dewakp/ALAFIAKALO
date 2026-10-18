# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""A partial meal total must say what it left out.

Operator, 2026-10-18: *"things that used to work stop working reliably"* — and
then, having been offered the choice between fixing the cause and making the
loss visible, *"do 54a first."*

Until 2026-10-18 a meal whose components included ONE the plausibility guard
refused was discarded whole: `nutrient_status='failed'`, and the screen read
**"unavailable"**. That was measured on this patient's own rows —
`1 boiled egg, 1 cup of tea, 1 slice of kiwi` had stored 92 kcal and later
failed entirely because `tea` at 1 kcal/100 g fell outside a `tea_coffee` band
of 22-110. Plain tea really is about 1 kcal/100 g; the band was wrong, and it
cost the egg and the kiwi too.

`5115341` stopped the collateral damage: the flagged component is excluded and
the rest is kept. That introduced a NEW risk, which this column exists to
close. On

    "Organic Milk (Pasteurized, Nonfat), Protein Drink / Nutritional Beverage"

the real milk was dropped as a wrong match, so the total reads 193 kcal — and
without this column it would render exactly like any complete total. A number
that omits an item reads as the whole meal (§3aa).

**The names, not a sentence.** The column stores the list of omitted food names
so each client composes its own localised line; a sentence written here would
reach eleven languages in English (§3aw).

**Why not a `nutrient_status` value.** "partial" was the obvious shape and is
wrong: `record_tools.py` treats any status outside `(None, "done")` as unusable,
so a partial meal would have become invisible to the assistant — the patient's
own record hidden from the thing that answers questions about it.

Additive only: one nullable column, no drops, no backfill (§3ao). Existing rows
stay NULL, which correctly means "nothing was excluded, as far as we know" —
the exclusions that happened before this column existed were never recorded and
must not be invented.
"""

import sqlalchemy as sa
from alembic import op

revision = "as001_nutrients_excluded"
down_revision = "ar001_therapy_switch"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "nutrition_logs",
        sa.Column("nutrients_excluded", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("nutrition_logs", "nutrients_excluded")
