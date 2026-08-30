"""Media capture endpoints — multipart upload to S3 with base64 fallback."""

from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.media import MediaAsset
from app.models.user import User
from app.schemas.media import MediaAssetCreate, MediaAssetResponse
from app.services import storage_service

router = APIRouter(prefix="/media", tags=["Media"])


@router.get("/", response_model=list[MediaAssetResponse])
async def list_media(
    category: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(MediaAsset).where(MediaAsset.user_id == current_user.id)
    if category:
        query = query.where(MediaAsset.category == category)
    if start_date:
        query = query.where(MediaAsset.captured_at >= start_date)
    if end_date:
        query = query.where(MediaAsset.captured_at <= end_date)

    query = query.order_by(MediaAsset.created_at.desc())
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{media_id}", response_model=MediaAssetResponse)
async def get_media(
    media_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """One stored asset, so a past meal can show the photo that was captured.

    Retention is pointless without retrieval: photos were being kept and there
    was no route that returned one — only list, create and delete. A patient
    opening last Tuesday's meal could not see the picture behind the numbers.

    Ownership is part of the lookup rather than a separate check, so another
    user's valid id is a 404 and never a disclosure. A clinician reading a
    shared record therefore does NOT come through here — they use
    `/clinician-dashboard/patient/{patient_id}/media/{media_id}`, which goes through
    `_permissions_for` so the access is authorized against the grant and the
    patient is told their chart was opened.
    """
    asset = (await db.execute(
        select(MediaAsset).where(
            MediaAsset.id == media_id,
            MediaAsset.user_id == current_user.id,
        )
    )).scalar_one_or_none()
    if asset is None:
        raise HTTPException(status_code=404, detail="Media not found")
    return asset


@router.post("/upload", response_model=MediaAssetResponse, status_code=status.HTTP_201_CREATED)
async def upload_media(
    file: UploadFile = File(...),
    category: str = Form(...),
    title: str | None = Form(None),
    notes: str | None = Form(None),
    captured_at: datetime | None = Form(None),
    source: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Multipart file upload — stored in S3 when configured, base64 fallback otherwise."""
    content_type = file.content_type or "application/octet-stream"
    raw = await file.read()

    storage_url: str | None = None
    image_base64: str | None = None

    if storage_service.is_configured():
        try:
            storage_url = storage_service.upload_media(
                data=raw,
                content_type=content_type,
                user_id=current_user.id,
                category=category,
                original_filename=file.filename,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc))
    else:
        # Fallback: base64 in DB (dev / unconfigured environments)
        import base64
        image_base64 = base64.b64encode(raw).decode()

    media = MediaAsset(
        user_id=current_user.id,
        category=category,
        title=title,
        notes=notes,
        captured_at=captured_at,
        content_type=content_type,
        file_name=file.filename,
        file_size_bytes=len(raw),
        image_base64=image_base64,
        storage_url=storage_url,
        source=source,
    )
    db.add(media)
    await db.flush()
    await db.refresh(media)
    return media


@router.post("/", response_model=MediaAssetResponse, status_code=status.HTTP_201_CREATED)
async def create_media_legacy(
    payload: MediaAssetCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Legacy JSON/base64 endpoint — kept for backwards compatibility with older clients."""
    if not payload.image_base64:
        raise HTTPException(status_code=400, detail="Image is required (use /upload for multipart)")

    media = MediaAsset(
        user_id=current_user.id,
        category=payload.category,
        title=payload.title,
        notes=payload.notes,
        captured_at=payload.captured_at,
        content_type=payload.content_type,
        file_name=payload.file_name,
        file_size_bytes=payload.file_size_bytes,
        image_base64=payload.image_base64,
        storage_url=None,
        source=payload.source,
    )
    db.add(media)
    await db.flush()
    await db.refresh(media)
    return media


@router.delete("/{media_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_media(
    media_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(MediaAsset).where(
            MediaAsset.id == media_id,
            MediaAsset.user_id == current_user.id,
        )
    )
    media = result.scalar_one_or_none()
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")

    # Remove from object storage if applicable
    if media.storage_url:
        storage_service.delete_media(media.storage_url)

    await db.delete(media)
    return None
