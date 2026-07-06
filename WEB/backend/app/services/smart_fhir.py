"""SMART on FHIR client for patient-portal record access (Epic MyChart et al.).

Implements the patient-facing "standalone launch" described by the SMART App
Launch spec (v2), which is what Epic MyChart portals (Kaiser Permanente,
Trinity Health, …) expose for consumer apps:

  1. Organization discovery — Epic publishes a public FHIR Bundle of every
     production R4 endpoint (open.epic.com/Endpoints/R4). We ingest it into
     `ehr_endpoints` so users can pick their portal by name.
  2. SMART discovery — {fhir_base}/.well-known/smart-configuration gives the
     org's authorize + token URLs.
  3. OAuth2 authorization-code + PKCE (public client, no secret) — the user
     signs in on their portal's own MyChart page; we never see credentials.
  4. FHIR R4 pulls (Patient, Observation, MedicationRequest, Condition) and
     mapping into ALAFIA's native tables.

Access/refresh tokens are encrypted at rest (Fernet keyed off SECRET_KEY).
"""

import base64
import hashlib
import logging
import secrets
from datetime import date, datetime, timezone

import httpx
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

logger = logging.getLogger(__name__)

EPIC_DIRECTORY_URL = "https://open.epic.com/Endpoints/R4"

# Patient-access scopes. Epic grants only what the app registration + the
# patient approve; unsupported scopes are ignored by the server.
DEFAULT_SCOPES = (
    "openid fhirUser launch/patient offline_access "
    "patient/Patient.read patient/Observation.read "
    "patient/MedicationRequest.read patient/Condition.read "
    "patient/AllergyIntolerance.read patient/Immunization.read"
)

# ── Token encryption ─────────────────────────────────────────────────────


def _fernet() -> Fernet:
    key = hashlib.sha256(f"ehr-tokens:{settings.SECRET_KEY}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_token(token: str | None) -> str | None:
    return _fernet().encrypt(token.encode()).decode() if token else None


def decrypt_token(blob: str | None) -> str | None:
    if not blob:
        return None
    try:
        return _fernet().decrypt(blob.encode()).decode()
    except InvalidToken:
        return None


# ── PKCE ─────────────────────────────────────────────────────────────────


def make_pkce() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) for S256 PKCE."""
    verifier = secrets.token_urlsafe(64)[:128]
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


# ── Organization directory ───────────────────────────────────────────────


async def fetch_epic_directory() -> list[dict]:
    """Fetch Epic's public R4 endpoint Bundle → [{name, fhir_base_url}]."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(EPIC_DIRECTORY_URL, headers={"Accept": "application/json"})
        resp.raise_for_status()
        bundle = resp.json()

    orgs: list[dict] = []
    seen_urls: set[str] = set()
    for entry in bundle.get("entry", []):
        res = entry.get("resource", {})
        if res.get("status") not in (None, "active"):
            continue
        contained = res.get("contained") or [{}]
        name = (contained[0].get("name") or "").strip()
        address = (res.get("address") or "").strip()
        # The directory occasionally lists one base URL under several org
        # names (case variants included) — keep the first, match case-insensitively.
        key = address.lower()
        if name and address and key not in seen_urls:
            seen_urls.add(key)
            orgs.append({"name": name, "fhir_base_url": address, "vendor": "epic"})
    return orgs


# ── SMART discovery ──────────────────────────────────────────────────────


async def smart_discover(fhir_base: str) -> dict:
    """Resolve the authorize/token endpoints for a FHIR server.

    Tries .well-known/smart-configuration, falls back to the CapabilityStatement
    OAuth-URIs extension (older Epic deployments).
    """
    base = fhir_base.rstrip("/")
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        try:
            resp = await client.get(
                f"{base}/.well-known/smart-configuration",
                headers={"Accept": "application/json"},
            )
            if resp.status_code == 200:
                cfg = resp.json()
                if cfg.get("authorization_endpoint") and cfg.get("token_endpoint"):
                    return {
                        "authorization_endpoint": cfg["authorization_endpoint"],
                        "token_endpoint": cfg["token_endpoint"],
                    }
        except httpx.HTTPError:
            pass

        # Fallback: CapabilityStatement security extension
        resp = await client.get(f"{base}/metadata", headers={"Accept": "application/fhir+json"})
        resp.raise_for_status()
        meta = resp.json()
        for rest in meta.get("rest", []):
            for ext in (rest.get("security", {}).get("extension") or []):
                if ext.get("url", "").endswith("oauth-uris"):
                    uris = {e["url"]: e.get("valueUri") for e in ext.get("extension", [])}
                    if uris.get("authorize") and uris.get("token"):
                        return {
                            "authorization_endpoint": uris["authorize"],
                            "token_endpoint": uris["token"],
                        }
    raise RuntimeError("This organization's portal does not advertise SMART OAuth endpoints")


def build_authorize_url(
    authorization_endpoint: str,
    fhir_base: str,
    client_id: str,
    redirect_uri: str,
    state: str,
    code_challenge: str,
    scopes: str = DEFAULT_SCOPES,
) -> str:
    params = httpx.QueryParams({
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": scopes,
        "state": state,
        "aud": fhir_base,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    })
    sep = "&" if "?" in authorization_endpoint else "?"
    return f"{authorization_endpoint}{sep}{params}"


async def exchange_code(
    token_endpoint: str,
    code: str,
    redirect_uri: str,
    client_id: str,
    code_verifier: str,
) -> dict:
    """Authorization-code → token exchange (public client + PKCE)."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            token_endpoint,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": client_id,
                "code_verifier": code_verifier,
            },
            headers={"Accept": "application/json"},
        )
        if resp.status_code != 200:
            logger.warning("Token exchange failed (%s): %s", resp.status_code, resp.text[:300])
            raise RuntimeError(f"The portal rejected the sign-in ({resp.status_code}).")
        return resp.json()


async def refresh_access_token(token_endpoint: str, refresh_token: str, client_id: str) -> dict | None:
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            token_endpoint,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": client_id,
            },
            headers={"Accept": "application/json"},
        )
        return resp.json() if resp.status_code == 200 else None


# ── FHIR reads ───────────────────────────────────────────────────────────


async def fhir_search(fhir_base: str, access_token: str, resource: str, params: dict) -> list[dict]:
    """Search a FHIR resource, following pagination. Returns resource dicts."""
    base = fhir_base.rstrip("/")
    out: list[dict] = []
    url: str | None = f"{base}/{resource}"
    query: dict | None = params
    async with httpx.AsyncClient(timeout=45.0, follow_redirects=True) as client:
        for _ in range(10):  # page cap
            resp = await client.get(
                url, params=query,
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/fhir+json"},
            )
            if resp.status_code != 200:
                logger.info("FHIR %s search %s: %s", resource, resp.status_code, resp.text[:200])
                break
            bundle = resp.json()
            for entry in bundle.get("entry", []):
                res = entry.get("resource")
                if res and res.get("resourceType") == resource:
                    out.append(res)
            nxt = next((l.get("url") for l in bundle.get("link", []) if l.get("relation") == "next"), None)
            if not nxt:
                break
            url, query = nxt, None
    return out


async def fhir_read(fhir_base: str, access_token: str, resource: str, rid: str) -> dict | None:
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        resp = await client.get(
            f"{fhir_base.rstrip('/')}/{resource}/{rid}",
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/fhir+json"},
        )
        return resp.json() if resp.status_code == 200 else None


# ── FHIR → ALAFIA mapping helpers (pure functions; unit-tested) ──────────

# LOINC → VitalsLog column
VITAL_LOINC = {
    "8867-4": "heart_rate_bpm",
    "8480-6": "blood_pressure_systolic",
    "8462-4": "blood_pressure_diastolic",
    "8310-5": "body_temperature_c",
    "9279-1": "respiratory_rate",
    "2708-6": "blood_oxygen_pct",
    "59408-5": "blood_oxygen_pct",
    "29463-7": "weight_kg",
    "8302-2": "height_cm",
    "39156-5": "bmi",
    "2339-0": "blood_glucose_mg_dl",
}


def _coding_codes(codeable: dict | None) -> list[str]:
    return [c.get("code") for c in (codeable or {}).get("coding", []) if c.get("code")]


def _code_text(codeable: dict | None) -> str:
    c = codeable or {}
    return c.get("text") or next((x.get("display") for x in c.get("coding", []) if x.get("display")), "") or ""


def _obs_date(obs: dict) -> date | None:
    raw = obs.get("effectiveDateTime") or obs.get("issued") or ""
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def map_lab_observation(obs: dict) -> dict | None:
    """FHIR laboratory Observation → lab_results row values."""
    d = _obs_date(obs)
    name = _code_text(obs.get("code"))
    if not d or not name:
        return None
    row = {
        "test_date": d,
        "test_name": name[:255],
        "category": "ehr",
        "status": obs.get("status", "final"),
        "notes": f"FHIR:{obs.get('id')}",
    }
    loinc = next((c for c in _coding_codes(obs.get("code"))), None)
    if loinc:
        row["loinc_code"] = loinc[:20]
    vq = obs.get("valueQuantity")
    if vq and vq.get("value") is not None:
        row["value"] = float(vq["value"])
        row["unit"] = (vq.get("unit") or vq.get("code") or "")[:50] or None
    elif obs.get("valueString"):
        row["value_string"] = obs["valueString"][:255]
    elif obs.get("valueCodeableConcept"):
        row["value_string"] = _code_text(obs["valueCodeableConcept"])[:255]
    else:
        return None
    rng = (obs.get("referenceRange") or [{}])[0]
    if rng.get("low", {}).get("value") is not None:
        row["reference_range_low"] = float(rng["low"]["value"])
    if rng.get("high", {}).get("value") is not None:
        row["reference_range_high"] = float(rng["high"]["value"])
    interp = _coding_codes((obs.get("interpretation") or [{}])[0]) if obs.get("interpretation") else []
    if interp:
        row["is_abnormal"] = any(c not in ("N", "NORMAL") for c in interp)
    return row


def map_vital_observations(observations: list[dict]) -> dict[date, dict]:
    """FHIR vital-signs Observations → {log_date: vitals_logs column values}.

    Handles both standalone observations and BP panels (85354-9 components).
    Multiple same-day readings collapse to the last one seen (EHR order).
    """
    by_day: dict[date, dict] = {}

    def put(d: date, col: str, value, src_id: str):
        rec = by_day.setdefault(d, {"log_date": d, "notes": f"FHIR:{src_id}"})
        rec[col] = value

    for obs in observations:
        d = _obs_date(obs)
        if not d:
            continue
        oid = obs.get("id", "")
        # BP panel → components
        for comp in obs.get("component", []):
            for code in _coding_codes(comp.get("code")):
                col = VITAL_LOINC.get(code)
                vq = comp.get("valueQuantity", {})
                if col and vq.get("value") is not None:
                    v = float(vq["value"])
                    put(d, col, int(v) if col.startswith("blood_pressure") or col in
                        ("heart_rate_bpm", "respiratory_rate") else v, oid)
        for code in _coding_codes(obs.get("code")):
            col = VITAL_LOINC.get(code)
            vq = obs.get("valueQuantity", {})
            if col and vq.get("value") is not None:
                v = float(vq["value"])
                # Normalize units
                unit = (vq.get("unit") or vq.get("code") or "").lower()
                if col == "weight_kg" and unit in ("lb", "lbs", "lb_av", "[lb_av]"):
                    v *= 0.45359237
                if col == "height_cm" and unit in ("in", "[in_i]", "inch"):
                    v *= 2.54
                if col == "body_temperature_c" and unit in ("f", "[degf]", "degf"):
                    v = (v - 32) * 5 / 9
                put(d, col, int(v) if col in ("blood_pressure_systolic", "blood_pressure_diastolic",
                    "heart_rate_bpm", "respiratory_rate") else round(v, 2), oid)
    return by_day


def map_medication_request(mr: dict) -> dict | None:
    """FHIR MedicationRequest → medications row values."""
    name = _code_text(mr.get("medicationCodeableConcept"))
    if not name and mr.get("medicationReference"):
        name = mr["medicationReference"].get("display") or ""
    if not name:
        return None
    dosage = (mr.get("dosageInstruction") or [{}])[0]
    row = {
        "name": name[:255],
        "is_active": mr.get("status") == "active",
        "notes": f"FHIR:{mr.get('id')}",
    }
    rx = next((c.get("code") for c in (mr.get("medicationCodeableConcept") or {}).get("coding", [])
               if "rxnorm" in (c.get("system") or "").lower()), None)
    if rx:
        row["rxnorm_code"] = rx[:20]
    if dosage.get("text"):
        row["frequency"] = dosage["text"][:100]
    dq = (dosage.get("doseAndRate") or [{}])[0].get("doseQuantity", {})
    if dq.get("value") is not None:
        row["dosage"] = str(dq["value"])[:100]
        row["dosage_unit"] = (dq.get("unit") or "")[:50] or None
    if mr.get("requester", {}).get("display"):
        row["prescribing_doctor"] = mr["requester"]["display"][:255]
    authored = mr.get("authoredOn")
    if authored:
        try:
            row["start_date"] = datetime.fromisoformat(authored.replace("Z", "+00:00")).date()
        except ValueError:
            pass
    return row


def _condition_category(name: str, icd10: str | None) -> str:
    """Best-effort category from the condition name / ICD-10 chapter."""
    n = name.lower()
    checks = [
        ("cancer", ("cancer", "carcinoma", "lymphoma", "leukemia", "melanoma", "tumor", "neoplasm")),
        ("renal", ("kidney", "renal", "nephro", "esrd", "dialysis")),
        ("diabetes", ("diabetes", "diabetic")),
        ("cardiovascular", ("heart", "cardiac", "hypertension", "coronary", "atrial", "stroke", "vascular")),
        ("respiratory", ("asthma", "copd", "pulmonary", "respiratory", "bronch")),
        ("blood_disorder", ("anemia", "g6pd", "sickle", "hemophilia", "thalassemia")),
        ("autoimmune", ("lupus", "rheumatoid", "psoriasis", "crohn", "colitis", "celiac", "sclerosis")),
        ("neurological", ("epilepsy", "parkinson", "alzheimer", "migraine", "neuropathy", "seizure")),
        ("endocrine", ("thyroid", "hormone", "adrenal", "pituitary")),
    ]
    for cat, words in checks:
        if any(w in n for w in words):
            return cat
    if icd10:
        first = icd10[0].upper()
        if first == "C":
            return "cancer"
        if first == "E":
            return "endocrine"
        if first == "I":
            return "cardiovascular"
        if first == "J":
            return "respiratory"
        if first == "N":
            return "renal"
        if first == "G":
            return "neurological"
    return "other"


def map_condition(cond: dict) -> dict | None:
    """FHIR Condition → chronic_conditions row values (name + ICD-10 + date)."""
    name = _code_text(cond.get("code"))
    if not name:
        return None
    clinical = _coding_codes(cond.get("clinicalStatus"))
    icd = next((c.get("code") for c in (cond.get("code") or {}).get("coding", [])
                if "icd-10" in (c.get("system") or "").lower()), None)
    row = {
        "condition_name": name[:200],
        "notes": f"FHIR:{cond.get('id')}",
        "is_active": (not clinical) or ("active" in clinical),
        "category": _condition_category(name, icd),
        "severity": "moderate",   # FHIR Condition carries no general severity; sensible default
    }
    if icd:
        row["icd10_code"] = icd[:20]
    onset = cond.get("onsetDateTime") or cond.get("recordedDate")
    if onset:
        try:
            dt = datetime.fromisoformat(onset.replace("Z", "+00:00"))
            # chronic_conditions.diagnosis_date is a tz-naive column
            row["diagnosis_date"] = dt.astimezone(timezone.utc).replace(tzinfo=None)
        except ValueError:
            pass
    return row
