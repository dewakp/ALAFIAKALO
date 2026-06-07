"""Insurance schemas."""

from datetime import date, datetime
from pydantic import BaseModel


class InsuranceCreate(BaseModel):
    region: str
    country_code: str
    country_name: str
    provider_code: str
    provider_name: str
    policy_number: str | None = None
    group_number: str | None = None
    member_id: str | None = None
    plan_name: str | None = None
    plan_type: str | None = None
    coverage_start: date | None = None
    coverage_end: date | None = None
    is_primary: bool = False
    is_active: bool = True
    subscriber_name: str | None = None
    subscriber_relationship: str | None = None
    insurance_phone: str | None = None
    notes: str | None = None


class InsuranceUpdate(BaseModel):
    region: str | None = None
    country_code: str | None = None
    country_name: str | None = None
    provider_code: str | None = None
    provider_name: str | None = None
    policy_number: str | None = None
    group_number: str | None = None
    member_id: str | None = None
    plan_name: str | None = None
    plan_type: str | None = None
    coverage_start: date | None = None
    coverage_end: date | None = None
    is_primary: bool | None = None
    is_active: bool | None = None
    subscriber_name: str | None = None
    subscriber_relationship: str | None = None
    insurance_phone: str | None = None
    notes: str | None = None


class InsuranceResponse(BaseModel):
    id: int
    user_id: int
    region: str
    country_code: str
    country_name: str
    provider_code: str
    provider_name: str
    policy_number: str | None = None
    group_number: str | None = None
    member_id: str | None = None
    plan_name: str | None = None
    plan_type: str | None = None
    coverage_start: date | None = None
    coverage_end: date | None = None
    is_primary: bool
    is_active: bool
    subscriber_name: str | None = None
    subscriber_relationship: str | None = None
    insurance_phone: str | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
