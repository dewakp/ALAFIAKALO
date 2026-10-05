# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""Vital-sign bands as DATA, and three more scored domains.

Two things, both of which existed as constants or as nothing at all.

**1. Blood pressure and heart rate had no authority anywhere.**
`health_score.vitals_component` carried its bands as literals in the source:

    if systolic < 130 and diastolic < 80:
        bp_score = 100.0

That is one-sided — it penalises only HIGH pressure — so a dialysis patient
whose latest reading was **81/62 scored 100**, and so would 54/30. On the
reference record this was not hypothetical: the latest self-recorded reading is
81/62, every one of the last eight sits between 79 and 95 systolic, and across
90 days **25 of 37 treatments ended below 90 mmHg systolic, the lowest at 54**.
The score read `Vitals 100/100` throughout.

`clinical_thresholds` is where a band belongs (tt001): a threshold is a fact
about a guideline, and `test_no_hardcoded_thresholds.py` already states the
canon — *no hardcoded data, no exception*. That guard only ever reached
`hebcs_engine`, so these literals sat beside it untouched. Each row below
carries the guideline it came from, so it can be revised without a deploy.

**Why a POST-dialysis band exists separately.** A resting systolic of 95 is
unremarkable; the same figure at the end of a treatment is intradialytic
hypotension, which is the finding. One band cannot express both, so the
post-dialysis reading is judged against its own.

**2. Three domains the score could never see.** `wellness_scores` had six
component columns — nutrition, fitness, sleep, mood, vitals, medication — so
dialysis, symptoms and elimination had nowhere to be stored even once computed.
A patient with 2,032 dialysis sessions had no dialysis contribution to their
wellness score at all.

Additive only: three nullable columns and four threshold rows. Nothing is
dropped or rewritten (§3ao).
"""

import sqlalchemy as sa
from alembic import op

revision = "an001_vital_thresholds"
down_revision = "am001_allergy_terms"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Three component columns, nullable: NULL means "not measured", which is
    # the distinction the whole score rests on. A 0 for a domain nobody looked
    # at is a claim we cannot support.
    op.add_column("wellness_scores",
                  sa.Column("dialysis_score", sa.Float(), nullable=True))
    op.add_column("wellness_scores",
                  sa.Column("symptom_score", sa.Float(), nullable=True))
    op.add_column("wellness_scores",
                  sa.Column("elimination_score", sa.Float(), nullable=True))

    thresholds = sa.table(
        "clinical_thresholds",
        sa.column("analyte", sa.String),
        sa.column("crit_low", sa.Float),
        sa.column("opt_low", sa.Float),
        sa.column("opt_high", sa.Float),
        sa.column("crit_high", sa.Float),
        sa.column("sex", sa.String),
        sa.column("age_min", sa.Integer),
        sa.column("age_max", sa.Integer),
        sa.column("source", sa.String),
        sa.column("is_active", sa.Boolean),
    )

    aha = ("ACC/AHA 2017 Guideline for the Prevention, Detection, Evaluation "
           "and Management of High Blood Pressure in Adults")
    kdoqi = "NKF-KDOQI 2015 Clinical Practice Guideline for Hemodialysis Adequacy"

    op.bulk_insert(thresholds, [
        # Resting blood pressure. The LOW side is the half that was missing:
        # below 90 systolic is hypotension, and on this record it is the
        # patient's ordinary state rather than an outlier.
        {"analyte": "Blood Pressure Systolic",
         "crit_low": 70.0, "opt_low": 90.0, "opt_high": 120.0, "crit_high": 180.0,
         "sex": None, "age_min": None, "age_max": None, "is_active": True,
         "source": f"{aha}: normal 90-120 mmHg systolic; <90 hypotensive, "
                   ">=180 hypertensive crisis"},
        {"analyte": "Blood Pressure Diastolic",
         "crit_low": 40.0, "opt_low": 60.0, "opt_high": 80.0, "crit_high": 120.0,
         "sex": None, "age_min": None, "age_max": None, "is_active": True,
         "source": f"{aha}: normal 60-80 mmHg diastolic; <60 hypotensive, "
                   ">=120 hypertensive crisis"},
        # Heart rate was read by nothing at all. Every one of this patient's
        # last eight readings is 96-109 bpm — sustained tachycardia, sitting
        # beside a systolic in the 80s, and neither reached the score.
        {"analyte": "Heart Rate",
         "crit_low": 40.0, "opt_low": 60.0, "opt_high": 100.0, "crit_high": 150.0,
         "sex": None, "age_min": None, "age_max": None, "is_active": True,
         "source": "AHA: normal resting heart rate 60-100 bpm in adults; "
                   "<40 or >150 requires urgent assessment"},
        # The end of a treatment is judged against its own band. KDOQI defines
        # intradialytic hypotension by an absolute systolic below 90, so that
        # is the lower bound here rather than the resting one.
        {"analyte": "Post-Dialysis Systolic BP",
         "crit_low": 70.0, "opt_low": 90.0, "opt_high": 140.0, "crit_high": 180.0,
         "sex": None, "age_min": None, "age_max": None, "is_active": True,
         "source": f"{kdoqi}: intradialytic hypotension is a systolic below "
                   "90 mmHg; treat a post-treatment reading on its own band"},
    ])


def downgrade() -> None:
    op.execute(
        "DELETE FROM clinical_thresholds WHERE analyte IN "
        "('Blood Pressure Systolic', 'Blood Pressure Diastolic', "
        "'Heart Rate', 'Post-Dialysis Systolic BP')"
    )
    op.drop_column("wellness_scores", "elimination_score")
    op.drop_column("wellness_scores", "symptom_score")
    op.drop_column("wellness_scores", "dialysis_score")
