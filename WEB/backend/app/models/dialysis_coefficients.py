"""Per-patient dialysis solute-transfer coefficients, and how well they predict.

The transfer model in `app/services/dialysis_balance.py` ships literature priors.
These rows replace them with values fitted to one patient's own serum by
`ML/scripts/fit_dialysis_coefficients.py`.

`beats_baseline` is the field that matters. A coefficient is only allowed to
widen a dietary limit if, on a **chronological hold-out**, it predicted that
patient's post-dialysis bloods better than assuming nothing changed. Storing the
score next to the coefficient means the runtime can ask "is this trustworthy?"
instead of assuming it, and an analyte that failed keeps its prior and is
treated as uncalibrated.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DialysisSoluteCoefficient(Base):
    """One analyte's fitted transfer parameters for one patient."""

    __tablename__ = "dialysis_solute_coefficients"
    __table_args__ = (
        UniqueConstraint("user_id", "analyte", name="uq_dialysis_coeff_user_analyte"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    #: potassium | phosphorus | magnesium | calcium | protein
    analyte: Mapped[str] = mapped_column(String(30), nullable=False, index=True)

    #: Serum-unit change per mg transferred. Absorbs both membrane saturation
    #: and 1/volume-of-distribution — only their ratio is observable from a
    #: concentration change, so fitting them separately would be ill-posed.
    alpha: Mapped[float] = mapped_column(Float, nullable=False)
    #: alpha re-expressed as a volume, kept because it is the sanity check a
    #: clinician can read: urea's should land near total body water.
    implied_volume_l: Mapped[float | None] = mapped_column(Float)

    #: "direct" (explicit post value) | "derived-post" (identified by drawing
    #: facility and day) | "interdialytic" (across consecutive draws).
    method: Mapped[str] = mapped_column(String(30), nullable=False)

    n_fit: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    n_holdout: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    holdout_mae: Mapped[float | None] = mapped_column(Float)
    baseline_mae: Mapped[float | None] = mapped_column(Float)
    holdout_bias: Mapped[float | None] = mapped_column(Float)

    #: False ⇒ this coefficient must not be used to widen a limit.
    beats_baseline: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    fitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    @property
    def trustworthy(self) -> bool:
        """Fitted, validated, and on enough observations to mean anything."""
        return bool(self.beats_baseline) and self.n_holdout >= 8
