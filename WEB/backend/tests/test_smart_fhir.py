"""Tests for the SMART on FHIR service: PKCE, token crypto, FHIR→ALAFIA mapping."""

from datetime import date

import pytest
from httpx import AsyncClient

from app.services.smart_fhir import (
    build_authorize_url,
    decrypt_token,
    encrypt_token,
    make_pkce,
    map_condition,
    map_lab_observation,
    map_medication_request,
    map_vital_observations,
)


# ── PKCE + crypto ────────────────────────────────────────────────────────

def test_pkce_shape():
    verifier, challenge = make_pkce()
    assert 43 <= len(verifier) <= 128
    assert challenge and "=" not in challenge  # S256, base64url unpadded


def test_token_roundtrip():
    blob = encrypt_token("secret-access-token")
    assert blob != "secret-access-token"
    assert decrypt_token(blob) == "secret-access-token"
    assert encrypt_token(None) is None
    assert decrypt_token(None) is None
    assert decrypt_token("garbage") is None


def test_authorize_url_contains_smart_params():
    url = build_authorize_url(
        "https://portal.example.org/oauth2/authorize",
        "https://portal.example.org/api/FHIR/R4",
        "client-123", "http://localhost:8080/ehr/callback", "st4te", "ch4llenge",
    )
    for frag in ("response_type=code", "client_id=client-123", "aud=", "state=st4te",
                 "code_challenge=ch4llenge", "code_challenge_method=S256"):
        assert frag in url


# ── Lab Observation mapping ──────────────────────────────────────────────

def test_map_lab_observation():
    obs = {
        "id": "obs-1", "status": "final",
        "code": {"coding": [{"system": "http://loinc.org", "code": "2823-3",
                             "display": "Potassium"}], "text": "Potassium"},
        "effectiveDateTime": "2025-08-18T09:30:00Z",
        "valueQuantity": {"value": 4.2, "unit": "mmol/L"},
        "referenceRange": [{"low": {"value": 3.5}, "high": {"value": 5.1}}],
        "interpretation": [{"coding": [{"code": "N"}]}],
    }
    row = map_lab_observation(obs)
    assert row["test_name"] == "Potassium"
    assert row["test_date"] == date(2025, 8, 18)
    assert row["value"] == 4.2 and row["unit"] == "mmol/L"
    assert row["loinc_code"] == "2823-3"
    assert row["reference_range_low"] == 3.5 and row["reference_range_high"] == 5.1
    assert row["is_abnormal"] is False
    assert row["notes"] == "FHIR:obs-1"


def test_map_lab_observation_skips_valueless():
    assert map_lab_observation({"id": "x", "code": {"text": "Panel"},
                                "effectiveDateTime": "2025-01-01"}) is None


# ── Vital-signs mapping (incl. BP panel + unit conversion) ───────────────

def test_map_vitals_bp_panel_and_units():
    observations = [
        {   # BP panel with components
            "id": "bp-1", "effectiveDateTime": "2026-06-01T08:00:00Z",
            "code": {"coding": [{"code": "85354-9"}]},
            "component": [
                {"code": {"coding": [{"code": "8480-6"}]}, "valueQuantity": {"value": 120}},
                {"code": {"coding": [{"code": "8462-4"}]}, "valueQuantity": {"value": 80}},
            ],
        },
        {   # weight in pounds → kg
            "id": "wt-1", "effectiveDateTime": "2026-06-01T08:05:00Z",
            "code": {"coding": [{"code": "29463-7"}]},
            "valueQuantity": {"value": 154.32, "unit": "lb"},
        },
        {   # temperature in °F → °C
            "id": "tmp-1", "effectiveDateTime": "2026-06-01T08:06:00Z",
            "code": {"coding": [{"code": "8310-5"}]},
            "valueQuantity": {"value": 98.6, "unit": "[degF]"},
        },
    ]
    by_day = map_vital_observations(observations)
    row = by_day[date(2026, 6, 1)]
    assert row["blood_pressure_systolic"] == 120
    assert row["blood_pressure_diastolic"] == 80
    assert abs(row["weight_kg"] - 70.0) < 0.05
    assert abs(row["body_temperature_c"] - 37.0) < 0.05


# ── MedicationRequest mapping ────────────────────────────────────────────

def test_map_medication_request():
    mr = {
        "id": "mr-1", "status": "active", "authoredOn": "2026-02-10",
        "medicationCodeableConcept": {
            "text": "Lisinopril 10 MG Oral Tablet",
            "coding": [{"system": "http://www.nlm.nih.gov/research/umls/rxnorm", "code": "314076"}],
        },
        "requester": {"display": "Dr. James Okafor"},
        "dosageInstruction": [{
            "text": "Take once daily",
            "doseAndRate": [{"doseQuantity": {"value": 10, "unit": "mg"}}],
        }],
    }
    row = map_medication_request(mr)
    assert row["name"].startswith("Lisinopril")
    assert row["rxnorm_code"] == "314076"
    assert row["is_active"] is True
    assert row["dosage"] == "10" and row["dosage_unit"] == "mg"
    assert row["frequency"] == "Take once daily"
    assert row["prescribing_doctor"] == "Dr. James Okafor"
    assert row["start_date"] == date(2026, 2, 10)


# ── Condition mapping ────────────────────────────────────────────────────

def test_map_condition_categorizes():
    cond = {
        "id": "c-1",
        "clinicalStatus": {"coding": [{"code": "active"}]},
        "code": {"text": "Chronic Kidney Disease Stage 3",
                 "coding": [{"system": "http://hl7.org/fhir/sid/icd-10-cm", "code": "N18.3"}]},
        "onsetDateTime": "2024-05-01",
    }
    row = map_condition(cond)
    assert row["condition_name"].startswith("Chronic Kidney")
    assert row["category"] == "renal"
    assert row["icd10_code"] == "N18.3"
    assert row["is_active"] is True


def test_map_condition_icd_chapter_fallback():
    row = map_condition({"id": "c2", "code": {
        "text": "Some unusual disorder",
        "coding": [{"system": "http://hl7.org/fhir/sid/icd-10-cm", "code": "I25.10"}],
    }})
    assert row["category"] == "cardiovascular"


# ── Endpoint auth-gates ──────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("method,path", [
    ("get", "/api/v1/ehr/organizations"),
    ("post", "/api/v1/ehr/connect"),
    ("post", "/api/v1/ehr/exchange"),
    ("post", "/api/v1/ehr/connections/1/sync"),
])
async def test_ehr_endpoints_require_auth(client: AsyncClient, method, path):
    r = await getattr(client, method)(path, **({"json": {}} if method == "post" else {}))
    assert r.status_code == 401
