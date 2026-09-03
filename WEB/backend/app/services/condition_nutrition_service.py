"""Resolve what a condition means for food — once — then remember it.

The canonical reader for `condition_nutrition_facts`. Nothing else should query
that model directly; the same rule `clinical_sources.py` enforces for
conditions and medications (§3aa), for the same reason: a second reader drifts.

Flow, mirroring `learned_nutrient_service` (§3c "look it up once, remember it
after"):

    stored facts  →  miss?  →  ask the model  →  store with provenance
                                              →  serve

The model is asked through the ordinary AI router, so provider strategy stays a
backend concern (§3) and the patient's identity never travels with the question
— a condition name is not a patient (§3al). The question is about a DISEASE,
not about a person, which is why it can be cached globally and shared across
every patient carrying that diagnosis.

Per-patient refinement lives in `UserMemory`, not here: "this patient reacted
to X" is an observation about them, and `confidence_score` / `evidence_count`
already model repeated confirmation.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.condition_nutrition import ConditionNutritionFact

logger = logging.getLogger(__name__)

AVOID = "avoid"
FAVOUR = "favour"

# A resolution that returns nothing is cached as a negative for this long, so a
# condition with no dietary implications is not re-asked on every plan.
_MAX_SUBJECTS_PER_RELATION = 12


def normalize_condition(name: str) -> str:
    """Lookup key for a condition, however the row spells it.

    The production record carries "G6PD Deficitency" — a typo — and elsewhere
    the same disease is "G6PD Deficiency" and "Glucose-6-phosphate
    dehydrogenase deficiency". Normalising strips punctuation and the noise
    words that differ between spellings.
    """
    text = (name or "").lower()
    text = re.sub(r"\([^)]*\)", " ", text)          # drop parenthetical asides
    text = re.sub(r"[^a-z0-9]+", " ", text)
    words = [w for w in text.split() if w not in {"disease", "disorder", "syndrome"}]
    return " ".join(words).strip()


def normalize_subject(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (name or "").lower()).strip()


@dataclass(frozen=True)
class NutritionFact:
    """One thing a condition says about food, ready to explain to a patient."""

    condition: str
    severity: str          # SEVERE | MODERATE | MILD | "" — from the diagnosis
    relation: str          # "avoid" | "favour"
    subject: str
    subject_kind: str      # "food" | "nutrient" | "ingredient"
    mechanism: str | None
    evidence_level: str
    confidence: float
    provenance: str

    @property
    def reason(self) -> str:
        """Patient-facing explanation. Never bare — §3aj."""
        if self.mechanism:
            return f"{self.condition} — {self.mechanism}"
        verb = "should be avoided with" if self.relation == AVOID else "supports"
        return f"{self.subject} {verb} {self.condition}"


def _row_to_fact(row: ConditionNutritionFact, severity: str = '') -> NutritionFact:
    return NutritionFact(
        condition=row.condition_label,
        severity=severity or "",
        relation=row.relation,
        subject=row.subject,
        subject_kind=row.subject_kind,
        mechanism=row.mechanism,
        evidence_level=row.evidence_level,
        confidence=row.confidence,
        provenance=row.provenance,
    )


async def stored_facts(
    db: AsyncSession,
    condition_names: list[str],
    *,
    relation: str | None = None,
    codes: list[str] | None = None,
) -> list[NutritionFact]:
    """Facts already known for these conditions. No network, no model call."""
    keys = {normalize_condition(n) for n in condition_names if n}
    keys.discard("")
    if not keys:
        return []
    stmt = select(ConditionNutritionFact).where(
        ConditionNutritionFact.condition_key.in_(keys),
        ConditionNutritionFact.is_active.is_(True),
    )
    if codes:
        # A code match wins over spelling. The production row reads "G6PD
        # Deficitency"; its icd11_code 3A10.00 is exact. §3ad — the code is
        # the fact, the label is how someone typed it. Fuzzy-matching the NAME
        # is the wrong instrument (§3aj), so we do not.
        stmt = select(ConditionNutritionFact).where(
            ConditionNutritionFact.is_active.is_(True),
            or_(ConditionNutritionFact.condition_key.in_(keys),
                ConditionNutritionFact.icd11_code.in_(codes)),
        )
    if relation:
        stmt = stmt.where(ConditionNutritionFact.relation == relation)
    rows = (await db.execute(stmt)).scalars().all()
    return [_row_to_fact(r) for r in rows]


async def known_conditions(
    db: AsyncSession,
    condition_names: list[str],
    codes: list[str] | None = None,
) -> set[str]:
    """Which of these we have already resolved (any relation)."""
    keys = {normalize_condition(n) for n in condition_names if n}
    keys.discard("")
    if not keys:
        return set()
    clause = ConditionNutritionFact.condition_key.in_(keys)
    if codes:
        clause = or_(clause, ConditionNutritionFact.icd11_code.in_(codes))
    rows = (await db.execute(
        select(ConditionNutritionFact.condition_key).where(clause)
    )).scalars().all()
    return set(rows)


_RESOLVE_PROMPT = """You are a clinical dietitian. For the medical condition below, \
list the foods or nutrients that matter dietetically.

CONDITION: {condition}

Return ONLY a JSON object matching this SHAPE, no prose and no code fences.
The angle brackets are placeholders — never echo them back:
{{"avoid":[{{"subject":"<food or ingredient>","kind":"food|ingredient|nutrient",
            "mechanism":"<short clinical reason>","evidence":"high|moderate|low"}}],
  "favour":[{{"subject":"<food or nutrient>","kind":"food|ingredient|nutrient",
             "mechanism":"<short clinical reason>","evidence":"high|moderate|low"}}]}}

RULES:
1. "avoid" is for foods or ingredients that TRIGGER or worsen this condition. \
Include only real, condition-specific triggers — not general healthy-eating advice.
2. "favour" is for foods or nutrients that help manage it or mitigate its \
complications. This half matters as much as the first.
3. "kind" is "food", "ingredient" or "nutrient". Prefer "nutrient" when the \
advice is really about a nutrient, so it can be met from any cuisine.
4. "mechanism" is a short clinical reason, in plain language, that can be shown \
to the patient.
5. "evidence" is one of: high, moderate, low.
6. If the condition has no specific dietary triggers or mitigators, return empty \
arrays. Do NOT invent them.
7. At most {limit} entries per list, most important first."""


async def resolve_condition(
    db: AsyncSession,
    condition_label: str,
    *,
    icd11_code: str | None = None,
) -> list[NutritionFact]:
    """Ask the model what this condition means for food, store it, return it.

    Never raises: a planner or chat request must not fail because the knowledge
    tier is unavailable. An empty result is recorded in the log with its reason
    rather than being indistinguishable from "this condition doesn't matter"
    (§3aa — an error is not an empty state).
    """
    key = normalize_condition(condition_label)
    if not key:
        return []

    prompt = _RESOLVE_PROMPT.format(
        condition=condition_label, limit=_MAX_SUBJECTS_PER_RELATION)

    try:
        from app.services.alafia_model_service import alafia_chat, ALAFIAModelError
        raw = (await alafia_chat(
            [{"role": "user", "content": prompt}], temperature=0.2, max_tokens=1400,
        )).strip()
    except Exception as exc:  # noqa: BLE001 - includes ALAFIAModelError
        logger.warning(
            "condition nutrition: could not resolve %r (%s: %s)",
            condition_label, type(exc).__name__, exc)
        return []

    try:
        payload = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
    except (ValueError, json.JSONDecodeError):
        logger.warning("condition nutrition: unparseable answer for %r", condition_label)
        return []

    facts: list[NutritionFact] = []
    for relation in (AVOID, FAVOUR):
        entries = payload.get(relation)
        if not isinstance(entries, list):
            continue
        for entry in entries[:_MAX_SUBJECTS_PER_RELATION]:
            if not isinstance(entry, dict):
                continue
            subject = str(entry.get("subject") or "").strip()
            if not subject:
                continue
            fact = await _upsert(
                db,
                condition_key=key,
                condition_label=condition_label,
                icd11_code=icd11_code,
                relation=relation,
                subject=subject,
                subject_kind=str(entry.get("kind") or "food").strip().lower(),
                mechanism=(str(entry.get("mechanism")).strip()
                           if entry.get("mechanism") else None),
                evidence_level=str(entry.get("evidence") or "moderate").strip().lower(),
            )
            if fact:
                facts.append(fact)

    if not facts:
        logger.info(
            "condition nutrition: %r resolved to no dietary facts", condition_label)
    return facts


async def _upsert(
    db: AsyncSession,
    *,
    condition_key: str,
    condition_label: str,
    icd11_code: str | None,
    relation: str,
    subject: str,
    subject_kind: str,
    mechanism: str | None,
    evidence_level: str,
) -> NutritionFact | None:
    """Store a fact, or sharpen the one already there.

    Re-resolving must CONVERGE, not duplicate. §3ab records what happens when a
    re-import inserts beside the row it was meant to correct: the patient ends
    up holding two contradictory facts on one subject.
    """
    subject_norm = normalize_subject(subject)
    if not subject_norm:
        return None
    if subject_kind not in {"food", "nutrient", "ingredient"}:
        subject_kind = "food"
    if evidence_level not in {"high", "moderate", "low", "expert_opinion"}:
        evidence_level = "moderate"

    existing = (await db.execute(
        select(ConditionNutritionFact).where(
            ConditionNutritionFact.condition_key == condition_key,
            ConditionNutritionFact.relation == relation,
            ConditionNutritionFact.subject_normalized == subject_norm,
        )
    )).scalar_one_or_none()

    if existing is not None:
        # Independent re-derivation of the same fact is evidence for it.
        existing.times_confirmed += 1
        existing.confidence = min(0.99, existing.confidence + 0.1)
        if mechanism and not existing.mechanism:
            existing.mechanism = mechanism
        if icd11_code and not existing.icd11_code:
            existing.icd11_code = icd11_code
        existing.is_active = True
        row = existing
    else:
        row = ConditionNutritionFact(
            condition_key=condition_key,
            condition_label=condition_label,
            icd11_code=icd11_code,
            relation=relation,
            subject=subject,
            subject_normalized=subject_norm,
            subject_kind=subject_kind,
            mechanism=mechanism,
            evidence_level=evidence_level,
            provenance="llm",
            confidence=0.6 if evidence_level == "high" else 0.5,
            times_confirmed=1,
        )
        db.add(row)

    # Writes here must never break the caller's own work — the SAVEPOINT
    # lesson from §3a: a failed flush poisons the session and the later commit
    # 500s even when the exception was caught.
    try:
        await db.flush()
    except Exception:  # noqa: BLE001
        logger.warning("condition nutrition: could not store %r/%r",
                       condition_key, subject, exc_info=True)
        return None
    return _row_to_fact(row)


async def facts_for_conditions(
    db: AsyncSession,
    conditions: list,
    *,
    resolve_missing: bool = True,
) -> list[NutritionFact]:
    """Everything known about this patient's conditions, resolving gaps once.

    `conditions` are rows from `clinical_sources.conditions()` — never queried
    from a model directly here (§3aa).
    """
    labels: list[str] = []
    codes: dict[str, str | None] = {}
    severities: dict[str, str] = {}
    for c in conditions or []:
        label = getattr(c, "name", None) or getattr(c, "condition_name", None)
        if not label:
            continue
        labels.append(str(label))
        key = normalize_condition(str(label))
        codes[key] = getattr(c, "icd11_code", None)
        sev = getattr(c, "severity", None)
        severities[key] = getattr(sev, "value", None) or (str(sev) if sev else "")

    if not labels:
        return []

    known_codes = [c for c in codes.values() if c]
    facts = await stored_facts(db, labels, codes=known_codes)
    facts = [
        NutritionFact(**{**f.__dict__,
                         "severity": severities.get(normalize_condition(f.condition), "")})
        for f in facts
    ]
    if not resolve_missing:
        return facts

    have = await known_conditions(db, labels, known_codes)
    for label in labels:
        if normalize_condition(label) in have:
            continue
        facts.extend(await resolve_condition(
            db, label, icd11_code=codes.get(normalize_condition(label))))
    return facts


# ── What the patient's body is actually doing ──────────────────────────
#
# A diagnosis label is a claim; the measurements are the evidence. They
# disagree more often than is comfortable, and acting on the label alone
# produces confidently wrong advice:
#
#   * a record carrying "Hypertension" whose 1,840 sessions average 118/77
#     pre-dialysis and 97/62 post, with 43% ending below 90 systolic. The
#     dietary answer to that patient is not the DASH diet; they are
#     hypotensive, and sodium restriction may be actively harmful.
#   * "avoid potassium" asserted for every ESRD patient, when this one's serum
#     K averages 4.93 across six draws, the most recent five months old — and
#     a session clearing 60 L against 90 L of processed blood leaves them
#     RELATIVELY LOW immediately afterwards (§3ac).
#
# So this does not decide anything. It states what was measured, how recently,
# and where that contradicts a diagnosis, and hands that to the model alongside
# the condition guidance. Encoding "if hypotensive then X" would be the same
# hardcoding this module exists to avoid — one layer up.

@dataclass(frozen=True)
class MeasuredState:
    """Observations, and any diagnosis they contradict."""

    observations: list[str]
    contradictions: list[str]

    def __bool__(self) -> bool:
        return bool(self.observations or self.contradictions)


# Windows a clinician would actually look at. An all-time mean over ten years
# of dialysis is not a clinical observation — it buries a trend under a decade
# of history, and the first version of this reported exactly that: "mean 119
# systolic over 1,840 sessions", spanning 2013 to now.
_BP_WINDOWS: tuple[tuple[str, int | None], ...] = (
    ("last 7 days", 7),
    ("last 30 days", 30),
    ("last year", 365),
)

# Lab recency is NOT a number invented here. `dialysis_day_adjustment` already
# defines the project's staleness window against a monthly draw cadence —
# full credit to 14 days, tapering to zero at 30, nothing beyond 30 loaded at
# all (DIALYSIS_BALANCE.md §3). A second threshold in a second module is how
# two parts of the same app come to disagree about whether a result is current.
from app.services.dialysis_day_adjustment import (  # noqa: E402
    FRESH_DAYS as _LAB_FRESH_DAYS,
    STALE_DAYS as _LAB_STALE_DAYS,
)


async def measured_state(db: AsyncSession, user_id: int, conditions: list) -> MeasuredState:
    """Summarise what this patient's own record says, versus their labels."""
    from datetime import date, datetime, timedelta

    from sqlalchemy import func

    from app.models.chronic_conditions import TherapySession
    from app.models.labs import LabResult

    def _as_date(v):
        """lab_results.test_date is a DATE; therapy_sessions.scheduled_date is
        a DATETIME. Coerce both."""
        if v is None:
            return None
        return v.date() if isinstance(v, datetime) else v

    observations: list[str] = []
    contradictions: list[str] = []
    labels = " ".join(
        str(getattr(c, "name", "") or getattr(c, "condition_name", "") or "")
        for c in (conditions or [])
    ).lower()
    today = date.today()

    # ── blood pressure, windowed ──────────────────────────────────────
    bp_lines: list[str] = []
    recent_low_share = None
    recent_pre = None
    for label, days in _BP_WINDOWS:
        since = datetime.now() - timedelta(days=days)
        row = (await db.execute(
            select(
                func.count(TherapySession.id).filter(
                    TherapySession.pre_systolic_bp.isnot(None)),
                func.avg(TherapySession.pre_systolic_bp),
                func.avg(TherapySession.pre_diastolic_bp),
                func.avg(TherapySession.post_systolic_bp),
                func.avg(TherapySession.post_diastolic_bp),
                # Denominator must be sessions that HAVE a post reading, not
                # sessions that have a pre one, or the share is computed across
                # two different populations.
                func.count(TherapySession.id).filter(
                    TherapySession.post_systolic_bp.isnot(None)),
                func.count(TherapySession.id).filter(
                    TherapySession.post_systolic_bp < 90),
            ).where(
                TherapySession.user_id == user_id,
                TherapySession.scheduled_date >= since,
            )
        )).one_or_none()
        if not row or not row[0]:
            continue
        n, pre_s, pre_d, post_s, post_d, n_post, lows = row
        lows = lows or 0
        if not (pre_s and post_s):
            continue
        # Render REAL blood pressures — systolic over diastolic, pre and post
        # stated separately. Printing pre-systolic over post-systolic produced
        # "91/83", which reads as a pulse pressure of 8 and would be a
        # catastrophic finding rather than the two ordinary readings it is.
        pre_txt = f"{pre_s:.0f}/{pre_d:.0f}" if pre_d else f"{pre_s:.0f}"
        post_txt = f"{post_s:.0f}/{post_d:.0f}" if post_d else f"{post_s:.0f}"
        share = (lows / n_post) if n_post else 0.0
        bp_lines.append(
            f"{label}: {n} session(s), mean pre {pre_txt}, post {post_txt}"
            + (f" — {lows} of {n_post} ended below 90 systolic ({share:.0%})"
               if lows else ""))
        # The tightest window with data is the one that describes them NOW.
        if recent_low_share is None:
            recent_low_share, recent_pre = share, pre_s

    if bp_lines:
        observations.append("Blood pressure, by window:")
        observations.extend(f"  {line}" for line in bp_lines)

    if (recent_pre is not None and recent_low_share is not None
            and "hypertension" in labels
            and recent_pre < 140 and recent_low_share >= 0.20):
        contradictions.append(
            "The record lists HYPERTENSION, but recent measured pressures are "
            f"normal pre-treatment ({recent_pre:.0f} systolic) and frequently "
            "hypotensive after. Do not apply blood-pressure-lowering dietary "
            "advice on the strength of the label.")

    # ── labs: recent, or explicitly absent ────────────────────────────
    missing: list[str] = []
    for test, unit in (("potassium", "mmol/L"), ("phosphorus", "mg/dL"),
                       ("hemoglobin", "g/dL")):
        row = (await db.execute(
            select(LabResult.value, LabResult.test_date)
            .where(LabResult.user_id == user_id,
                   LabResult.test_name.ilike(f"%{test}%"),
                   LabResult.value.isnot(None))
            .order_by(LabResult.test_date.desc())
            .limit(1)
        )).first()
        if not row:
            missing.append(test)
            continue
        value, when = row
        d = _as_date(when)
        age = (today - d).days if d else None
        if age is not None and age >= _LAB_STALE_DAYS:
            # NOT presented as "latest". A 147-day-old draw is not this
            # patient's current chemistry, and offering it as one invites
            # advice built on a number nobody has checked since.
            missing.append(f"{test} (last drawn {age} days ago: {value} {unit})")
        elif age is not None and age > _LAB_FRESH_DAYS:
            # Inside the taper. Real, but ageing — say so rather than letting
            # it read as this morning's result.
            observations.append(
                f"{test.capitalize()}: {value} {unit}, {age} days ago — "
                f"past the {_LAB_FRESH_DAYS}-day fresh window, treat as "
                "provisional.")
        else:
            observations.append(
                f"{test.capitalize()}: {value} {unit}"
                + (f", {age} day(s) ago" if age is not None else ""))

    if missing:
        contradictions.append(
            "NO RECENT BLOOD WORK on record for: " + "; ".join(missing) + ". "
            f"Anything {_LAB_STALE_DAYS} days or older is history. Do not "
            "state or imply a current value for these, and say plainly that a "
            "current draw is needed if the advice would depend on one.")

    # ── dialysis clears in gram quantities (§3ac) ─────────────────────
    recent = (await db.execute(
        select(TherapySession.scheduled_date, TherapySession.actual_end_time,
               TherapySession.actual_start_time, TherapySession.total_uf_liters,
               TherapySession.total_blood_volume_processed)
        .where(TherapySession.user_id == user_id,
               TherapySession.scheduled_date.isnot(None))
        .order_by(TherapySession.scheduled_date.desc())
        .limit(1)
    )).first()
    if recent and recent[0]:
        sched, ended, started, uf, blood = recent
        # WHEN THE TREATMENT ENDED is what sets post-dialysis chemistry.
        # `scheduled_date` is stored at midnight, so measuring from it invents
        # up to a day of error and reports it to the hour — false precision on
        # the one number that decides whether potassium is at its trough.
        basis, marker = None, None
        if ended:
            basis, marker = "ended", ended
        elif started:
            basis, marker = "started", started
        if marker is not None:
            hours = (datetime.now() - marker).total_seconds() / 3600.0
            when_str = (f"{hours:.0f} hours ago" if hours < 48
                        else f"{hours / 24:.1f} days ago")
            when_str = f"{when_str} ({basis} {marker:%Y-%m-%d %H:%M})"
        else:
            # No clock time recorded — say the date and claim nothing finer.
            hours = None
            when_str = f"on {_as_date(sched)} (no treatment time recorded)"

        detail = []
        if blood:
            detail.append(f"{blood:.0f} L of blood processed")
        if uf:
            detail.append(f"{uf:.1f} L removed")
        observations.append(
            f"Last dialysis {when_str}"
            + (f" — {', '.join(detail)}" if detail else "") + ".")
        if hours is not None and hours <= 24:
            observations.append(
                "Within 24 hours of treatment, serum potassium and phosphorus "
                "are at their LOWEST of the cycle. A session changes the day's "
                "TOTALS, never the daily limit (§3ac).")

    return MeasuredState(observations=observations, contradictions=contradictions)
