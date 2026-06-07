"""Pantry item schemas."""

from datetime import date, datetime
from pydantic import BaseModel


class PantryItemCreate(BaseModel):
    name: str
    category: str = "other"
    quantity: float = 1.0
    unit: str = "pieces"
    location: str = "pantry"  # refrigerator, freezer, pantry
    expiration_date: date | None = None
    notes: str | None = None
    auto_replenish: bool = False
    low_threshold: float | None = None


class PantryItemUpdate(BaseModel):
    name: str | None = None
    category: str | None = None
    quantity: float | None = None
    unit: str | None = None
    location: str | None = None
    expiration_date: date | None = None
    notes: str | None = None
    auto_replenish: bool | None = None
    low_threshold: float | None = None


class PantryItemResponse(BaseModel):
    id: int
    user_id: int
    name: str
    category: str
    quantity: float
    unit: str
    location: str
    expiration_date: date | None = None
    notes: str | None = None
    auto_replenish: bool
    low_threshold: float | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
