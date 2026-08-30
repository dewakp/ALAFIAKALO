"""nPCR derived from urea kinetics, because the lab never reports it.

`nPCR` (normalised protein catabolic rate, also written nPNA — normalised
protein nitrogen appearance) is the marker of how much protein a dialysis
patient is actually eating. It carries 40% of HEBCS's `Nutritional` pathway,
and on this record it is **N/A on all seven dates the lab printed it** — the row
exists, with unit `G/KG/D`, and no value. So the pathway has been scoring on
albumin and BUN alone, at 60% coverage, for the patient's entire history.

It does not have to be measured directly: it is computed from urea kinetics,
and every input is already in `lab_results`. Daugirdas' second-generation
equation for a mid-week session is

    nPCR = C0 / (36.3 + 5.48·Kt/V + 53.5/Kt/V) + 0.168

with C0 the PRE-dialysis BUN in mg/dL and Kt/V the delivered single-pool spKt/V.

⚠️ **This is an ESTIMATE and must never be presented as a lab result.** Two
things qualify it, and both travel with the value:

- The equation assumes a thrice-weekly schedule sampled mid-week. This patient
  dialyses roughly every other day (~4 distinct session days per week), so the
  assumption is approximate rather than exact.
- It is only as good as its inputs: a spKt/V that is itself falling drags the
  estimate with it, which is clinically real but means the two are not
  independent readings.

`source="derived"` is returned alongside every value so a caller can label it,
and `estimate_npcr` returns None rather than a number whenever the inputs are
missing or outside the range the equation is defined over.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass


#: Physiologically plausible nPCR. KDOQI's protein target for a maintenance
#: dialysis patient is 1.2 g/kg/day; below ~0.8 indicates inadequate intake.
#: Outside this window the inputs are wrong, not the patient.
_NPCR_PLAUSIBLE = (0.3, 3.0)

#: The equation is undefined at Kt/V = 0 and meaningless outside delivered
#: dialysis. Values above 3 are not a real single-pool Kt/V.
_KTV_VALID = (0.3, 3.0)

#: A pre-dialysis BUN outside this is not a dialysis patient's draw.
_BUN_VALID = (5.0, 200.0)


#: Saline given back during a session. Free text in the record — "100 ml",
#: "100 mL", "20 ml", "~" — so it is parsed rather than cast.
_SALINE_ML = re.compile(r"([\d.]+)\s*(ml|cc|l)?\b", re.IGNORECASE)

#: A plausible ceiling on saline returned in one session. Beyond this the entry
#: is a transcription error, not a clinical event.
_MAX_SALINE_LITRES = 2.0


def parse_saline_ml(text: str | None) -> float | None:
    """Millilitres from a free-text saline entry, or None if it says nothing.

    "~" is the record's way of writing "some, unspecified" and must not become
    a zero: absent is not none-given.
    """
    if not text or not text.strip() or text.strip() in {"~", "-", "--", "nil"}:
        return None
    match = _SALINE_ML.search(text)
    if not match:
        return None
    try:
        value = float(match.group(1))
    except ValueError:
        return None
    unit = (match.group(2) or "ml").lower()
    return value * 1000.0 if unit == "l" else value


def net_ultrafiltration_litres(readings: list) -> float | None:
    """What the session actually removed, net of saline returned.

    NOT pre-minus-post weight. That figure inherits every scale error, and this
    record holds the proof: a post-dialysis weight of 0.3 kg produced a
    "60,900 ml removed", and 4.7 kg produced "-59,800 ml". Those are weighing
    machine faults, not sessions.

    The machine's own counter is the source. Note `uf_volume_removed` COUNTS
    DOWN — it is the volume still to be removed, despite the name — verified
    across the record: 6,423 reading-to-reading transitions decrease against
    166 that rise. So what came off is (first - last), and taking `max()` of the
    column, as an earlier version did, reads the target rather than the result.

    Saline given back is then subtracted, because returned fluid is clearance
    not delivered.
    """
    values = [r.uf_volume_removed for r in readings
              if getattr(r, "uf_volume_removed", None) is not None]
    if len(values) < 2:
        return None

    removed = values[0] - values[-1]
    if removed < 0 or removed > 10:          # not a session
        return None

    saline_ml = sum(
        v for v in (parse_saline_ml(getattr(r, "saline_amount", None))
                    for r in readings) if v
    )
    saline_l = min(saline_ml / 1000.0, _MAX_SALINE_LITRES)

    net = removed - saline_l
    # Net may be negative — more saline back than fluid off — which is a real
    # session. It is bounded only by what is physically plausible.
    if abs(net) > 10:
        return None
    return round(net, 3)


@dataclass(frozen=True)
class KineticEstimate:
    """A computed dialysis-adequacy figure, with what it was computed from."""
    value: float
    inputs: dict
    source: str = "derived"
    method: str = ""

    def describe(self) -> str:
        detail = ", ".join(f"{k} {v}" for k, v in self.inputs.items())
        return f"{self.value:.2f} — computed from {detail}, not reported"


def urea_reduction_ratio(pre_bun: float | None,
                         post_bun: float | None) -> KineticEstimate | None:
    """URR as a percentage: how much urea one session removed.

        URR = (pre - post) / pre x 100

    Arithmetic on two numbers the lab already reports, so a session with both
    draws never needs the lab to have computed it as well.
    """
    if pre_bun is None or post_bun is None:
        return None
    try:
        pre, post = float(pre_bun), float(post_bun)
    except (TypeError, ValueError):
        return None
    if not (_BUN_VALID[0] <= pre <= _BUN_VALID[1]) or post <= 0 or post >= pre:
        return None

    urr = (pre - post) / pre * 100.0
    if not (0 < urr < 100):
        return None
    return KineticEstimate(
        value=round(urr, 1),
        inputs={"pre-dialysis BUN": pre, "post-dialysis BUN": post},
        method="(pre - post) / pre x 100",
    )


def single_pool_ktv(pre_bun: float | None, post_bun: float | None,
                    duration_minutes: float | None,
                    ultrafiltration_litres: float | None,
                    post_weight_kg: float | None) -> KineticEstimate | None:
    """spKt/V by Daugirdas' second-generation equation.

        Kt/V = -ln(R - 0.008t) + (4 - 3.5R) x UF/W

    with R = post/pre BUN, t the session in HOURS, UF the volume removed in
    litres and W the post-dialysis weight in kg.

    Validated against this record's own reported spKt/V on every date that has
    both the inputs and a reported value:

        2025-10-16  computed 1.61  reported 1.62
        2025-11-03  computed 1.34  reported 1.35
        2026-01-05  computed 1.44  reported 1.44
        2026-04-08  computed 0.90  reported 0.90

    Net ultrafiltration may be NEGATIVE — saline returned to the patient during
    a session outweighing what was removed — and that is carried into the
    arithmetic rather than rejected. Returns None only when an input is missing
    or physically impossible; a fabricated adequacy figure is worse than a
    missing one.
    """
    if None in (pre_bun, post_bun, duration_minutes, post_weight_kg):
        return None
    try:
        pre, post = float(pre_bun), float(post_bun)
        minutes = float(duration_minutes)
        weight = float(post_weight_kg)
        uf = float(ultrafiltration_litres or 0.0)
    except (TypeError, ValueError):
        return None

    if post <= 0 or pre <= 0 or post >= pre:
        return None
    if not (30 <= minutes <= 600) or not (20 <= weight <= 300):
        return None

    # NEGATIVE ultrafiltration is a real session, not a data fault. Saline goes
    # back into the patient — boluses for intradialytic hypotension, and the
    # rinse-back at the end — so net fluid can be negative. It happens on **365
    # of 1775** sessions here (21%), and the 1st percentile of the whole
    # distribution is -1426 ml: routine, not exceptional.
    #
    # It also belongs in the arithmetic. Returning fluid makes the convective
    # term (4 - 3.5R) x UF/W negative, which lowers Kt/V — correctly, because
    # saline returned is clearance not delivered.
    #
    # What IS implausible is a session changing body mass by more than about a
    # tenth, in either direction: this data holds -59,800 ml and +60,900 ml
    # entries. The bound is the patient's own weight rather than a fixed number
    # of litres, and it rejects 9 sessions out of 1775.
    if abs(uf) > 0.10 * weight:
        return None

    hours = minutes / 60.0
    r = post / pre
    inner = r - 0.008 * hours
    if inner <= 0:
        return None

    ktv = -math.log(inner) + (4 - 3.5 * r) * (uf / weight)
    if not (0.1 <= ktv <= 5.0):
        return None

    return KineticEstimate(
        value=round(ktv, 3),
        inputs={"pre BUN": pre, "post BUN": post,
                "minutes": minutes, "UF L": uf, "post weight kg": weight},
        method="Daugirdas 2nd-generation single-pool Kt/V",
    )


@dataclass(frozen=True)
class NpcrEstimate:
    """A derived nPCR, with what it was derived from."""
    value: float                 # g/kg/day
    pre_dialysis_bun: float      # mg/dL
    spktv: float
    source: str = "derived"
    method: str = "Daugirdas 2nd-generation urea kinetics (mid-week assumption)"

    def describe(self) -> str:
        """One line a clinician can read, provenance included."""
        return (f"{self.value:.2f} g/kg/day — estimated from pre-dialysis BUN "
                f"{self.pre_dialysis_bun:.0f} mg/dL and spKt/V {self.spktv:.2f}, "
                f"not measured")


def estimate_npcr(pre_dialysis_bun: float | None,
                  spktv: float | None) -> NpcrEstimate | None:
    """nPCR in g/kg/day, or None when it cannot be computed honestly.

    Returns None — never a fallback number — when an input is absent or out of
    range. A fabricated nutritional marker is worse than a missing one: it would
    be scored as though it were measured.
    """
    if pre_dialysis_bun is None or spktv is None:
        return None
    try:
        c0 = float(pre_dialysis_bun)
        ktv = float(spktv)
    except (TypeError, ValueError):
        return None

    if not (_BUN_VALID[0] <= c0 <= _BUN_VALID[1]):
        return None
    if not (_KTV_VALID[0] <= ktv <= _KTV_VALID[1]):
        return None

    denominator = 36.3 + 5.48 * ktv + 53.5 / ktv
    if denominator <= 0:
        return None

    npcr = c0 / denominator + 0.168
    if not (_NPCR_PLAUSIBLE[0] <= npcr <= _NPCR_PLAUSIBLE[1]):
        # The arithmetic succeeded but the answer is not a person. Say nothing
        # rather than feed a nutritional pathway an impossible figure.
        return None

    return NpcrEstimate(value=round(npcr, 3), pre_dialysis_bun=c0, spktv=ktv)
