"""A learned food category needs its own row, not a borrowed one.

`resolve_band_category` wrote the category onto `food_nutrient_cache` — but only
when a row already existed. For a food never seen before, the USDA lookup ran
and the answer was thrown away, so every later meal repeated it. That is the
half of "check -> store -> learn" that was described but not implemented.

It could not simply create a cache row: `food_nutrient_cache.nutrients` is the
nutrient answer, and a row with an empty one would sit in front of a real
lookup — the "all-zero row counted as a hit" fault of canon 3c. So the category
gets its own small table, which cannot shadow anything.

Revision ID: vv001_food_category_store
Revises: uu001_wellness_nullable
"""

import sqlalchemy as sa
from alembic import op

revision = "vv001_food_category_store"
down_revision = "uu001_wellness_nullable"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "food_category_cache",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("food_name_normalized", sa.String(512), nullable=False, unique=True),
        sa.Column("usda_food_category", sa.String(120), nullable=True),
        sa.Column("band_category", sa.String(40), nullable=False),
        # "usda" | "keyword" | "user" — a guess must never pass for a lookup.
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("hit_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_food_category_cache_name", "food_category_cache",
                    ["food_name_normalized"])


def downgrade() -> None:
    op.drop_index("ix_food_category_cache_name", table_name="food_category_cache")
    op.drop_table("food_category_cache")
