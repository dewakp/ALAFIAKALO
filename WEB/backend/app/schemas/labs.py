"""Lab results schemas (EHR-compliant)."""

from datetime import date, datetime
from pydantic import BaseModel, computed_field

from app.services.docparse.dictionaries import display_name as analyte_display_name


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

    @computed_field
    @property
    def display_name(self) -> str:
        """The analyte's name ("ALP" is Alkaline Phosphatase). `test_name` stays
        the report's own wording; the server decides what it means, not each client."""
        return analyte_display_name(self.test_name)
