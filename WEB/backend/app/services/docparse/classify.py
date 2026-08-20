"""Layer 2 — decide what kind of clinical document this is.

Deterministic first: each type has a signature of vocabulary and structure, and
a document that matches one clearly is settled without a model. Only a genuinely
ambiguous document is put to the local LLM, and only as redacted excerpt.

That order matters for more than cost. A deterministic classifier is testable
and gives the same answer twice, which is what lets the import pipeline be
verified at all.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

LAB_REPORT = "lab_report"
MEDICATION_LIST = "medication_list"
DISCHARGE_SUMMARY = "discharge_summary"
DIALYSIS_FLOWSHEET = "dialysis_flowsheet"
IMAGING_REPORT = "imaging_report"
UNKNOWN = "unknown"

#: type -> (strong terms, weak terms). Strong terms are close to decisive.
SIGNATURES: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    LAB_REPORT: (
        ("lab draw report", "laboratory report", "specimen collected",
         "reference range", "result release date", "performing lab"),
        ("hemoglobin", "creatinine", "albumin", "ferritin", "potassium", "wbc",
         "analyte", "collection date", "clia", "final", "specimen"),
    ),
    MEDICATION_LIST: (
        ("medication list", "current medications", "prescription list",
         "discharge medications", "medication reconciliation"),
        ("mg", "tablet", "capsule", "oral", "twice daily", "once daily", "prn",
         "refill", "sig", "dispense", "pharmacy", "rxnorm"),
    ),
    DISCHARGE_SUMMARY: (
        ("discharge summary", "hospital course", "discharge diagnosis",
         "admission diagnosis", "principal diagnosis", "problem list"),
        ("admitted", "discharged", "icd-10", "diagnosis", "chief complaint",
         "history of present illness", "assessment and plan"),
    ),
    DIALYSIS_FLOWSHEET: (
        ("treatment flowsheet", "dialysis flowsheet", "run sheet",
         "intradialytic", "patient profile worksheet"),
        ("kt/v", "urr", "ultrafiltration", "dialysate", "blood flow", "dry weight",
         "pre-weight", "post-weight", "exchange", "dwell", "modality"),
    ),
    IMAGING_REPORT: (
        ("radiology report", "impression:", "findings:", "technique:"),
        ("ct", "mri", "ultrasound", "x-ray", "radiograph", "contrast", "imaging"),
    ),
}

_STRONG_WEIGHT = 6
_WEAK_WEIGHT = 1

#: Below this, the deterministic scorer is not trusted on its own.
_CONFIDENT_SCORE = 8
_WORD = re.compile(r"[a-z0-9][a-z0-9/\-\.']*")


@dataclass
class Classification:
    doc_type: str
    confidence: float
    method: str = "signature"      # "signature" | "structure" | "model"
    scores: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def _score(text: str) -> dict[str, int]:
    lowered = text.lower()
    tokens = set(_WORD.findall(lowered))

    scores: dict[str, int] = {}
    for doc_type, (strong, weak) in SIGNATURES.items():
        total = 0
        for phrase in strong:
            if phrase in lowered:
                total += _STRONG_WEIGHT
        for phrase in weak:
            if " " in phrase:
                total += _WEAK_WEIGHT if phrase in lowered else 0
            else:
                total += _WEAK_WEIGHT if phrase in tokens else 0
        scores[doc_type] = total
    return scores


def classify(
    text: str,
    *,
    has_lab_table: bool = False,
    has_trend_matrix: bool = False,
) -> Classification:
    """Classify from text plus what the layout engines found.

    Structure is evidence in its own right: a document whose columns resolved to
    RESULT and REFERENCE RANGE is a lab report whatever its title says.
    """
    scores = _score(text)
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    best_type, best_score = ranked[0]
    runner_up = ranked[1][1] if len(ranked) > 1 else 0

    if has_lab_table:
        scores[LAB_REPORT] = scores.get(LAB_REPORT, 0) + _STRONG_WEIGHT
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        best_type, best_score = ranked[0]
        runner_up = ranked[1][1] if len(ranked) > 1 else 0

    margin = best_score - runner_up
    if best_score >= _CONFIDENT_SCORE and margin >= 3:
        confidence = min(0.5 + 0.05 * margin, 0.98)
        method = "structure" if has_lab_table else "signature"
        return Classification(best_type, round(confidence, 2), method, scores)

    if has_trend_matrix and scores.get(DIALYSIS_FLOWSHEET, 0) >= _WEAK_WEIGHT * 3:
        return Classification(
            DIALYSIS_FLOWSHEET, 0.6, "structure", scores,
            ["Classified from a trend grid rather than a title."],
        )

    if best_score == 0:
        return Classification(UNKNOWN, 0.0, "signature", scores)

    return Classification(
        best_type,
        round(min(0.3 + 0.03 * best_score, 0.6), 2),
        "signature",
        scores,
        ["Signature match was weak — confirm the document type before importing."],
    )


async def classify_with_model(text: str, fallback: Classification) -> Classification:
    """Ask the local model only when the deterministic pass was unsure.

    `text` must already be redacted. Any failure returns the deterministic
    answer — a classifier outage must not block an import.
    """
    if fallback.confidence >= 0.7:
        return fallback

    try:
        from app.services.alafia_model_service import alafia_chat_detailed
    except ImportError:  # pragma: no cover - app-only dependency
        return fallback

    options = ", ".join(SIGNATURES.keys())
    prompt = (
        "Classify this clinical document. Reply with JSON only: "
        '{"type": "<one of: ' + options + ', unknown>", "confidence": <0-1>}.\n\n'
        f"{text[:2000]}"
    )

    try:
        result = await alafia_chat_detailed(
            [{"role": "user", "content": prompt}],
            temperature=0.0,
            json_mode=True,
            task="doc_classify",
        )
        import json

        payload = json.loads(result.get("text") or "{}")
        doc_type = str(payload.get("type", "")).strip().lower()
        if doc_type in SIGNATURES or doc_type == UNKNOWN:
            confidence = float(payload.get("confidence", 0.5))
            return Classification(
                doc_type,
                round(max(0.0, min(confidence, 0.95)), 2),
                "model",
                fallback.scores,
                ["Document type proposed by the local model."],
            )
    except Exception as exc:  # noqa: BLE001 - classification must never block
        logger.info("Model classification unavailable: %s", exc)

    return fallback
