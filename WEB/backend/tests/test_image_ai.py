"""Tests for Image AI: caption cleanup, dual-input reading, auth gates."""

import base64

import pytest
from httpx import AsyncClient

from app.api.image_ai import _clean_caption as _clean
from app.api.image_ai import _NON_FOOD_TOKENS


def test_caption_cleanup_strips_lead_in_and_qualifiers():
    assert _clean("The plate contains rice and a piece of meat, possibly chicken.") == "rice, meat"
    assert _clean("The image shows a bowl of soup, probably vegetable broth.") == "soup"
    assert _clean("There are eggs and toast.") == "eggs, toast"


def test_caption_cleanup_drops_or_alternatives():
    # "chicken or fish" must not be priced as chicken AND "or fish"
    assert _clean("rice, chicken or fish, and vegetables") == "rice, chicken, vegetables"
    assert _clean("The plate contains rice and meat, possibly chicken or pork.") == "rice, meat"


def test_caption_cleanup_drops_scene_sentences():
    assert _clean("Rice and grilled chicken. A fork is placed next to the plate.") == "Rice, grilled chicken"


def test_caption_cleanup_keeps_plain_lists():
    assert _clean("jollof rice, fried plantain, grilled fish") == "jollof rice, fried plantain, grilled fish"


def test_non_food_tokens_cover_conjunctions():
    # The component-level leakage guard must reject bare conjunctions —
    # these previously got priced by the AI fallback ("and": 47 kcal).
    for token in ("and", "or", "with", "fork", "plate"):
        assert token in _NON_FOOD_TOKENS


@pytest.mark.asyncio
@pytest.mark.parametrize("path", [
    "/api/v1/image-ai/nutrition-from-image",
    "/api/v1/image-ai/medication-from-image",
])
async def test_image_endpoints_require_auth(client: AsyncClient, path):
    b64 = base64.b64encode(b"notreallyanimage").decode()
    r = await client.post(path, json={"image_base64": b64})
    assert r.status_code == 401


# ── Elimination / symptom extraction (pure functions) ────────────────────

from app.api.image_ai import _extract_elimination


def test_extract_bowel_bristol_and_flags():
    s, flags = _extract_elimination("bowel", "The stool appears soft and brown with visible mucus.")
    assert s["bristol_scale"] == 5 and s["consistency"] == "soft"
    assert s["color"] == "brown"
    assert s.get("mucus_present") is True
    assert not any("blood" in f.lower() for f in flags)


def test_extract_bowel_blood_flagged():
    s, flags = _extract_elimination("bowel", "Liquid, watery stool with red streaks of blood.")
    assert s["bristol_scale"] == 7
    assert s.get("blood_present") is True
    assert any("blood" in f.lower() for f in flags)


def test_extract_urine_red_flagged():
    s, flags = _extract_elimination("urination", "The urine is red and cloudy.")
    assert s["color"] == "red"
    assert any("blood" in f.lower() for f in flags)
    assert any("cloudy" in f.lower() for f in flags)


def test_extract_negations_not_flagged():
    s, flags = _extract_elimination("bowel", "Formed brown stool, no blood or mucus visible.")
    assert s.get("blood_present") is None
    assert not flags


@pytest.mark.asyncio
@pytest.mark.parametrize("path", [
    "/api/v1/image-ai/elimination-from-image",
    "/api/v1/image-ai/symptom-from-image",
])
async def test_new_image_endpoints_require_auth(client: AsyncClient, path):
    r = await client.post(path, json={"image_base64": "aGVsbG8="})
    assert r.status_code == 401


# ── Sentence-fragment guard (the "vegetables. there is chicken" bug) ─────

from app.api.image_ai import _plausible_food_name


def test_plausible_food_names_accepted():
    for name in ("rice", "grilled chicken", "fried plantain", "jollof rice",
                 "egusi soup", "meat"):
        assert _plausible_food_name(name), name


def test_sentence_fragments_rejected():
    for name in (
        "vegetables. there is chicken",
        "along with sliced bananas (, which can be used as an alternative to rice",
        "the combination of these ingredients creates a flavorful, nutritious meal",
        "and", "or fish", "with sauce on top of it all day",
        "a flavorful, nutritious meal option for those who enjoy dining",
    ):
        # every one of these previously appeared as a priced row
        assert not _plausible_food_name(name), name


# ── Visual memory (labeled food images) ──────────────────────────────────

import io
from PIL import Image as PILImage

from app.services.image_learning import dhash, hamming, MATCH_THRESHOLD


def _img_bytes(color, size=(64, 64), noise=0):
    img = PILImage.new("RGB", size, color)
    if noise:
        px = img.load()
        for x in range(0, size[0], 7):
            for y in range(0, size[1], 7):
                px[x, y] = ((color[0] + noise) % 256, color[1], color[2])
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _gradient_bytes(flip=False, tweak=0):
    img = PILImage.new("L", (64, 64))
    px = img.load()
    for x in range(64):
        for y in range(64):
            v = (63 - x if flip else x) * 4
            px[x, y] = min(255, v + (tweak if (x + y) % 9 == 0 else 0))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG")
    return buf.getvalue()


def test_dhash_stable_and_discriminative():
    a1 = dhash(_gradient_bytes())
    a2 = dhash(_gradient_bytes(tweak=12))     # same scene, slight change
    b = dhash(_gradient_bytes(flip=True))     # different scene
    assert hamming(a1, a1) == 0
    assert hamming(a1, a2) <= MATCH_THRESHOLD
    assert hamming(a1, b) > MATCH_THRESHOLD


@pytest.mark.asyncio
async def test_label_endpoint_requires_auth(client: AsyncClient):
    r = await client.post("/api/v1/image-ai/label",
                          json={"image_base64": "aGVsbG8=", "foods": "rice"})
    assert r.status_code == 401
