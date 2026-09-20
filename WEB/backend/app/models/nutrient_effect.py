"""What an AGENT does to a NUTRIENT — resolved once, remembered, never typed in.

An agent is anything a patient is exposed to that can move a nutrient total: a
treatment, a medication, a condition, a supplement, a herb. The mechanism is the
same in every case, so the representation is too — which is the whole point.
Waiting for someone to name each case is what froze the previous design at four
solutes plus a bolted-on fifth.

See the migration (`ah001_nutrient_effects`) for why this exists and what it
replaces. Two rules matter most at the call site:

1. **This holds RATE- and DOSE-driven effects, not gradient transfer.**
   `dialysis_balance` stays the specialist path for the four solutes that have a
   serum draw and a bath concentration. Anything without those — glucose,
   thiamine, folate, zinc — can only ever be rate-driven, and belongs here.

2. **Gating is about false reassurance, not about sign.** An effect that moves a
   nutrient toward "you are fine" (a limit lowered, a target raised) needs a
   recent measurement behind it. One that moves toward "you need more" or "you
   are over" applies unconditionally. `requires_measurement` carries it.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    String, Float, Integer, DateTime, Boolean, Text, Index, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


# ── Agent kinds ───────────────────────────────────────────────────────
AGENT_TREATMENT = "treatment"      # hemodialysis, peritoneal dialysis, chemo
AGENT_MEDICATION = "medication"    # resolved against RxNorm (§3aj)
AGENT_CONDITION = "condition"      # resolved against ICD-11 (§3ad)
AGENT_SUPPLEMENT = "supplement"
AGENT_HERB = "herb"
AGENT_PROCEDURE = "procedure"

# ── Directions ────────────────────────────────────────────────────────
#: Delivered without being eaten — dialysate dextrose, bath calcium, IV iron.
ADDS = "adds"
#: Taken out of the body — amino acids in the effluent, vitamins stripped.
REMOVES = "removes"
#: Subtracts what the patient DID eat, before absorption. A phosphate binder is
#: the case `med_nutrient_profiles` structurally cannot express: its contract is
#: "how much ONE unit delivers", so calcium carbonate credits its calcium and
#: silently ignores the dietary phosphorus it removes.
BINDS_DIETARY = "binds_dietary"
#: Reduces the fraction absorbed — calcium against iron, tannins against iron.
BLOCKS_ABSORPTION = "blocks_absorption"
#: Moves the goal itself rather than the total: steroids raise glucose handling
#: needs; dialysis raises the protein target (KDOQI ~1.2 g/kg).
INCREASES_REQUIREMENT = "increases_requirement"

# ── Bases ─────────────────────────────────────────────────────────────
PER_SESSION = "per_session"
PER_DOSE_UNIT = "per_dose_unit"
PER_G_DIETARY = "per_g_dietary"
PER_LITRE_DIALYSATE = "per_litre_dialysate"
FRACTION_OF_INTAKE = "fraction_of_intake"


class NutrientEffect(Base):
    """One (agent → nutrient) relationship, with its size, basis and evidence."""

    __tablename__ = "nutrient_effects"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # ── What is acting ────────────────────────────────────────────────
    agent_kind: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    #: Normalised key. Agents arrive spelled many ways, so matching is on this
    #: and never on the display label.
    agent_key: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    agent_label: Mapped[str] = mapped_column(String(300), nullable=False)
    #: RxNorm rxcui / ICD-11 code / therapy_type. The authority decides
    #: identity; our spelling does not.
    agent_code: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)

    # ── What it moves ─────────────────────────────────────────────────
    #: A key from `app/core/nutrition_data.NUTRIENT_CATALOG`. A value outside
    #: that catalog cannot reach a total and must be rejected at write time —
    #: storing one would be a fact nothing can ever apply.
    nutrient_key: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String(24), nullable=False, index=True)

    # ── How much, and per what ────────────────────────────────────────
    magnitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    magnitude_unit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    #: Without a basis a magnitude means nothing: "9 g" is a per-session loss,
    #: "0.4" is a binding ratio per gram of dietary phosphorus.
    basis: Mapped[str] = mapped_column(String(32), nullable=False)
    dose_unit: Mapped[str | None] = mapped_column(String(24), nullable=True)

    # ── Scaling, exactly as the protein prior already scales ──────────
    #: Protein: 9 g/session × (dialysate_volume_l / 30.0), clamped 0.5–2.0.
    #: Carrying these as columns is what lets the migration reproduce today's
    #: numbers rather than approximate them.
    scales_with: Mapped[str | None] = mapped_column(String(40), nullable=True)
    scale_reference: Mapped[float | None] = mapped_column(Float, nullable=True)
    scale_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    scale_max: Mapped[float | None] = mapped_column(Float, nullable=True)

    # ── Why ───────────────────────────────────────────────────────────
    mechanism: Mapped[str | None] = mapped_column(Text, nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── How much to trust it ──────────────────────────────────────────
    evidence_level: Mapped[str] = mapped_column(String(20), default="moderate", nullable=False)
    source: Mapped[str | None] = mapped_column(String(300), nullable=True)
    provenance: Mapped[str] = mapped_column(String(32), default="llm", nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    #: Independent re-derivation of the same fact is evidence for it.
    times_confirmed: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # ── Safety ────────────────────────────────────────────────────────
    #: True when crediting this would move the patient toward "you are fine".
    requires_measurement: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        UniqueConstraint("agent_kind", "agent_key", "nutrient_key", "direction",
                         name="uq_nutrient_effect_agent_nutrient_direction"),
        Index("ix_nutrient_effects_agent", "agent_kind", "agent_key", "is_active"),
        Index("ix_nutrient_effects_nutrient", "nutrient_key", "direction", "is_active"),
    )
