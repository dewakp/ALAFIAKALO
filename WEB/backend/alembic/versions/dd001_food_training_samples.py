"""food_training_samples: the Phase 5 vision corpus

Nothing was accumulating training data. `labeled_food_images` keeps a 64-bit
perceptual hash and discards the photo (right for recall, useless for training),
and `/ai/vision` recorded nothing at all — so every user correction was thrown
away when the meal was saved.

This table is append-only: one row per analysis, holding the model's prediction
and, once the user edits it, their ground truth. Rows with `corrected_items` set
are supervised examples.

Image bytes live in `media_assets` (category 'food_training') and are retained
ONLY with `privacy_settings.allow_collective_insights`. Without consent the row
is still written — accuracy is measurable without keeping anyone's photo — and
`media_asset_id` stays NULL.

NOTE ON PARENTAGE: this repo currently has multiple alembic heads. This revision
is parented on cc003_med_dose_logtime (the head prod is nearest to). The heads
still need an `alembic merge` before `upgrade head` is unambiguous.

Revision ID: dd001_food_training_samples
Revises: cc003_med_dose_logtime
"""

from alembic import op
import sqlalchemy as sa


revision = "dd001_food_training_samples"
down_revision = "cc003_med_dose_logtime"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "food_training_samples",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("image_sha256", sa.String(64), nullable=False, index=True),
        sa.Column("phash", sa.String(32), nullable=True, index=True),
        sa.Column("media_asset_id", sa.Integer(),
                  sa.ForeignKey("media_assets.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("image_retained", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("image_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("source_model", sa.String(120), nullable=True),
        sa.Column("predicted_items", sa.JSON(), nullable=True),
        sa.Column("predicted_nutrition", sa.JSON(), nullable=True),
        sa.Column("corrected_items", sa.JSON(), nullable=True),
        sa.Column("correction_kind", sa.String(20), nullable=False, server_default="none"),
        sa.Column("corrected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now(), index=True),
    )
    # "every correction of a given kind, newest first" is the training query.
    op.create_index(
        "ix_food_training_samples_kind_created",
        "food_training_samples", ["correction_kind", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_food_training_samples_kind_created", table_name="food_training_samples")
    op.drop_table("food_training_samples")
