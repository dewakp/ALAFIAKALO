# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""A meal keeps the components it was estimated from.

Operator, 2026-10-22: *"save meals component."*

`estimate_meal_nutrients` has always computed one result per item — the name it
parsed, the grams, the record it resolved to, the source, the scaled nutrients —
and `nutrient_enrichment` threw them away, storing only the sum. So a breakfast
stored at 3,090 kcal could not say that 2,706 of it was ONE component
("sardines", resolved to USDA "Fish oil, sardine"), and the 2026-10-22 repair
had to RECONSTRUCT which meals went through a wrong cache row by re-running the
estimator over 836 meals — 4,157 USDA rate-limit refusals to answer a question
a table would answer with a join.

One row per component, written by the enrichment writer each time it estimates
a meal (an earlier estimate's rows are replaced, never kept beside the new
ones — two component sets for one meal would be §3ab's contradictory copy).

Additive only: one new table, no drops, no backfill (§3ao). Existing meals get
components the next time they are estimated; nothing is invented for them.
"""

import sqlalchemy as sa
from alembic import op

revision = "au001_meal_components"
down_revision = "at001_comp_invitations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "nutrition_log_components",
        sa.Column("id", sa.Integer(), primary_key=True),
        # A component has no meaning without its meal: deleting the meal deletes
        # these, which is the one cascade here and the right one.
        sa.Column("nutrition_log_id", sa.Integer(),
                  sa.ForeignKey("nutrition_logs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        # What the PARSER extracted from the patient's words ("sardines") …
        sa.Column("food_name", sa.String(255), nullable=False),
        # … and what the LOOKUP resolved it to ("Fish oil, sardine"). The pair is
        # what makes a wrong match visible; either alone hides it.
        sa.Column("matched_name", sa.String(512), nullable=True),
        # NULL when no weight was known — never a guessed 100 g.
        sa.Column("qty_g", sa.Float(), nullable=True),
        sa.Column("qty_text", sa.String(120), nullable=True),
        sa.Column("source", sa.String(40), nullable=True),
        sa.Column("fdc_id", sa.Integer(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        # FALSE when the estimator judged the component implausible and left it
        # out of the meal's total (`nutrients_excluded`): it is still recorded,
        # because the omission is the finding.
        sa.Column("counted", sa.Boolean(), nullable=False, server_default=sa.true()),
        # Nutrients for THIS component at ITS weight — not per 100 g.
        sa.Column("nutrients", sa.JSON(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.UniqueConstraint("nutrition_log_id", "position",
                            name="uq_nutrition_log_components_position"),
    )
    op.create_index("ix_nutrition_log_components_log", "nutrition_log_components",
                    ["nutrition_log_id"])
    # The repair question — "which meals went through this food?" — by name.
    op.create_index("ix_nutrition_log_components_food", "nutrition_log_components",
                    [sa.text("lower(food_name)")])


def downgrade() -> None:
    op.drop_index("ix_nutrition_log_components_food", table_name="nutrition_log_components")
    op.drop_index("ix_nutrition_log_components_log", table_name="nutrition_log_components")
    op.drop_table("nutrition_log_components")
