"""What a reviewer decided about a row — remembered, so the parser improves.

THE SIGNAL WE WERE THROWING AWAY. Every document import already ends with a
human judging each row: `DocumentImportItem.accepted`, and the
`accepted_item_ids` list the confirm call carries. Nothing has ever read those
decisions back. That is the §3ar dead control — a flag nothing observes — on the
single richest training signal in the product, because unlike a model's guess it
is a clinician or the patient themselves saying "this line is not a result".

It is also §3ay's failure waiting to happen again: `telemetry.register_sink` was
built, documented as the corpus a future ALAFIA distils from, and never called,
so every pair hit `if not _sinks: return` and was dropped. A table with no reader
is worse than no table, so this one is written AND read: `docparse.normalize`
consults it before a row is offered, and `document_import_service` records what
the reviewer did with it.

WHAT IS STORED — A SHAPE, NOT A MEASUREMENT
-------------------------------------------
The learning signal is "rows that look like THIS are document furniture", which
needs the row's shape and not the patient's number. So a judgment holds:

  * the normalised NAME the document printed ("performing laboratory"),
  * which column roles were populated (name+value, or name+value+flag+range),
  * the SHAPE of the value ("numeric", "word", "words"), never the value.

A haemoglobin of 9.4 and one of 14.1 produce the same signature, which is what
makes the table shareable across patients at all. `signature` is the sha256 of
those three parts so a lookup is one indexed equality test.

`sample_label` keeps the readable name so an operator can audit what was learned
— `looks_like_prose` rejects by shape and nobody could tell you WHY without it.
Analyte names and footnote text are not patient identifiers, but a document's
furniture does sometimes carry a clinician's name ("Director: Dr Robert L"), so
this table is ours, never leaves, and is not a retrieval source — the same
standing rule as `inference_samples` (§3ay).

WHY VERDICTS SHARPEN RATHER THAN ACCUMULATE
-------------------------------------------
One row per signature, with `times_confirmed`. Re-seeing the same shape raises
confidence in place; it never inserts a second, contradictory judgment beside
the first. That is §3ab's lesson applied to the learning store itself, and it is
the same shape as `ConditionNutritionFact`.

A verdict is advisory. It can UNTICK a row and say why; it can never delete one,
and it can never overrule a row the deterministic guard already judged a real
measurement. A learned mistake that silently removed clinical data would be
strictly worse than the boilerplate it was meant to catch.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, DateTime, Float, Index, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

#: DocumentRowJudgment.verdict
VERDICT_FURNITURE = "furniture"   # not a measurement — heading, footnote, address
VERDICT_RESULT = "result"         # a real clinical finding

#: Who said so. A reviewer outranks everything else: they are looking at the
#: document. The guard and the model are recorded so a wrong lesson can be
#: traced to what taught it.
DECIDED_BY_REVIEWER = "reviewer"
DECIDED_BY_GUARD = "guard"
DECIDED_BY_MODEL = "model"


class DocumentRowJudgment(Base):
    """One learned verdict about one SHAPE of parsed row."""

    __tablename__ = "document_row_judgments"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    #: sha256 of (normalised name, populated roles, value shape). One indexed
    #: equality test per candidate row.
    signature: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)

    #: Readable, for audit. Without it nobody can say WHY a row was refused.
    sample_label: Mapped[str | None] = mapped_column(String(255))
    #: "name,value" / "name,value,flag,ref_range" — the document's structure.
    roles: Mapped[str | None] = mapped_column(String(120))
    #: "numeric" | "word" | "words" | "empty"
    value_shape: Mapped[str | None] = mapped_column(String(20))

    verdict: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    decided_by: Mapped[str] = mapped_column(String(16), nullable=False,
                                            default=DECIDED_BY_REVIEWER)

    #: How many reviewers have agreed, and how far to trust it. A judgment only
    #: acts once it has been seen more than once — one person's slip must not
    #: teach the parser to hide a real analyte from everyone else.
    times_confirmed: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    times_contradicted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)

    #: Which lab's documents taught this, when we know. A footnote belongs to a
    #: vendor's template; the same words rarely mean the same thing elsewhere.
    lab_name: Mapped[str | None] = mapped_column(String(255), index=True)

    #: Retire a judgment without deleting it, so a bad lesson stays auditable.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notes: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("signature", name="uq_document_row_signature"),
        Index("idx_row_judgment_active", "verdict", "is_active"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (f"<DocumentRowJudgment {self.sample_label!r} {self.verdict} "
                f"x{self.times_confirmed} ({self.decided_by})>")
