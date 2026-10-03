# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""What a declared allergy term actually names, resolved once and remembered.

The patient's own words stay in `users.allergies`, verbatim and untouched. This
table says what one of those words MEANS, so that a profile reading `Penicilin`
also guards against a dose logged as `Penicillin`.

Deliberately has no `user_id`: a spelling is a fact about a word, not about a
person. See the migration `am001_allergy_terms` for the full argument.
"""

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

#: `verdict` values. Only SPELLING produces a new matchable alias.
EXACT = "exact"
SPELLING = "spelling"
REFUSED = "refused"
UNKNOWN = "unknown"
UNREACHABLE = "unreachable"


class AllergyTermResolution(Base):
    __tablename__ = "allergy_term_resolutions"
    __table_args__ = (
        UniqueConstraint("declared_term", name="uq_allergy_term_declared"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    #: `food_safety._normalise` output — what the matcher compares.
    declared_term: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    #: One verbatim example of how a patient wrote it. Audit only.
    declared_sample: Mapped[str | None] = mapped_column(String(200))

    resolved_name: Mapped[str | None] = mapped_column(String(200))
    #: The normalised form of `resolved_name` — the alias actually matched on.
    resolved_term: Mapped[str | None] = mapped_column(String(200))
    rxcui: Mapped[str | None] = mapped_column(String(20))

    verdict: Mapped[str] = mapped_column(String(16), nullable=False)
    refused_reason: Mapped[str | None] = mapped_column(String(300))
    edit_distance: Mapped[int | None] = mapped_column(Integer)
    similarity: Mapped[float | None] = mapped_column(Float)

    provenance: Mapped[str] = mapped_column(String(32), nullable=False, default="rxnorm")
    times_confirmed: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc))

    @property
    def gives_alias(self) -> bool:
        """Only an accepted misspelling adds a new term to match on."""
        return bool(self.is_active and self.verdict == SPELLING and self.resolved_term)
