"""Pantry CRUD endpoints.

TODO (Future): Integrate with third-party grocer APIs (Instacart, Kroger,
Walmart, Amazon Fresh, etc.) to enable automatic replenishment when pantry
items drop below `low_threshold`.  The `auto_replenish` and `low_threshold`
fields are already wired into the model — a scheduler job would periodically
check quantities and push orders through the grocer's API.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.pantry import PantryItem
from app.schemas.pantry import PantryItemCreate, PantryItemUpdate, PantryItemResponse

router = APIRouter()


@router.get("/", response_model=list[PantryItemResponse])
async def list_pantry_items(
    location: str | None = Query(None, description="Filter by location: refrigerator, freezer, pantry"),
    category: str | None = Query(None, description="Filter by category"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(PantryItem).where(PantryItem.user_id == current_user.id)
    if location:
        query = query.where(PantryItem.location == location)
    if category:
        query = query.where(PantryItem.category == category)
    query = query.order_by(PantryItem.name)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/", response_model=PantryItemResponse, status_code=201)
async def create_pantry_item(
    item_in: PantryItemCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    item = PantryItem(**item_in.model_dump(), user_id=current_user.id)
    db.add(item)
    await db.flush()
    await db.refresh(item)
    await db.commit()
    return item


@router.put("/{item_id}", response_model=PantryItemResponse)
async def update_pantry_item(
    item_id: int,
    item_in: PantryItemUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PantryItem).where(PantryItem.id == item_id, PantryItem.user_id == current_user.id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(404, "Pantry item not found")
    for field, value in item_in.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    await db.flush()
    await db.refresh(item)
    await db.commit()
    return item


@router.delete("/{item_id}", status_code=204)
async def delete_pantry_item(
    item_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PantryItem).where(PantryItem.id == item_id, PantryItem.user_id == current_user.id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(404, "Pantry item not found")
    await db.delete(item)
    await db.commit()
