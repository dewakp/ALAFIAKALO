# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""A nutrient quota is DATA with a citation, not a branch in the source.

`compute_goals` is a hand-written ladder: 13 nutrients, 6 condition flags, 26
`flags[...]` reads, a literal at every leaf. Calcium had no branch at all, so
every patient received the bone-health RDA as a target to aim FOR — including
a dialysis patient whose calcium load is mostly their phosphate binder, and a
patient whose parathyroid glands have been removed.

Adding a 16th branch would not have fixed it. Measured on 2026-10-05:
35,369 ICD-11 MMS codes x 116 catalog nutrients is ~4.1M single-condition
cells before any combination, and age, sex, weight and height are continuous.
The literature does not enumerate it either — EFSA's DRVs are
healthy-population only, ESPEN ships 14 disease guidelines as prose, the
Academy's EAL has ~40 projects, and no body publishes per-condition nutrient
quotas as machine-readable data. There is nothing to import, so quotas are
resolved once, cited, and stored.

`condition_nutrient_quotas` is the store. Seeded here with the calcium rows
actually measured from their guidelines on 2026-10-05, each carrying the
sentence it came from — the same discipline an001 used for the vital-sign
bands, and the reason `cited_text` is NOT NULL.

Note what the seed makes expressible that the ladder could not:

  - CKD's figure is TOTAL ELEMENTAL calcium and counts calcium-based binders
    (`includes_supplements=true`). A patient told to "reach 800 mg" while
    taking 1,500 mg of calcium carbonate is being told the opposite of the
    guideline.
  - CKD G5D has NO number in KDOQI 2020 or in KDIGO 2009/2017 — so no G5D row
    is seeded. An absent quota is the honest answer, and the resolver leaves
    the nutrient UNSCOPED rather than inventing a figure for it.
  - Hungry bone syndrome is a TAPER, not a constant (`time_course`).
  - Hypoparathyroidism carries a PER-DOSE ceiling beside its daily target,
    because intestinal absorption saturates around 500 mg per ingestion.
  - Calcium oxalate stones say explicitly do NOT restrict, which is the
    opposite direction from the renal rows and would be invisible in any
    scheme that only ever lowers a figure.

Additive only: one new table and its seed rows. Nothing is dropped, altered
or rewritten (§3ao — autogenerate proposed dropping five live tables).
"""

import sqlalchemy as sa
from alembic import op

revision = "ap001_nutrient_quotas"
down_revision = "ao001_hospital_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "condition_nutrient_quotas",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("condition_key", sa.String(length=200), nullable=False),
        sa.Column("condition_label", sa.String(length=300), nullable=False),
        sa.Column("icd11_code", sa.String(length=20), nullable=True),
        sa.Column("subject", sa.String(length=160), nullable=False),
        sa.Column("subject_normalized", sa.String(length=120), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(length=16), nullable=False),
        sa.Column("basis", sa.String(length=20), nullable=False,
                  server_default="absolute"),
        sa.Column("includes_supplements", sa.Boolean(), nullable=False,
                  server_default="false"),
        sa.Column("time_course", sa.Text(), nullable=True),
        sa.Column("scope_key", sa.String(length=200), nullable=False,
                  server_default=""),
        sa.Column("stage", sa.String(length=60), nullable=True),
        sa.Column("therapy", sa.String(length=160), nullable=True),
        sa.Column("sex", sa.String(length=10), nullable=True),
        sa.Column("age_min", sa.Integer(), nullable=True),
        sa.Column("age_max", sa.Integer(), nullable=True),
        # The citation is part of the row, not an annotation on it.
        sa.Column("source", sa.String(length=300), nullable=False),
        sa.Column("citation_url", sa.Text(), nullable=True),
        sa.Column("cited_text", sa.Text(), nullable=False),
        sa.Column("evidence_level", sa.String(length=20), nullable=True,
                  server_default="moderate"),
        sa.Column("provenance", sa.String(length=32), nullable=False,
                  server_default="llm"),
        sa.Column("confidence", sa.Float(), nullable=True, server_default="0.5"),
        sa.Column("times_confirmed", sa.Integer(), nullable=True,
                  server_default="1"),
        sa.Column("is_active", sa.Boolean(), nullable=False,
                  server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        # Scope is in the key as a NON-NULL string: Postgres treats NULLs as
        # distinct, so a unique key over the nullable stage/therapy columns
        # would let re-resolution insert beside the row it meant to sharpen.
        sa.UniqueConstraint("condition_key", "subject_normalized", "kind",
                            "basis", "scope_key",
                            name="uq_condition_nutrient_quota"),
    )
    op.create_index("ix_condition_nutrient_quotas_condition_key",
                    "condition_nutrient_quotas", ["condition_key"])
    op.create_index("ix_condition_nutrient_quotas_subject_normalized",
                    "condition_nutrient_quotas", ["subject_normalized"])
    op.create_index("ix_condition_nutrient_quotas_icd11_code",
                    "condition_nutrient_quotas", ["icd11_code"])
    op.create_index("ix_condition_nutrient_quotas_created_at",
                    "condition_nutrient_quotas", ["created_at"])
    op.create_index("idx_quota_condition_active", "condition_nutrient_quotas",
                    ["condition_key", "is_active"])
    op.create_index("idx_quota_subject_active", "condition_nutrient_quotas",
                    ["subject_normalized", "is_active"])

    quotas = sa.table(
        "condition_nutrient_quotas",
        sa.column("condition_key", sa.String),
        sa.column("condition_label", sa.String),
        sa.column("subject", sa.String),
        sa.column("subject_normalized", sa.String),
        sa.column("kind", sa.String),
        sa.column("amount", sa.Float),
        sa.column("unit", sa.String),
        sa.column("basis", sa.String),
        sa.column("includes_supplements", sa.Boolean),
        sa.column("time_course", sa.Text),
        sa.column("scope_key", sa.String),
        sa.column("stage", sa.String),
        sa.column("therapy", sa.String),
        sa.column("source", sa.String),
        sa.column("citation_url", sa.Text),
        sa.column("cited_text", sa.Text),
        sa.column("evidence_level", sa.String),
        sa.column("provenance", sa.String),
        sa.column("confidence", sa.Float),
    )

    _KDOQI = "KDOQI Clinical Practice Guideline for Nutrition in CKD: 2020 Update"
    _KDOQI_URL = "https://www.ajkd.org/article/S0272-6386(20)30726-5/fulltext"
    _EU = ("Recommended calcium intake in adults and children with chronic "
           "kidney disease — a European consensus statement (NDT 2024)")
    _EU_URL = "https://academic.oup.com/ndt/article/39/2/341/7269225"

    op.bulk_insert(quotas, [
        # ── CKD 3-4, not on an active vitamin D analog ───────────────
        {
            "condition_key": "chronic kidney disease",
            "condition_label": "Chronic kidney disease",
            "subject": "total elemental calcium",
            "subject_normalized": "calcium_mg",
            "kind": "target", "amount": 800.0, "unit": "mg",
            "basis": "absolute", "includes_supplements": True,
            "time_course": None,
            "scope_key": "stage=3-4|therapy=no_active_vitamin_d_analog",
            "stage": "3-4", "therapy": "no_active_vitamin_d_analog",
            "source": _KDOQI, "citation_url": _KDOQI_URL,
            "cited_text": (
                "In adults with CKD 3-4 not taking active vitamin D analogs, we "
                "suggest that a total elemental calcium intake of 800-1,000 mg/d "
                "(including dietary calcium, calcium supplementation, and "
                "calcium-based phosphate binders) be prescribed to maintain a "
                "neutral calcium balance."),
            "evidence_level": "moderate", "provenance": "guideline_seed",
            "confidence": 0.8,
        },
        # ── CKD, any stage: the ceiling ──────────────────────────────
        {
            "condition_key": "chronic kidney disease",
            "condition_label": "Chronic kidney disease",
            "subject": "total elemental calcium",
            "subject_normalized": "calcium_mg",
            "kind": "limit", "amount": 1500.0, "unit": "mg",
            "basis": "absolute", "includes_supplements": True,
            "time_course": None,
            "scope_key": "", "stage": None, "therapy": None,
            "source": _EU, "citation_url": _EU_URL,
            "cited_text": (
                "In adults with CKD, we suggest not to exceed a total elemental "
                "calcium intake of 1500 mg/day to avoid hypercalcemia and risk "
                "of vascular calcification."),
            # The authors state these are clinical practice points without
            # high-level evidence. Recorded as they described it, not upgraded.
            "evidence_level": "expert_opinion", "provenance": "guideline_seed",
            "confidence": 0.7,
        },
        {
            "condition_key": "chronic kidney disease",
            "condition_label": "Chronic kidney disease",
            "subject": "total elemental calcium",
            "subject_normalized": "calcium_mg",
            "kind": "target", "amount": 800.0, "unit": "mg",
            "basis": "absolute", "includes_supplements": True,
            "time_course": None,
            "scope_key": "stage=any", "stage": "any", "therapy": None,
            "source": _EU, "citation_url": _EU_URL,
            "cited_text": (
                "In adults with CKD, we suggest a minimum total elemental "
                "calcium intake of 800-1000 mg/day to maintain a neutral "
                "calcium balance."),
            "evidence_level": "expert_opinion", "provenance": "guideline_seed",
            "confidence": 0.7,
        },
        # ── Hungry bone syndrome: a taper, not a constant ────────────
        {
            "condition_key": "hungry bone syndrome",
            "condition_label": "Hungry bone syndrome",
            "subject": "elemental calcium",
            "subject_normalized": "calcium_mg",
            "kind": "target", "amount": 3200.0, "unit": "mg",
            "basis": "absolute", "includes_supplements": True,
            "time_course": (
                "Secondary hyperparathyroidism: ~3.2 g/day in week 1, "
                "decreasing to ~2.4 g/day by week 6. Severe cases require "
                "intravenous replacement initially."),
            "scope_key": "therapy=post_parathyroidectomy",
            "stage": None, "therapy": "post_parathyroidectomy",
            "source": ("Hungry Bone Syndrome After Parathyroidectomy for "
                       "Secondary Hyperparathyroidism: Pathogenesis and "
                       "Contemporary Clinical Considerations"),
            "citation_url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC12525365/",
            "cited_text": (
                "For patients with secondary hyperparathyroidism the calcium "
                "requirement is 3.2 g at week one and gradually decreasing to "
                "about 2.4 g at week six."),
            "evidence_level": "low", "provenance": "guideline_seed",
            "confidence": 0.6,
        },
        # ── Chronic hypoparathyroidism: daily target ... ─────────────
        {
            "condition_key": "hypoparathyroidism",
            "condition_label": "Chronic hypoparathyroidism",
            "subject": "elemental calcium",
            "subject_normalized": "calcium_mg",
            "kind": "target", "amount": 2000.0, "unit": "mg",
            "basis": "absolute", "includes_supplements": True,
            "time_course": None,
            "scope_key": "", "stage": None, "therapy": None,
            "source": ("European Society of Endocrinology Clinical Guideline: "
                       "Treatment of chronic hypoparathyroidism in adults"),
            "citation_url": ("https://www.ese-hormones.org/media/ap3ljdqc/"
                             "ese-clinical-guideline_-treatment-of-chronic-"
                             "hypoparathyroidism-in-adults.pdf"),
            "cited_text": (
                "Patients with hypoparathyroidism are most often recommended to "
                "use calcium supplements in a total daily dose of 800-2000 mg of "
                "elemental calcium, although sometimes higher doses are used."),
            "evidence_level": "moderate", "provenance": "guideline_seed",
            "confidence": 0.75,
        },
        # ── ... and its PER-DOSE ceiling, which a daily figure hides ─
        {
            "condition_key": "hypoparathyroidism",
            "condition_label": "Chronic hypoparathyroidism",
            "subject": "elemental calcium per ingestion",
            "subject_normalized": "calcium_mg",
            "kind": "limit", "amount": 500.0, "unit": "mg",
            "basis": "per_dose", "includes_supplements": True,
            "time_course": None,
            "scope_key": "", "stage": None, "therapy": None,
            "source": ("European Society of Endocrinology Clinical Guideline: "
                       "Treatment of chronic hypoparathyroidism in adults"),
            "citation_url": ("https://www.ese-hormones.org/media/ap3ljdqc/"
                             "ese-clinical-guideline_-treatment-of-chronic-"
                             "hypoparathyroidism-in-adults.pdf"),
            "cited_text": (
                "The absorptive capacity of the intestine is probably saturated "
                "by intake of a dose of approximately 500 mg of calcium in one "
                "ingestion. This suggests that dividing doses is important for "
                "optimal absorption."),
            "evidence_level": "moderate", "provenance": "guideline_seed",
            "confidence": 0.75,
        },
        # ── Stones: the row that points the OTHER way ────────────────
        {
            "condition_key": "calcium oxalate kidney stones",
            "condition_label": "Calcium oxalate kidney stones",
            "subject": "dietary calcium",
            "subject_normalized": "calcium_mg",
            "kind": "target", "amount": 1000.0, "unit": "mg",
            "basis": "absolute", "includes_supplements": False,
            "time_course": None,
            # scope_key encodes stage and therapy ONLY, exactly as
            # `scope_key_for()` computes it. The age bound lives in `age_max`
            # and is applied by `_applies_to`. Writing "age_max=70" here — as
            # the first version of this seed did — produces a key the
            # normaliser would never generate, so a later re-resolution of
            # this condition computes "" instead, misses this row, and
            # inserts beside it: §3ab's contradictory duplicate, created by
            # the very column added to prevent it.
            "scope_key": "", "stage": None, "therapy": None,
            "source": "Prevention of Recurrent Kidney Stones: a CARI Guidelines Summary",
            "citation_url": "https://www.sciencedirect.com/science/article/pii/S2468024926025775",
            "cited_text": (
                "We strongly recommend achieving the recommended dietary intake "
                "for calcium (1000 mg/d for adults aged < 70 years) for people "
                "with calcium stones, especially those with high urine oxalate. "
                "Dietary calcium should not be restricted, since calcium "
                "combines with oxalate in intestine."),
            "evidence_level": "high", "provenance": "guideline_seed",
            "confidence": 0.85,
        },
    ])


def downgrade() -> None:
    # Every upgrade() in this project's history is additive; this is the one
    # direction a downgrade can take without destroying clinical data, because
    # the table did not exist before.
    op.drop_table("condition_nutrient_quotas")
