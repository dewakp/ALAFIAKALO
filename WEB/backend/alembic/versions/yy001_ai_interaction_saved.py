"""Let a patient KEEP an AI answer, and remember the conversation.

An AI answer vanished the moment the screen changed. `ai_interactions` was
already recording every chat exchange — the data was there the whole time — but
nothing read it back, so the record existed and the patient could not see it.
Symptom analyses were not recorded at all.

Two additive columns, no drops (§3ao — every upgrade in this project's history
is additive, and autogenerate would happily propose dropping five live tables):

  saved_at   when the patient chose to keep this answer. NULL = not saved.
             A flag rather than a copy: the answer is already stored, and a
             second copy is a second thing to keep in step.
  title      what the patient called it, if anything.

Revision ID: yy001_ai_interaction_saved
Revises: xx001_contact_submissions
"""

from alembic import op
import sqlalchemy as sa

revision = "yy001_ai_interaction_saved"
down_revision = "xx001_contact_submissions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ai_interactions",
                  sa.Column("saved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("ai_interactions",
                  sa.Column("saved_title", sa.String(200), nullable=True))
    # Partial index: the saved list is what gets queried, and it is a small
    # fraction of every interaction ever recorded.
    op.create_index("ix_ai_interactions_saved", "ai_interactions",
                    ["user_id", "saved_at"],
                    postgresql_where=sa.text("saved_at IS NOT NULL"))


def downgrade() -> None:
    op.drop_index("ix_ai_interactions_saved", table_name="ai_interactions")
    op.drop_column("ai_interactions", "saved_title")
    op.drop_column("ai_interactions", "saved_at")
