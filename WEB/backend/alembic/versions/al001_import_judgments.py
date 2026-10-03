# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""document_row_judgments — what a reviewer decided, remembered

Revision ID: al001_import_judgments
Revises: ak001_session_drugs
Create Date: 2026-09-30

WHY THIS TABLE EXISTS. Every document import already ends with a human judging
each row — `document_import_items.accepted`, and the `accepted_item_ids` the
confirm call carries — and nothing has ever read those decisions back. That is
the §3ar dead control on the richest training signal in the product.

WHAT IT HOLDS. A row SHAPE, never a measurement: the normalised name the
document printed, which column roles were populated, and whether the value was a
number or a word. A haemoglobin of 9.4 and one of 14.1 produce the same
signature, which is what lets one patient's review help the next patient's
import without either seeing the other's data.

WRITTEN BY HAND, deliberately. `alembic revision --autogenerate` on this schema
emits ~200 lines that DROP five live tables (`facilities`,
`physician_facilities`, `deactivated_accounts`, `deactivated_identity_only`) and
rewrite indexes across the database, because the models in code do not describe
the deployed schema exactly and autogenerate reads every unmodelled table as one
to delete (§3ao). Every upgrade() in this project's history is additive. This
one adds a table and nothing else.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "al001_import_judgments"
down_revision: Union[str, None] = "ak001_session_drugs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "document_row_judgments",
        sa.Column("id", sa.Integer(), nullable=False),
        # sha256 of (normalised name, populated roles, value shape).
        sa.Column("signature", sa.String(length=64), nullable=False),
        # Readable, for audit: a guard that cannot explain itself gets blamed
        # for the thing it did not do (§3aj).
        sa.Column("sample_label", sa.String(length=255), nullable=True),
        sa.Column("roles", sa.String(length=120), nullable=True),
        sa.Column("value_shape", sa.String(length=20), nullable=True),
        sa.Column("verdict", sa.String(length=16), nullable=False),
        sa.Column("decided_by", sa.String(length=16), nullable=False,
                  server_default="reviewer"),
        # A judgment only acts once seen more than once: one person's slip must
        # not teach the parser to hide a real analyte from everyone else.
        sa.Column("times_confirmed", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("times_contradicted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("lab_name", sa.String(length=255), nullable=True),
        # Retire a bad lesson without deleting it, so it stays auditable.
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        # Re-seeing a shape SHARPENS the judgment in place. Without this a
        # second, contradictory verdict lands beside the first — §3ab's
        # duplicate, in the learning store itself.
        sa.UniqueConstraint("signature", name="uq_document_row_signature"),
    )
    op.create_index(op.f("ix_document_row_judgments_id"),
                    "document_row_judgments", ["id"], unique=False)
    op.create_index(op.f("ix_document_row_judgments_signature"),
                    "document_row_judgments", ["signature"], unique=True)
    op.create_index(op.f("ix_document_row_judgments_verdict"),
                    "document_row_judgments", ["verdict"], unique=False)
    op.create_index(op.f("ix_document_row_judgments_lab_name"),
                    "document_row_judgments", ["lab_name"], unique=False)
    op.create_index(op.f("ix_document_row_judgments_created_at"),
                    "document_row_judgments", ["created_at"], unique=False)
    op.create_index("idx_row_judgment_active", "document_row_judgments",
                    ["verdict", "is_active"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_row_judgment_active", table_name="document_row_judgments")
    op.drop_index(op.f("ix_document_row_judgments_created_at"),
                  table_name="document_row_judgments")
    op.drop_index(op.f("ix_document_row_judgments_lab_name"),
                  table_name="document_row_judgments")
    op.drop_index(op.f("ix_document_row_judgments_verdict"),
                  table_name="document_row_judgments")
    op.drop_index(op.f("ix_document_row_judgments_signature"),
                  table_name="document_row_judgments")
    op.drop_index(op.f("ix_document_row_judgments_id"),
                  table_name="document_row_judgments")
    op.drop_table("document_row_judgments")
