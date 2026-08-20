"""Staging tables for parsed clinical documents.

Uploaded documents are read into `document_imports` + `document_import_items`
and shown to the patient for review. Nothing reaches `lab_results`,
`medications` or `chronic_conditions` until they accept it.

The alternative — writing straight through on upload — puts the parser's
mistakes into the clinical record, where they are indistinguishable from
measurements a lab actually reported. A staged row carries its confidence, what
the document literally said, and whether it duplicates something already
recorded, so a wrong reading is caught while it is still a proposal.

`content_hash` is indexed per user: re-uploading the same file must return the
existing import rather than stage a second copy of the same readings.

Revision ID: ll001_document_imports
Revises: kk001_reading_time_nullable
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "ll001_document_imports"
down_revision: Union[str, None] = "kk001_reading_time_nullable"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "document_imports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("doc_type", sa.String(length=40), nullable=True),
        sa.Column("doc_type_confidence", sa.Float(), nullable=True),
        sa.Column("classification_method", sa.String(length=20), nullable=True),
        sa.Column("extraction_method", sa.String(length=20), nullable=True),
        sa.Column("layout_kind", sa.String(length=20), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("parse_confidence", sa.Float(), nullable=True),
        sa.Column("patient_name", sa.String(length=255), nullable=True),
        sa.Column("report_date", sa.String(length=20), nullable=True),
        sa.Column("lab_name", sa.String(length=255), nullable=True),
        sa.Column("ordering_provider", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="parsed"),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("notes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_document_imports_id", "document_imports", ["id"])
    op.create_index("ix_document_imports_user_id", "document_imports", ["user_id"])
    op.create_index("ix_document_imports_status", "document_imports", ["status"])
    op.create_index(
        "ix_document_imports_user_hash", "document_imports", ["user_id", "content_hash"]
    )

    op.create_table(
        "document_import_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("import_id", sa.Integer(), nullable=False),
        sa.Column("target_table", sa.String(length=40), nullable=False),
        sa.Column("row_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_label", sa.String(length=255), nullable=True),
        sa.Column("canonical_name", sa.String(length=255), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("dedupe_status", sa.String(length=20), nullable=False, server_default="new"),
        sa.Column("existing_row_id", sa.Integer(), nullable=True),
        sa.Column("accepted", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("imported_row_id", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["import_id"], ["document_imports.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_document_import_items_id", "document_import_items", ["id"])
    op.create_index("ix_document_import_items_import_id", "document_import_items", ["import_id"])
    op.create_index("ix_document_import_items_target", "document_import_items", ["target_table"])


def downgrade() -> None:
    op.drop_table("document_import_items")
    op.drop_table("document_imports")
