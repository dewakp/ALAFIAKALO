"""ICD-11 coding for chronic conditions.

Conditions are one of the app's cornerstones (CLAUDE.md §3aa) but carried only
`icd10_code`, and on production not one row had even that filled in. ICD-11 is
what the patient-facing picker writes.

`icd10_code` is KEPT rather than migrated. It is not a legacy duplicate: the
FHIR import (`services/smart_fhir.py`) and the PDF parser
(`services/docparse/records_clinical.py`) both extract ICD-10 from the source
document, and that is a fact about the document. A condition can legitimately
carry an ICD-10 read off a discharge summary and an ICD-11 the patient chose.

`icd11_title` is denormalised alongside the code so a condition still displays
its official label without a catalog round-trip, and so the label the patient
actually selected survives WHO retitling an entity in a later release.

Revision ID: nn001_condition_icd11
Revises: mm001_dialysis_coefficients
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "nn001_condition_icd11"
down_revision: Union[str, None] = "mm001_dialysis_coefficients"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "chronic_conditions",
        sa.Column("icd11_code", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "chronic_conditions",
        sa.Column("icd11_title", sa.String(length=300), nullable=True),
    )
    # Clinicians filter by code across a patient's history; the column is
    # sparse today, so a plain btree is the right shape.
    op.create_index(
        "ix_chronic_conditions_icd11_code",
        "chronic_conditions",
        ["icd11_code"],
    )


def downgrade() -> None:
    op.drop_index("ix_chronic_conditions_icd11_code", table_name="chronic_conditions")
    op.drop_column("chronic_conditions", "icd11_title")
    op.drop_column("chronic_conditions", "icd11_code")
