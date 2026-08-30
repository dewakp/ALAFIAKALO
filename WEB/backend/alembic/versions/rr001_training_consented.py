"""Rename image_retained -> training_consented.

"Retained" and "stored" mean the same thing, so using one for "kept at all" and
the other for "kept for training" was a contradiction sitting in the schema. It
is not a distinction anyone can hold: if an image is retained, it is stored.

The two facts are now named for what they actually are:

    media_asset_id      the photo IS stored — always, as part of the patient's
                        own record, so they and their clinician can open a past
                        meal and see it
    training_consented  the patient allowed that photo to train a SHARED model
                        (PrivacySettings.allow_collective_insights)

Revision ID: rr001_training_consented
Revises: qq001_dose_override
"""

from alembic import op

revision = "rr001_training_consented"
down_revision = "qq001_dose_override"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("food_training_samples",
                    "image_retained", new_column_name="training_consented")


def downgrade() -> None:
    op.alter_column("food_training_samples",
                    "training_consented", new_column_name="image_retained")
