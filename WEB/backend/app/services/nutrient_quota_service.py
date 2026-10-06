# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""Resolve a nutrient QUANTITY for a condition, cite it, store it, serve it.

The companion to `condition_nutrition_service`, which answers *which
direction* a condition pushes a nutrient. This answers *how much*, and the two
are deliberately separate stores: direction is far more robust than magnitude.
"avoid potassium in ESRD" is settled; the number attached to it is a
guideline's scoped, time-varying, sometimes-absent judgement.

Three rules, each paid for by a failure already in this codebase:

1. **A quota with no citation is refused.** Not downgraded, not stored with a
   blank source — refused. §3az's own history is a hardcoded potassium limit
   of 4,700 mg sitting LOOSER than the patient's real 2,200 mg cap, so the
   alert could never fire for the patient it existed to protect. A figure
   nobody can trace is the kind that gets quoted to a clinician.

2. **Nothing resolves on a read path.** `stored_quotas` is one indexed SELECT
   with no network. `resolve_quota` makes the model call and belongs to a
   background task or a script. `facts_for_conditions` already learned this:
   `resolve_missing=False` is load-bearing, because the alternative is an
   LLM round trip inside a request a patient is waiting on (§3ae).

3. **Conflicting quotas become a stated TENSION, never a union.** §3an
   measured this on a real record: hypertension resolves to "prioritise
   potassium, fruit, legumes, nuts" while ESRD resolves to "avoid potassium" —
   and the union tells a planner to load a dialysis patient with potassium.
   The multimorbidity literature says the same thing with numbers: formalising
   12 guidelines into logic found **90.6% of all conflicts arise only at the
   intersection of comorbidities**, and frontier LLMs failed to detect them
   where a symbolic check reached F1 0.861 (Xie & Du, AAAI 2026). So the
   conflict check here is deterministic code, not a prompt.

What this module does NOT do is decide between two conditions on the
patient's behalf. Where a floor and a ceiling cannot both be met, the
**ceiling governs the emitted figure** — that is the bound whose breach the
guideline itself describes as harmful (hypercalcaemia, vascular
calcification) — and the tension travels with both citations so a clinician
sees the disagreement rather than a number that quietly resolved it.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.nutrition_data import NUTRIENT_BY_KEY
from app.models.nutrient_quota import (
    BASES, BASIS_ABSOLUTE, BASIS_PER_1000_KCAL, BASIS_PER_DOSE, BASIS_PER_KG,
    EVIDENCE_LEVELS, KINDS, LIMIT, TARGET, ConditionNutrientQuota,
)
from app.services.condition_nutrition_service import normalize_condition

logger = logging.getLogger(__name__)

#: Cap on how many quotas one resolution may produce, so a confused answer
#: cannot flood the store for a single condition.
_MAX_QUOTAS_PER_CONDITION = 8


def scope_key_for(stage: str | None, therapy: str | None) -> str:
    """Normalised, NON-NULL scope identity.

    Part of the unique constraint instead of the nullable `stage`/`therapy`
    columns: Postgres treats NULLs as distinct, so a unique key over those
    would let re-resolution insert BESIDE the row it meant to sharpen — the
    §3ab contradictory-duplicate failure, with a clinical quantity in it.
    """
    parts = []
    if stage:
        parts.append(f"stage={str(stage).strip().lower()}")
    if therapy:
        parts.append(f"therapy={str(therapy).strip().lower()}")
    return "|".join(parts)


def is_known_nutrient(key: str) -> bool:
    """True only for a key in the 116-nutrient catalog.

    The resolver is handed the allowed keys and its answer is validated
    against them, rather than fuzzy-matching whatever wording came back.
    §3c: "do not add aliases" — if a lookup is wrong, fix what blocks the
    lookup, don't accumulate a mapping table.
    """
    return bool(key) and key in NUTRIENT_BY_KEY


@dataclass(frozen=True)
class ResolvedQuota:
    """One quota with its basis already applied to this patient's biology."""

    nutrient_key: str
    kind: str
    amount: float          # in `unit`, already scaled for per_kg / per_1000_kcal
    unit: str
    basis: str
    includes_supplements: bool
    time_course: str | None
    source: str
    citation_url: str | None
    cited_text: str
    evidence_level: str
    condition_label: str
    scope_key: str

    @property
    def rationale(self) -> str:
        """Why this figure, in words a patient or clinician can check."""
        bits = [f"{self.condition_label}: "]
        bits.append("stay under " if self.kind == LIMIT else "aim for ")
        bits.append(f"{self.amount:g} {self.unit}")
        if self.basis == BASIS_PER_DOSE:
            bits.append(" per dose")
        else:
            bits.append("/day")
        if self.includes_supplements:
            bits.append(" INCLUDING supplements and calcium-based medication")
        bits.append(f" ({self.source}).")
        if self.time_course:
            bits.append(f" {self.time_course}")
        return "".join(bits)


@dataclass
class QuotaSet:
    """Everything the goal computation needs, with nothing decided silently."""

    #: nutrient_key -> the governing DAILY quota. `per_dose` never appears
    #: here: 500 mg is a ceiling on one ingestion, not a daily allowance, and
    #: treating it as one would cut a 2,000 mg/day requirement to a quarter.
    daily: dict[str, ResolvedQuota] = field(default_factory=dict)
    #: Per-ingestion ceilings, carried separately and shown beside the daily
    #: figure rather than replacing it.
    per_dose: list[ResolvedQuota] = field(default_factory=list)
    #: Quotas that cannot all be satisfied. Stated, never merged.
    tensions: list[dict[str, Any]] = field(default_factory=list)
    #: Nutrients a condition is known to govern where no figure could be
    #: resolved — an absence, reported as one (§3aa: an error is not an empty
    #: state, and neither is a gap).
    unscoped: list[str] = field(default_factory=list)

    def as_goal_overrides(self) -> dict[str, dict[str, Any]]:
        """The shape `compute_goals(quotas=...)` consumes."""
        out: dict[str, dict[str, Any]] = {}
        for key, q in self.daily.items():
            out[key] = {
                "amount": q.amount,
                "unit": q.unit,
                "kind": q.kind,
                "source": q.source,
                "citation_url": q.citation_url,
                "cited_text": q.cited_text,
                "evidence_level": q.evidence_level,
                "includes_supplements": q.includes_supplements,
                "time_course": q.time_course,
                "condition_label": q.condition_label,
                "rationale": q.rationale,
                "tension": any(t["nutrient_key"] == key for t in self.tensions),
            }
        return out


async def stored_quotas(
    db: AsyncSession,
    condition_keys: Iterable[str],
    *,
    nutrient_keys: Iterable[str] | None = None,
) -> list[ConditionNutrientQuota]:
    """Every active quota for these conditions. One SELECT, no network."""
    keys = [k for k in {normalize_condition(c) for c in (condition_keys or [])} if k]
    if not keys:
        return []
    stmt = select(ConditionNutrientQuota).where(
        ConditionNutrientQuota.condition_key.in_(keys),
        ConditionNutrientQuota.is_active.is_(True),
    )
    wanted = [k for k in (nutrient_keys or []) if k]
    if wanted:
        stmt = stmt.where(ConditionNutrientQuota.subject_normalized.in_(wanted))
    return list((await db.execute(stmt)).scalars().all())


def _scale(
    row: ConditionNutrientQuota,
    *,
    weight_kg: float | None,
    energy_kcal: float | None,
) -> float | None:
    """Apply the row's basis to this patient. None when it cannot be applied.

    Returning None rather than falling back to a reference body weight is
    deliberate: §3am's unit lesson is that an unreadable input must raise
    rather than assume, because guessing is how a number lands in the wrong
    column. A per-kg quota with no weight on file is UNSCOPED, not 70 kg.
    """
    if row.basis == BASIS_ABSOLUTE:
        return float(row.amount)
    if row.basis == BASIS_PER_KG:
        return float(row.amount) * weight_kg if weight_kg else None
    if row.basis == BASIS_PER_1000_KCAL:
        return float(row.amount) * (energy_kcal / 1000.0) if energy_kcal else None
    if row.basis == BASIS_PER_DOSE:
        return float(row.amount)
    return None


def _applies_to(
    row: ConditionNutrientQuota, *, sex: str | None, age: int | None
) -> bool:
    """Scope filter. An unstated bound does not exclude anybody."""
    if row.sex and sex and row.sex.strip().lower() != sex.strip().lower():
        return False
    if row.age_min is not None and age is not None and age < row.age_min:
        return False
    if row.age_max is not None and age is not None and age > row.age_max:
        return False
    return True


def resolve_for_patient(
    rows: Sequence[ConditionNutrientQuota],
    *,
    weight_kg: float | None = None,
    energy_kcal: float | None = None,
    sex: str | None = None,
    age: int | None = None,
) -> QuotaSet:
    """Turn stored rows into this patient's governing figures plus tensions.

    Pure: no database, no network, no clock. That is what makes it testable
    against a contrived set of conflicting rows, which is the case that
    matters and the one a real record rarely contains.
    """
    out = QuotaSet()
    by_nutrient: dict[str, list[tuple[ConditionNutrientQuota, float]]] = {}

    for row in rows:
        if not _applies_to(row, sex=sex, age=age):
            continue
        amount = _scale(row, weight_kg=weight_kg, energy_kcal=energy_kcal)
        if amount is None:
            if row.subject_normalized not in out.unscoped:
                out.unscoped.append(row.subject_normalized)
            continue
        by_nutrient.setdefault(row.subject_normalized, []).append((row, amount))

    for key, entries in by_nutrient.items():
        per_dose = [(r, a) for r, a in entries if r.basis == BASIS_PER_DOSE]
        daily = [(r, a) for r, a in entries if r.basis != BASIS_PER_DOSE]

        for row, amount in per_dose:
            out.per_dose.append(_to_resolved(row, amount))

        if not daily:
            continue

        limits = [(r, a) for r, a in daily if r.kind == LIMIT]
        targets = [(r, a) for r, a in daily if r.kind == TARGET]

        # The tightest ceiling and the highest floor are what actually bind.
        tightest_limit = min(limits, key=lambda ra: ra[1]) if limits else None
        highest_target = max(targets, key=lambda ra: ra[1]) if targets else None

        if tightest_limit and highest_target and highest_target[1] > tightest_limit[1]:
            # Irreconcilable: a floor above a ceiling. Both are stated, and the
            # CEILING governs — it is the bound whose breach the guideline
            # describes as harmful. Never averaged, never silently dropped.
            out.tensions.append({
                "nutrient_key": key,
                "governing": "limit",
                "reason": (
                    f"{highest_target[0].condition_label} calls for at least "
                    f"{highest_target[1]:g} {highest_target[0].unit}/day while "
                    f"{tightest_limit[0].condition_label} caps intake at "
                    f"{tightest_limit[1]:g} {tightest_limit[0].unit}/day. Both "
                    "cannot be met; the cap is applied and the shortfall is a "
                    "clinical decision, not an arithmetic one."),
                "target": _to_resolved(*highest_target).__dict__,
                "limit": _to_resolved(*tightest_limit).__dict__,
            })
            out.daily[key] = _to_resolved(*tightest_limit)
            continue

        # Two floors or two ceilings that merely differ is not a conflict:
        # the binding one governs and nothing is hidden.
        chosen = tightest_limit or highest_target
        if chosen:
            out.daily[key] = _to_resolved(*chosen)

    return out


def _to_resolved(row: ConditionNutrientQuota, amount: float) -> ResolvedQuota:
    return ResolvedQuota(
        nutrient_key=row.subject_normalized,
        kind=row.kind,
        amount=round(float(amount), 2),
        unit=row.unit,
        basis=row.basis,
        includes_supplements=bool(row.includes_supplements),
        time_course=row.time_course,
        source=row.source,
        citation_url=row.citation_url,
        cited_text=row.cited_text,
        evidence_level=row.evidence_level or "moderate",
        condition_label=row.condition_label,
        scope_key=row.scope_key or "",
    )


async def quotas_for_conditions(
    db: AsyncSession,
    conditions: Iterable[Any],
    *,
    weight_kg: float | None = None,
    energy_kcal: float | None = None,
    sex: str | None = None,
    age: int | None = None,
    date_of_birth: Any = None,
) -> QuotaSet:
    """Read-path entry point: stored quotas only, resolved for this patient.

    Deliberately takes no `resolve_missing` flag. `facts_for_conditions` has
    one and has to document why it must stay False; this function cannot
    resolve at all, so there is no flag to leave in the wrong position.
    """
    labels: list[str] = []
    for c in conditions or []:
        if isinstance(c, str):
            labels.append(c)
            continue
        val = (c.get("condition_name") or c.get("name") if isinstance(c, dict)
               else getattr(c, "condition_name", None) or getattr(c, "name", None))
        if val:
            labels.append(str(val))

    # Age is derived HERE from the date of birth rather than at each call
    # site, using the same helper `compute_goals` uses. An age-scoped quota —
    # the stones figure is stated for adults under 70 — silently applies to
    # everybody when the caller has no age to pass, and five call sites each
    # computing their own age is the drift this canon keeps paying for.
    # Imported inside the function: `nutrient_goals_service` deliberately does
    # not import this module (it takes quotas as a parameter), and keeping the
    # dependency one-directional is what makes that safe.
    if age is None and date_of_birth is not None:
        from app.services.nutrient_goals_service import _calc_age
        age = _calc_age(str(date_of_birth))

    rows = await stored_quotas(db, labels)
    return resolve_for_patient(
        rows, weight_kg=weight_kg, energy_kcal=energy_kcal, sex=sex, age=age)


# ─────────────────────────────────────────────────────────────────────────
# Resolution — the WRITE path. Never called from a request a patient waits on.
# ─────────────────────────────────────────────────────────────────────────

_RESOLVE_PROMPT = """You are consulting published clinical nutrition guidelines.

For the condition named below, state any DAILY NUTRIENT QUANTITY that a named
guideline specifies, and nothing else.

Condition: {condition}

Report ONLY nutrients from this list, using these exact keys:
{nutrient_keys}

Return JSON of this shape and no prose:

{{"quotas": [
  {{"nutrient_key": "<one of the keys above>",
    "kind": "target" | "limit",
    "amount": <number>,
    "unit": "<mg|g|mcg|IU>",
    "basis": "absolute" | "per_kg" | "per_1000_kcal" | "per_dose",
    "includes_supplements": true | false,
    "time_course": "<null, or how the figure changes over time>",
    "stage": "<null, or the disease stage this applies to>",
    "therapy": "<null, or the concurrent therapy this applies to>",
    "source": "<the guideline's name and year>",
    "citation_url": "<null, or a URL>",
    "cited_text": "<the guideline's own sentence stating the figure>",
    "evidence": "high" | "moderate" | "low" | "expert_opinion"}}
]}}

Rules you must follow:
- If a guideline states NO figure for this condition, return {{"quotas": []}}.
  An absent recommendation is a real and common answer — KDIGO states no
  calcium intake figure for dialysis at all. Do not supply a number to fill
  the gap.
- `cited_text` must be the guideline's wording, not a paraphrase. A quota
  without it is discarded.
- Set `includes_supplements` true when the figure counts supplements or
  medication toward itself, as a total-elemental figure counts calcium-based
  phosphate binders.
- Use `per_dose` only for a ceiling on a single ingestion, never for a daily
  amount.
- Do not restate a general-population RDA. Only a figure this condition
  changes belongs here.
"""


async def resolve_quota(
    db: AsyncSession,
    condition_label: str,
    *,
    icd11_code: str | None = None,
    nutrient_keys: Sequence[str] | None = None,
) -> list[ConditionNutrientQuota]:
    """Ask for this condition's cited quotas, store them, return them.

    Never raises: the knowledge tier being unavailable must not fail a
    caller. An empty result is logged with its reason rather than being
    indistinguishable from "this condition changes no nutrient" (§3aa).
    """
    key = normalize_condition(condition_label)
    if not key:
        return []

    allowed = [k for k in (nutrient_keys or []) if is_known_nutrient(k)]
    if not allowed:
        logger.warning("nutrient quota: no known nutrient keys requested for %r",
                       condition_label)
        return []

    prompt = _RESOLVE_PROMPT.format(
        condition=condition_label, nutrient_keys=", ".join(sorted(allowed)))

    try:
        from app.services.alafia_model_service import alafia_chat
        raw = (await alafia_chat(
            [{"role": "user", "content": prompt}],
            temperature=0.1, max_tokens=1600, json_mode=True,
            task="nutrient_quota_resolution",
        )).strip()
    except Exception as exc:  # noqa: BLE001 - includes ALAFIAModelError
        logger.warning("nutrient quota: could not resolve %r (%s: %s)",
                       condition_label, type(exc).__name__, exc)
        return []

    try:
        payload = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
    except (ValueError, json.JSONDecodeError):
        logger.warning("nutrient quota: unparseable answer for %r", condition_label)
        return []

    entries = payload.get("quotas")
    if not isinstance(entries, list):
        logger.warning("nutrient quota: answer for %r carried no quota list",
                       condition_label)
        return []

    stored: list[ConditionNutrientQuota] = []
    for entry in entries[:_MAX_QUOTAS_PER_CONDITION]:
        if not isinstance(entry, dict):
            continue
        row = await _upsert_quota(
            db, condition_key=key, condition_label=condition_label,
            icd11_code=icd11_code, allowed=set(allowed), entry=entry)
        if row is not None:
            stored.append(row)

    if not stored:
        logger.info("nutrient quota: %r resolved to no storable quota",
                    condition_label)
    return stored


async def _upsert_quota(
    db: AsyncSession,
    *,
    condition_key: str,
    condition_label: str,
    icd11_code: str | None,
    allowed: set[str],
    entry: dict[str, Any],
) -> ConditionNutrientQuota | None:
    """Validate, then store or sharpen. Returns None for anything refused."""
    nutrient_key = str(entry.get("nutrient_key") or "").strip()
    if nutrient_key not in allowed:
        logger.info("nutrient quota: %r refused — %r is not a requested nutrient",
                    condition_label, nutrient_key)
        return None

    cited_text = str(entry.get("cited_text") or "").strip()
    source = str(entry.get("source") or "").strip()
    if not cited_text or not source:
        # The whole point of the store. A figure nobody can trace is worse
        # than no figure, because it will be quoted (§3az).
        logger.info("nutrient quota: %r/%s refused — no citation",
                    condition_label, nutrient_key)
        return None

    try:
        amount = float(entry.get("amount"))
    except (TypeError, ValueError):
        logger.info("nutrient quota: %r/%s refused — amount is not a number",
                    condition_label, nutrient_key)
        return None
    if amount <= 0:
        logger.info("nutrient quota: %r/%s refused — non-positive amount %r",
                    condition_label, nutrient_key, amount)
        return None

    kind = str(entry.get("kind") or "").strip().lower()
    if kind not in KINDS:
        logger.info("nutrient quota: %r/%s refused — kind %r is neither target "
                    "nor limit", condition_label, nutrient_key, kind)
        return None

    basis = str(entry.get("basis") or BASIS_ABSOLUTE).strip().lower()
    if basis not in BASES:
        logger.info("nutrient quota: %r/%s refused — unknown basis %r",
                    condition_label, nutrient_key, basis)
        return None

    unit = str(entry.get("unit") or "").strip() or NUTRIENT_BY_KEY[nutrient_key].get("unit", "")
    if not unit:
        logger.info("nutrient quota: %r/%s refused — no unit",
                    condition_label, nutrient_key)
        return None

    evidence = str(entry.get("evidence") or "moderate").strip().lower()
    if evidence not in EVIDENCE_LEVELS:
        evidence = "moderate"

    stage = (str(entry.get("stage")).strip()
             if entry.get("stage") not in (None, "", "null") else None)
    therapy = (str(entry.get("therapy")).strip()
               if entry.get("therapy") not in (None, "", "null") else None)
    time_course = (str(entry.get("time_course")).strip()
                   if entry.get("time_course") not in (None, "", "null") else None)
    scope = scope_key_for(stage, therapy)

    existing = (await db.execute(
        select(ConditionNutrientQuota).where(
            ConditionNutrientQuota.condition_key == condition_key,
            ConditionNutrientQuota.subject_normalized == nutrient_key,
            ConditionNutrientQuota.kind == kind,
            ConditionNutrientQuota.basis == basis,
            ConditionNutrientQuota.scope_key == scope,
        )
    )).scalar_one_or_none()

    if existing is not None:
        # Independent re-derivation is evidence FOR the figure already held.
        # The amount is not overwritten: a second opinion that disagrees is a
        # reason to look, not a reason to replace a cited number silently.
        existing.times_confirmed += 1
        existing.confidence = min(0.99, (existing.confidence or 0.5) + 0.1)
        if time_course and not existing.time_course:
            existing.time_course = time_course
        if icd11_code and not existing.icd11_code:
            existing.icd11_code = icd11_code
        existing.is_active = True
        row = existing
    else:
        row = ConditionNutrientQuota(
            condition_key=condition_key,
            condition_label=condition_label,
            icd11_code=icd11_code,
            subject=str(entry.get("subject") or nutrient_key)[:160],
            subject_normalized=nutrient_key,
            kind=kind,
            amount=amount,
            unit=unit[:16],
            basis=basis,
            includes_supplements=bool(entry.get("includes_supplements")),
            time_course=time_course,
            scope_key=scope,
            stage=stage,
            therapy=therapy,
            source=source[:300],
            citation_url=(str(entry.get("citation_url")).strip()
                          if entry.get("citation_url") not in (None, "", "null") else None),
            cited_text=cited_text,
            evidence_level=evidence,
            provenance="llm",
            confidence=0.6 if evidence == "high" else 0.5,
            times_confirmed=1,
        )
        db.add(row)

    # A failed flush poisons the session and the caller's later commit 500s
    # even when the exception was caught (§3a).
    try:
        await db.flush()
    except Exception:  # noqa: BLE001
        logger.warning("nutrient quota: could not store %r/%s",
                       condition_key, nutrient_key, exc_info=True)
        return None
    return row
