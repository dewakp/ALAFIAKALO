"""A small thumbnail kept with the meal itself.

Additive only (canon §3ao): one nullable column, no drops.

Why not reuse `food_image_uris`: that holds the FULL photo in media storage and
is only written when the patient runs "Analyse Image(s) with Alafia". Choose a
photo and save without analysing and nothing is kept at all — the log shows a
filename while it is being typed and then nothing afterwards, so a patient
cannot tell which meal the picture belonged to.

Why a data URI rather than another media row: this renders in a LIST. Fetching
each photo through `/media/{id}` is one authenticated round-trip per row, and
the stored photo is the full-size original — megabytes, to draw something 48 px
wide. The thumbnail is generated client-side at ~96 px and lands at a few KB,
so a page of meals costs no extra requests at all.

It is the patient's own photo on the patient's own record, shown back only to
them. It is NOT the training corpus: retention for training stays gated on
`PrivacySettings.allow_collective_insights` (§3a) and is unaffected by this.

Revision ID: af001_meal_thumbnail
Revises: ae001_saline_machine_time
"""
from alembic import op
import sqlalchemy as sa

revision = "af001_meal_thumbnail"
down_revision = "ae001_saline_machine_time"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("nutrition_logs",
                  sa.Column("food_thumbnail", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("nutrition_logs", "food_thumbnail")
