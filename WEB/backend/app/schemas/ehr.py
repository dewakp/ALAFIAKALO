"""EHR schemas (FHIR-only scaffolding)."""

from datetime import datetime
from pydantic import BaseModel, Field


class EHRConnectionBase(BaseModel):
    provider: str = Field(..., examples=["Epic", "Siemens", "Cerner"])
    fhir_base_url: str | None = None
    patient_id: str | None = None
    scopes: str | None = None
    notes: str | None = None


class EHRConnectionCreate(EHRConnectionBase):
    status: str | None = "pending"


class EHRConnectionUpdate(BaseModel):
    status: str | None = None
    fhir_base_url: str | None = None
    patient_id: str | None = None
    scopes: str | None = None
    notes: str | None = None
    last_sync_at: datetime | None = None


class EHRConnectionResponse(EHRConnectionBase):
    id: int
    status: str
    org_name: str | None = None
    last_sync_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
