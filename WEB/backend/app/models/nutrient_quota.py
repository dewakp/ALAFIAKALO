# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""HOW MUCH of a nutrient a condition calls for — with the sentence that says so.

`condition_nutrition_facts` (ww001) can say a condition means **avoid** or
**favour** a nutrient. It has no amount, no unit, no basis and no
target/limit column, so there has never been anywhere to put a quantity.
`clinical_thresholds` (tt001) cannot help either: it is keyed
`(analyte, sex, age_min, age_max)` and scopes a **measured serum value**, not
dietary intake, and nothing in it is keyed by condition.

So `compute_goals` answered with a hand-written ladder — 13 nutrients, 6
condition flags, a literal at every leaf — and calcium had no branch at all:
every patient was given the bone-health RDA as a `target` to aim FOR,
including a dialysis patient whose calcium load is mostly their phosphate
binder.

**Why a scalar column was never going to be enough.** Measured against the
actual guideline literature on 2026-10-05, calcium alone:

    healthy adult              1,000-1,200 mg/d     dietary RDA
    CKD 3-4, no vit D analog     800-1,000 mg/d     TOTAL ELEMENTAL, incl. binders
    CKD G5D (dialysis)           no number at all   "adjust to avoid hypercalcemia"
    CKD any stage (EU consensus) 800-1,500 mg/d     total elemental, ceiling
    hungry bone, post-PTX      6,000-16,000 mg/d    TAPERING over ~6 weeks
    chronic hypoparathyroidism 2,000-3,000 mg/d     and <=500 mg PER DOSE
    calcium oxalate stones       1,000 mg/d         explicitly do NOT restrict
    sarcoidosis + hypercalcaemia restrict           contested

One nutrient, spanning ~0 to 16,000 mg/day, and three of those rows are not a
daily dietary number: one counts a MEDICATION toward the figure, one is a
per-ingestion ceiling (absorption saturates ~500 mg), one changes week by
week. A single float called `goal` cannot represent any of them — which is
why `basis`, `includes_supplements` and `time_course` are columns and not
prose.

**A quota with no citation is REFUSED.** §3az forbids inventing a nutrient
figure, and its own history is a hardcoded potassium limit of 4,700 mg
sitting LOOSER than the patient's real 2,200 mg cap, so the alert could never
fire for the patient it existed to protect. `source` and `cited_text` are
NOT NULL for that reason: a number nobody can trace is exactly the kind that
gets quoted to a clinician. There is no machine-readable authority to import
here — EFSA's DRVs are population-only, ESPEN ships 14 disease guidelines as
prose, and no body publishes per-condition quotas as data — so every row is
resolved once, cited, and stored.

Scope is per CONDITION SET, never per patient. "CKD G5D means this" is a fact
about a guideline, not about whoever happened to be in front of us, which is
what lets one patient's resolution serve the next — the same privacy shape as
`document_row_judgments` and `allergy_term_resolutions`.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, DateTime, Float, Index, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

#: A quota either names a floor to reach or a ceiling to stay under. Both can
#: exist for one nutrient and one condition — the European CKD consensus
#: states a minimum of 800-1,000 AND a ceiling of 1,500 — so `kind` is part of
#: the identity of a row rather than a property of it.
TARGET = "target"
LIMIT = "limit"
KINDS = frozenset({TARGET, LIMIT})

#: What the amount is measured against.
#:
#: `per_dose` is the one that must never be summed into a daily total: 500 mg
#: is a ceiling on a single ingestion in hypoparathyroidism, not a daily
#: allowance, and treating it as one would cut a 2,000 mg/day requirement to a
#: quarter of itself.
BASIS_ABSOLUTE = "absolute"
BASIS_PER_KG = "per_kg"
BASIS_PER_1000_KCAL = "per_1000_kcal"
BASIS_PER_DOSE = "per_dose"
BASES = frozenset({BASIS_ABSOLUTE, BASIS_PER_KG, BASIS_PER_1000_KCAL, BASIS_PER_DOSE})

EVIDENCE_LEVELS = frozenset({"high", "moderate", "low", "expert_opinion"})


class ConditionNutrientQuota(Base):
    """One cited nutrient quantity for one condition scope."""

    __tablename__ = "condition_nutrient_quotas"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # ── Which condition ──────────────────────────────────────────────
    # Normalised through the same `normalize_condition` the fact store uses,
    # so "End-Stage Renal Disease (ESRD)" and "end stage renal disease" are
    # one key and a misspelling is NOT silently folded in.
    condition_key: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    condition_label: Mapped[str] = mapped_column(String(300), nullable=False)
    icd11_code: Mapped[str | None] = mapped_column(String(20), index=True)

    # ── Which nutrient ───────────────────────────────────────────────
    # `subject` keeps the guideline's own wording ("total elemental calcium");
    # `subject_normalized` is the nutrient-catalog key ("calcium_mg") that
    # `compute_goals` and the diary join on. Storing only the catalog key
    # would lose the distinction the guideline actually drew — §3ax's
    # ALP/Alk Phos lesson, in the nutrient dimension.
    subject: Mapped[str] = mapped_column(String(160), nullable=False)
    subject_normalized: Mapped[str] = mapped_column(String(120), nullable=False, index=True)

    # ── The quantity ─────────────────────────────────────────────────
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(16), nullable=False)
    basis: Mapped[str] = mapped_column(
        String(20), nullable=False, default=BASIS_ABSOLUTE,
        server_default=BASIS_ABSOLUTE)

    #: TRUE when the figure counts supplements and drugs toward itself, as
    #: KDOQI's calcium figure counts calcium-based phosphate binders. A
    #: patient told to "aim for 800 mg of calcium" who is already taking
    #: 1,500 mg of calcium carbonate as a binder is being told the opposite of
    #: what the guideline says. This flag is what makes the two readable apart.
    includes_supplements: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false")

    #: "3.2 g/day in week 1, tapering to 2.4 g by week 6". Free text because
#: the shape differs per guideline; present means the figure is not static.
    time_course: Mapped[str | None] = mapped_column(Text)

    # ── Scope ────────────────────────────────────────────────────────
    # `scope_key` is a NON-NULL normalised join of stage+therapy, and it is in
    # the unique constraint instead of the nullable columns on purpose:
    # Postgres treats NULLs as distinct, so a unique key over nullable scope
    # columns lets re-resolution insert BESIDE the row it meant to sharpen —
    # §3ab's contradictory-duplicate failure, which is the exact thing this
    # store must not reproduce for a clinical quantity.
    scope_key: Mapped[str] = mapped_column(
        String(200), nullable=False, default="", server_default="")
    stage: Mapped[str | None] = mapped_column(String(60))
    therapy: Mapped[str | None] = mapped_column(String(160))
    sex: Mapped[str | None] = mapped_column(String(10))
    age_min: Mapped[int | None] = mapped_column(Integer)
    age_max: Mapped[int | None] = mapped_column(Integer)

    # ── The citation. Not optional. ──────────────────────────────────
    source: Mapped[str] = mapped_column(String(300), nullable=False)
    citation_url: Mapped[str | None] = mapped_column(Text)
    #: The guideline's own sentence. This is what separates a resolved figure
    #: from a plausible one, and it is what a clinician is shown when they ask
    #: why a target says what it says.
    cited_text: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_level: Mapped[str] = mapped_column(String(20), default="moderate")
    #: "llm" | "clinician" | "guideline_seed". Never blank (§3an).
    provenance: Mapped[str] = mapped_column(String(32), nullable=False, default="llm")
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    times_confirmed: Mapped[int] = mapped_column(Integer, default=1)

    #: Retire rather than delete, so a bad resolution stays traceable.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("condition_key", "subject_normalized", "kind", "basis",
                         "scope_key", name="uq_condition_nutrient_quota"),
        Index("idx_quota_condition_active", "condition_key", "is_active"),
        Index("idx_quota_subject_active", "subject_normalized", "is_active"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (f"<ConditionNutrientQuota {self.condition_key} "
                f"{self.subject_normalized} {self.kind}={self.amount}{self.unit} "
                f"/{self.basis} ({self.source})>")
