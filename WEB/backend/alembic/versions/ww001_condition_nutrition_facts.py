"""condition_nutrition_facts — what a diagnosis means for food, learned and stored

Revision ID: ww001_condition_nutrition
Revises: vv001_food_category_store
Create Date: 2026-09-02

WRITTEN BY HAND, deliberately. `alembic revision --autogenerate` produced this
table AND a further ~200 lines that would have DROPPED five live tables
(`facilities`, `physician_facilities`, `deactivated_accounts`,
`deactivated_identity_only`) and rewritten indexes across the schema — because
the models in code do not describe the deployed database exactly, so
autogenerate reads every unmodelled table as one to delete.

Every upgrade() in this project's history is additive: no drops, no deletes.
This one adds a table and nothing else. Do not replace it with autogenerate
output without reading every line of that output first.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision: str = "ww001_condition_nutrition"
down_revision: Union[str, None] = "vv001_food_category_store"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "condition_nutrition_facts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("condition_key", sa.String(length=200), nullable=False),
        sa.Column("condition_label", sa.String(length=300), nullable=False),
        sa.Column("icd11_code", sa.String(length=20), nullable=True),
        sa.Column("relation", sa.String(length=16), nullable=False),
        sa.Column("subject_kind", sa.String(length=16), nullable=False,
                  server_default="food"),
        sa.Column("subject", sa.String(length=200), nullable=False),
        sa.Column("subject_normalized", sa.String(length=200), nullable=False),
        sa.Column("mechanism", sa.Text(), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("evidence_level", sa.String(length=20), nullable=False,
                  server_default="moderate"),
        sa.Column("source", sa.String(length=300), nullable=True),
        sa.Column("provenance", sa.String(length=32), nullable=False,
                  server_default="llm"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("times_confirmed", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        # Re-resolving a condition must sharpen the existing fact, never insert
        # a second contradictory one beside it (§3ab).
        sa.UniqueConstraint("condition_key", "relation", "subject_normalized",
                            name="uq_condition_relation_subject"),
    )
    op.create_index("idx_condition_relation", "condition_nutrition_facts",
                    ["condition_key", "relation", "is_active"], unique=False)
    op.create_index(op.f("ix_condition_nutrition_facts_condition_key"),
                    "condition_nutrition_facts", ["condition_key"], unique=False)
    op.create_index(op.f("ix_condition_nutrition_facts_created_at"),
                    "condition_nutrition_facts", ["created_at"], unique=False)
    op.create_index(op.f("ix_condition_nutrition_facts_icd11_code"),
                    "condition_nutrition_facts", ["icd11_code"], unique=False)
    op.create_index(op.f("ix_condition_nutrition_facts_id"),
                    "condition_nutrition_facts", ["id"], unique=False)
    op.create_index(op.f("ix_condition_nutrition_facts_relation"),
                    "condition_nutrition_facts", ["relation"], unique=False)
    op.create_index(op.f("ix_condition_nutrition_facts_subject_normalized"),
                    "condition_nutrition_facts", ["subject_normalized"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_condition_nutrition_facts_subject_normalized"),
                  table_name="condition_nutrition_facts")
    op.drop_index(op.f("ix_condition_nutrition_facts_relation"),
                  table_name="condition_nutrition_facts")
    op.drop_index(op.f("ix_condition_nutrition_facts_id"),
                  table_name="condition_nutrition_facts")
    op.drop_index(op.f("ix_condition_nutrition_facts_icd11_code"),
                  table_name="condition_nutrition_facts")
    op.drop_index(op.f("ix_condition_nutrition_facts_created_at"),
                  table_name="condition_nutrition_facts")
    op.drop_index(op.f("ix_condition_nutrition_facts_condition_key"),
                  table_name="condition_nutrition_facts")
    op.drop_index("idx_condition_relation", table_name="condition_nutrition_facts")
    op.drop_table("condition_nutrition_facts")
