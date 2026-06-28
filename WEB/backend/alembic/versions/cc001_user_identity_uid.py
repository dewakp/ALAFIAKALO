"""Add identity_uid bridge to users (link to the shared 6IGMA Identity user).

Reference-only key (zero duplication): identity data lives in the `identity`
schema; ALAFIA `users` carries only this UUID to resolve the shared user.
"""

from alembic import op
import sqlalchemy as sa

revision = 'cc001_user_identity_uid'
down_revision = 'bb001_dose_log_temperature'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('identity_uid', sa.String(36), nullable=True))
    op.create_index('ix_users_identity_uid', 'users', ['identity_uid'], unique=True)


def downgrade():
    op.drop_index('ix_users_identity_uid', table_name='users')
    op.drop_column('users', 'identity_uid')
