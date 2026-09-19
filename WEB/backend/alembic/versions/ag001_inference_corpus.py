"""inference_samples: the ALAFIA training corpus, for every modality

ALAFIA is the model we train ourselves. It is NOT Ollama — Ollama is a runtime
that serves third-party weights (gpt-oss, llava) and is the terminal rung of the
lookup path, nothing more. The long-term goal is that ALAFIA answers these
questions itself; until then every resolution, whatever answered it, is a
training sample.

`telemetry.register_sink` was built for exactly this and was never called, so
`telemetry.record()` reached `if not _sinks: return` and threw the
(input -> output) pair away on every call since the feature was designed. Food
photos were the only thing accumulating anywhere (`food_training_samples`), and
only from the one `/ai/vision` food path.

Additive only (canon §3ao): one new table, no drops, no alterations.

WHAT IS STORED, AND WHY IT IS THE PATIENT'S OWN WORDS
-----------------------------------------------------
`prompt` holds the RAW input, not the redacted copy. Redaction (§3al) exists to
stop a third party learning who the patient is; this table is ours, sits beside
the record the text already came from, and never leaves. Storing the scrubbed
copy instead would teach ALAFIA to expect `[name]` and `[dob]` tokens that never
appear at inference time — and since the hosted rung scrubs while the local rung
does not, the same question would be stored two different ways depending on
which provider happened to win. `input_was_redacted` records, per row, which
copy we actually got, so a sample can never silently misrepresent itself.

Precedent: `ai_interactions.user_request` / `.ai_response` have stored chat
verbatim since that feature shipped.

⚠️ This table is a TRAINING corpus, never a retrieval source. Nothing that
builds a prompt may read it: the egress path redacts what it is given, and rows
here are deliberately unredacted.

CONSENT
-------
Gated on `users.ai_training_consent` (default false), which until now was a
control all three clients offered and nothing on the server observed. A row is
written only for a user who granted it, so withdrawal is a purge of `user_id`
rather than a filter every future reader must remember.

Revision ID: ag001_inference_corpus
Revises: af001_meal_thumbnail
"""

from alembic import op
import sqlalchemy as sa


revision = "ag001_inference_corpus"
down_revision = "af001_meal_thumbnail"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "inference_samples",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        # Nullable: background and unauthenticated inference has no subject, and
        # a sample is still worth keeping. Set when we know who asked, so that
        # withdrawing consent can delete the rows it covers.
        sa.Column("user_id", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True),
        # The opaque handle from privacy.subject_token(). Lets samples be grouped
        # per subject for training without carrying the id into an export.
        sa.Column("subject_token", sa.String(40), nullable=True, index=True),

        # llm | vision | nlm | voice | video
        sa.Column("modality", sa.String(16), nullable=False, index=True),
        # chat, complete, classify_intent, food_photo_nutrition, image_question…
        sa.Column("task", sa.String(60), nullable=False, index=True),

        # WHICH RUNG ANSWERED. The lookup path is: local DB search, then the
        # external provider pool, then the local runtime. Recording the rung is
        # the point — it is what tells us where ALAFIA has to get good, and a
        # sample answered from our own store is a different kind of evidence
        # from one answered by a vendor.
        sa.Column("resolved_by", sa.String(20), nullable=False, index=True),
        sa.Column("tier", sa.String(16), nullable=True),       # local | free | paid
        sa.Column("provider", sa.String(40), nullable=True),   # ollama, anthropic…
        sa.Column("model", sa.String(120), nullable=True),

        # The pair. `prompt` is the input as the patient wrote it (see above).
        sa.Column("prompt", sa.Text(), nullable=True),
        sa.Column("response", sa.Text(), nullable=True),
        # Structured payload that is not prose: tool calls, json_mode output,
        # the item/nutrition arrays a vision answer carries.
        sa.Column("structured", sa.JSON(), nullable=True),
        # True when all we could capture was the scrubbed copy. A row that says
        # so can be excluded from training rather than quietly degrading it.
        sa.Column("input_was_redacted", sa.Boolean(), nullable=False,
                  server_default=sa.false()),

        sa.Column("tokens", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        # A FAILURE is training data too: it is how we learn which questions the
        # chain cannot answer at all. Storing only successes would describe a
        # system that always works.
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("error", sa.String(300), nullable=True),

        # Claimed by a training run, so a later run can take only what is new.
        sa.Column("trained_on", sa.Boolean(), nullable=False, server_default=sa.false()),

        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now(), index=True),
    )

    # "everything for this task that no run has taken yet" is the training query.
    op.create_index(
        "ix_inference_samples_task_trained",
        "inference_samples", ["task", "trained_on", "created_at"],
    )
    # "how much have we collected, per rung" is the readiness query.
    op.create_index(
        "ix_inference_samples_modality_rung",
        "inference_samples", ["modality", "resolved_by", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_inference_samples_modality_rung", table_name="inference_samples")
    op.drop_index("ix_inference_samples_task_trained", table_name="inference_samples")
    op.drop_table("inference_samples")
