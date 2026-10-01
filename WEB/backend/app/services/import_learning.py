"""Remember what a reviewer decided about a parsed row, and use it next time.

Every import already ends with a human judging each row — `accepted` on the
staged item, and the `accepted_item_ids` the confirm call carries. Nothing has
ever read those back. That is §3ar's dead control on the richest signal in the
product: unlike a model's guess it is the patient or their clinician, looking at
the document, saying "this line is not a result".

This module is deliberately BOTH halves. `telemetry.register_sink` was built,
documented as the corpus ALAFIA distils from, and never called, so every pair
hit `if not _sinks: return` (§3ay). A table with no reader is worse than no
table, so `record_review_decisions` writes and `learned_verdicts` reads, and the
tests exercise the loop end to end.

WHAT IS LEARNED IS A SHAPE, NOT A MEASUREMENT
---------------------------------------------
A signature is built from the normalised NAME the document printed, WHICH column
roles were populated, and the SHAPE of the value — never the value. Haemoglobin
9.4 and haemoglobin 14.1 produce the same signature, which is the property that
lets one patient's review help the next patient's import without either seeing
the other's data.

WHAT A VERDICT MAY DO
---------------------
Untick a row and say why. Nothing else. It may not delete, and it may not
overrule a row the deterministic guard already judged a real measurement — a
learned mistake that silently removed clinical data would be strictly worse than
the boilerplate it was meant to catch.

And it acts only once CONFIRMED MORE THAN ONCE. One person's slip must not teach
the parser to hide an analyte from everybody else.
"""

from __future__ import annotations

import hashlib
import logging
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.import_judgment import (
    DECIDED_BY_REVIEWER,
    VERDICT_FURNITURE,
    VERDICT_RESULT,
    DocumentRowJudgment,
)

logger = logging.getLogger(__name__)

#: Where staging parks the row's signature on the staged payload, so confirm
#: reads back the SAME key instead of recomputing it. `_build_row` constructs
#: clinical rows from named fields and never splats the dict, so these are inert.
SIGNATURE_KEY = "_row_signature"
ROLES_KEY = "_row_roles"
SHAPE_KEY = "_row_value_shape"

#: A judgment is advisory until this many reviewers have agreed.
MIN_CONFIRMATIONS = 2
#: …and until it is this confident. Contradictions pull it back down.
MIN_CONFIDENCE = 0.6

_WHITESPACE = re.compile(r"\s+")


def _normalise(name: str) -> str:
    return _WHITESPACE.sub(" ", (name or "").strip().casefold()).strip(" .,:;")


def _value_shape(value: float | None, value_text: str | None) -> str:
    if value is not None:
        return "numeric"
    text = (value_text or "").strip()
    if not text:
        return "empty"
    return "word" if len(text.split()) == 1 else "words"


def row_signature(
    name: str,
    value: float | None = None,
    value_text: str | None = None,
    unit: str | None = None,
    ref_text: str | None = None,
) -> tuple[str, str, str]:
    """(signature, roles, value_shape) for one parsed row.

    `roles` records which columns the DOCUMENT populated, because that is the
    structure the guard reasons about: on the report that prompted this work,
    every real finding carried a flag and a range while the lab's address and
    the section headings carried neither.
    """
    roles = ",".join(
        role for role, present in (
            ("name", bool((name or "").strip())),
            ("value", value is not None or bool((value_text or "").strip())),
            ("unit", bool((unit or "").strip())),
            ("ref_range", bool((ref_text or "").strip())),
        ) if present
    )
    shape = _value_shape(value, value_text)
    digest = hashlib.sha256(
        f"{_normalise(name)}|{roles}|{shape}".encode("utf-8")
    ).hexdigest()
    return digest, roles, shape


async def learned_verdicts(
    db: AsyncSession, signatures: list[str]
) -> dict[str, DocumentRowJudgment]:
    """Judgments strong enough to act on, keyed by signature.

    Returns only ACTIVE furniture verdicts that clear both thresholds. A result
    verdict needs no action — the row was going to be offered anyway — and
    returning it would invite a caller to treat "we have seen this" as "this is
    definitely fine", which is the reassurance this whole change exists to stop.
    """
    if not signatures:
        return {}
    try:
        rows = await db.execute(
            select(DocumentRowJudgment).where(
                DocumentRowJudgment.signature.in_(signatures),
                DocumentRowJudgment.verdict == VERDICT_FURNITURE,
                DocumentRowJudgment.is_active.is_(True),
                DocumentRowJudgment.times_confirmed >= MIN_CONFIRMATIONS,
                DocumentRowJudgment.confidence >= MIN_CONFIDENCE,
            )
        )
        return {j.signature: j for j in rows.scalars().all()}
    except Exception:  # noqa: BLE001 - a learning outage must never block an import
        logger.warning("learned verdict lookup failed; staging without it", exc_info=True)
        return {}


async def record_review_decisions(
    db: AsyncSession, items, lab_name: str | None = None
) -> int:
    """Learn from what the reviewer just did. Returns how many rows were learned.

    ONLY informative decisions count:

      * `dedupe_status` must be "new" — a duplicate arrives unticked BY DESIGN,
        so unticking it says nothing about whether the row is a result;
      * the item must carry no `error` — the system already flagged those (no
        date, implausible value), and learning from them would teach the parser
        that its own warnings are evidence.

    Re-seeing a shape SHARPENS the existing judgment (`times_confirmed`) rather
    than inserting a second, contradictory one beside it — §3ab's duplicate, in
    the learning store. A disagreement is recorded too and pulls confidence
    down, because a verdict that can only strengthen is not learning.
    """
    learned = 0
    for item in items:
        if item.dedupe_status != "new" or item.error:
            continue
        payload = item.payload or {}
        # Read the signature STAGING computed. Deliberately not recomputed here.
        #
        # Recomputing looked equivalent and was not: staging sees the range as
        # the document PRINTED it, while the payload keeps only the parsed
        # low/high bounds. A range the parser could not read — "< OR = 5 /HPF
        # 01" — is present in one and absent in the other, so the two paths
        # derive DIFFERENT digests for the same row. Lessons would be filed
        # under keys nothing ever looks up, and the whole loop would present as
        # "the learning just never fires".
        signature = payload.get(SIGNATURE_KEY)
        if not signature:
            continue
        roles = payload.get(ROLES_KEY)
        shape = payload.get(SHAPE_KEY)
        verdict = VERDICT_RESULT if item.accepted else VERDICT_FURNITURE

        existing = (await db.execute(
            select(DocumentRowJudgment).where(
                DocumentRowJudgment.signature == signature)
        )).scalar_one_or_none()

        if existing is None:
            db.add(DocumentRowJudgment(
                signature=signature,
                sample_label=(item.source_label or "")[:255] or None,
                roles=roles,
                value_shape=shape,
                verdict=verdict,
                decided_by=DECIDED_BY_REVIEWER,
                times_confirmed=1,
                confidence=0.5,
                lab_name=lab_name,
            ))
        elif existing.verdict == verdict:
            existing.times_confirmed += 1
            # Asymptotic, so no amount of agreement reaches certainty.
            existing.confidence = min(0.95, existing.confidence + 0.15)
        else:
            existing.times_contradicted += 1
            existing.confidence = max(0.0, existing.confidence - 0.25)
            # Reviewers disagree about this shape. Stop acting on it rather than
            # flip-flopping: a row that is furniture on one lab's template can
            # be a real analyte on another's.
            if existing.confidence < MIN_CONFIDENCE:
                existing.is_active = False
                existing.notes = "retired: reviewers disagreed about this shape"
        learned += 1

    return learned
