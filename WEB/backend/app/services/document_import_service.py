# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""Stage a parsed document, then import what the patient accepts.

Two steps on purpose. `stage` writes only to `document_imports` /
`document_import_items`; `confirm` is the only thing that touches a clinical
table, and it writes exactly the rows the reviewer kept.

Canon §3aa applies throughout:

* conditions go to `chronic_conditions` — never `health_conditions`, which has
  no writer and would make every imported diagnosis invisible;
* a medication read off a document is a *prescription*, so it goes to
  `medications`, not `medication_dose_logs`, which records what was actually
  taken;
* duplicate checks read through `app/services/clinical_sources.py`, because
  querying those models directly here would both miss half the data and fail the
  guard in `tests/test_clinical_sources.py`.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chronic_conditions import (
    ChronicCondition,
    ConditionCategory,
    ConditionSeverity,
)
from app.models.document_import import (
    DEDUPE_CONFLICT,
    DEDUPE_DUPLICATE,
    DEDUPE_NEW,
    STATUS_CONFIRMED,
    STATUS_DISCARDED,
    STATUS_FAILED,
    STATUS_PARSED,
    STATUS_REJECTED,
    DocumentImport,
    DocumentImportItem,
)
from app.models.labs import LabResult
from app.models.medications import Medication
from app.services import clinical_sources as sources
from app.services.docparse import claims
from app.services.docparse import classify as doc_types
from app.services.docparse.claims import result_is_reported_failure
from app.services.docparse.dictionaries import analyte_key
from app.services.docparse.pipeline import ParseResult
from app.services.docparse.records_clinical import (
    records_from_condition_table,
    records_from_medication_table,
)
from app.services.import_learning import (
    ROLES_KEY,
    SHAPE_KEY,
    SIGNATURE_KEY,
    learned_verdicts,
    record_review_decisions,
    row_signature,
)
from app.services.plausibility import review_lab_value

logger = logging.getLogger(__name__)

TABLE_LABS = "lab_results"
TABLE_MEDICATIONS = "medications"
TABLE_CONDITIONS = "chronic_conditions"

#: ⚠️ NO LONGER A ROUTER (2026-10-11). Kept because it records which table each
#: document type was ASSUMED to feed, and because `doc_type` is still stored and
#: shown to the reviewer as a hint. Routing is now per-claim — see `stage()`.
#:
#: Reading this as the destination is what made a treatment report importable
#: only as "lab results", and `DIALYSIS_FLOWSHEET: TABLE_LABS` is the line that
#: proves the axis was wrong: a dialysis flowsheet is not a lab report, and the
#: mapping was only harmless because both pointed at the same table.
LEGACY_TARGET_FOR_DOC_TYPE = {
    doc_types.LAB_REPORT: TABLE_LABS,
    doc_types.DIALYSIS_FLOWSHEET: TABLE_LABS,
    doc_types.MEDICATION_LIST: TABLE_MEDICATIONS,
    doc_types.DISCHARGE_SUMMARY: TABLE_CONDITIONS,
}

#: Marks the provenance of anything this pipeline writes, so an imported row can
#: always be told apart from one the patient entered by hand.
IMPORT_SOURCE = "document_import"


# ── Staging ──────────────────────────────────────────────────────────────────

async def find_existing_import(
    db: AsyncSession, user_id: int, content_hash: str
) -> DocumentImport | None:
    """The same file staged before — re-uploading must not duplicate readings."""
    result = await db.execute(
        select(DocumentImport)
        .where(
            DocumentImport.user_id == user_id,
            DocumentImport.content_hash == content_hash,
            # A rejected or DISCARDED import must not block re-uploading the
            # same file. Discarding exists precisely so a bad import can be
            # taken out and the document read again; if the hash still matched a
            # discarded row the patient would be handed back the import they
            # just deleted, and the re-import could never happen.
            DocumentImport.status.notin_([STATUS_REJECTED, STATUS_DISCARDED]),
        )
        .order_by(DocumentImport.id.desc())
    )
    return result.scalars().first()


async def stage(db: AsyncSession, user_id: int, parsed: ParseResult) -> DocumentImport:
    """Persist a parse result for review. Writes no clinical rows."""
    meta = parsed.metadata
    record = DocumentImport(
        user_id=user_id,
        filename=parsed.filename,
        content_hash=parsed.content_hash,
        doc_type=parsed.doc_type,
        doc_type_confidence=parsed.doc_type_confidence,
        classification_method=parsed.classification_method,
        extraction_method=parsed.extraction_method,
        layout_kind=parsed.layout_kind,
        page_count=parsed.page_count,
        parse_confidence=parsed.confidence,
        patient_name=meta.patient_name,
        report_date=str(meta.report_date) if meta.report_date else None,
        lab_name=meta.lab_name,
        ordering_provider=meta.ordering_provider,
        status=STATUS_PARSED if parsed.ok else STATUS_FAILED,
        error_detail=parsed.error_detail,
        notes=list(parsed.notes) or None,
    )
    db.add(record)
    await db.flush()

    # Route on WHAT THE DATA IS, not on one label.
    #
    # `TARGET_FOR_DOC_TYPE` allowed exactly ONE destination per document. Real
    # documents are not one thing: the 10/09 DaVita Treatment Details Report
    # carries a session, six timed readings, pre/post vitals, a prescription and
    # a close reason in one PDF, so no value of `doc_type` could import it — it
    # was written by hand as production session 2776 on 2026-10-10. A visit
    # summary is the same shape: conditions AND medications AND measurements.
    #
    # `document_import_items.target_table` is already a per-item indexed column,
    # `confirm()` already dispatches on it and `_MODEL_FOR_TABLE` already drives
    # discard generically — so several targets per document needs NO migration.
    # This if/elif was the only thing collapsing it to one.
    #
    # The label is KEPT as metadata (it is stored on `record.doc_type` above and
    # shown to the reviewer) and is no longer a switch. That also defuses a live
    # trap: `September labs AA.pdf` classifies as `dialysis_flowsheet` while
    # yielding 75 LAB rows, so anything routing on that label would have broken
    # a working import.
    #
    # Each stager is gated on EVIDENCE, never run unconditionally. Measured over
    # the lab corpus 2026-10-11, calling every extractor stages 1115 false
    # medications and 1115 false conditions beside 1014 true lab rows — more
    # false claims than true ones, because `records_from_medication_table` and
    # `records_from_condition_table` append a record for every named row and were
    # written assuming the caller had already settled the type.
    kinds = claims.kinds_in_document(
        parsed.tables,
        layout_kind=parsed.layout_kind,
        record_count=len(parsed.records),
    )

    items: list[DocumentImportItem] = []
    if claims.MEASUREMENT in kinds:
        items.extend(await _stage_labs(db, user_id, parsed))
    if claims.MEDICATION in kinds:
        items.extend(await _stage_medications(db, user_id, parsed))
    if claims.CONDITION in kinds:
        items.extend(await _stage_conditions(db, user_id, parsed))

    if not items and parsed.ok:
        # Read, and deliberately not filed. §3aa — an error is not an empty
        # state, and this is not a guess either: say what was recognised and
        # that it has nowhere to go, rather than filing it somewhere plausible.
        unplaceable = ", ".join(sorted(kinds)) or "no recognisable clinical data"
        record.error_detail = (
            f"This document was read, but what it contains ({unplaceable}) "
            "cannot be imported yet. The values below are shown for reference "
            "only."
        )

    for item in items:
        item.import_id = record.id
        db.add(item)

    await db.flush()
    return record


async def _stage_labs(db: AsyncSession, user_id: int, parsed: ParseResult) -> list[DocumentImportItem]:
    meta = parsed.metadata
    existing = await _existing_labs(db, user_id)

    # One indexed lookup for the whole document rather than one per row.
    signatures = [
        row_signature(r.raw_name, r.value, r.value_text, r.unit, r.reference_text)[0]
        for r in parsed.records
    ]
    verdicts = await learned_verdicts(db, signatures)

    items: list[DocumentImportItem] = []

    for index, record in enumerate(parsed.records):
        test_date = record.test_date or meta.report_date
        payload: dict[str, Any] = {
            "test_date": str(test_date) if test_date else None,
            "test_name": record.test_name,
            "category": record.category,
            "value": record.value,
            "value_string": record.value_text,
            "unit": record.unit,
            "reference_range_low": record.reference_low,
            "reference_range_high": record.reference_high,
            "is_abnormal": record.is_abnormal,
            "status": (record.status or "final").lower(),
            "ordering_provider": meta.ordering_provider,
            "performing_lab": meta.lab_name,
            "notes": "; ".join(record.notes) or None,
        }

        dedupe, existing_id = DEDUPE_NEW, None
        # Compared by analyte: a report printing ALP must find the "Alk Phos" row
        # already on file, or confirming it writes a second copy beside it.
        key = (str(test_date), analyte_key(record.test_name))
        prior = existing.get(key)
        if prior is not None:
            prior_id, prior_value = prior
            existing_id = prior_id
            dedupe = DEDUPE_DUPLICATE if prior_value == record.value else DEDUPE_CONFLICT

        # What does LOINC say this analyte IS?
        #
        # Deliberately NOT routed through `canonical_name()`. That feeds
        # `analyte_key()`, which is the dedupe key, and §3ab is explicit that a
        # fix which changes the NAME makes a re-import land BESIDE the wrong row
        # instead of correcting it — the patient ends up holding two
        # contradictory values for one date. So the document's wording is left
        # exactly as it was (§3ax) and LOINC is added alongside it.
        #
        # This finally populates `lab_results.loinc_code`, a column that has
        # existed since the first migration and that docparse has never written;
        # only the FHIR import ever filled it in, so the two importers disagreed
        # about identity.
        # ⚠️ LOINC IS DELIBERATELY NOT WIRED HERE (measured 2026-10-01).
        #
        # This block used to read `term = loinc.resolve(record.raw_name)` and
        # write `payload["loinc_code"] = term.loinc_num`. It was removed before
        # it ever reached a patient record, because the resolver cannot yet
        # answer DETERMINATELY and this column is not a place for a default.
        #
        # `scripts/loinc_precision_audit.py`, over the 136 names in
        # ANALYTE_NAMES — 76 resolve, and of those:
        #
        #     29  decided by COMMON_TEST_RANK between tests the authority
        #         itself separates (ALBUMIN: Ser/Plas vs Urine vs Synv fld)
        #     46  answered from the SYNONYM tier, which the resolver's own
        #         docstring calls its weakest and noisiest signal
        #      1  determinate
        #
        # The failure is not theoretical. `Platelet` resolves to 32623-1
        # `PMV Bld Auto` — mean platelet VOLUME — while `Platelets` resolves to
        # 777-3, the count: a singular/plural difference in the printed word
        # changes the analyte. `MCV` resolved to a rheumatoid-arthritis
        # autoantibody until the long-name head index landed.
        #
        # `lab_results.loinc_code` is also written by the FHIR import with codes
        # that came off a real system. Mixing a rank tiebreak into that column
        # makes the two indistinguishable — §3c's confidently-wrong match, with
        # a clinical identifier attached, which this resolver's own docstring
        # calls worse than the 33% dictionary it replaces.
        #
        # `value_shape_disagrees()` is left out for the same reason: a scale
        # warning derived from the WRONG term is a confident false alarm, and
        # §3ab is explicit that a guard which cries wolf gets ticked past — which
        # is how a haematocrit of 338.4 was approved in the first place.
        #
        # WHAT WOULD MAKE IT SAFE: a specimen read off the report, so the
        # (COMPONENT, SYSTEM) tier can fire. `ReportMetadata` carries patient,
        # dates, lab and provider — no specimen — and nothing in the parse result
        # records one, so that is its own change. Until then the document's own
        # wording is the identity (§3ax) and `analyte_key()` does the matching.

        # Is the VALUE possible? Deliberately not "is it abnormal" — a dialysis
        # patient's creatinine of 11.91 is 9.2x its reference ceiling and
        # entirely real. This catches what cannot be true at all: a haematocrit
        # of 338.4%, which reached a real record and was rendered with a green
        # tick beside it.
        #
        # An implausible row is NEVER dropped. It arrives UNTICKED and carries
        # its reason, because the failure this is guarding against is a reviewer
        # in a hurry ticking through what the system already ticked for them.
        problems, believable = review_lab_value(
            record.test_name, record.value, record.unit,
            record.reference_low, record.reference_high,
        )
        if not test_date:
            problems.insert(0, "No date could be determined for this result.")

        # The lab said it could not produce a result, and that was being stored
        # AS one. Measured on the corpus 2026-10-11: 60 rows read `Error` and 60
        # read `N/A`, every one with `has_result` true, confidence 0.75,
        # `is_abnormal` NULL and an empty `notes` — so a reviewer saw 120 rows
        # claiming Albumin, ALP, AST/SGOT, BUN and Calcium were resulted on that
        # date with "Error" as the value, and nothing said otherwise.
        #
        # Worse than cosmetic: dedupe is keyed `(test_date, lower(test_name))`
        # and §3ab records that `existing_row_id` is never read back, so when the
        # lab re-issues a corrected panel the real Albumin lands BESIDE the
        # Error row and the patient holds two contradictory results for one date.
        #
        # `review_lab_value` cannot catch this — it is handed the numeric value
        # and never sees `value_text`. NEG is deliberately NOT a failure: it is a
        # finding, exactly like §3ab's `NONE SEEN`.
        reported_failure = result_is_reported_failure(record.value_text)
        if reported_failure:
            problems.insert(0, (
                f"The report printed “{record.value_text}” here rather than a "
                "result, so nothing was measured for this analyte. Tick it only "
                "if you want that recorded."
            ))

        # What did previous reviewers make of a row shaped like this one?
        #
        # Advisory only: it unticks and explains. It cannot delete, and it does
        # not overrule the deterministic guard — a row that reached here has
        # already been judged a measurement by `row_is_prose`, and a learned
        # mistake that removed clinical data would be worse than the boilerplate
        # this exists to catch.
        signature, roles, shape = row_signature(
            record.raw_name, record.value, record.value_text,
            record.unit, record.reference_text,
        )
        # Stamp it on the staged payload so CONFIRM reads back this exact key
        # rather than recomputing it from a lossier dict — see
        # `record_review_decisions` for what recomputation silently broke.
        payload[SIGNATURE_KEY] = signature
        payload[ROLES_KEY] = roles
        payload[SHAPE_KEY] = shape

        judged = verdicts.get(signature)
        if judged is not None:
            problems.append(
                f"Previous reviewers marked this line as part of the document "
                f"rather than a result ({judged.times_confirmed} times). "
                f"Tick it if that is wrong."
            )

        items.append(DocumentImportItem(
            target_table=TABLE_LABS,
            row_index=index,
            payload=payload,
            source_label=record.raw_name,
            canonical_name=record.test_name,
            confidence=record.confidence,
            dedupe_status=dedupe,
            existing_row_id=existing_id,
            # A duplicate is unticked by default: confirming an import must not
            # quietly write a second copy of a reading already on file. An
            # implausible value is unticked for the same reason.
            # `judged is None` is what makes the learned verdict DO something.
            # Without it the note below still rendered while the row stayed
            # ticked — which is worse than saying nothing, because it tells the
            # reader the case was handled. §3ar, inside the feature built to
            # act on what reviewers decided.
            accepted=((dedupe != DEDUPE_DUPLICATE) and bool(test_date)
                      and believable and judged is None
                      and not reported_failure),
            error="; ".join(problems) or None,
        ))
    return items


async def _existing_labs(db: AsyncSession, user_id: int) -> dict[tuple, tuple[int, float | None]]:
    """(date, analyte) -> (row id, value) for this user's labs.

    `lab_results` is not one of the split-table models, so reading it directly
    is correct here.
    """
    result = await db.execute(
        select(LabResult.id, LabResult.test_date, LabResult.test_name, LabResult.value)
        .where(LabResult.user_id == user_id)
    )
    return {
        (str(row.test_date), analyte_key(row.test_name)): (row.id, row.value)
        for row in result
    }


async def _stage_medications(db: AsyncSession, user_id: int, parsed: ParseResult) -> list[DocumentImportItem]:
    # Prescriptions already on file, read through the canonical source.
    prescribed = await sources.medications_prescribed(db, user_id)
    known = {(m.name or "").lower() for m in prescribed}

    items: list[DocumentImportItem] = []
    records = []
    for table in parsed.tables:
        records.extend(records_from_medication_table(table))

    for index, record in enumerate(records):
        payload = {
            "name": record.name,
            "dosage": record.dosage,
            "dosage_unit": record.dosage_unit,
            "frequency": record.frequency,
            "route": record.route,
            "start_date": str(record.start_date) if record.start_date else None,
            "prescribing_doctor": record.prescribing_doctor or parsed.metadata.ordering_provider,
            "is_active": record.is_active,
            "notes": record.notes,
            "source": IMPORT_SOURCE,
        }
        duplicate = record.name.lower() in known
        items.append(DocumentImportItem(
            target_table=TABLE_MEDICATIONS,
            row_index=index,
            payload=payload,
            source_label=record.raw_name,
            canonical_name=record.name,
            confidence=record.confidence,
            dedupe_status=DEDUPE_DUPLICATE if duplicate else DEDUPE_NEW,
            accepted=not duplicate,
            error="; ".join(record.parse_notes) or None,
        ))
    return items


async def _stage_conditions(db: AsyncSession, user_id: int, parsed: ParseResult) -> list[DocumentImportItem]:
    current = await sources.conditions(db, user_id)
    known = {(c.name or "").lower() for c in current}

    items: list[DocumentImportItem] = []
    records = []
    for table in parsed.tables:
        records.extend(records_from_condition_table(table))

    for index, record in enumerate(records):
        payload = {
            "condition_name": record.condition_name,
            "category": record.category,
            "severity": record.severity,
            "icd10_code": record.icd10_code,
            "diagnosis_date": str(record.diagnosis_date) if record.diagnosis_date else None,
            "is_active": record.is_active,
            "stage": record.stage,
        }
        duplicate = record.condition_name.lower() in known
        items.append(DocumentImportItem(
            target_table=TABLE_CONDITIONS,
            row_index=index,
            payload=payload,
            source_label=record.raw_name,
            canonical_name=record.condition_name,
            confidence=record.confidence,
            dedupe_status=DEDUPE_DUPLICATE if duplicate else DEDUPE_NEW,
            accepted=not duplicate,
            error="; ".join(record.parse_notes) or None,
        ))
    return items


# ── Confirmation ─────────────────────────────────────────────────────────────

async def _live_keys(db: AsyncSession, user_id: int) -> dict[str, set]:
    """What is in each clinical table RIGHT NOW, by the key its stage step uses.

    ⚠️ **Staging deduped against a snapshot and confirm trusted it.**
    `_existing_labs` and the two `known` sets are read when a document is
    STAGED, so a second document staged before the first was confirmed saw a
    table that did not yet contain the first document's rows. Both were marked
    `DEDUPE_NEW` and both were written.

    Measured 2026-10-15 on a two-document batch: albumin for 2026-03-14 landed
    **twice, 4.1 and 4.4** — two contradictory values for one date, which is
    the exact failure §3ab describes and the dedupe exists to prevent.

    Sequential uploading mostly hid it, because confirming A put A's rows in
    `lab_results` before B was ever staged. Multi-file import makes staging two
    documents before confirming either the NORMAL path, so the window stops
    being an edge case.

    The keys are deliberately the SAME ones the stage steps compute — analyte
    identity for labs (§3ax: a report printing ALP must find the "Alk Phos" row
    already on file), folded name for medications and conditions. Two
    computations of one quantity must not disagree (§3ai).
    """
    labs = {
        (str(r.test_date), analyte_key(r.test_name))
        for r in (await db.execute(
            select(LabResult).where(LabResult.user_id == user_id)
        )).scalars().all()
        if r.test_date and r.test_name
    }
    # Both go through the canonical readers, as the stage steps do — a
    # medication lives in more than one table and reading one is how a fact
    # gets hidden (§3aa).
    meds = {(m.name or "").lower()
            for m in await sources.medications_prescribed(db, user_id)}
    conds = {(c.name or "").lower()
             for c in await sources.conditions(db, user_id)}
    return {TABLE_LABS: labs, TABLE_MEDICATIONS: meds, TABLE_CONDITIONS: conds}


def _live_key_for(item: DocumentImportItem):
    """This staged row's key in the shape `_live_keys` holds, or None."""
    payload = item.payload or {}
    if item.target_table == TABLE_LABS:
        date_text, name = payload.get("test_date"), payload.get("test_name")
        if not date_text or not name:
            return None
        return (str(date_text), analyte_key(name))
    if item.target_table == TABLE_MEDICATIONS:
        name = payload.get("medication_name") or payload.get("name")
        return name.lower() if name else None
    if item.target_table == TABLE_CONDITIONS:
        name = payload.get("condition_name")
        return name.lower() if name else None
    return None


async def confirm(
    db: AsyncSession,
    user_id: int,
    record: DocumentImport,
    accepted_item_ids: list[int] | None = None,
) -> dict[str, int]:
    """Write the accepted rows into their clinical tables.

    `accepted_item_ids` overrides the staged decisions when the reviewer changed
    them. Returns a per-table count of what was written.
    """
    counts = {TABLE_LABS: 0, TABLE_MEDICATIONS: 0, TABLE_CONDITIONS: 0}
    #: Re-read NOW, not trusted from stage time. Updated as rows are written,
    #: so a document that repeats an analyte within itself is caught too.
    live = await _live_keys(db, user_id)
    skipped_existing = 0

    for item in record.items:
        wanted = (
            item.id in accepted_item_ids
            if accepted_item_ids is not None
            else item.accepted
        )
        # Write the reviewer's ACTUAL decision back onto the row.
        #
        # `accepted` held the staged default and nothing ever recorded what the
        # person chose, so the learning step below would have learned what the
        # PARSER proposed rather than what the HUMAN decided — the one thing it
        # exists to capture. §3ar, one layer deeper than the usual case: the
        # control was read, just never updated.
        item.accepted = bool(wanted)
        if not wanted or item.imported_row_id is not None:
            continue

        try:
            row = _build_row(user_id, item)
        except Exception as exc:  # noqa: BLE001 - one bad row must not sink the import
            logger.warning("Could not build %s row from item %s: %s", item.target_table, item.id, exc)
            item.error = f"Could not import this row: {exc}"
            continue

        if row is None:
            continue

        # The row may have arrived from ANOTHER document since this one was
        # staged. Writing it anyway is how a patient ends up holding two
        # contradictory values for one date (§3ab).
        #
        # It is SKIPPED, never overwritten: which of two readings is right is a
        # clinical judgement, and §3ab's own instruction for a genuine
        # correction is to delete first and re-import, not to have the importer
        # silently pick. The item says what happened so the reviewer can see it.
        key = _live_key_for(item)
        if key is not None and key in live[item.target_table]:
            item.error = (
                "Already on your record from another document — not added "
                "again. Remove the existing entry first if this one corrects it.")
            skipped_existing += 1
            continue

        db.add(row)
        await db.flush()
        item.imported_row_id = row.id
        if key is not None:
            live[item.target_table].add(key)
        counts[item.target_table] = counts.get(item.target_table, 0) + 1

    # Learn from what the reviewer just decided. This is the half that was
    # missing: `accepted` has always been written and never read back (§3ar).
    #
    # Wrapped, because a learning outage must never fail a clinical import —
    # the same rule §3ah applies to the payment webhook's email. The rows are
    # already written by this point; losing a lesson costs far less than losing
    # the import.
    try:
        learned = await record_review_decisions(db, record.items, record.lab_name)
        if learned:
            logger.info("import %s taught %d row judgments", record.id, learned)
    except Exception:  # noqa: BLE001
        logger.warning("could not record review decisions for import %s",
                       record.id, exc_info=True)

    if skipped_existing:
        logger.info("import %s: %d row(s) already present from another "
                    "document, not written again", record.id, skipped_existing)

    record.status = STATUS_CONFIRMED
    record.confirmed_at = datetime.now(timezone.utc)
    await db.flush()
    return counts


def _build_row(user_id: int, item: DocumentImportItem):
    payload = dict(item.payload or {})

    if item.target_table == TABLE_LABS:
        return LabResult(
            user_id=user_id,
            test_date=_as_date(payload.get("test_date")),
            test_name=payload["test_name"],
            category=payload.get("category"),
            value=payload.get("value"),
            value_string=payload.get("value_string"),
            unit=payload.get("unit"),
            reference_range_low=payload.get("reference_range_low"),
            reference_range_high=payload.get("reference_range_high"),
            is_abnormal=payload.get("is_abnormal"),
            status=payload.get("status") or "final",
            ordering_provider=payload.get("ordering_provider"),
            performing_lab=payload.get("performing_lab"),
            notes=payload.get("notes"),
        )

    if item.target_table == TABLE_MEDICATIONS:
        # Prescriptions, not dose logs — canon §3aa.
        return Medication(
            user_id=user_id,
            name=payload["name"],
            dosage=payload.get("dosage"),
            dosage_unit=payload.get("dosage_unit"),
            frequency=payload.get("frequency"),
            route=payload.get("route"),
            start_date=_as_date(payload.get("start_date")),
            prescribing_doctor=payload.get("prescribing_doctor"),
            is_active=bool(payload.get("is_active", True)),
            notes=payload.get("notes"),
            source=payload.get("source") or IMPORT_SOURCE,
        )

    if item.target_table == TABLE_CONDITIONS:
        # chronic_conditions, never health_conditions — canon §3aa.
        return ChronicCondition(
            user_id=user_id,
            condition_name=payload["condition_name"],
            category=ConditionCategory(payload.get("category") or "other"),
            severity=ConditionSeverity(payload.get("severity") or "moderate"),
            icd10_code=payload.get("icd10_code"),
            diagnosis_date=_as_datetime(payload.get("diagnosis_date")),
            is_active=bool(payload.get("is_active", True)),
            stage=payload.get("stage"),
        )

    return None


def _as_date(value):
    from datetime import date as _date

    if not value:
        return None
    if isinstance(value, _date):
        return value
    return _date.fromisoformat(str(value)[:10])


def _as_datetime(value):
    parsed = _as_date(value)
    return datetime(parsed.year, parsed.month, parsed.day) if parsed else None


async def reject(db: AsyncSession, record: DocumentImport) -> None:
    record.status = STATUS_REJECTED
    await db.flush()


#: Which model each staged row was written into, so a discard can take it back
#: out of the same table it went into.
_MODEL_FOR_TABLE = {
    TABLE_LABS: LabResult,
    TABLE_MEDICATIONS: Medication,
    TABLE_CONDITIONS: ChronicCondition,
}


async def discard(
    db: AsyncSession, user_id: int, record: DocumentImport
) -> dict[str, int]:
    """Take a CONFIRMED import back out — delete the rows it wrote.

    Returns a per-table count of what was removed.

    WHY THIS HAS TO EXIST. §3ab: a parser fix does not repair what it already
    imported, and re-importing makes it WORSE. Dedupe is keyed on
    `(test_date, lower(test_name))` and the commit path only ever constructs a
    new row, so a corrected reading lands BESIDE the wrong one and the patient
    ends up holding two contradictory values for one date. The documented remedy
    has always been "delete first, then re-import" — and until now the only way
    to do that was a DBA running SQL against production. `reject` does not do
    it: that marks an import nothing was ever written from.

    WHAT MAKES IT SAFE. `imported_row_id` is stamped on every staged row at
    confirm time, so this deletes exactly the rows THIS import created — not
    everything matching a name and a date, which would take out readings the
    patient entered by hand or a different document supplied. `lab_results`
    carries no foreign keys pointing at it (checked), so nothing is orphaned.

    Every delete is scoped by `user_id` as well as by row id. The id alone would
    be enough given the import is already loaded for this patient, and it is
    still written twice: a bug in the row that finds the import must never
    become a bug that deletes somebody else's clinical record.

    `imported_row_id` is cleared as each row goes, so a discard interrupted
    half-way can be run again without trying to delete rows that are gone.
    """
    removed: dict[str, int] = {}
    for item in record.items:
        if item.imported_row_id is None:
            continue
        model = _MODEL_FOR_TABLE.get(item.target_table)
        if model is None:
            logger.warning(
                "Import %s item %s targets unknown table %r — left in place",
                record.id, item.id, item.target_table,
            )
            continue

        result = await db.execute(
            delete(model).where(
                model.id == item.imported_row_id,
                model.user_id == user_id,
            )
        )
        if result.rowcount:
            removed[item.target_table] = removed.get(item.target_table, 0) + result.rowcount
        # Whether or not a row was there, this item no longer points at one.
        item.imported_row_id = None

    record.status = STATUS_DISCARDED
    await db.flush()
    return removed
