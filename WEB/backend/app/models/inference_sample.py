"""The ALAFIA training corpus — one row per resolution, whatever answered it.

ALAFIA is the model we train ourselves, independent of any third party. Ollama
is not ALAFIA: it is a runtime serving other people's weights, and it is the
last rung of the lookup path (local DB search -> external provider -> local
runtime). The rungs stay exactly as they are; what changes is that every answer
they produce now becomes a training sample.

Separation of concerns, matching the vision corpus that already exists:

  FoodTrainingSample   photos + predictions + corrections   (vision, consented)
  InferenceSample      text in -> text out, and which rung   (every modality)

A sample is written for ANY outcome, success or failure. A chain that could not
answer is the clearest possible statement of what ALAFIA has to learn, and a
corpus of successes alone describes a system that always works.

⚠️ TRAINING CORPUS, NEVER A RETRIEVAL SOURCE. `prompt` holds the patient's own
words unredacted (see the migration for why), so nothing that assembles a prompt
may read this table — the egress redaction in §3al assumes its input has not
already been through here.
"""

from datetime import datetime, timezone

from sqlalchemy import String, DateTime, ForeignKey, Text, Boolean, JSON, Integer, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


# The rungs of the lookup path, normalised. The vocabularies differ per surface
# — the nutrient estimator says "learned"/"usda"/"ai", the LLM says
# "local"/"free"/"paid" — and a corpus that kept both could not be counted.
RESOLVED_BY_DB = "db"              # answered from our own store, no model ran
RESOLVED_BY_EXTERNAL = "external"  # a hosted third-party provider answered
RESOLVED_BY_LOCAL = "local_model"  # the self-hosted runtime answered
RESOLVED_BY_ALAFIA = "alafia"      # ALAFIA itself answered — the destination
RESOLVED_BY_NONE = "unresolved"    # nothing answered; the failure is the sample


class InferenceSample(Base):
    __tablename__ = "inference_samples"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Nullable: background work has no signed-in subject and its samples are
    # still worth keeping. Set when known, so withdrawing consent is a delete.
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    # privacy.subject_token() — groups a subject's samples without the id.
    subject_token: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)

    modality: Mapped[str] = mapped_column(String(16), index=True)   # llm | vision | nlm | …
    task: Mapped[str] = mapped_column(String(60), index=True)

    # Which rung produced this answer. The training signal that says where
    # ALAFIA has to get good, and what it would be replacing.
    resolved_by: Mapped[str] = mapped_column(String(20), index=True)
    tier: Mapped[str | None] = mapped_column(String(16), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(40), nullable=True)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)

    prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    response: Mapped[str | None] = mapped_column(Text, nullable=True)
    structured: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    # True when only the scrubbed copy could be captured. Such a row carries
    # placeholder tokens that never occur at inference, so a trainer can drop it
    # rather than learn from text no user ever typed.
    input_was_redacted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    error: Mapped[str | None] = mapped_column(String(300), nullable=True)

    # Claimed by a training run so the next one takes only what is new.
    trained_on: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)

    __table_args__ = (
        Index("ix_inference_samples_task_trained", "task", "trained_on", "created_at"),
        Index("ix_inference_samples_modality_rung", "modality", "resolved_by", "created_at"),
    )
