# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""Food-composition authorities beyond USDA, held as rows.

Operator, 2026-10-23: *"when USDA fails, fall back to search, LLM or RAG. The
data usually exist somewhere. Then build knowledge."* and, on WAFCT 2019:
*"build with it. I am asking FAO for permission."*

USDA does not hold the foods this record eats most. Measured against live
FoodData Central: "bitter leaf" retrieves bitter GOURD (a different plant),
"paw paw" retrieves nothing, and egusi, ogbono and gari have no entry. The
FAO/INFOODS West African Food Composition Table 2019 holds every one —
Vernonia leaves, papaya, melon seed, dikanut, toasted grated cassava.

ONE table for any composition authority (`source` + `code`), so the next one
is a loader, not a migration.

⚠️ **The table ships EMPTY, and that is the licence gate.** WAFCT 2019 is
CC BY-NC-SA 3.0 IGO — non-commercial — and ALAFIA is a paid product. No data is
in the repository or the image; `scripts/load_reference_foods.py` fills it from
the operator's own copy of the workbook. Production is loaded when FAO's
permission arrives; until then the lookup tier finds no rows and does nothing.

Additive only (§3ao).
"""

import sqlalchemy as sa
from alembic import op

revision = "av001_reference_foods"
down_revision = "au001_meal_components"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reference_foods",
        sa.Column("id", sa.Integer(), primary_key=True),
        # The authority and edition — "wafct_2019". Cached lookups record it
        # as their source, so every figure traces back to a table and a row.
        sa.Column("source", sa.String(40), nullable=False),
        # The authority's own identifier ("04_022"), so a value can be checked
        # against the printed table.
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("name_en", sa.String(400), nullable=False),
        sa.Column("name_fr", sa.String(400), nullable=True),
        sa.Column("scientific_name", sa.String(200), nullable=True),
        sa.Column("food_group", sa.String(200), nullable=True),
        # Per 100 g EDIBLE PORTION, in ALAFIA's catalog keys and units.
        sa.Column("nutrients", sa.JSON(), nullable=False),
        # Keys whose value the authority printed in [brackets] — imputed or
        # borrowed from another table, not analysed for this food.
        sa.Column("imputed", sa.JSON(), nullable=True),
        sa.Column("biblio", sa.Text(), nullable=True),
        sa.Column("loaded_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.UniqueConstraint("source", "code", name="uq_reference_foods_source_code"),
    )
    op.create_index("ix_reference_foods_name_en", "reference_foods", [sa.text("lower(name_en)")])


def downgrade() -> None:
    op.drop_index("ix_reference_foods_name_en", table_name="reference_foods")
    op.drop_table("reference_foods")
