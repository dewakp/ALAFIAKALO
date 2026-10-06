# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""FHIR Encounter / Procedure → hospital history rows.

Pure mapper tests: no database, no network. They exist because the mappers
make several decisions that look like oversights to a later reader and are
deliberate, and a decision nobody pinned is a decision somebody "fixes":

- a partial `Encounter.class` map (only the unambiguous codes),
- `not-done` and `entered-in-error` producing NO row at all,
- `ongoing_effects` never being derived from a procedure name,
- an over-long unrecognised system URI never being truncated into the column.
"""

from datetime import datetime

from app.models.hospitalization import (AdmissionStatus, AdmissionType,
                                        ProcedureOutcome)
from app.services.smart_fhir import map_encounter, map_procedure

SNOMED = "http://snomed.info/sct"


# ── Encounter ────────────────────────────────────────────────────────────────

def test_an_encounter_without_a_start_is_not_a_stay():
    assert map_encounter({"id": "e1", "status": "finished"}) is None
    assert map_encounter({"id": "e1", "period": {"end": "2024-03-06T09:00:00Z"}}) is None


def test_a_finished_encounter_maps_to_a_discharged_stay():
    row = map_encounter({
        "id": "enc-1",
        "status": "finished",
        "class": {"code": "EMER"},
        "period": {"start": "2024-03-02T14:00:00Z", "end": "2024-03-06T09:30:00Z"},
        "serviceProvider": {"display": "Montgomery General"},
        "reasonCode": [{"text": "Fluid overload"}],
        "hospitalization": {"dischargeDisposition": {"text": "Home"}},
    })
    assert row["admitted_at"] == datetime(2024, 3, 2, 14, 0)
    assert row["discharged_at"] == datetime(2024, 3, 6, 9, 30)
    # tz-naive: both columns are DateTime without timezone, and an aware value
    # raises asyncpg DataError on the first comparison.
    assert row["admitted_at"].tzinfo is None
    assert row["status"] is AdmissionStatus.DISCHARGED
    assert row["admission_type"] is AdmissionType.EMERGENCY
    assert row["facility_name"] == "Montgomery General"
    assert row["reason"] == "Fluid overload"
    assert row["discharge_disposition"] == "Home"
    assert row["external_ref"] == "FHIR:enc-1"
    assert row["source"] == "fhir"


def test_a_stay_in_progress_has_no_discharge():
    row = map_encounter({
        "id": "enc-2", "status": "in-progress",
        "period": {"start": "2026-09-30T03:15:00Z"},
    })
    assert row["discharged_at"] is None
    assert row["status"] is AdmissionStatus.IN_PROGRESS


def test_an_unmapped_class_leaves_admission_type_absent():
    """Partial on purpose — IMP and AMB state a SETTING, not a reason.

    `IMP` says inpatient and `AMB` says ambulatory; neither says whether the
    admission was elective, urgent or a day case. Choosing the nearest-looking
    member would put a clinical claim in the record that the source never made,
    so the key is simply absent and the column stays NULL.
    """
    for code in ("IMP", "AMB", "ACUTE", ""):
        row = map_encounter({
            "id": "e", "status": "finished", "class": {"code": code},
            "period": {"start": "2024-01-01T00:00:00Z"},
        })
        assert "admission_type" not in row, code


def test_an_unknown_status_falls_through_to_the_column_default():
    """`entered-in-error` and `unknown` are not states of a stay."""
    for status in ("entered-in-error", "unknown", ""):
        row = map_encounter({
            "id": "e", "status": status,
            "period": {"start": "2024-01-01T00:00:00Z"},
        })
        assert "status" not in row, status


def test_the_facility_falls_back_to_the_first_named_location():
    row = map_encounter({
        "id": "e", "period": {"start": "2024-01-01T00:00:00Z"},
        "location": [{"location": {}}, {"location": {"display": "Ward B, St Luke's"}}],
    })
    assert row["facility_name"] == "Ward B, St Luke's"


def test_an_unparseable_date_does_not_invent_one():
    assert map_encounter({"id": "e", "period": {"start": "last Tuesday"}}) is None
    row = map_encounter({
        "id": "e", "period": {"start": "2024-01-01T00:00:00Z", "end": "soon"},
    })
    assert row["discharged_at"] is None


def test_a_resource_with_no_id_is_refused_rather_than_given_a_colliding_key():
    """"FHIR:None" would make two different stays dedupe against each other.

    The marker is the dedupe key, so an absent id does not merely weaken
    dedupe — it makes the SECOND real admission look like a duplicate of the
    first and vanish. Refusing the row is the direction that loses less, and a
    server-returned resource always carries an id.
    """
    assert map_encounter({
        "status": "finished",
        "period": {"start": "2024-03-02T14:00:00Z"},
        "serviceProvider": {"display": "Montgomery General"},
    }) is None
    assert map_procedure({
        "status": "completed", "code": {"text": "Parathyroidectomy"},
    }) is None


# ── Procedure ────────────────────────────────────────────────────────────────

def test_a_procedure_that_never_happened_is_not_imported():
    """`not-done` says the operation did NOT take place.

    Importing it as a row in a surgical history would assert an operation the
    patient never had — and `ongoing_effects` reasoning downstream would treat
    it as real.
    """
    for status in ("not-done", "entered-in-error"):
        assert map_procedure({
            "id": "p", "status": status,
            "code": {"text": "Parathyroidectomy"},
            "performedDateTime": "2019-06-11T08:00:00Z",
        }) is None, status


def test_a_procedure_without_a_name_is_not_a_procedure():
    assert map_procedure({"id": "p", "status": "completed", "code": {}}) is None


def test_a_completed_procedure_carries_its_code_with_its_system():
    row = map_procedure({
        "id": "proc-1",
        "status": "completed",
        "code": {"text": "Parathyroidectomy",
                 "coding": [{"system": SNOMED, "code": "36360001"}]},
        "performedDateTime": "2019-06-11T08:00:00Z",
        "bodySite": [{"text": "Parathyroid gland"}],
        "outcome": {"coding": [{"system": SNOMED, "code": "385669000"}]},
        "performer": [{"actor": {}}, {"actor": {"display": "Dr A. Surgeon"}}],
        "location": {"display": "Montgomery General"},
        "encounter": {"reference": "Encounter/enc-1"},
    })
    assert row["name"] == "Parathyroidectomy"
    assert row["code"] == "36360001"
    assert row["code_system"] == "SNOMED"
    assert row["performed_at"] == datetime(2019, 6, 11, 8, 0)
    assert row["body_site"] == "Parathyroid gland"
    assert row["outcome"] is ProcedureOutcome.SUCCESSFUL
    assert row["surgeon"] == "Dr A. Surgeon"
    assert row["facility_name"] == "Montgomery General"
    assert row["_encounter_fhir_id"] == "enc-1"
    assert row["external_ref"] == "FHIR:proc-1"


def test_a_procedure_with_no_encounter_still_maps():
    """The orphan case, at the import boundary.

    The caller reads `_encounter_fhir_id` as None and leaves
    `hospitalization_id` NULL rather than discarding the row.
    """
    row = map_procedure({
        "id": "p", "status": "completed",
        "code": {"text": "Cataract surgery"},
        "performedPeriod": {"start": "2022-01-04T10:00:00Z"},
    })
    assert row["_encounter_fhir_id"] is None
    assert row["performed_at"] == datetime(2022, 1, 4, 10, 0)


def test_an_over_long_unknown_system_is_recorded_whole_not_truncated():
    """`code_system` is String(40); half a URI is a WRONG vocabulary name."""
    system = "http://example.org/terminology/local-procedure-codes/v2"
    assert len(system) > 40
    row = map_procedure({
        "id": "p", "status": "completed",
        "code": {"text": "Local procedure",
                 "coding": [{"system": system, "code": "LP-9"}]},
    })
    assert "code_system" not in row
    assert row["notes"] == f"code system: {system}"
    assert row["code"] == "LP-9"


def test_a_short_unknown_system_is_kept_as_itself():
    """Unrecognised is not unusable — provenance survives."""
    row = map_procedure({
        "id": "p", "status": "completed",
        "code": {"text": "Local procedure",
                 "coding": [{"system": "urn:oid:2.16.840.1.113883.6.4",
                             "code": "0JH60XZ"}]},
    })
    assert row["code_system"] == "urn:oid:2.16.840.1.113883.6.4"


def test_an_unrecognised_outcome_code_is_left_unset():
    row = map_procedure({
        "id": "p", "status": "completed",
        "code": {"text": "Appendectomy"},
        "outcome": {"coding": [{"system": SNOMED, "code": "999999999"}]},
    })
    assert "outcome" not in row


def test_ongoing_effects_is_never_derived_from_the_procedure_name():
    """FHIR has no field for it, so nothing may claim one (§0).

    This is the field the whole model was written for — a parathyroidectomy
    explains a calcium requirement no guideline default can — which is exactly
    why it must come from something that SAYS it, not from pattern-matching an
    operation name.
    """
    row = map_procedure({
        "id": "p", "status": "completed",
        "code": {"text": "Parathyroidectomy"},
        "performedDateTime": "2019-06-11T08:00:00Z",
    })
    assert "ongoing_effects" not in row
