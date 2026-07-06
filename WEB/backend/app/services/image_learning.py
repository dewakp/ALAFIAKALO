"""Visual memory for labeled food photos.

Users teach ALAFIA what a photo actually contained; we store a perceptual hash
(dHash, 64-bit) of the image with the corrected food list. New photos are
matched against the user's own labeled set by Hamming distance — repeat meals
(the common case) are then identified from the user's ground truth instead of
the vision model. The labeled set doubles as the training corpus for the
planned on-device food classifier (ALAFIAModel Phase 5).

Hashes, not photos, are stored — no image bytes are retained.
"""

import io
import logging
from datetime import datetime, timezone

from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.image_label import LabeledFoodImage

logger = logging.getLogger(__name__)

# Hamming distance (out of 64 bits) at or below which two photos are
# considered the same meal. 10 tolerates re-shots (angle/lighting) while
# keeping distinct dishes apart.
MATCH_THRESHOLD = 10


def dhash(image_bytes: bytes) -> int:
    """64-bit difference hash: 9×8 grayscale, horizontal gradient signs."""
    img = Image.open(io.BytesIO(image_bytes)).convert("L").resize((9, 8), Image.LANCZOS)
    px = list(img.getdata())
    bits = 0
    for row in range(8):
        for col in range(8):
            left = px[row * 9 + col]
            right = px[row * 9 + col + 1]
            bits = (bits << 1) | (1 if left > right else 0)
    return bits


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


async def find_learned_match(
    db: AsyncSession, user_id: int, image_bytes: bytes,
    max_distance: int = MATCH_THRESHOLD,
) -> LabeledFoodImage | None:
    """Best labeled image of this user within the Hamming threshold."""
    try:
        h = dhash(image_bytes)
    except Exception as e:
        logger.warning("dhash failed: %s", e)
        return None
    rows = (await db.execute(
        select(LabeledFoodImage).where(LabeledFoodImage.user_id == user_id)
    )).scalars().all()
    best, best_d = None, max_distance + 1
    for row in rows:
        d = hamming(h, int(row.phash))
        if d < best_d:
            best, best_d = row, d
    return best


async def save_label(
    db: AsyncSession, user_id: int, image_bytes: bytes, labels: str,
) -> LabeledFoodImage:
    """Store (or update) the user's ground-truth label for a photo."""
    h = dhash(image_bytes)
    existing = await find_learned_match(db, user_id, image_bytes)
    if existing is not None:
        existing.labels = labels
        existing.phash = str(h)   # re-center on the latest shot
        existing.updated_at = datetime.now(timezone.utc)
        await db.flush()
        return existing
    row = LabeledFoodImage(user_id=user_id, phash=str(h), labels=labels)
    db.add(row)
    await db.flush()
    await db.refresh(row)
    return row
