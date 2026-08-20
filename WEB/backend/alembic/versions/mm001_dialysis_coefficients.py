"""Per-patient dialysis solute-transfer coefficients.

The transfer model ships literature priors. These rows hold values fitted to a
patient's own serum, together with the hold-out score that says whether the
fitted version actually predicted their bloods better than assuming the session
changed nothing.

`beats_baseline` is stored, not just the coefficient, because the runtime has to
be able to ask "is this trustworthy?" before letting a model output alter a
nutrient total. An analyte that failed validation keeps its prior and is
discounted.

Revision ID: mm001_dialysis_coefficients
Revises: ll001_document_imports
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "mm001_dialysis_coefficients"
down_revision: Union[str, None] = "ll001_document_imports"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "dialysis_solute_coefficients",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("analyte", sa.String(length=30), nullable=False),
        sa.Column("alpha", sa.Float(), nullable=False),
        sa.Column("implied_volume_l", sa.Float(), nullable=True),
        sa.Column("method", sa.String(length=30), nullable=False),
        sa.Column("n_fit", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("n_holdout", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("holdout_mae", sa.Float(), nullable=True),
        sa.Column("baseline_mae", sa.Float(), nullable=True),
        sa.Column("holdout_bias", sa.Float(), nullable=True),
        sa.Column("beats_baseline", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("fitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "analyte", name="uq_dialysis_coeff_user_analyte"),
    )
    op.create_index("ix_dialysis_coeff_id", "dialysis_solute_coefficients", ["id"])
    op.create_index("ix_dialysis_coeff_user_id", "dialysis_solute_coefficients", ["user_id"])
    op.create_index("ix_dialysis_coeff_analyte", "dialysis_solute_coefficients", ["analyte"])


def downgrade() -> None:
    op.drop_table("dialysis_solute_coefficients")
