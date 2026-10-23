# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""Meal photos were never kept: `media_assets.storage_url` did not exist.

Operator, 2026-10-23: *"Photo disappeared when reanalyzed"*, then *"images
consent cannot be on per image basis. that is unworkable and breaks the app"*.

Consent was not the cause. `food_vision_store` keeps a meal photo for the
patient's own record ALWAYS; the insert failed. Production's log, both
analyses of the reported meal:

    Could not retain meal photo; continuing without it
    UndefinedColumnError: column "storage_url" of relation "media_assets" does not exist

The model declares `storage_url`; `u001_media_s3_storage` adds it and sits in
the chain below head — and the column is absent from production AND from the
dev copy. The database was stamped past `u001` without running it, the drift §5
describes. So every meal photo insert has failed, which is why a photo vanished
from its meal and why recall had no image to match.

Idempotent on purpose (IF NOT EXISTS / nullability checked first): a database
that DID run `u001` must not fail here. Additive only (§3ao).
"""

import sqlalchemy as sa
from alembic import op

revision = "aw001_media_storage_url"
down_revision = "av001_reference_foods"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE media_assets ADD COLUMN IF NOT EXISTS storage_url VARCHAR(2048)")
    # u001 also made image_base64 nullable (a photo in object storage has no
    # inline copy); the model already declares it so.
    op.execute("ALTER TABLE media_assets ALTER COLUMN image_base64 DROP NOT NULL")


def downgrade() -> None:
    # Deliberately a no-op: dropping the column would discard stored photo
    # locations, and the column belongs to u001, below this revision.
    pass
