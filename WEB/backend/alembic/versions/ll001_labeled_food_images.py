"""Visual memory: user-labeled food photos (perceptual hash + ground truth).

Stores dHash + the corrected food list per user — repeat meals are identified
from the user's own labels before consulting the vision model. Also the
training corpus for the Phase-5 on-device food classifier.
"""

from alembic import op
import sqlalchemy as sa

revision = "ll001_labeled_food_images"
down_revision = "kk001_ehr_smart_fhir"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "labeled_food_images",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("phash", sa.String(32), nullable=False, index=True),
        sa.Column("labels", sa.Text(), nullable=False),
        sa.Column("source", sa.String(20), nullable=False, server_default="user"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_table("labeled_food_images")
