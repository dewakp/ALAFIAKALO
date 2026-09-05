"""Turn "I take Calcitriol" into a dose the user only has to confirm.

Two jobs, kept apart on purpose:

  1. read a medication out of free text, and
  2. supply a dose the text did not state, from what this user has actually
     logged before.

Nothing here writes. It returns a *proposal* — the caller shows it, the user
confirms, and the existing POST /medications/dose-logs records it. That is the
whole safety posture: on this database, of the user/medication pairs with two or
more dose logs, **6 of 9 use more than one dose over time**, so "the dose from
history" is frequently not a single answer. A proposal with its provenance shown
("10 mg — your last 6 doses") is honest; silently writing one is not.

Every proposal is run through `validate_dose` before it is returned, because the
history it draws on is itself user-entered and can be wrong: this database holds
`calcium calcitriol 1000 mg`, which read literally is ~1000x a real calcitriol
dose. Replaying that under a confident "your usual dose" caption is exactly the
failure this module has to refuse to commit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.med_nutrient import MedicationDoseLog
from app.models.medications import Medication
from app.services.med_dose_validation import validate_dose

logger = get_logger(__name__)

# "I take X", "took X", "had my X", "taking X" — the lead-ins people actually
# use. Everything after the verb is the medication phrase until a dose or the end.
_LEADINS = re.compile(
    r"\b(?:i\s+(?:just\s+)?(?:take|took|had|have\s+taken|am\s+taking)|took|taking|had)\b",
    re.IGNORECASE,
)

# A dose written inline: "2 tablets", "0.5 mcg", "1000mg", "1 pill".
_DOSE = re.compile(
    r"(?P<amount>\d+(?:\.\d+)?)\s*"
    r"(?P<unit>mcg|µg|ug|mg|g|ml|mL|iu|units?|meq|tablets?|tabs?|pills?|capsules?|caps?|drops?|puffs?|sachets?)\b",
    re.IGNORECASE,
)

_UNIT_CANON = {
    "µg": "mcg", "ug": "mcg", "tab": "tablet", "tabs": "tablet", "tablets": "tablet",
    "pill": "tablet", "pills": "tablet", "cap": "capsule", "caps": "capsule",
    "capsules": "capsule", "unit": "units", "ml": "mL",
}

# Words that are never part of a medication name.
_STOPWORDS = {
    "my", "the", "a", "an", "of", "for", "this", "that", "today", "now",
    "morning", "evening", "night", "afternoon", "tonight", "dose", "doses",
    "and", "with", "at", "in", "on", "just", "again",
}


@dataclass
class DoseProposal:
    medication_name: str
    dose_amount: float | None = None
    dose_unit: str | None = None
    # "stated"      — the text said the dose
    # "history"     — inferred from this user's own dose logs
    # "prescription"— taken from their active medications list
    # "unknown"     — we could not supply one; ask
    dose_source: str = "unknown"
    provenance: str | None = None      # human-readable, shown under the value
    confidence: float = 0.0
    needs_confirmation: bool = True    # always true; kept explicit, not implied
    alternatives: list[dict] = field(default_factory=list)
    findings: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


def parse_intake_text(text: str) -> tuple[str, float | None, str | None]:
    """Extract (medication phrase, amount, unit) from free text."""
    raw = (text or "").strip()
    if not raw:
        return "", None, None

    amount: float | None = None
    unit: str | None = None
    m = _DOSE.search(raw)
    if m:
        amount = float(m.group("amount"))
        u = m.group("unit").lower()
        unit = _UNIT_CANON.get(u, u)
        raw = (raw[: m.start()] + " " + raw[m.end():]).strip()

    lead = _LEADINS.search(raw)
    if lead:
        raw = raw[lead.end():]

    words = [w for w in re.split(r"[\s,;.]+", raw) if w]
    words = [w for w in words if w.lower() not in _STOPWORDS]
    return " ".join(words).strip(), amount, unit


async def _dose_from_history(
    db: AsyncSession, user_id: int, name: str,
) -> tuple[float | None, str | None, str | None, float, list[dict]]:
    """Most-used dose for this user and medication, with its provenance."""
    rows = (await db.execute(
        select(
            MedicationDoseLog.dose_amount,
            MedicationDoseLog.dose_unit,
            func.count().label("n"),
            func.max(MedicationDoseLog.log_date).label("last"),
        )
        .where(
            MedicationDoseLog.user_id == user_id,
            func.lower(MedicationDoseLog.medication_name) == name.lower(),
        )
        .group_by(MedicationDoseLog.dose_amount, MedicationDoseLog.dose_unit)
        .order_by(func.count().desc())
    )).all()
    if not rows:
        return None, None, None, 0.0, []

    top = rows[0]
    total = sum(r.n for r in rows)
    # Confidence is the share of past doses that agree. It is NOT 1.0 just
    # because we found something — a medication whose dose has changed should
    # not be proposed as if it were settled.
    confidence = round(top.n / total, 2) if total else 0.0
    plural = "dose" if top.n == 1 else "doses"
    provenance = (f"{top.dose_amount:g} {top.dose_unit} — your last {top.n} {plural}"
                  f", most recently {top.last:%-d %b %Y}") if top.last else None
    alternatives = [
        {"dose_amount": r.dose_amount, "dose_unit": r.dose_unit, "times_logged": r.n}
        for r in rows[1:4]
    ]
    return top.dose_amount, top.dose_unit, provenance, confidence, alternatives


async def _dose_from_prescription(
    db: AsyncSession, user_id: int, name: str,
) -> tuple[float | None, str | None, str | None]:
    """Fall back to the standing list — ACTIVE prescriptions only.

    `is_active` matters: this database's only two rows for the test user are
    2017 SMART-sandbox imports with is_active=false. Proposing a dose from a
    prescription that stopped nine years ago would be worse than proposing none.
    """
    row = (await db.execute(
        select(Medication).where(
            Medication.user_id == user_id,
            func.lower(Medication.name).contains(name.lower()),
            Medication.is_active.is_(True),
        ).limit(1)
    )).scalar_one_or_none()
    if row is None or not row.dosage:
        return None, None, None
    try:
        amount = float(re.sub(r"[^\d.]", "", str(row.dosage)) or 0) or None
    except ValueError:
        amount = None
    if amount is None:
        return None, None, None
    return amount, (row.dosage_unit or None), f"from your prescription for {row.name}"


async def propose_intake(db: AsyncSession, user_id: int, text: str) -> DoseProposal:
    """Read free text into a confirmable dose proposal. Writes nothing."""
    name, amount, unit = parse_intake_text(text)
    if not name:
        return DoseProposal(medication_name="", dose_source="unknown",
                            provenance="No medication named in that message.")

    proposal = DoseProposal(medication_name=name)

    if amount is not None:
        proposal.dose_amount, proposal.dose_unit = amount, unit
        proposal.dose_source, proposal.confidence = "stated", 1.0
        proposal.provenance = "as you typed it"
    else:
        h_amt, h_unit, h_prov, h_conf, alts = await _dose_from_history(db, user_id, name)
        if h_amt is not None:
            proposal.dose_amount, proposal.dose_unit = h_amt, h_unit
            proposal.dose_source, proposal.confidence = "history", h_conf
            proposal.provenance, proposal.alternatives = h_prov, alts
        else:
            p_amt, p_unit, p_prov = await _dose_from_prescription(db, user_id, name)
            if p_amt is not None:
                proposal.dose_amount, proposal.dose_unit = p_amt, p_unit
                proposal.dose_source, proposal.confidence = "prescription", 0.6
                proposal.provenance = p_prov
            else:
                proposal.provenance = "No previous dose on record — please enter one."

    # The history is user-entered and can itself be wrong. Check before proposing.
    if proposal.dose_amount is not None:
        findings = await validate_dose(
            db, proposal.medication_name, proposal.dose_amount, proposal.dose_unit or "",
        )
        proposal.findings = [f.as_dict() for f in findings]
        if any(f.level == "error" for f in findings):
            # Refuse to pre-fill a value we can prove is wrong, even if the user
            # logged it before. Keep the finding so the UI can explain why.
            proposal.dose_amount = None
            proposal.dose_unit = None
            proposal.dose_source = "unknown"
            proposal.confidence = 0.0
            proposal.provenance = "Your past entries for this look wrong — please confirm the dose."
    return proposal
