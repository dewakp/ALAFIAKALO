"""Advanced Directives schemas."""

from datetime import datetime
from pydantic import BaseModel


class AdvancedDirectiveCreate(BaseModel):
    primary_agent_name: str | None = None
    primary_agent_relationship: str | None = None
    primary_agent_phone: str | None = None
    primary_agent_email: str | None = None
    primary_agent_address: str | None = None
    alternate_agent_name: str | None = None
    alternate_agent_relationship: str | None = None
    alternate_agent_phone: str | None = None
    alternate_agent_email: str | None = None
    alternate_agent_address: str | None = None
    organ_donation_preference: str | None = None
    specific_organs_to_donate: str | None = None
    specific_organs_not_to_donate: str | None = None
    life_support_preference: str | None = None
    cpr_preference: str | None = None
    ventilator_preference: str | None = None
    feeding_tube_preference: str | None = None
    dialysis_preference: str | None = None
    blood_transfusion_preference: str | None = None
    additional_instructions: str | None = None
    document_signed: bool | None = False
    document_date: str | None = None
    witness_name: str | None = None
    notarized: bool | None = False
    document_location: str | None = None


class AdvancedDirectiveUpdate(AdvancedDirectiveCreate):
    pass


class AdvancedDirectiveResponse(BaseModel):
    id: int
    user_id: int
    primary_agent_name: str | None = None
    primary_agent_relationship: str | None = None
    primary_agent_phone: str | None = None
    primary_agent_email: str | None = None
    primary_agent_address: str | None = None
    alternate_agent_name: str | None = None
    alternate_agent_relationship: str | None = None
    alternate_agent_phone: str | None = None
    alternate_agent_email: str | None = None
    alternate_agent_address: str | None = None
    organ_donation_preference: str | None = None
    specific_organs_to_donate: str | None = None
    specific_organs_not_to_donate: str | None = None
    life_support_preference: str | None = None
    cpr_preference: str | None = None
    ventilator_preference: str | None = None
    feeding_tube_preference: str | None = None
    dialysis_preference: str | None = None
    blood_transfusion_preference: str | None = None
    additional_instructions: str | None = None
    document_signed: bool | None = None
    document_date: str | None = None
    witness_name: str | None = None
    notarized: bool | None = None
    document_location: str | None = None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}
