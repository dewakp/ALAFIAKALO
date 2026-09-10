"""Turn whatever a phone camera produced into a small square avatar.

`profile_picture_url` has existed since the first migration and nothing ever
wrote to it, so every face in the app is initials on a coloured circle.

Phone photos are 3-12 MB and rotated by EXIF. Stored raw they would be the
largest column in the database and would arrive sideways. This normalises:
EXIF-rotate, centre-crop to square, resize, re-encode as JPEG.

S3 is NOT configured in production (zero S3_ env vars), so media already falls
back to base64 in the database. An avatar at this size is ~15 KB, which is
honest storage rather than a dependency nobody has provisioned.
"""

from __future__ import annotations

import base64
import io
import logging

logger = logging.getLogger(__name__)

#: Big enough for a retina 96px circle, small enough to sit on a row.
AVATAR_PX = 256
JPEG_QUALITY = 82

#: What a camera or file picker may hand us.
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}

#: Refused before decoding. A 12 MP photo is fine; a 60 MB file is not a face.
MAX_UPLOAD_BYTES = 15 * 1024 * 1024


class AvatarError(ValueError):
    """The upload could not be made into an avatar. The message is user-facing."""


def build_avatar(raw: bytes, content_type: str | None = None) -> str:
    """bytes -> a `data:image/jpeg;base64,...` string ready to store and render."""
    if not raw:
        raise AvatarError("That file was empty.")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise AvatarError("That image is too large — please choose one under 15 MB.")
    if content_type and content_type.lower() not in ALLOWED_TYPES:
        raise AvatarError("Please upload a photo (JPEG, PNG, WEBP or HEIC).")

    try:
        from PIL import Image, ImageOps
    except ImportError as exc:  # pragma: no cover
        raise AvatarError("Image processing is unavailable right now.") from exc

    try:
        img = Image.open(io.BytesIO(raw))
        # EXIF orientation, or every phone portrait arrives on its side.
        img = ImageOps.exif_transpose(img)
        # Centre-crop to square BEFORE resizing, so a portrait is not squashed.
        img = ImageOps.fit(img, (AVATAR_PX, AVATAR_PX), method=Image.LANCZOS,
                           centering=(0.5, 0.4))
        # 0.4 vertically: faces sit above centre in most photos.
        if img.mode not in ("RGB", "L"):
            # JPEG has no alpha; a transparent PNG would otherwise go black.
            background = Image.new("RGB", img.size, (255, 255, 255))
            rgba = img.convert("RGBA")
            background.paste(rgba, mask=rgba.split()[-1])
            img = background
        else:
            img = img.convert("RGB")
    except AvatarError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.info("avatar decode failed: %s", type(exc).__name__)
        raise AvatarError("That file could not be read as an image.") from exc

    out = io.BytesIO()
    img.save(out, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    encoded = base64.b64encode(out.getvalue()).decode()
    return f"data:image/jpeg;base64,{encoded}"
