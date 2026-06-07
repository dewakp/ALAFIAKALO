"""blockchain_ledger_tables

Revision ID: e1f2a3b4c5d6
Revises: d4e5f6a7b8c0
Create Date: 2025-01-01 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "e1f2a3b4c5d6"
down_revision = "d4e5f6a7b8c0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── block_records ────────────────────────────────────────────────
    op.create_table(
        "block_records",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("block_uid", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("index", sa.Integer(), nullable=False),
        sa.Column("chain_type", sa.String(50), nullable=False, index=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("action", sa.String(80), nullable=False, index=True),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("previous_hash", sa.String(128), nullable=False),
        sa.Column("hash", sa.String(128), nullable=False, index=True),
        sa.Column("nonce", sa.String(64), nullable=True),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True, index=True),
        sa.Column("entity_type", sa.String(80), nullable=True, index=True),
        sa.Column("entity_id", sa.Integer(), nullable=True, index=True),
        sa.Column("merkle_root", sa.String(128), nullable=True),
        sa.Column("signature", sa.String(256), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
    )

    # composite indexes
    op.create_index("ix_block_records_chain_index", "block_records", ["chain_type", "index"])
    op.create_index("ix_block_records_entity", "block_records", ["entity_type", "entity_id"])
    op.create_index("ix_block_records_actor_chain", "block_records", ["actor_id", "chain_type"])

    # ── chain_meta ───────────────────────────────────────────────────
    op.create_table(
        "chain_meta",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("chain_type", sa.String(50), nullable=False, unique=True, index=True),
        sa.Column("genesis_hash", sa.String(128), nullable=True),
        sa.Column("latest_hash", sa.String(128), nullable=True),
        sa.Column("latest_index", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("block_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("merkle_root", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
    )


def downgrade() -> None:
    op.drop_index("ix_block_records_actor_chain", table_name="block_records")
    op.drop_index("ix_block_records_entity", table_name="block_records")
    op.drop_index("ix_block_records_chain_index", table_name="block_records")
    op.drop_table("chain_meta")
    op.drop_table("block_records")
