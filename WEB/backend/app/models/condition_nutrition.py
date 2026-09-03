"""What a CONDITION means for food — learned and stored, never hardcoded.

A diagnosis changes what a patient should eat in two directions, and only one of
them was ever modelled:

  • TRIGGERS      fava beans in G6PD deficiency, gluten in coeliac disease,
                  dehydration in sickle cell. Foods to avoid.
  • MITIGATORS    antioxidants that reduce oxidative stress in G6PD; B12,
                  folate and iron (with vitamin C for absorption) that support
                  erythropoiesis in anaemia. Foods to FAVOUR.

The first version of this was a nine-line Python dict mapping "g6pd" to four
bean names. That is the same mistake as pinning a model id (§3ae) or typing an
ICD code from memory (§3ad): it covers only the condition someone happened to
think of, it cannot say WHY, it has no source, it never improves, and it goes
stale silently. ALAFIA has thousands of possible diagnoses; a dict will never
hold sickle cell, coeliac, gout, phenylketonuria, hereditary fructose
intolerance and the rest.

So facts are RESOLVED once and stored here with their provenance — the same
"look it up once, remember it after" shape as `learned_food_nutrients` (§3c) —
and refined per patient in `UserMemory`.

A trigger is NOT an allergy. An allergy is immune-mediated and belongs to the
patient's profile; favism is enzymatic and follows from the diagnosis; coeliac
is autoimmune. They are enforced alike but must be EXPLAINED differently, so
`relation` and `mechanism` are carried separately rather than collapsed into
one "forbidden" list.
"""

from datetime import datetime, timezone

from sqlalchemy import String, Float, Integer, DateTime, Boolean, Text, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ConditionNutritionFact(Base):
    """One food/nutrient relationship for one condition, with its evidence."""

    __tablename__ = "condition_nutrition_facts"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # ── What condition ────────────────────────────────────────────────
    # Normalised lookup key ("g6pd deficiency", "coeliac disease"). Conditions
    # arrive spelled many ways — the production record carries "G6PD
    # Deficitency" — so matching is on this, never on the display label.
    condition_key: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    condition_label: Mapped[str] = mapped_column(String(300), nullable=False)
    # ICD-11 when we have it. The catalog is authoritative (§3ad) and lets the
    # same facts serve a condition however the patient's row spells it.
    icd11_code: Mapped[str | None] = mapped_column(String(20), index=True)

    # ── What it says about food ───────────────────────────────────────
    # "avoid" | "favour". Both directions matter: a plan that only removes
    # things is a restriction list, not nutrition advice.
    relation: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    # "food" | "nutrient" | "ingredient" — a nutrient subject ("folate") is
    # resolved to actual foods through the MCP composition tools at use time,
    # so the advice survives a patient's cuisine and what they can buy.
    subject_kind: Mapped[str] = mapped_column(String(16), nullable=False, default="food")
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    subject_normalized: Mapped[str] = mapped_column(String(200), nullable=False, index=True)

    # ── Why — a guard that cannot explain itself gets blamed (§3aj) ────
    # "triggers acute haemolysis (favism)" / "supports erythropoiesis".
    mechanism: Mapped[str | None] = mapped_column(Text)
    rationale: Mapped[str | None] = mapped_column(Text)

    # ── How much to trust it ──────────────────────────────────────────
    # "high" | "moderate" | "low" | "expert_opinion" — mirrors GlobalKnowledge.
    evidence_level: Mapped[str] = mapped_column(String(20), default="moderate")
    source: Mapped[str | None] = mapped_column(String(300))
    # "llm" | "clinician" | "patient_feedback" | "seed". Never blank: a fact
    # whose origin is unknown cannot be audited or retired.
    provenance: Mapped[str] = mapped_column(String(32), nullable=False, default="llm")
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    times_confirmed: Mapped[int] = mapped_column(Integer, default=1)

    # Retire a fact without deleting it, so a bad resolution can be traced.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        # One row per (condition, direction, subject). Re-resolving the same
        # condition must sharpen the existing fact rather than duplicate it —
        # the failure mode §3ab records for lab imports.
        UniqueConstraint("condition_key", "relation", "subject_normalized",
                         name="uq_condition_relation_subject"),
        Index("idx_condition_relation", "condition_key", "relation", "is_active"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (f"<ConditionNutritionFact {self.condition_key} "
                f"{self.relation} {self.subject!r} ({self.provenance})>")
