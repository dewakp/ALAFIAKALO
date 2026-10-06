# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""Hospital admissions and the procedures performed during them.

Written because a real clinical fact had nowhere to live. A patient told the
assistant *"I use it as calcium supplement after removal of parathyroid
glands"* — and a parathyroidectomy is the single fact that makes their calcium
reality different from a generic dialysis patient's. Measured 2026-10-05: zero
rows mention it in `chronic_conditions`, `symptom_logs` or anywhere else. The
record simply could not hold it, so no amount of retrieval reached it and the
targets engine kept quoting a bone-health RDA.

**Shaped for the import, not for the form.** A discharge summary or FHIR bundle
carries an `Encounter` (the stay) with `Procedure` resources hanging off it, so
that is the shape here: one admission, many procedures, and a procedure may
stand alone because day-case surgery and historical operations arrive with no
encounter at all.

Three decisions worth stating:

- **Codes travel WITH their system.** `chronic_conditions` already carries
  `icd10_code` and `icd11_code` as deliberately different facts (ICD-10 is what
  an import read off a document; ICD-11 is what the patient selected). The same
  applies here and is worse for procedures, where the vocabularies are
  licensed: SNOMED CT's Affiliate Licence restricts redistribution (§3ab) and
  CPT is AMA-licensed. So `code` + `code_system` is stored verbatim as the
  source gave it and nothing converts between them.
- **Nothing an imported record may legitimately lack is NOT NULL.** A discharge
  summary routinely omits a discharge date (still admitted), a surgeon, or a
  code. `AIInteraction.llm_provider` being NOT NULL is how a whole feature
  silently recorded nothing inside a best-effort `try/except`.
- **The facility link is `SET NULL`, not `CASCADE`.** `physician_facilities`
  cascades because that row only describes a relationship. An admission is the
  patient's own history: removing a hospital from the directory must never
  delete the record of having been in it.
"""

import enum
from datetime import datetime

from sqlalchemy import (Boolean, Column, DateTime, ForeignKey, Integer, String,
                        Text, func, Enum as SQLEnum)
from sqlalchemy.orm import relationship

from app.core.database import Base


class AdmissionType(str, enum.Enum):
    """Why the stay happened. Mirrors FHIR Encounter.class / type loosely."""
    EMERGENCY = "emergency"
    ELECTIVE = "elective"
    URGENT = "urgent"
    OBSERVATION = "observation"
    DAY_CASE = "day_case"          # admitted and discharged the same day
    MATERNITY = "maternity"
    REHABILITATION = "rehabilitation"
    OTHER = "other"


class AdmissionStatus(str, enum.Enum):
    """Where the stay is in its lifecycle."""
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"    # still an inpatient
    DISCHARGED = "discharged"
    TRANSFERRED = "transferred"
    CANCELLED = "cancelled"


class ProcedureOutcome(str, enum.Enum):
    """How it went, as the record states it — never inferred."""
    SUCCESSFUL = "successful"
    PARTIALLY_SUCCESSFUL = "partially_successful"
    UNSUCCESSFUL = "unsuccessful"
    COMPLICATED = "complicated"
    ABANDONED = "abandoned"
    UNKNOWN = "unknown"


class Hospitalization(Base):
    """One hospital stay.

    `admitted_at` is the only required clinical date: a record of being
    admitted is meaningful before anyone knows when it ended, and demanding a
    discharge date would refuse exactly the rows that matter most — the
    current one.
    """
    __tablename__ = "hospitalizations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"),
                     nullable=False, index=True)

    # ── Where ────────────────────────────────────────────────────────────
    # Both, on purpose. The FK links to the directory when the hospital is in
    # it; the free text keeps what the source document actually said, because
    # an imported record routinely names a facility the directory has never
    # heard of and losing that name loses the provenance.
    facility_id = Column(Integer, ForeignKey("facilities.id", ondelete="SET NULL"),
                         nullable=True, index=True)
    facility_name = Column(String(300), nullable=True)
    ward = Column(String(120), nullable=True)
    room = Column(String(60), nullable=True)

    # ── When ─────────────────────────────────────────────────────────────
    admitted_at = Column(DateTime, nullable=False, index=True)
    discharged_at = Column(DateTime, nullable=True, index=True)

    # ── What ─────────────────────────────────────────────────────────────
    admission_type = Column(SQLEnum(AdmissionType), nullable=True, index=True)
    #: `server_default` is the member NAME because `SQLEnum` persists by name
    #: (the stored label is `DISCHARGED`, not the value `"discharged"`). It is
    #: declared here as well as in migration ao001 so the model and the
    #: deployed column agree — a default that exists only in the DDL is
    #: precisely the unmodelled drift that makes `--autogenerate` propose
    #: destructive changes (§3ao).
    status = Column(SQLEnum(AdmissionStatus), nullable=False,
                    default=AdmissionStatus.DISCHARGED,
                    server_default="DISCHARGED", index=True)

    reason = Column(String(300), nullable=True)          # presenting complaint
    primary_diagnosis = Column(String(300), nullable=True)
    #: As the SOURCE coded it. ICD-10 from an import, ICD-11 where the patient
    #: or a clinician selected one. Never converted between systems.
    icd10_code = Column(String(20), nullable=True)
    icd11_code = Column(String(20), nullable=True, index=True)
    icd11_title = Column(String(300), nullable=True)

    # ── Who ──────────────────────────────────────────────────────────────
    attending_physician = Column(String(200), nullable=True)
    referring_physician = Column(String(200), nullable=True)

    # ── Outcome ──────────────────────────────────────────────────────────
    discharge_disposition = Column(String(120), nullable=True)   # home, SNF, transfer…
    discharge_summary = Column(Text, nullable=True)
    complications = Column(Text, nullable=True)
    #: A readmission within 30 days is a quality signal a clinician reads
    #: directly; it is recorded only when the source says so, never computed
    #: here from date arithmetic over an incomplete history.
    is_readmission = Column(Boolean, nullable=True)

    # ── Provenance ───────────────────────────────────────────────────────
    #: "manual" | "fhir" | "document" — which path wrote this row. §3aa: when
    #: one domain has several writers, a reader that cannot tell them apart
    #: cannot explain a disagreement between them.
    source = Column(String(40), nullable=True, index=True)
    #: Dedupe marker, written as `FHIR:{resource id}` by the import, matching
    #: `map_condition`'s existing convention. `existing_markers()` compares
    #: this, so a re-sync updates nothing and inserts nothing — §3ab: a second
    #: import that cannot recognise its own rows produces two contradictory
    #: copies of one admission.
    external_ref = Column(String(120), nullable=True, index=True)
    notes = Column(Text, nullable=True)

    #: `server_default` is declared here as well as in migration ao001 so the
    #: model and the deployed column agree — a default that exists only in the
    #: DDL is the unmodelled drift `--autogenerate` reads as a change to make
    #: (§3ao). The Python default still supplies the value on every ORM write;
    #: this only covers a raw INSERT that omits the column.
    created_at = Column(DateTime, default=datetime.utcnow,
                        server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow,
                        onupdate=datetime.utcnow,
                        server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="hospitalizations")
    #: NOT `delete-orphan`, and that is a correction rather than an omission.
    #: The deployed FK is `ON DELETE SET NULL` (verified against the database),
    #: so an ORM cascade would contradict the schema by destroying procedures
    #: when a stay is deleted. An operation that happened is a fact about the
    #: patient's body: removing a mistyped admission must never erase the
    #: record of a parathyroidectomy. `passive_deletes=True` lets the database
    #: apply SET NULL instead of the ORM nulling or deleting children itself.
    procedures = relationship("SurgicalProcedure", back_populates="hospitalization",
                              passive_deletes=True,
                              order_by="SurgicalProcedure.performed_at")


class SurgicalProcedure(Base):
    """One procedure.

    `hospitalization_id` is NULLABLE and that is the point: a parathyroidectomy
    recorded years after the fact, a day-case endoscopy, or a procedure read
    off a document that never mentioned the stay all have to land somewhere. A
    required admission FK would have refused precisely the row this model was
    written for.
    """
    __tablename__ = "surgical_procedures"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    hospitalization_id = Column(
        Integer, ForeignKey("hospitalizations.id", ondelete="SET NULL"),
        nullable=True, index=True)

    # ── What ─────────────────────────────────────────────────────────────
    name = Column(String(300), nullable=False)          # "Parathyroidectomy"
    #: The code AS GIVEN, with the system that issued it. Deliberately not an
    #: enum and deliberately not normalised: ICD-10-PCS, ICHI, CPT and SNOMED
    #: are different vocabularies with different licences, and guessing which
    #: one a source used is the §3ad "never type a code from memory" failure.
    code = Column(String(40), nullable=True, index=True)
    code_system = Column(String(40), nullable=True)      # "ICD-10-PCS", "CPT", "SNOMED", "ICHI"
    body_site = Column(String(200), nullable=True)
    laterality = Column(String(20), nullable=True)       # left | right | bilateral

    # ── When / where / who ───────────────────────────────────────────────
    performed_at = Column(DateTime, nullable=True, index=True)
    facility_id = Column(Integer, ForeignKey("facilities.id", ondelete="SET NULL"),
                         nullable=True, index=True)
    facility_name = Column(String(300), nullable=True)
    surgeon = Column(String(200), nullable=True)
    anesthesia_type = Column(String(60), nullable=True)

    # ── Outcome ──────────────────────────────────────────────────────────
    outcome = Column(SQLEnum(ProcedureOutcome), nullable=True)
    complications = Column(Text, nullable=True)
    #: The lasting consequence, in the patient's own terms. This is the field
    #: that answers "why is this patient's calcium different" — a
    #: parathyroidectomy permanently changes calcium handling, and that
    #: persists long after the admission is history.
    ongoing_effects = Column(Text, nullable=True)

    # ── Provenance ───────────────────────────────────────────────────────
    source = Column(String(40), nullable=True, index=True)
    external_ref = Column(String(120), nullable=True, index=True)
    notes = Column(Text, nullable=True)

    #: `server_default` is declared here as well as in migration ao001 so the
    #: model and the deployed column agree — a default that exists only in the
    #: DDL is the unmodelled drift `--autogenerate` reads as a change to make
    #: (§3ao). The Python default still supplies the value on every ORM write;
    #: this only covers a raw INSERT that omits the column.
    created_at = Column(DateTime, default=datetime.utcnow,
                        server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow,
                        onupdate=datetime.utcnow,
                        server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="surgical_procedures")
    hospitalization = relationship("Hospitalization", back_populates="procedures")
