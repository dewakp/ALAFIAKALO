"""Peritoneal Dialysis schemas."""

from datetime import date, datetime
from pydantic import BaseModel


class PDExchangeBase(BaseModel):
    exchange_number: int
    start_time: str | None = None
    drain_start: str | None = None
    drain_end: str | None = None
    fill_end: str | None = None
    solution_type: str | None = None
    inflow_volume_ml: float | None = None
    outflow_volume_ml: float | None = None
    uf_ml: float | None = None
    dwell_time_minutes: int | None = None
    effluent_clarity: str | None = "clear"
    effluent_color: str | None = None
    notes: str | None = None


class PDExchangeCreate(PDExchangeBase):
    pass


class PDExchangeResponse(PDExchangeBase):
    id: int
    session_id: int
    model_config = {"from_attributes": True}


class PDSessionCreate(BaseModel):
    condition_id: int | None = None
    session_date: date
    modality: str = "capd"
    pre_weight_kg: float | None = None
    post_weight_kg: float | None = None
    target_uf_ml: float | None = None
    total_uf_ml: float | None = None
    pre_bp_systolic: int | None = None
    pre_bp_diastolic: int | None = None
    post_bp_systolic: int | None = None
    post_bp_diastolic: int | None = None
    pre_temp_f: float | None = None
    post_temp_f: float | None = None
    machine_type: str | None = None
    total_volume_ml: float | None = None
    fill_volume_ml: float | None = None
    number_of_cycles: int | None = None
    therapy_time_hours: float | None = None
    last_fill_volume_ml: float | None = None
    exit_site_status: str | None = None
    complications: str | None = None
    notes: str | None = None
    exchanges: list[PDExchangeCreate] = []


class PDSessionUpdate(BaseModel):
    modality: str | None = None
    pre_weight_kg: float | None = None
    post_weight_kg: float | None = None
    target_uf_ml: float | None = None
    total_uf_ml: float | None = None
    pre_bp_systolic: int | None = None
    pre_bp_diastolic: int | None = None
    post_bp_systolic: int | None = None
    post_bp_diastolic: int | None = None
    pre_temp_f: float | None = None
    post_temp_f: float | None = None
    machine_type: str | None = None
    total_volume_ml: float | None = None
    fill_volume_ml: float | None = None
    number_of_cycles: int | None = None
    therapy_time_hours: float | None = None
    last_fill_volume_ml: float | None = None
    exit_site_status: str | None = None
    complications: str | None = None
    notes: str | None = None


class PDSessionResponse(BaseModel):
    id: int
    user_id: int
    condition_id: int | None = None
    session_date: date
    modality: str
    pre_weight_kg: float | None = None
    post_weight_kg: float | None = None
    target_uf_ml: float | None = None
    total_uf_ml: float | None = None
    pre_bp_systolic: int | None = None
    pre_bp_diastolic: int | None = None
    post_bp_systolic: int | None = None
    post_bp_diastolic: int | None = None
    pre_temp_f: float | None = None
    post_temp_f: float | None = None
    machine_type: str | None = None
    total_volume_ml: float | None = None
    fill_volume_ml: float | None = None
    number_of_cycles: int | None = None
    therapy_time_hours: float | None = None
    last_fill_volume_ml: float | None = None
    exit_site_status: str | None = None
    complications: str | None = None
    notes: str | None = None
    exchanges: list[PDExchangeResponse] = []
    created_at: datetime
    model_config = {"from_attributes": True}
