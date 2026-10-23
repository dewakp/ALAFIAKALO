# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""A photo the patient corrected is recalled, whatever the image consent.

2026-10-23: "When photo is reapplied and re-analyzed, all learning
disappeared." Production held the correction — sample 49, the patient's
"3 Pieces of Sardines, 2 Brioche Bread Slices …" with grams — and sample 50,
the same photo re-analysed, carried the SAME perceptual hash. Recall never
looked at it: it consulted corrected samples only after a match in
`labeled_food_images`, which is written only when the image itself is
retained, i.e. only with data-sharing consent. A hash is not the photo.
"""

import io
import uuid

import pytest
from httpx import AsyncClient
from PIL import Image

from app.models.food_training_sample import FoodTrainingSample
from app.models.user import User
from app.services import image_learning

pytestmark = pytest.mark.asyncio


def _photo() -> bytes:
    # Seeded noise: a smooth gradient hashes to 0, which would "match" any
    # other featureless image and prove nothing.
    import random
    rnd = random.Random(7)
    img = Image.new("RGB", (64, 48))
    for x in range(64):
        for y in range(48):
            img.putpixel((x, y), (rnd.randrange(256), rnd.randrange(256), rnd.randrange(256)))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


async def _token(client: AsyncClient, email: str) -> str:
    await client.post("/api/v1/auth/register", json={
        "email": email, "password": "SecureP@ss123", "full_name": "Recall User",
        "date_of_birth": "1990-01-01"})
    r = await client.post("/api/v1/auth/login", data={"username": email, "password": "SecureP@ss123"})
    return r.json()["access_token"]


async def test_a_corrected_photo_is_recalled_without_a_retained_image(client: AsyncClient, db, monkeypatch):
    email = f"rec{uuid.uuid4().hex[:6]}@example.com"
    token = await _token(client, email)
    from sqlalchemy import select
    user = (await db.execute(select(User).where(User.email == email))).scalar_one()
    photo = _photo()
    corrected = [{"name": "3 Pieces of Sardines", "estimated_grams": 100.0},
                 {"name": "2 Brioche Bread Slices", "estimated_grams": 60.0}]
    import datetime
    from app.services.food_vision_store import sha256_of
    h = image_learning.dhash(photo)
    assert h != 0, "fixture must have a real perceptual hash"
    db.add(FoodTrainingSample(user_id=user.id, image_sha256=sha256_of(photo), phash=str(h),
                              corrected_items=corrected, media_asset_id=None,
                              corrected_at=datetime.datetime.now(datetime.timezone.utc)))
    await db.commit()

    async def no_model(*a, **k):
        raise AssertionError("the model must not be asked about a photo the patient corrected")
    monkeypatch.setattr("app.services.alafia_model_service.alafia_infer", no_model)

    r = await client.post("/api/v1/ai/vision", headers={"Authorization": f"Bearer {token}"},
                          files={"file": ("IMG_0703.jpeg", photo, "image/jpeg")},
                          data={"task": "food_photo_nutrition"})

    assert r.status_code == 200, r.text
    names = [i["name"] for i in r.json()["items"]]
    assert names == ["3 Pieces of Sardines", "2 Brioche Bread Slices"]
