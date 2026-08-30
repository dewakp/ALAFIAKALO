"""Clinical thresholds become data, seeded from the published bands.

Every trapezoid bound HEBCS used lived as a constant in `hebcs_engine`. A
constant applies to everybody: the albumin band said 4.0-5.0 while the reporting
lab said 3.2-4.8, and the BUN band once used 21 — the adult female ceiling — on
a male patient. Across millions of patients that is wrong for most of them.

The rows here are seeded FROM the existing published definitions, so nothing
changes behaviour on the way in. What changes is that they can now be corrected
for a lab, a population or a guideline revision without a deploy, and each
carries the source of its number.

Revision ID: tt001_clinical_thresholds
Revises: ss001_food_category
"""

import sqlalchemy as sa
from alembic import op

revision = "tt001_clinical_thresholds"
down_revision = "ss001_food_category"
branch_labels = None
depends_on = None


def upgrade() -> None:
    table = op.create_table(
        "clinical_thresholds",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("analyte", sa.String(120), nullable=False),
        sa.Column("crit_low", sa.Float(), nullable=True),
        sa.Column("opt_low", sa.Float(), nullable=True),
        sa.Column("opt_high", sa.Float(), nullable=True),
        sa.Column("crit_high", sa.Float(), nullable=True),
        sa.Column("sex", sa.String(10), nullable=True),
        sa.Column("age_min", sa.Integer(), nullable=True),
        sa.Column("age_max", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(200), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("analyte", "sex", "age_min", "age_max",
                            name="uq_clinical_threshold_scope"),
    )
    op.create_index("ix_clinical_thresholds_analyte", "clinical_thresholds", ["analyte"])

    # Seeded from the framework's own published bands so the migration is
    # behaviour-preserving. Lab-reported ranges override these at read time.
    published = "HEBCS ESRD framework (J-BHI 2026) published band"
    kdoqi = "NKF-KDOQI clinical practice guideline"
    op.bulk_insert(table, [
        {"analyte": "Glucose", "crit_low": 50, "opt_low": 70, "opt_high": 140,
         "crit_high": 400, "source": published},
        {"analyte": "Sodium", "crit_low": 120, "opt_low": 135, "opt_high": 145,
         "crit_high": 160, "source": published},
        {"analyte": "Potassium", "crit_low": 2.5, "opt_low": 3.5, "opt_high": 5.5,
         "crit_high": 6.5, "source": published},
        {"analyte": "CO2 (Bicarbonate)", "crit_low": 15, "opt_low": 22,
         "opt_high": 28, "crit_high": 35, "source": published},
        {"analyte": "Hemoglobin", "crit_low": 7, "opt_low": 10, "opt_high": 12,
         "crit_high": 18, "source": published},
        {"analyte": "Albumin", "crit_low": 1.5, "opt_low": 4.0, "opt_high": 5.0,
         "crit_high": None, "source": published},
        {"analyte": "BUN", "crit_low": 3, "opt_low": 7, "opt_high": 20,
         "crit_high": 40, "source": "General adult reference range, fallback only"},
        # Guideline TARGETS, not lab reference ranges — a lab never prints a
        # reference range for Kt/V or URR, so these have no other source.
        {"analyte": "KtV (Dialysis Adequacy)", "crit_low": 0.8, "opt_low": 1.4,
         "opt_high": 1.8, "crit_high": None,
         "source": f"{kdoqi}: single-pool Kt/V target >= 1.4"},
        {"analyte": "URR (Urea Reduction Ratio)", "crit_low": 40, "opt_low": 65,
         "opt_high": 80, "crit_high": None,
         "source": f"{kdoqi}: urea reduction ratio target >= 65%"},
        {"analyte": "CaxP Product", "crit_low": None, "opt_low": 0,
         "opt_high": 55.0, "crit_high": 80.0,
         "source": f"{kdoqi}: calcium-phosphorus product < 55"},
    ])


def downgrade() -> None:
    op.drop_index("ix_clinical_thresholds_analyte", table_name="clinical_thresholds")
    op.drop_table("clinical_thresholds")
