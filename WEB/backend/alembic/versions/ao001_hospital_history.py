# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""Hospital admissions and surgical procedures.

The record had nowhere to hold a surgery. A patient said *"I use it as calcium
supplement after removal of parathyroid glands"* — and a parathyroidectomy is
precisely what makes their calcium handling unlike any other dialysis
patient's. Measured 2026-10-05: **zero** mentions in `chronic_conditions`,
`symptom_logs` or anywhere else in the database. The fact existed only in a chat
message, so no amount of retrieval could reach it and the nutrient targets kept
quoting a bone-health RDA.

Two tables because a discharge summary and a FHIR bundle both carry an
Encounter with Procedure resources hanging off it — and because **either row
can stand alone**. `surgical_procedures.hospitalization_id` is NULLABLE on
purpose: day-case surgery and anything recorded years after the fact have no
encounter, and a required FK would refuse exactly the row this exists for.

Facility links are **SET NULL, not CASCADE**. `physician_facilities` cascades
because that row only describes a relationship; an admission is the patient's
own history, and removing a hospital from the directory must never delete the
record of having been in it.

Hand-written and additive — no drops, no rewrites (§3ao: autogenerate proposed
dropping five live tables when asked for one).
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "ao001_hospital_history"
down_revision = "an001_vital_thresholds"
branch_labels = None
depends_on = None

_ADMISSION_TYPE = "admissiontype"
_ADMISSION_STATUS = "admissionstatus"
_PROCEDURE_OUTCOME = "procedureoutcome"


def upgrade() -> None:
    bind = op.get_bind()

    # `create_type=False` + an explicit create: SQLAlchemy would otherwise emit
    # CREATE TYPE as a side effect of the first column that uses it, which
    # raises `duplicate key value violates unique constraint
    # "pg_type_typname_nsp_index"` on any database where the type already
    # exists. `checkfirst=True` makes this migration safe to run against a
    # database built from models as well as one built from migrations.
    # ⚠️ The labels are the Python enum member NAMES, not their values.
    # `SQLEnum(AdmissionType)` with no `values_callable` persists by NAME, so
    # the column writes `DISCHARGED` while `AdmissionStatus.DISCHARGED.value`
    # is `"discharged"`. Measured on the dev database rather than assumed —
    # `therapystatus` holds SCHEDULED, IN_PROGRESS, COMPLETED, CANCELLED,
    # MISSED, RESCHEDULED, and every enum in this schema is the same. Writing
    # the values here would create a type that refuses every row the ORM
    # inserts, and a `server_default` its own type rejects. §3az recorded this
    # exact confusion pointing the other way (reading the uppercase domain and
    # inferring a case mismatch in Python, which was wrong); the rule is that
    # the DB enum domain and the Python enum are different things and you ask
    # the database which is which.
    admission_type = postgresql.ENUM(
        "EMERGENCY", "ELECTIVE", "URGENT", "OBSERVATION", "DAY_CASE",
        "MATERNITY", "REHABILITATION", "OTHER",
        name=_ADMISSION_TYPE, create_type=False)
    admission_status = postgresql.ENUM(
        "PLANNED", "IN_PROGRESS", "DISCHARGED", "TRANSFERRED", "CANCELLED",
        name=_ADMISSION_STATUS, create_type=False)
    procedure_outcome = postgresql.ENUM(
        "SUCCESSFUL", "PARTIALLY_SUCCESSFUL", "UNSUCCESSFUL", "COMPLICATED",
        "ABANDONED", "UNKNOWN",
        name=_PROCEDURE_OUTCOME, create_type=False)

    admission_type.create(bind, checkfirst=True)
    admission_status.create(bind, checkfirst=True)
    procedure_outcome.create(bind, checkfirst=True)

    op.create_table(
        "hospitalizations",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("user_id", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False, index=True),

        # Both the link and the name the source gave. An imported record
        # routinely names a hospital the directory has never heard of, and
        # dropping that name loses the provenance.
        sa.Column("facility_id", sa.Integer(),
                  sa.ForeignKey("facilities.id", ondelete="SET NULL"),
                  nullable=True, index=True),
        sa.Column("facility_name", sa.String(300), nullable=True),
        sa.Column("ward", sa.String(120), nullable=True),
        sa.Column("room", sa.String(60), nullable=True),

        # The only required clinical date. A stay is meaningful before anyone
        # knows when it ended; requiring a discharge would refuse the current
        # admission, which is the one that matters most.
        sa.Column("admitted_at", sa.DateTime(), nullable=False, index=True),
        sa.Column("discharged_at", sa.DateTime(), nullable=True, index=True),

        sa.Column("admission_type", admission_type, nullable=True, index=True),
        sa.Column("status", admission_status, nullable=False,
                  server_default="DISCHARGED", index=True),

        sa.Column("reason", sa.String(300), nullable=True),
        sa.Column("primary_diagnosis", sa.String(300), nullable=True),
        # ICD-10 is what an import read off a document; ICD-11 is what someone
        # selected in the app. Different facts, never converted between.
        sa.Column("icd10_code", sa.String(20), nullable=True),
        sa.Column("icd11_code", sa.String(20), nullable=True, index=True),
        sa.Column("icd11_title", sa.String(300), nullable=True),

        sa.Column("attending_physician", sa.String(200), nullable=True),
        sa.Column("referring_physician", sa.String(200), nullable=True),

        sa.Column("discharge_disposition", sa.String(120), nullable=True),
        sa.Column("discharge_summary", sa.Text(), nullable=True),
        sa.Column("complications", sa.Text(), nullable=True),
        # Recorded only when the source says so — never computed here from date
        # arithmetic over a history that may be incomplete.
        sa.Column("is_readmission", sa.Boolean(), nullable=True),

        sa.Column("source", sa.String(40), nullable=True, index=True),
        # `FHIR:{id}`, matching map_condition's existing dedupe convention, so a
        # re-sync recognises its own rows instead of producing a second
        # contradictory copy of one admission (§3ab).
        sa.Column("external_ref", sa.String(120), nullable=True, index=True),
        sa.Column("notes", sa.Text(), nullable=True),

        sa.Column("created_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("now()")),
    )

    op.create_table(
        "surgical_procedures",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("user_id", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        # NULLABLE, and that is the point — see the module docstring.
        sa.Column("hospitalization_id", sa.Integer(),
                  sa.ForeignKey("hospitalizations.id", ondelete="SET NULL"),
                  nullable=True, index=True),

        sa.Column("name", sa.String(300), nullable=False),
        # The code AS GIVEN, with the system that issued it. Deliberately not
        # normalised: ICD-10-PCS, ICHI, CPT and SNOMED are different
        # vocabularies with different licences (SNOMED's Affiliate Licence
        # restricts redistribution, CPT is AMA-licensed), and guessing which
        # one a source used is §3ad's "never type a code from memory".
        sa.Column("code", sa.String(40), nullable=True, index=True),
        sa.Column("code_system", sa.String(40), nullable=True),
        sa.Column("body_site", sa.String(200), nullable=True),
        sa.Column("laterality", sa.String(20), nullable=True),

        sa.Column("performed_at", sa.DateTime(), nullable=True, index=True),
        sa.Column("facility_id", sa.Integer(),
                  sa.ForeignKey("facilities.id", ondelete="SET NULL"),
                  nullable=True, index=True),
        sa.Column("facility_name", sa.String(300), nullable=True),
        sa.Column("surgeon", sa.String(200), nullable=True),
        sa.Column("anesthesia_type", sa.String(60), nullable=True),

        sa.Column("outcome", procedure_outcome, nullable=True),
        sa.Column("complications", sa.Text(), nullable=True),
        # The field that answers "why is this patient's calcium different".
        # A parathyroidectomy permanently changes calcium handling, and that
        # persists long after the admission is history.
        sa.Column("ongoing_effects", sa.Text(), nullable=True),

        sa.Column("source", sa.String(40), nullable=True, index=True),
        sa.Column("external_ref", sa.String(120), nullable=True, index=True),
        sa.Column("notes", sa.Text(), nullable=True),

        sa.Column("created_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("now()")),
    )

    # Reading a patient's history is always scoped by user and ordered by when,
    # so the composite serves both readers in `clinical_sources`.
    op.create_index("ix_hospitalizations_user_admitted",
                    "hospitalizations", ["user_id", "admitted_at"])
    op.create_index("ix_surgical_procedures_user_performed",
                    "surgical_procedures", ["user_id", "performed_at"])


def downgrade() -> None:
    op.drop_index("ix_surgical_procedures_user_performed", table_name="surgical_procedures")
    op.drop_index("ix_hospitalizations_user_admitted", table_name="hospitalizations")
    op.drop_table("surgical_procedures")
    op.drop_table("hospitalizations")
    bind = op.get_bind()
    for name in (_PROCEDURE_OUTCOME, _ADMISSION_STATUS, _ADMISSION_TYPE):
        postgresql.ENUM(name=name, create_type=False).drop(bind, checkfirst=True)
