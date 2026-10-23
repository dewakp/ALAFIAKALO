# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""The food cache remembers WHAT a name resolved to.

A cache hit returned `food_name_original` — the patient's own words — so every
stored meal component read "chicken wings -> chicken wings" and the per-item
view could not show the wrong-match it exists to expose ("sardines -> Fish oil,
sardine"). Measured on the production repair, 2026-10-23: of the components
written that day, the matched name repeated the typed name wherever the food
came from the cache.

Nullable and not backfilled: an old row's resolved record is not recorded
anywhere, and inventing it would be a fabricated provenance. Additive (§3ao).
"""

import sqlalchemy as sa
from alembic import op

revision = "ax001_cache_matched_name"
down_revision = "aw001_media_storage_url"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("food_nutrient_cache", sa.Column("matched_name", sa.String(512), nullable=True))


def downgrade() -> None:
    op.drop_column("food_nutrient_cache", "matched_name")
