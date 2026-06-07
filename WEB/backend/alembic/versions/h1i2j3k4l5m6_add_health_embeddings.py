"""Add health_embeddings table for semantic RAG

Revision ID: h1i2j3k4l5m6
Revises: 3e5633413cb9
Create Date: 2026-04-02 12:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'h1i2j3k4l5m6'
down_revision: Union[str, None] = 'c5ffe803fcf5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'health_embeddings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('chunk_key', sa.String(length=100), nullable=False),
        sa.Column('chunk_text', sa.Text(), nullable=False),
        sa.Column('embedding', sa.JSON(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'chunk_key', name='uq_user_chunk'),
    )
    op.create_index(op.f('ix_health_embeddings_id'), 'health_embeddings', ['id'], unique=False)
    op.create_index(op.f('ix_health_embeddings_user_id'), 'health_embeddings', ['user_id'], unique=False)
    op.create_index(op.f('ix_health_embeddings_chunk_key'), 'health_embeddings', ['chunk_key'], unique=False)
    op.create_index('idx_health_emb_user_updated', 'health_embeddings', ['user_id', 'updated_at'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_health_emb_user_updated', table_name='health_embeddings')
    op.drop_index(op.f('ix_health_embeddings_chunk_key'), table_name='health_embeddings')
    op.drop_index(op.f('ix_health_embeddings_user_id'), table_name='health_embeddings')
    op.drop_index(op.f('ix_health_embeddings_id'), table_name='health_embeddings')
    op.drop_table('health_embeddings')
