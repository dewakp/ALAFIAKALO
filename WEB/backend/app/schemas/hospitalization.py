# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""Hospital stays and surgical procedures — request/response shapes.

Two canon rules decide the structure here.

**Plausibility belongs on CREATE, never on a response.** `TherapySessionBase`
carried weight checks and the response model inherited them, so one
implausible row already in the record turned a patient's whole history into a
500 that the screen rendered as "no sessions found" (§3at). So the checks live
on `*Create` only: what they refuse on the way in is unchanged, and nothing we
have already stored can ever become unreadable.

**Naive UTC is enforced here, not in each route.** `admitted_at`,
`discharged_at` and `performed_at` are `timestamp WITHOUT time zone`, while a
browser sends `new Date().toISOString()` ending in `Z`, which FastAPI parses as
tz-AWARE. Comparing the two makes asyncpg raise DataError, the endpoint 500s,
and the page shows an empty state (§3aa). `api/chronic_conditions.py` fixes
this with a `_naive_utc()` the caller must remember; putting the conversion in
the validator means a route added later cannot forget it.
"""

from datetime import datetime, timezone

from pydantic import BaseModel, field_validator, model_validator

from app.models.hospitalization import (AdmissionStatus, AdmissionType,
                                        ProcedureOutcome)


def _naive_utc(value: datetime | None) -> datetime | None:
    """Aware → UTC → naive. A naive value is passed through untouched."""
    if value is None or value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


# ── Surgical procedure ───────────────────────────────────────────────────────

class SurgicalProcedureBase(BaseModel):
    name: str
    #: The code AS GIVEN, with the vocabulary that issued it. Never normalised
    #: between systems: ICD-10-PCS, ICHI, CPT and SNOMED are different
    #: vocabularies under different licences (§3ad).
    code: str | None = None
    code_system: str | None = None
    body_site: str | None = None
    laterality: str | None = None
    performed_at: datetime | None = None
    hospitalization_id: int | None = None
    facility_id: int | None = None
    facility_name: str | None = None
    surgeon: str | None = None
    anesthesia_type: str | None = None
    outcome: ProcedureOutcome | None = None
    complications: str | None = None
    #: The lasting consequence, in words. The field a nutrient target or an AI
    #: answer actually needs — and the one thing no import can derive, because
    #: deriving it from a procedure name invents a clinical fact (§0).
    ongoing_effects: str | None = None
    source: str | None = None
    external_ref: str | None = None
    notes: str | None = None


class SurgicalProcedureCreate(SurgicalProcedureBase):
    @field_validator("performed_at")
    @classmethod
    def _naive(cls, v: datetime | None) -> datetime | None:
        return _naive_utc(v)

    @field_validator("name")
    @classmethod
    def _named(cls, v: str) -> str:
        if not (v or "").strip():
            raise ValueError("A procedure needs a name.")
        return v.strip()


class SurgicalProcedureUpdate(BaseModel):
    name: str | None = None
    code: str | None = None
    code_system: str | None = None
    body_site: str | None = None
    laterality: str | None = None
    performed_at: datetime | None = None
    hospitalization_id: int | None = None
    facility_id: int | None = None
    facility_name: str | None = None
    surgeon: str | None = None
    anesthesia_type: str | None = None
    outcome: ProcedureOutcome | None = None
    complications: str | None = None
    ongoing_effects: str | None = None
    notes: str | None = None

    @field_validator("performed_at")
    @classmethod
    def _naive(cls, v: datetime | None) -> datetime | None:
        return _naive_utc(v)


class SurgicalProcedureResponse(SurgicalProcedureBase):
    id: int
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


# ── Hospital stay ────────────────────────────────────────────────────────────

class HospitalizationBase(BaseModel):
    #: The one required clinical date. A stay is meaningful before anyone knows
    #: when it ended, and demanding a discharge would refuse the current
    #: admission — the one that matters most.
    admitted_at: datetime
    discharged_at: datetime | None = None
    facility_id: int | None = None
    facility_name: str | None = None
    ward: str | None = None
    room: str | None = None
    admission_type: AdmissionType | None = None
    status: AdmissionStatus | None = None
    reason: str | None = None
    primary_diagnosis: str | None = None
    icd10_code: str | None = None
    icd11_code: str | None = None
    icd11_title: str | None = None
    attending_physician: str | None = None
    referring_physician: str | None = None
    discharge_disposition: str | None = None
    discharge_summary: str | None = None
    complications: str | None = None
    is_readmission: bool | None = None
    source: str | None = None
    external_ref: str | None = None
    notes: str | None = None


class HospitalizationCreate(HospitalizationBase):
    #: Procedures may be sent with the stay — how a discharge summary or a FHIR
    #: bundle actually arrives. They may equally be posted on their own, which
    #: is why `hospitalization_id` is nullable everywhere.
    procedures: list[SurgicalProcedureCreate] = []

    @field_validator("admitted_at", "discharged_at")
    @classmethod
    def _naive(cls, v: datetime | None) -> datetime | None:
        return _naive_utc(v)

    @model_validator(mode="after")
    def _discharge_follows_admission(self):
        """Impossible, not merely unusual — so it is refused on input only.

        Deliberately NOT the overnight-rollover rule of §3av: that applies to a
        treatment whose end time is a clock reading on the following day. These
        are full timestamps, so an end before the start is a genuine error, and
        a stay is never corrected silently on the patient's behalf.
        """
        if self.discharged_at and self.admitted_at and self.discharged_at < self.admitted_at:
            raise ValueError(
                "Discharge is before admission — check the dates.")
        return self


class HospitalizationUpdate(BaseModel):
    admitted_at: datetime | None = None
    discharged_at: datetime | None = None
    facility_id: int | None = None
    facility_name: str | None = None
    ward: str | None = None
    room: str | None = None
    admission_type: AdmissionType | None = None
    status: AdmissionStatus | None = None
    reason: str | None = None
    primary_diagnosis: str | None = None
    icd10_code: str | None = None
    icd11_code: str | None = None
    icd11_title: str | None = None
    attending_physician: str | None = None
    referring_physician: str | None = None
    discharge_disposition: str | None = None
    discharge_summary: str | None = None
    complications: str | None = None
    is_readmission: bool | None = None
    notes: str | None = None

    @field_validator("admitted_at", "discharged_at")
    @classmethod
    def _naive(cls, v: datetime | None) -> datetime | None:
        return _naive_utc(v)


class HospitalizationResponse(HospitalizationBase):
    """A stay WITHOUT its procedures.

    No nested list, deliberately: reading `stay.procedures` off a lazily-loaded
    relationship inside an async session raises MissingGreenlet, so a nested
    field here would 500 on every route that did not eagerly load it. Routes
    that do load it return `HospitalizationDetail` below.
    """

    id: int
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class HospitalizationDetail(HospitalizationResponse):
    procedures: list[SurgicalProcedureResponse] = []

    class Config:
        from_attributes = True


# ── Read views (what `clinical_sources` returns) ─────────────────────────────
#
# These mirror the canonical reader's dataclasses rather than the tables. The
# reader is the only place allowed to decide what a "stay" or a "procedure"
# looks like to a caller, and it already merges, labels and orders them.

class ProcedureView(BaseModel):
    name: str
    performed: str | None = None
    code: str | None = None
    code_system: str | None = None
    body_site: str | None = None
    outcome: str | None = None
    ongoing_effects: str | None = None
    facility: str | None = None
    surgeon: str | None = None
    admission: str | None = None
    source: str | None = None

    class Config:
        from_attributes = True


class HospitalizationView(BaseModel):
    admitted: str
    discharged: str | None = None
    facility: str | None = None
    reason: str | None = None
    diagnosis: str | None = None
    admission_type: str | None = None
    status: str | None = None
    #: None while still an inpatient — never a length measured against today.
    nights: int | None = None
    procedures: list[ProcedureView] = []
    source: str | None = None

    class Config:
        from_attributes = True


class HospitalHistoryResponse(BaseModel):
    """Everything, in the shape the clients draw.

    `procedures` is the COMPLETE list, including those with no admission, and
    is not derivable from `stays` — that is the whole reason both exist.
    """

    stays: list[HospitalizationView] = []
    procedures: list[ProcedureView] = []
    lasting_effects: list[str] = []
