"""nutrient_effects: what an AGENT does to a nutrient, learned and stored

Anything a patient is exposed to can move a nutrient total, in one of a few
mechanisms — and only two of them were ever modelled. Food contains nutrients
(resolved by the estimator ladder). Dialysis moves four solutes (a gradient
model). Everything else was invisible:

  * a treatment ADDS what was never eaten — PD dialysate is glucose-based and
    delivers hundreds of absorbed kcal; HD bath calcium already crosses in;
  * a treatment STRIPS micronutrients — water-soluble vitamins, trace elements;
  * a medication BINDS dietary nutrient — a phosphate binder subtracts the
    phosphorus the patient actually ate. `med_nutrient_profiles` cannot express
    this at all: its contract is "how much of each nutrient ONE unit delivers",
    strictly additive, so calcium carbonate credits calcium and ignores the
    phosphorus it removes;
  * a medication DEPLETES — loop diuretics waste potassium and magnesium, PPIs
    impair B12, metformin impairs B12;
  * something BLOCKS ABSORPTION — calcium against iron, tannins against iron;
  * a condition or treatment RAISES the requirement itself.

WHY A STORE AND NOT A TABLE
---------------------------
The enumeration tax is visible in the code this replaces. Adding protein as a
fifth dialysis analyte cost three separate edits: a `GOAL_KEY` entry, a bespoke
`elif analyte == PROTEIN`, and an inline unit hack. Glucose would cost the same
three. Every new clinical fact charged a code change, so the set of facts froze
at whatever someone had thought of — which is the mistake §3ad (never type an
ICD code from memory), §3c (do not add aliases) and §3an (a nine-line dict of
condition→food) each already paid for.

So effects are RESOLVED once per (agent, nutrient, direction) and remembered,
with mechanism, evidence and provenance — the same "look it up once, remember
it after" shape as `learned_food_nutrients` and `condition_nutrition_facts`.
Re-resolution SHARPENS the row (`times_confirmed`, `confidence`) rather than
inserting beside it (§3ab: a re-import that inserts beside the row it meant to
correct leaves the patient holding two contradictory facts).

TWO MECHANISMS, DELIBERATELY SEPARATED
--------------------------------------
`dialysis_balance` is a physics model: saturation, sieving, diffusible fraction,
per-ion conversions from atomic weight and valence. It needs a serum draw and a
bath concentration, and `SerumLevels` carries exactly four analytes — so
potassium, phosphorus, magnesium and calcium can be gradient-computed and
NOTHING ELSE EVER CAN. Glucose, thiamine, folate and zinc have no serum draw
here and never will.

This table holds the OTHER kind: rate- and dose-driven effects, which need no
gradient at all. That distinction is not invented here — it is already in the
code, badly. Protein's coefficient row is
`Coefficients(saturation=0.0, sieving=0.0, diffusible_fraction=0.0,
grams_per_session=9.0)`: every physics parameter zeroed to disable the physics,
with a flat per-session constant bolted on because there was nowhere else to put
it. Protein is this table's first row, and migrating it must reproduce today's
numbers exactly or it is a rewrite rather than a migration.

GATING IS ABOUT FALSE REASSURANCE, NOT ABOUT SIGN
-------------------------------------------------
`_gate_removal` says a removal must be justified because "crediting a removal
lowers a total and therefore looks like room to eat more", while a gain "needs
no permission". But protein — a removal — is deliberately NOT gated, because
lowering a TARGET's achieved value tells the patient to eat more, which is the
safe direction. The real rule, computable from each goal's own `kind`:

    ↓ a LIMIT   (potassium cleared)      → creates headroom      → GATE
    ↑ a LIMIT   (dextrose → sugar)       → tightens the budget   → apply
    ↓ a TARGET  (protein lost)           → eat more              → apply
    ↑ a TARGET  (IV iron → iron)         → "you are fine"        → GATE

That last row has no implementation anywhere today, and it is the dangerous one:
crediting Venofer against an iron target would tell an anaemic patient they had
met their needs. `requires_measurement` carries that decision per effect.

Additive only (canon §3ao): one new table, no drops, no alterations.

Revision ID: ah001_nutrient_effects
Revises: ag001_inference_corpus
"""

from alembic import op
import sqlalchemy as sa


revision = "ah001_nutrient_effects"
down_revision = "ag001_inference_corpus"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "nutrient_effects",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),

        # ── WHAT is acting ────────────────────────────────────────────
        # treatment | medication | condition | supplement | herb | procedure.
        # One vocabulary, because the consumer asks "what is this patient
        # exposed to today" and must not care which table it came from.
        sa.Column("agent_kind", sa.String(24), nullable=False, index=True),
        # Normalised lookup key. Agents arrive spelled many ways — the
        # production record carries "G6PD Deficitency" — so matching is on
        # this, never on the display label (§3an).
        sa.Column("agent_key", sa.String(200), nullable=False, index=True),
        sa.Column("agent_label", sa.String(300), nullable=False),
        # RxNorm rxcui for a drug, ICD-11 for a condition, therapy_type for a
        # treatment. The authority decides identity, not our spelling (§3aj).
        sa.Column("agent_code", sa.String(40), nullable=True, index=True),

        # ── WHAT it moves ─────────────────────────────────────────────
        # MUST be a key from app/core/nutrition_data.NUTRIENT_CATALOG (116
        # entries). The vocabulary was never the constraint — thiamine is
        # already a column and a catalog entry; only resolution was missing.
        sa.Column("nutrient_key", sa.String(60), nullable=False, index=True),
        # adds | removes | binds_dietary | blocks_absorption | increases_requirement
        sa.Column("direction", sa.String(24), nullable=False, index=True),

        # ── HOW MUCH, and per what ────────────────────────────────────
        sa.Column("magnitude", sa.Float(), nullable=True),
        sa.Column("magnitude_unit", sa.String(16), nullable=True),
        # per_session | per_dose_unit | per_g_dietary | per_litre_dialysate |
        # fraction_of_intake. Without the basis a magnitude is meaningless:
        # "9 g" is a session's loss, "0.4" is a binding ratio.
        sa.Column("basis", sa.String(32), nullable=False),
        sa.Column("dose_unit", sa.String(24), nullable=True),

        # ── Scaling, as the protein prior already does it ─────────────
        # Protein is 9 g/session scaled by dialysate volume against a 30 L
        # reference and clamped to 0.5–2.0×. Carrying those as columns is what
        # makes the migration faithful rather than approximate.
        sa.Column("scales_with", sa.String(40), nullable=True),
        sa.Column("scale_reference", sa.Float(), nullable=True),
        sa.Column("scale_min", sa.Float(), nullable=True),
        sa.Column("scale_max", sa.Float(), nullable=True),

        # ── WHY — a guard that cannot explain itself gets blamed (§3aj) ─
        sa.Column("mechanism", sa.Text(), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),

        # ── How much to trust it ──────────────────────────────────────
        sa.Column("evidence_level", sa.String(20), nullable=False, server_default="moderate"),
        sa.Column("source", sa.String(300), nullable=True),
        # llm | clinician | literature_prior | seed | patient_feedback. Never
        # blank: a fact whose origin is unknown cannot be audited or retired.
        sa.Column("provenance", sa.String(32), nullable=False, server_default="llm"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("times_confirmed", sa.Integer(), nullable=False, server_default="1"),

        # ── Safety ────────────────────────────────────────────────────
        # True when crediting this effect would move the patient toward "you
        # are fine" — a limit lowered or a target raised. Those need a recent
        # measurement behind them; the others apply unconditionally.
        sa.Column("requires_measurement", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),

        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
    )

    # Re-resolution must CONVERGE on one row, not insert beside it (§3ab).
    op.create_unique_constraint(
        "uq_nutrient_effect_agent_nutrient_direction",
        "nutrient_effects",
        ["agent_kind", "agent_key", "nutrient_key", "direction"],
    )
    # "everything this agent does" — the per-day lookup.
    op.create_index(
        "ix_nutrient_effects_agent",
        "nutrient_effects", ["agent_kind", "agent_key", "is_active"],
    )
    # "everything that touches this nutrient" — the explain-my-total query.
    op.create_index(
        "ix_nutrient_effects_nutrient",
        "nutrient_effects", ["nutrient_key", "direction", "is_active"],
    )


def downgrade() -> None:
    op.drop_index("ix_nutrient_effects_nutrient", table_name="nutrient_effects")
    op.drop_index("ix_nutrient_effects_agent", table_name="nutrient_effects")
    op.drop_constraint(
        "uq_nutrient_effect_agent_nutrient_direction",
        "nutrient_effects", type_="unique",
    )
    op.drop_table("nutrient_effects")
