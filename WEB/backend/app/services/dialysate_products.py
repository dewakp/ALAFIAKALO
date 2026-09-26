"""What bath a SAK number actually delivered.

The flowsheet records TWO things about the dialysate: a typed `K+` cell, and the
**SAK number** — the product code of the cartridge that was run. The SAK number
is the stronger statement: it identifies the concentrate, whereas the K+ cell is
a human transcribing what they believe is in it.

WHY THIS EXISTS RATHER THAN TRUSTING THE TYPED CELL
---------------------------------------------------
Measured across this record's sessions, the two disagree in a way that is
obviously transcription error rather than a real change of prescription:

    SAK 401   K=1 on 995 sessions   ·   K=2 on 13   ·   blank on 4
    SAK 404   K=1 on   5 sessions   ·   K=2 on 56
    SAK 405   K=1 on   1 session    ·   K=2 on  2

A product does not change its own potassium 13 times in 1,012 uses. So 401 is a
K 1.0 bath and 404 is a K 2.0 bath, and roughly 18 typed cells are wrong — which
is exactly the "excel sometimes contains errors (human)" case.

**405 is deliberately NOT mapped.** Three sessions, split 1:2, is not evidence of
anything. Guessing it to complete the table is how a wrong figure becomes
authoritative (§3ad: never type a clinical code from memory — and never infer
one from a sample of three).

WHAT IS AND IS NOT DERIVED HERE
-------------------------------
Only POTASSIUM. It is the one constituent the record measures often enough to
derive, and every figure below is read off the data above rather than typed from
a product sheet.

Calcium, magnesium and glucose are genuine constituents of these baths and are
NOT here, because nothing in this repository establishes their concentrations:
the bath labels are not on disk and no citation exists for these SAK codes.
`dialysis_balance` continues to apply DEFAULT_BATH_CALCIUM_MEQ /
DEFAULT_BATH_MAGNESIUM_MEQ and to DECLARE them as assumed. Filling them in from
recollection would turn an honest assumption into a false measurement, and a
glucose gradient cannot be modelled at all until its bath concentration has a
source.

A SAK number that is not in the table returns None, and the caller keeps
whatever the record typed. Unrecognised is not the same as absent.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Sessions behind each mapping, so a reader can weigh it without re-deriving it.
_EVIDENCE = {401: "K=1 on 995 of 1,012 sessions", 404: "K=2 on 56 of 61 sessions"}


@dataclass(frozen=True)
class BathComposition:
    """What a SAK product delivers. None means "this repo cannot say"."""

    sak_number: int
    potassium_meq: float
    #: Why this figure is believed, carried with it so a caller can show it.
    evidence: str

    #: Deliberately absent: calcium, magnesium, glucose. See the module
    #: docstring — no source, so no number.


_BY_SAK: dict[int, BathComposition] = {
    401: BathComposition(401, 1.0, _EVIDENCE[401]),
    404: BathComposition(404, 2.0, _EVIDENCE[404]),
}


def bath_for_sak(sak_number: int | None) -> BathComposition | None:
    """The bath a SAK code delivered, or None if this repo cannot say.

    None covers three different situations on purpose — no SAK recorded, a SAK
    we have no evidence for (405, three sessions), and a mistyped code (one
    session records `1`, which is not a product). All three mean the same thing
    to a caller: fall back to what the flowsheet typed.
    """
    if sak_number is None:
        return None
    return _BY_SAK.get(int(sak_number))


def reconcile_bath_potassium(
    sak_number: int | None, typed_meq: float | None
) -> tuple[float | None, str | None]:
    """Resolve bath potassium from the SAK code and the typed cell.

    Returns `(value, note)`. The note is None when there is nothing to say.

    The SAK code wins when the two disagree, because it identifies the product
    actually run — but the disagreement is REPORTED rather than swallowed. The
    typed value is a clinical entry on the patient's record; silently replacing
    it would hide a transcription error instead of surfacing one, and 18 of them
    exist to surface.
    """
    product = bath_for_sak(sak_number)
    if product is None:
        return typed_meq, None

    if typed_meq is None:
        # Five sessions record a SAK and no K at all. This is the case the
        # mapping is worth the most on: it fills a blank rather than overruling
        # anyone.
        return product.potassium_meq, (
            f"Bath potassium {product.potassium_meq:g} mEq/L taken from SAK "
            f"{product.sak_number} ({product.evidence}); the flowsheet left it blank."
        )

    if abs(typed_meq - product.potassium_meq) < 1e-9:
        return product.potassium_meq, None

    return product.potassium_meq, (
        f"Flowsheet records {typed_meq:g} mEq/L but SAK {product.sak_number} is a "
        f"{product.potassium_meq:g} mEq/L bath ({product.evidence}). The product "
        f"code was used. Check the K+ cell on this sheet."
    )
