"""Remember what a food IS, not just what it contains.

`food_nutrient_cache` stored a food's nutrients but never its category, so every
lookup re-derived the category from a hand-written keyword list — the thing that
decided "hard boiled eggs" was an oil and "ripe plantain boiled" was a fat.

USDA FoodData Central already publishes a `foodCategory` for every food
("Plantains, raw" -> "Fruits and Fruit Juices"). Storing it turns a guess into a
lookup that is remembered: know it? -> check -> store -> learn.

Revision ID: ss001_food_category
Revises: rr001_training_consented
"""

import sqlalchemy as sa
from alembic import op

revision = "ss001_food_category"
down_revision = "rr001_training_consented"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The authority's own words, kept verbatim so a future taxonomy change is
    # visible rather than silently re-derived.
    op.add_column("food_nutrient_cache",
                  sa.Column("usda_food_category", sa.String(120), nullable=True))
    # Our band category, resolved from the above.
    op.add_column("food_nutrient_cache",
                  sa.Column("band_category", sa.String(40), nullable=True))
    # How we came to know it: "usda" | "keyword" | "user".
    op.add_column("food_nutrient_cache",
                  sa.Column("category_source", sa.String(20), nullable=True))
    op.create_index("ix_food_cache_band_category", "food_nutrient_cache",
                    ["band_category"])


def downgrade() -> None:
    op.drop_index("ix_food_cache_band_category", table_name="food_nutrient_cache")
    op.drop_column("food_nutrient_cache", "category_source")
    op.drop_column("food_nutrient_cache", "band_category")
    op.drop_column("food_nutrient_cache", "usda_food_category")
