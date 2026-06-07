"""upgrade hash columns from SHA-256 (64 chars) to SHA-512 (128 chars)

Revision ID: s512_upgrade_hash
Revises: h1i2j3k4l5m6
Create Date: 2026-04-15-sha512-upgrade
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "s512_upgrade_hash"
down_revision = "h1i2j3k4l5m6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # block_records: hash columns 64 → 128
    op.alter_column("block_records", "previous_hash",
                     type_=sa.String(128), existing_type=sa.String(64))
    op.alter_column("block_records", "hash",
                     type_=sa.String(128), existing_type=sa.String(64))
    op.alter_column("block_records", "merkle_root",
                     type_=sa.String(128), existing_type=sa.String(64))

    # chain_meta: hash columns 64 → 128
    op.alter_column("chain_meta", "genesis_hash",
                     type_=sa.String(128), existing_type=sa.String(64))
    op.alter_column("chain_meta", "latest_hash",
                     type_=sa.String(128), existing_type=sa.String(64))
    op.alter_column("chain_meta", "merkle_root",
                     type_=sa.String(128), existing_type=sa.String(64))

    # therapy_sessions: add payload_hash if not present
    op.add_column("therapy_sessions",
                  sa.Column("payload_hash", sa.String(128), nullable=True))

    # clinical_notes: create table matching ClinicalNote model
    op.create_table(
        "clinical_notes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("session_id", sa.Integer, sa.ForeignKey("therapy_sessions.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("author_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("author_role", sa.String(50), nullable=True),
        sa.Column("note_type", sa.String(50), nullable=False, server_default="general"),
        sa.Column("note_text", sa.Text, nullable=False),
        sa.Column("note_hash", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("clinical_notes")
    op.drop_column("therapy_sessions", "payload_hash")
    op.alter_column("chain_meta", "merkle_root",
                     type_=sa.String(64), existing_type=sa.String(128))
    op.alter_column("chain_meta", "latest_hash",
                     type_=sa.String(64), existing_type=sa.String(128))
    op.alter_column("chain_meta", "genesis_hash",
                     type_=sa.String(64), existing_type=sa.String(128))
    op.alter_column("block_records", "merkle_root",
                     type_=sa.String(64), existing_type=sa.String(128))
    op.alter_column("block_records", "hash",
                     type_=sa.String(64), existing_type=sa.String(128))
    op.alter_column("block_records", "previous_hash",
                     type_=sa.String(64), existing_type=sa.String(128))
