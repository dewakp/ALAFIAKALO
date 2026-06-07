"""Lab results schemas (EHR-compliant)."""

from datetime import date, datetime
from pydantic import BaseModel


class LabResultCreate(BaseModel):
    test_date: date
    test_name: str
    loinc_code: str | None = None
    category: str | None = None
    value: float | None = None
    value_string: str | None = None
    unit: str | None = None
    reference_range_low: float | None = None
    reference_range_high: float | None = None
    is_abnormal: bool | None = None
    status: str = "final"
    ordering_provider: str | None = None
    performing_lab: str | None = None
    notes: str | None = None


class LabResultUpdate(BaseModel):
    test_name: str | None = None
    loinc_code: str | None = None
    category: str | None = None
    value: float | None = None
    value_string: str | None = None
    unit: str | None = None
    reference_range_low: float | None = None
    reference_range_high: float | None = None
    is_abnormal: bool | None = None
    status: str | None = None
    ordering_provider: str | None = None
    performing_lab: str | None = None
    notes: str | None = None


class LabResultResponse(BaseModel):
    id: int
    user_id: int
    test_date: date
    test_name: str
    loinc_code: str | None = None
    category: str | None = None
    value: float | None = None
    value_string: str | None = None
    unit: str | None = None
    reference_range_low: float | None = None
    reference_range_high: float | None = None
    is_abnormal: bool | None = None
    status: str
    ordering_provider: str | None = None
    performing_lab: str | None = None
    notes: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
