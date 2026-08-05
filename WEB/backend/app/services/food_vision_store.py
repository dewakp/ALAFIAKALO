"""Persist meal photos, model predictions, and user corrections.

Phase 5 (an on-device food classifier) needs a labelled corpus. Nothing was
collecting one — the label path hashed each photo and discarded the bytes, and
the `/ai/vision` path recorded nothing at all, so every user correction was
thrown away the moment the meal was saved.

This module closes both gaps:

  record_prediction()  every analysis becomes a sample (photo kept if consented)
  record_correction()  the user's edit becomes the ground-truth half of the pair

Consent: images are retained only when the user has enabled
`PrivacySettings.allow_collective_insights` ("cross-user AI learning", off by
default). Without it the sample is still written — accuracy can be measured
without keeping anyone's photo — but no image is stored.
"""

from __future__ import annotations

import base64
import hashlib
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.food_training_sample import FoodTrainingSample
from app.models.media import MediaAsset
from app.models.privacy import PrivacySettings

logger = logging.getLogger(__name__)

TRAINING_CATEGORY = "food_training"
# Refuse absurd payloads outright rather than filling the DB with them.
MAX_RETAINED_BYTES = 8 * 1024 * 1024


def sha256_of(image_bytes: bytes) -> str:
    return hashlib.sha256(image_bytes).hexdigest()


async def may_retain_images(db: AsyncSession, user_id: int) -> bool:
    """True when this user has opted into cross-user AI learning.

    Defaults to False: absent settings means no consent on record, and a meal
    photo is health data. Never retain by default.
    """
    row = (await db.execute(
        select(PrivacySettings).where(PrivacySettings.user_id == user_id)
    )).scalar_one_or_none()
    return bool(row and row.allow_collective_insights)


async def _store_image(
    db: AsyncSession, user_id: int, image_bytes: bytes, content_type: str,
) -> MediaAsset | None:
    """Persist one photo as a MediaAsset, or None if it is unusable."""
    if not image_bytes or len(image_bytes) > MAX_RETAINED_BYTES:
        return None
    asset = MediaAsset(
        user_id=user_id,
        category=TRAINING_CATEGORY,
        title="Meal photo (training)",
        content_type=content_type or "image/jpeg",
        file_size_bytes=len(image_bytes),
        # TODO(media): move to GCS and store storage_url instead once the media
        # bucket is provisioned; image_base64 keeps the corpus intact until then.
        image_base64=base64.b64encode(image_bytes).decode("ascii"),
        source="food_vision",
        captured_at=datetime.now(timezone.utc),
    )
    db.add(asset)
    await db.flush()
    return asset


async def record_prediction(
    db: AsyncSession,
    user_id: int,
    images: list[tuple[bytes, str]],
    *,
    source_model: str | None,
    items: list[dict] | None,
    nutrition: dict | None = None,
    notes: str | None = None,
    phash: str | None = None,
) -> FoodTrainingSample | None:
    """Record one analysis. Returns the sample so the client can correct it.

    Only the FIRST photo is retained when several shots of one plate were sent —
    they are near-duplicates, and keeping all three triples storage for almost no
    training signal.

    Never raises: a failure to log training data must not fail the user's meal
    analysis. Returns None if it could not record.
    """
    if not images:
        return None

    first_bytes, first_type = images[0]
    digest = sha256_of(first_bytes)

    # Retention and sample-writing each run inside their own SAVEPOINT.
    #
    # Catching the exception is NOT enough: a failed flush leaves the session in
    # a "pending rollback" state, so the caller's later commit() raises and the
    # user's analysis 500s — logging training data would take down the feature it
    # was meant to support. A nested transaction rolls back only the failed part
    # and leaves the outer transaction usable.
    asset_id = None
    try:
        if await may_retain_images(db, user_id):
            async with db.begin_nested():
                asset = await _store_image(db, user_id, first_bytes, first_type)
                asset_id = asset.id if asset else None
    except Exception:
        logger.exception("Could not retain meal photo; continuing without it")
        asset_id = None

    try:
        async with db.begin_nested():
            sample = FoodTrainingSample(
                user_id=user_id,
                image_sha256=digest,
                phash=phash,
                media_asset_id=asset_id,
                image_retained=asset_id is not None,
                image_count=len(images),
                source_model=source_model,
                predicted_items=items or [],
                predicted_nutrition=nutrition or {},
                notes=(notes or None),
            )
            db.add(sample)
            await db.flush()
        await db.refresh(sample)
        return sample
    except Exception:
        logger.exception("Failed to record food-vision training sample")
        return None


def _classify_correction(predicted: list[dict] | None, corrected: list[dict]) -> str:
    """What did the user actually change — the foods, the amounts, or nothing?

    This is the label that makes the corpus queryable: "show me every photo
    where the model named the wrong food" is the set worth retraining on.
    """
    pred = predicted or []

    def by_name(rows) -> dict[str, float | None]:
        """Index grams by normalised food name.

        Keyed rather than positional: the user retyping the same foods in a
        different order is not a correction, and comparing two lists index-by-
        index would call it one — mislabelling most of the corpus as "both".
        """
        out: dict[str, float | None] = {}
        for row in rows or []:
            name = str(row.get("name") or "").strip().lower()
            if not name:
                continue
            grams = row.get("estimated_grams")
            try:
                out[name] = float(grams) if grams is not None else None
            except (TypeError, ValueError):
                out[name] = None
        return out

    before, after = by_name(pred), by_name(corrected)
    items_changed = set(before) != set(after)

    # Quantity is judged ONLY on foods present on both sides. A dropped or added
    # item is an item-level change; counting its missing grams as a quantity
    # change too would make every item edit look like "both".
    shared = set(before) & set(after)
    qty_changed = any(before[name] != after[name] for name in shared)

    if items_changed and qty_changed:
        return "both"
    if items_changed:
        return "item"
    if qty_changed:
        return "quantity"
    return "accepted"


async def record_correction(
    db: AsyncSession,
    user_id: int,
    sample_id: int,
    corrected_items: list[dict],
    notes: str | None = None,
) -> FoodTrainingSample | None:
    """Attach the user's ground truth to a prediction.

    Scoped to the owning user — a sample id from someone else's meal is simply
    not found rather than editable.
    """
    sample = (await db.execute(
        select(FoodTrainingSample).where(
            FoodTrainingSample.id == sample_id,
            FoodTrainingSample.user_id == user_id,
        )
    )).scalar_one_or_none()
    if sample is None:
        return None

    cleaned: list[dict] = []
    for row in corrected_items or []:
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        grams = row.get("estimated_grams", row.get("grams"))
        try:
            grams = float(grams) if grams is not None else None
        except (TypeError, ValueError):
            grams = None
        cleaned.append({
            "name": name[:200],
            "estimated_portion": (str(row.get("estimated_portion"))[:120]
                                  if row.get("estimated_portion") else None),
            "estimated_grams": grams,
        })

    sample.corrected_items = cleaned
    sample.correction_kind = _classify_correction(sample.predicted_items, cleaned)
    sample.corrected_at = datetime.now(timezone.utc)
    if notes:
        sample.notes = notes[:1000]
    await db.flush()
    await db.refresh(sample)
    return sample


async def corpus_stats(db: AsyncSession) -> dict:
    """How much training data actually exists — the Phase 5 readiness number."""
    from sqlalchemy import func

    total, retained, corrected, users = (await db.execute(
        select(
            func.count(FoodTrainingSample.id),
            func.count().filter(FoodTrainingSample.image_retained.is_(True)),
            func.count().filter(FoodTrainingSample.corrected_items.isnot(None)),
            func.count(func.distinct(FoodTrainingSample.user_id)),
        )
    )).one()
    by_kind = dict((await db.execute(
        select(FoodTrainingSample.correction_kind, func.count())
        .group_by(FoodTrainingSample.correction_kind)
    )).all())
    return {
        "samples": total or 0,
        "images_retained": retained or 0,
        "corrected": corrected or 0,
        "contributing_users": users or 0,
        "by_correction_kind": by_kind,
    }
