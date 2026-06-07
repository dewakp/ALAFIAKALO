"""S3-compatible object storage service for media assets.

Supports AWS S3, Cloudflare R2, MinIO, or any S3-compatible provider.
Configure via environment variables:
  S3_BUCKET, S3_REGION, S3_ACCESS_KEY, S3_SECRET_KEY
  S3_ENDPOINT_URL  — leave blank for AWS; set for MinIO/R2
  S3_CDN_BASE_URL  — optional CloudFront/CDN prefix for served URLs
"""

from __future__ import annotations

import logging
import mimetypes
import uuid
from pathlib import PurePosixPath

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import settings

logger = logging.getLogger(__name__)

# Allowed MIME types for health media uploads
_ALLOWED_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
    "application/pdf",
}

_MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB


def _get_s3_client():
    kwargs: dict = {
        "region_name": settings.S3_REGION,
        "aws_access_key_id": settings.S3_ACCESS_KEY or None,
        "aws_secret_access_key": settings.S3_SECRET_KEY or None,
    }
    if settings.S3_ENDPOINT_URL:
        kwargs["endpoint_url"] = settings.S3_ENDPOINT_URL
    return boto3.client("s3", **kwargs)


def is_configured() -> bool:
    """Return True when S3 credentials and bucket are set."""
    return bool(settings.S3_BUCKET and settings.S3_ACCESS_KEY and settings.S3_SECRET_KEY)


def upload_media(
    data: bytes,
    content_type: str,
    user_id: int,
    category: str,
    original_filename: str | None = None,
) -> str:
    """Upload raw bytes to S3 and return the public URL.

    Raises ``ValueError`` for invalid MIME type or oversized files.
    Raises ``RuntimeError`` if S3 is not configured or the upload fails.
    """
    if not is_configured():
        raise RuntimeError("S3 is not configured — set S3_BUCKET, S3_ACCESS_KEY, S3_SECRET_KEY")

    # Validate MIME type at system boundary
    if content_type not in _ALLOWED_MIME_TYPES:
        raise ValueError(f"Unsupported media type: {content_type}")

    if len(data) > _MAX_FILE_SIZE:
        raise ValueError(f"File exceeds {_MAX_FILE_SIZE // (1024 * 1024)} MB limit")

    ext = mimetypes.guess_extension(content_type) or ".bin"
    if ext == ".jpe":
        ext = ".jpg"

    key = f"media/{user_id}/{category}/{uuid.uuid4().hex}{ext}"

    try:
        client = _get_s3_client()
        client.put_object(
            Bucket=settings.S3_BUCKET,
            Key=key,
            Body=data,
            ContentType=content_type,
            # Server-side encryption
            ServerSideEncryption="AES256",
        )
    except (BotoCoreError, ClientError) as exc:
        logger.error("S3 upload failed: %s", exc)
        raise RuntimeError(f"Upload failed: {exc}") from exc

    cdn = settings.S3_CDN_BASE_URL.rstrip("/")
    if cdn:
        return f"{cdn}/{key}"
    return f"https://{settings.S3_BUCKET}.s3.{settings.S3_REGION}.amazonaws.com/{key}"


def delete_media(storage_url: str) -> None:
    """Delete an object from S3 given its public URL. Fails silently on errors."""
    if not is_configured() or not storage_url:
        return
    try:
        # Extract the key from the URL
        cdn = settings.S3_CDN_BASE_URL.rstrip("/")
        if cdn and storage_url.startswith(cdn):
            key = storage_url[len(cdn) + 1:]
        else:
            # Parse from S3 URL: https://{bucket}.s3.{region}.amazonaws.com/{key}
            from urllib.parse import urlparse
            path = urlparse(storage_url).path.lstrip("/")
            key = path

        client = _get_s3_client()
        client.delete_object(Bucket=settings.S3_BUCKET, Key=key)
    except Exception as exc:
        logger.warning("S3 delete failed for %s: %s", storage_url, exc)
