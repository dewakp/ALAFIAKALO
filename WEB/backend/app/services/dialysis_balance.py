"""Solute mass transfer across a dialysis session.

A dialysis day is not a normal day. Potassium and phosphorus leave the body in
gram quantities, amino acids are lost, and — where the bath is richer than the
blood — calcium and magnesium move the *other* way and are gained. Treating a
dialysis day and a rest day as nutritionally identical is wrong in both
directions.

Nothing here touches a database or a patient record: it takes session parameters
and serum concentrations and returns masses, so it can be fitted offline against
a decade of labs and unit-tested without fixtures.

## Why saturation, not Kt/V

The sessions this was built for run ~30 L of dialysate against a blood flow of
~350 mL/min for ~3 hours (low-volume home HD). Dialysate flow is far below blood
flow, so effluent leaves close to equilibrium with plasma and removal is bounded
by *volume and gradient*, not by clearance. Kt/V is the right frame for a
high-flux in-centre machine; for this one it would answer a different question.

## Sign convention

Positive mass = removed from the patient. **Negative = gained**, which is the
normal outcome for calcium against a 3.0 mEq/L bath and is not an error.

Every coefficient here is a literature-derived *prior*. They are replaced by
per-patient values fitted against that patient's own serum
(`ML/scripts/fit_dialysis_coefficients.py`), and an analyte whose fit fails to
beat a naive baseline keeps the prior and is reported as uncalibrated.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

# ── Unit conversion ──────────────────────────────────────────────────────────
#
# Everything is converted to mg per litre and multiplied by litres, so the whole
# model works in milligrams. Getting this wrong is the classic way to be off by
# a factor of 2 (divalent ions) or 10 (mg/dL vs mg/L), so the factors are named
# rather than inlined.

#: mmol → mg for a monovalent ion
_MG_PER_MMOL_K = 39.10
#: mEq → mg. For a divalent ion 1 mEq = ½ mmol, hence the atomic weight halved.
_MG_PER_MEQ_K = 39.10          # monovalent: 1 mEq = 1 mmol
_MG_PER_MEQ_CA = 40.08 / 2     # 20.04
_MG_PER_MEQ_MG = 24.31 / 2     # 12.155

#: mg/dL → mg/L
_DL_PER_L = 10.0

POTASSIUM = "potassium"
PHOSPHORUS = "phosphorus"
MAGNESIUM = "magnesium"
CALCIUM = "calcium"
PROTEIN = "protein"
#: Validation only — urea is not a dietary target.
UREA = "urea"

ANALYTES = (POTASSIUM, PHOSPHORUS, MAGNESIUM, CALCIUM, PROTEIN)

#: A potassium bath outside this band is a recording error, not a prescription.
#: 11 sessions in the corpus carry 45 mEq/L — the *lactate* value written into
#: the potassium column. A 45 mEq/L potassium bath is not survivable, so such a
#: session is excluded rather than modelled.
BATH_K_PLAUSIBLE_MEQ = (0.0, 4.0)

#: Dialysate volume outside this band is a recording error.
DIALYSATE_VOLUME_PLAUSIBLE_L = (5.0, 120.0)

#: NxStage PureFlow lactate bath (RFP-40x). Calcium and magnesium bath
#: concentrations are NOT recorded per session — only volume, lactate and
#: potassium are — so these are assumed, and every calcium/magnesium result
#: says so. If a future flowsheet records them, prefer the record.
DEFAULT_BATH_CALCIUM_MEQ = 3.0
DEFAULT_BATH_MAGNESIUM_MEQ = 1.0

BATH_ASSUMPTION_NOTE = (
    "Bath calcium and magnesium are not recorded for this session; "
    "standard NxStage lactate concentrate is assumed."
)


@dataclass(frozen=True)
class Coefficients:
    """Per-analyte transfer parameters. Priors here; fitted per patient later.

    `diffusible_fraction` is the share of the measured serum concentration that
    can actually cross the membrane. It is the reason calcium behaves the way it
    does: only the ionised half of total calcium is dialysable, so a 3.0 mEq/L
    bath (1.5 mmol/L) sits *above* a normal ionised calcium (~1.2 mmol/L) and
    the patient gains calcium during treatment.
    """

    saturation: float          # effluent equilibration, 0–1
    sieving: float             # convective transport with ultrafiltrate, 0–1
    diffusible_fraction: float # share of measured serum that can cross

    #: Phosphorus only: removal saturates with time (intracellular rebound
    #: limits it), so a 5-hour session does not remove 25% more than a 4-hour
    #: one. `None` for analytes that scale with volume.
    time_constant_min: float | None = None
    max_mass_mg: float | None = None

    #: Protein/amino acids only: a per-session loss, largely independent of the
    #: concentration gradient.
    grams_per_session: float | None = None

    #: How much blood flow governs this solute's removal, 0–1.
    #:
    #: Urea is flow-limited: push blood through faster and more comes out, which
    #: is why Kt/V is written the way it is. Potassium, phosphorus and magnesium
    #: are not — their bottleneck is release from the intracellular pool, and the
    #: membrane is never the constraint. Applying a blood-flow term to them made
    #: the hold-out error *worse* on this patient's own bloods (potassium 0.340 →
    #: 0.344, phosphorus 0.375 → 0.390) while improving urea by 14%.
    flow_sensitivity: float = 1.0

    calibrated: bool = False
    holdout_mae: float | None = None


#: Literature priors. Sources are KDOQI 2020 nutrition guidance and the standard
#: dialysis-kinetics literature; each is a starting point for fitting, not a
#: claim about this patient.
DEFAULT_COEFFICIENTS: dict[str, Coefficients] = {
    # Fully diffusible; effluent leaves near equilibrium at low dialysate flow.
    # Intracellular release is the bottleneck, not the membrane.
    POTASSIUM: Coefficients(saturation=0.85, sieving=1.0, diffusible_fraction=0.98,
                            flow_sensitivity=0.25),
    # Rebound-limited: ~800 mg over a 4 h session, saturating.
    PHOSPHORUS: Coefficients(
        saturation=0.55, sieving=1.0, diffusible_fraction=0.95,
        time_constant_min=110.0, max_mass_mg=1100.0, flow_sensitivity=0.25,
    ),
    # ~70% of serum magnesium is unbound and dialysable.
    MAGNESIUM: Coefficients(saturation=0.75, sieving=1.0, diffusible_fraction=0.70,
                            flow_sensitivity=0.25),
    # ~50% ionised. Against a 3.0 mEq/L bath this normally yields a net GAIN.
    CALCIUM: Coefficients(saturation=0.70, sieving=1.0, diffusible_fraction=0.50,
                          flow_sensitivity=0.25),
    # Not a nutrient. Urea is carried because it is the solute with the most
    # pre/post pairs and is genuinely flow-limited, which makes it the best
    # independent check that the transfer machinery is right.
    UREA: Coefficients(saturation=0.60, sieving=1.0, diffusible_fraction=1.0,
                       flow_sensitivity=1.0),
    # Free amino acid loss; drives the KDOQI 1.2 g/kg dialysis protein target.
    PROTEIN: Coefficients(
        saturation=0.0, sieving=0.0, diffusible_fraction=0.0, grams_per_session=9.0,
    ),
}

#: Reference dialysate volume the protein prior was expressed against.
_REFERENCE_DIALYSATE_L = 30.0

#: Blood flow relative to dialysate flow governs how close the effluent gets to
#: equilibrium with plasma. Volume alone is not enough: run the same 30 L
#: against a poor access at 200 mL/min instead of 350 and less comes out, which
#: is exactly the session a patient needs told about.
#:
#: Half-saturation constant of the Qb:Qd response. Efficiency is normalised so
#: the reference prescription scores 1.0, and only degrades below it — a very
#: high blood flow cannot extract more than the dialysate can carry away.
_FLOW_HALF_RATIO = 0.5
_REFERENCE_QB_QD_RATIO = 350.0 / (30_000.0 / 184.0)   # ≈ 2.15

#: Ceiling on single-pass extraction for a small solute. Removal can never
#: exceed what the blood actually carried through the filter.
_MAX_SINGLE_PASS_EXTRACTION = 0.90


def _flow_efficiency(blood_flow_ml_min: float | None, dialysate_flow_ml_min: float | None) -> float:
    """How completely the dialysate equilibrates, from the Qb:Qd ratio.

    Returns 1.0 at or above the reference prescription and falls off below it.
    Unknown flows return 1.0 — the volume-limited estimate — rather than
    silently penalising a session whose blood flow simply was not recorded.
    """
    if not blood_flow_ml_min or not dialysate_flow_ml_min or dialysate_flow_ml_min <= 0:
        return 1.0

    ratio = blood_flow_ml_min / dialysate_flow_ml_min
    response = ratio / (ratio + _FLOW_HALF_RATIO)
    reference = _REFERENCE_QB_QD_RATIO / (_REFERENCE_QB_QD_RATIO + _FLOW_HALF_RATIO)
    return min(response / reference, 1.0)


@dataclass
class SessionParams:
    """What the machine did. Volumes in litres, time in minutes."""

    dialysate_volume_l: float | None = None          # ordered
    dialysate_delivered_l: float | None = None       # actually run, if known
    duration_minutes: float | None = None
    blood_flow_ml_min: float | None = None
    ultrafiltration_ml: float | None = None
    bath_potassium_meq: float | None = None
    bath_calcium_meq: float | None = None            # rarely recorded
    bath_magnesium_meq: float | None = None          # rarely recorded
    #: Recorded on some flowsheets. Not used by the transfer model because
    #: sodium is not one of the analytes it covers — kept so the record is
    #: complete rather than silently dropped.
    bath_sodium_meq: float | None = None
    completed: bool = True

    @property
    def dialysate_flow_ml_min(self) -> float | None:
        """Qd, derived from volume and duration.

        Low-volume home machines prescribe a total volume rather than a flow
        rate, so Qd has to be computed. This is what makes *duration* matter for
        every analyte rather than only for phosphorus: the same 30 L run over
        two hours is a faster, less efficient dialysate flow than over four.
        """
        volume = self.effective_volume_l
        if not volume or not self.duration_minutes or self.duration_minutes <= 0:
            return None
        return (volume * 1000.0) / self.duration_minutes

    @property
    def blood_volume_processed_l(self) -> float | None:
        """Litres of blood actually passed through the filter (Qb × duration)."""
        if not self.blood_flow_ml_min or not self.duration_minutes:
            return None
        return (self.blood_flow_ml_min * self.duration_minutes) / 1000.0

    @property
    def flow_efficiency(self) -> float:
        return _flow_efficiency(self.blood_flow_ml_min, self.dialysate_flow_ml_min)

    @property
    def effective_volume_l(self) -> float | None:
        """Litres actually run.

        Delivered wins over ordered: a session cut short must not be credited
        with the full prescription, which would overstate removal and hand the
        patient dietary headroom they never earned.
        """
        if self.dialysate_delivered_l is not None:
            return self.dialysate_delivered_l
        return self.dialysate_volume_l

    @property
    def ultrafiltration_l(self) -> float:
        return (self.ultrafiltration_ml or 0.0) / 1000.0


@dataclass
class SerumLevels:
    """Measured concentrations, in the units the labs report them in."""

    potassium_mmol_l: float | None = None   # mmol/L (= mEq/L)
    phosphorus_mg_dl: float | None = None
    magnesium_mg_dl: float | None = None
    calcium_mg_dl: float | None = None
    measured_on: object | None = None       # date; used for the staleness gate


@dataclass
class RemovalEstimate:
    """One analyte's transfer across one session."""

    analyte: str
    mass_mg: float                  # >0 removed, <0 gained
    diffusive_mg: float = 0.0
    convective_mg: float = 0.0
    calibrated: bool = False
    assumptions: list[str] = field(default_factory=list)
    note: str | None = None

    @property
    def is_gain(self) -> bool:
        return self.mass_mg < 0


class SessionNotModellable(ValueError):
    """The session record cannot support an estimate — say so, don't guess."""


def validate_session(session: SessionParams) -> list[str]:
    """Reasons this session cannot be modelled. Empty list = usable."""
    problems: list[str] = []

    volume = session.effective_volume_l
    if volume is None:
        problems.append("No dialysate volume recorded.")
    else:
        low, high = DIALYSATE_VOLUME_PLAUSIBLE_L
        if not (low <= volume <= high):
            problems.append(
                f"Dialysate volume {volume:g} L is outside the plausible range "
                f"{low:g}–{high:g} L."
            )

    bath_k = session.bath_potassium_meq
    if bath_k is not None:
        low, high = BATH_K_PLAUSIBLE_MEQ
        if not (low <= bath_k <= high):
            # The corpus has 45 mEq/L here — the lactate value in the wrong
            # column. Modelling it would predict a colossal potassium gain.
            problems.append(
                f"Bath potassium {bath_k:g} mEq/L is outside the plausible range "
                f"{low:g}–{high:g} mEq/L; this looks like another field's value."
            )

    if session.duration_minutes is not None and session.duration_minutes <= 0:
        problems.append("Session duration is not positive.")

    return problems


def _transfer(
    serum_mg_l: float,
    bath_mg_l: float,
    volume_l: float,
    uf_l: float,
    coeff: Coefficients,
    efficiency: float = 1.0,
    blood_volume_l: float | None = None,
) -> tuple[float, float]:
    """(diffusive_mg, convective_mg) across one session.

    Two sides can limit the transfer and both are applied:

    * the **dialysate** side — how much the effluent volume can carry away,
      scaled by how completely it equilibrates (`efficiency`, from Qb:Qd);
    * the **blood** side — solute can only leave in the blood that actually
      went through the filter, so `blood_volume_l × concentration` is a hard
      ceiling. This is what makes a session with a poor access remove less even
      when the full dialysate volume was run.
    """
    diffusible = serum_mg_l * coeff.diffusible_fraction
    # Blend toward 1.0 for a solute whose removal blood flow does not govern.
    applied_efficiency = 1.0 - coeff.flow_sensitivity * (1.0 - efficiency)
    diffusive = volume_l * (diffusible - bath_mg_l) * coeff.saturation * applied_efficiency
    # Ultrafiltrate carries solute out at plasma concentration regardless of the
    # bath, so convection is never a gain.
    convective = uf_l * diffusible * coeff.sieving

    if blood_volume_l:
        # Only meaningful for removal; a gain comes from the bath, not the blood.
        deliverable = blood_volume_l * diffusible * _MAX_SINGLE_PASS_EXTRACTION
        if diffusive > deliverable:
            diffusive = deliverable

    return diffusive, convective


def estimate_session_removal(
    session: SessionParams,
    serum: SerumLevels,
    coefficients: dict[str, Coefficients] | None = None,
) -> dict[str, RemovalEstimate]:
    """Mass of each analyte moved by one session.

    Raises `SessionNotModellable` when the record cannot support an estimate —
    an empty result would be indistinguishable from "this session removed
    nothing", which is a very different clinical statement.
    """
    problems = validate_session(session)
    if problems:
        raise SessionNotModellable(" ".join(problems))

    coeffs = {**DEFAULT_COEFFICIENTS, **(coefficients or {})}
    volume_l = session.effective_volume_l or 0.0
    uf_l = session.ultrafiltration_l
    # Blood volume processed and the Qb:Qd ratio — the treatment parameters
    # that make two sessions with identical dialysate volume differ.
    efficiency = session.flow_efficiency
    blood_l = session.blood_volume_processed_l
    results: dict[str, RemovalEstimate] = {}

    # ── Potassium: bath is recorded, so this one is not assumed ──
    if serum.potassium_mmol_l is not None:
        coeff = coeffs[POTASSIUM]
        serum_mg_l = serum.potassium_mmol_l * _MG_PER_MMOL_K
        bath_mg_l = (session.bath_potassium_meq or 0.0) * _MG_PER_MEQ_K
        diffusive, convective = _transfer(
            serum_mg_l, bath_mg_l, volume_l, uf_l, coeff, efficiency, blood_l
        )
        results[POTASSIUM] = RemovalEstimate(
            analyte=POTASSIUM,
            mass_mg=diffusive + convective,
            diffusive_mg=diffusive,
            convective_mg=convective,
            calibrated=coeff.calibrated,
        )

    # ── Phosphorus: no bath phosphate, and removal saturates with time ──
    if serum.phosphorus_mg_dl is not None:
        coeff = coeffs[PHOSPHORUS]
        serum_mg_l = serum.phosphorus_mg_dl * _DL_PER_L
        diffusive, convective = _transfer(
            serum_mg_l, 0.0, volume_l, uf_l, coeff, efficiency, blood_l
        )
        mass = diffusive + convective

        # Phosphorus leaves the extracellular space faster than it is
        # replenished from cells, so removal plateaus. Without this a 5-hour
        # session would be credited with 25% more phosphorus than a 4-hour one,
        # which is not what happens.
        if coeff.time_constant_min and session.duration_minutes:
            mass *= 1.0 - math.exp(-session.duration_minutes / coeff.time_constant_min)
        if coeff.max_mass_mg is not None:
            mass = min(mass, coeff.max_mass_mg)

        results[PHOSPHORUS] = RemovalEstimate(
            analyte=PHOSPHORUS,
            mass_mg=mass,
            diffusive_mg=diffusive,
            convective_mg=convective,
            calibrated=coeff.calibrated,
            note="Removal plateaus with session length (intracellular rebound).",
        )

    # ── Magnesium and calcium: bath assumed, and often a net GAIN ──
    for analyte, serum_value, bath_meq, mg_per_meq, default_bath in (
        (MAGNESIUM, serum.magnesium_mg_dl, session.bath_magnesium_meq,
         _MG_PER_MEQ_MG, DEFAULT_BATH_MAGNESIUM_MEQ),
        (CALCIUM, serum.calcium_mg_dl, session.bath_calcium_meq,
         _MG_PER_MEQ_CA, DEFAULT_BATH_CALCIUM_MEQ),
    ):
        if serum_value is None:
            continue
        coeff = coeffs[analyte]
        assumed = bath_meq is None
        bath = default_bath if assumed else bath_meq

        serum_mg_l = serum_value * _DL_PER_L
        bath_mg_l = bath * mg_per_meq
        diffusive, convective = _transfer(
            serum_mg_l, bath_mg_l, volume_l, uf_l, coeff, efficiency, blood_l
        )
        mass = diffusive + convective

        results[analyte] = RemovalEstimate(
            analyte=analyte,
            mass_mg=mass,
            diffusive_mg=diffusive,
            convective_mg=convective,
            calibrated=coeff.calibrated,
            assumptions=[BATH_ASSUMPTION_NOTE] if assumed else [],
            note=(
                "Net gain from the dialysate — this tightens the day's budget."
                if mass < 0 else None
            ),
        )

    # ── Protein / amino acids: a per-session loss ──
    coeff = coeffs[PROTEIN]
    if coeff.grams_per_session:
        # Scale gently with dialysate volume; loss is driven by the treatment
        # itself rather than by a concentration gradient.
        scale = (volume_l / _REFERENCE_DIALYSATE_L) if volume_l else 1.0
        grams = coeff.grams_per_session * max(0.5, min(scale, 2.0))
        results[PROTEIN] = RemovalEstimate(
            analyte=PROTEIN,
            mass_mg=grams * 1000.0,
            diffusive_mg=grams * 1000.0,
            calibrated=coeff.calibrated,
            note="Free amino acid loss; the basis for the raised protein target on dialysis.",
        )

    return results


def predict_post_concentration(
    analyte: str,
    pre_value: float,
    removal_mg: float,
    volume_of_distribution_l: float,
) -> float:
    """Serum concentration after a session, in the analyte's own units.

    This is what calibration optimises against: the measured post-dialysis value
    is the control, and the coefficient is whatever makes the prediction match.
    """
    if volume_of_distribution_l <= 0:
        raise ValueError("Volume of distribution must be positive.")

    if analyte == POTASSIUM:
        delta_mmol_l = (removal_mg / _MG_PER_MMOL_K) / volume_of_distribution_l
        return pre_value - delta_mmol_l

    # Phosphorus, magnesium and calcium are all reported in mg/dL.
    delta_mg_dl = (removal_mg / volume_of_distribution_l) / _DL_PER_L
    return pre_value - delta_mg_dl


def with_calibration(
    analyte: str,
    saturation: float,
    holdout_mae: float | None = None,
) -> Coefficients:
    """A fitted coefficient set for one analyte, marked as calibrated."""
    base = DEFAULT_COEFFICIENTS[analyte]
    return replace(base, saturation=saturation, calibrated=True, holdout_mae=holdout_mae)
