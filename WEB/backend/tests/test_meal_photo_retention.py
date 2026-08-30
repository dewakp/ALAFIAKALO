"""A retained meal photo must be retrievable, and only by its owner.

Two halves of one decision. Consent
(`PrivacySettings.allow_collective_insights`) governs whether a photo may TRAIN
a shared model — it was never meant to govern whether the patient keeps the
picture of their own meal. Previously an account without that opt-in had its
photo discarded, so opening last Tuesday's entry showed numbers with no way to
see what produced them, for patient and clinician alike.

The other half is that retention without retrieval is pointless: photos were
being stored while `media` exposed only list, create and delete. There was no
route that returned one.
"""

import pytest
from sqlalchemy import select

from app.models.food_training_sample import FoodTrainingSample
from app.models.media import MediaAsset
from app.models.user import User
from app.services import food_vision_store


async def _user(db, email: str) -> User:
    u = User(email=email, hashed_password="x", full_name="Test User")
    db.add(u)
    await db.flush()
    return u


@pytest.mark.asyncio
async def test_photo_is_kept_without_training_consent(db):
    """No opt-in still keeps the patient's own picture — it just can't train."""
    user = await _user(db, "photo-noconsent@example.com")

    sample = await food_vision_store.record_prediction(
        db, user.id, [(b"\xff\xd8fake-jpeg", "image/jpeg")],
        source_model="test", items=[{"name": "jollof rice"}],
    )
    await db.flush()

    assert sample is not None
    # Stored: the meal keeps its photo.
    assert sample.media_asset_id is not None
    # But not corpus material — that is what consent buys.
    assert sample.training_consented is False

    asset = (await db.execute(
        select(MediaAsset).where(MediaAsset.id == sample.media_asset_id)
    )).scalar_one()
    assert asset.image_base64
    assert asset.category == food_vision_store.MEAL_CATEGORY


@pytest.mark.asyncio
async def test_owner_can_fetch_the_photo(client, db):
    from app.core.security import get_current_user
    from app.main import app

    user = await _user(db, "photo-owner@example.com")
    sample = await food_vision_store.record_prediction(
        db, user.id, [(b"\xff\xd8fake-jpeg", "image/jpeg")],
        source_model="test", items=[{"name": "egusi"}],
    )
    await db.commit()

    app.dependency_overrides[get_current_user] = lambda: user
    try:
        resp = await client.get(f"/api/v1/media/{sample.media_asset_id}")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["id"] == sample.media_asset_id
        # Enough to render: the client builds a data URI from these.
        assert body["image_base64"]
        assert body["content_type"] == "image/jpeg"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_another_users_photo_is_not_found(client, db):
    """A valid id belonging to someone else is a 404, never a disclosure."""
    from app.core.security import get_current_user
    from app.main import app

    owner = await _user(db, "photo-a@example.com")
    stranger = await _user(db, "photo-b@example.com")
    sample = await food_vision_store.record_prediction(
        db, owner.id, [(b"\xff\xd8fake-jpeg", "image/jpeg")],
        source_model="test", items=[{"name": "pounded yam"}],
    )
    await db.commit()

    app.dependency_overrides[get_current_user] = lambda: stranger
    try:
        resp = await client.get(f"/api/v1/media/{sample.media_asset_id}")
        assert resp.status_code == 404, resp.text
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_missing_photo_is_404(client, db):
    from app.core.security import get_current_user
    from app.main import app

    user = await _user(db, "photo-missing@example.com")
    await db.commit()

    app.dependency_overrides[get_current_user] = lambda: user
    try:
        resp = await client.get("/api/v1/media/99999999")
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_sample_is_still_recorded_when_the_photo_cannot_be_stored(db, monkeypatch):
    """A storage failure must never cost the user their analysis."""
    user = await _user(db, "photo-fail@example.com")

    async def boom(*a, **kw):
        raise RuntimeError("object store down")

    monkeypatch.setattr(food_vision_store, "_store_image", boom)

    sample = await food_vision_store.record_prediction(
        db, user.id, [(b"\xff\xd8fake-jpeg", "image/jpeg")],
        source_model="test", items=[{"name": "suya"}],
    )
    await db.flush()

    assert sample is not None
    assert sample.media_asset_id is None
    assert sample.training_consented is False


@pytest.mark.asyncio
async def test_clinician_with_a_nutrition_grant_sees_the_photo(client, db):
    """The other half of the ask: a shared record shows its meal pictures."""
    from app.core.security import get_current_user
    from app.main import app
    from app.models.data_sharing import DataGrant

    patient = await _user(db, "photo-patient@example.com")
    clinician = await _user(db, "photo-doc@example.com")
    sample = await food_vision_store.record_prediction(
        db, patient.id, [(b"\xff\xd8fake-jpeg", "image/jpeg")],
        source_model="test", items=[{"name": "moi moi"}],
    )
    db.add(DataGrant(owner_id=patient.id, grantee_user_id=clinician.id,
                     data_type="nutrition", is_active=True))
    await db.commit()

    app.dependency_overrides[get_current_user] = lambda: clinician
    try:
        resp = await client.get(
            f"/api/v1/clinician-dashboard/patient/{patient.id}/media/{sample.media_asset_id}")
        assert resp.status_code == 200, resp.text
        assert resp.json()["image_base64"]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_a_labs_only_grant_does_not_reach_meal_photos(client, db):
    """A grant is per-category; sharing labs never hands over food pictures."""
    from app.core.security import get_current_user
    from app.main import app
    from app.models.data_sharing import DataGrant

    patient = await _user(db, "photo-patient2@example.com")
    clinician = await _user(db, "photo-doc2@example.com")
    sample = await food_vision_store.record_prediction(
        db, patient.id, [(b"\xff\xd8fake-jpeg", "image/jpeg")],
        source_model="test", items=[{"name": "akara"}],
    )
    db.add(DataGrant(owner_id=patient.id, grantee_user_id=clinician.id,
                     data_type="labs", is_active=True))
    await db.commit()

    app.dependency_overrides[get_current_user] = lambda: clinician
    try:
        resp = await client.get(
            f"/api/v1/clinician-dashboard/patient/{patient.id}/media/{sample.media_asset_id}")
        assert resp.status_code == 403, resp.text
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_no_grant_at_all_is_refused(client, db):
    from app.core.security import get_current_user
    from app.main import app

    patient = await _user(db, "photo-patient3@example.com")
    stranger = await _user(db, "photo-stranger@example.com")
    sample = await food_vision_store.record_prediction(
        db, patient.id, [(b"\xff\xd8fake-jpeg", "image/jpeg")],
        source_model="test", items=[{"name": "efo riro"}],
    )
    await db.commit()

    app.dependency_overrides[get_current_user] = lambda: stranger
    try:
        resp = await client.get(
            f"/api/v1/clinician-dashboard/patient/{patient.id}/media/{sample.media_asset_id}")
        assert resp.status_code == 403, resp.text
    finally:
        app.dependency_overrides.clear()
