"""EHR endpoints — SMART on FHIR patient-portal access (Epic MyChart et al.).

Flow: pick an organization (Epic's public R4 directory: Kaiser, Trinity, …) →
/connect returns the portal's MyChart authorize URL (PKCE) → patient signs in
on the portal → frontend /ehr/callback posts {code, state} to /exchange →
tokens stored encrypted → /connections/{id}/sync pulls FHIR records into
ALAFIA's labs / vitals / medications / conditions tables.
"""

import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, delete, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.ehr import EHRConnection, EHREndpoint, EHROAuthState
from app.models.user import User
from app.schemas.ehr import (
    EHRConnectionCreate,
    EHRConnectionUpdate,
    EHRConnectionResponse,
)
from app.services import smart_fhir

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ehr", tags=["EHR"])

# Registration-free SMART Health IT sandbox (standalone patient launch sim).
# Lets the whole flow run locally before an Epic client ID exists.
SANDBOX_NAME = "SMART Sandbox (Test Portal)"
SANDBOX_FHIR_BASE = "https://launch.smarthealthit.org/v/r4/sim/WzMsIiIsIiIsIkFVVE8iLDAsMCwwLCIiLCIiLCIiLCIiLCIiLCIiLCIiLDAsMV0/fhir"

FHIR_PROVIDERS = [
    {
        "id": "epic",
        "name": "Epic",
        "auth_type": "smart_on_fhir",
        "supports": ["Patient", "Condition", "Observation", "MedicationStatement"],
    },
    {
        "id": "siemens",
        "name": "Siemens Healthineers",
        "auth_type": "smart_on_fhir",
        "supports": ["Patient", "Condition", "Observation", "MedicationStatement"],
    },
    {
        "id": "cerner",
        "name": "Cerner",
        "auth_type": "smart_on_fhir",
        "supports": ["Patient", "Condition", "Observation", "MedicationStatement"],
    },
]


@router.get("/providers")
async def list_providers():
    return FHIR_PROVIDERS


# ── Organization directory ───────────────────────────────────────────────


async def _ensure_directory(db: AsyncSession) -> None:
    """Ingest/refresh Epic's public endpoint directory (24 h cache)."""
    newest = (await db.execute(
        select(EHREndpoint.updated_at).order_by(EHREndpoint.updated_at.desc()).limit(1)
    )).scalar_one_or_none()
    if newest and newest > datetime.now(timezone.utc) - timedelta(hours=24):
        return
    try:
        orgs = await smart_fhir.fetch_epic_directory()
    except Exception as e:
        logger.warning("Epic directory fetch failed: %s", e)
        return
    if not orgs:
        return
    existing = {
        u: i for i, u in (await db.execute(
            select(EHREndpoint.id, EHREndpoint.fhir_base_url))).all()
    }
    now = datetime.now(timezone.utc)
    for org in orgs:
        eid = existing.get(org["fhir_base_url"])
        if eid:
            await db.execute(
                EHREndpoint.__table__.update().where(EHREndpoint.id == eid)
                .values(name=org["name"], updated_at=now)
            )
        else:
            db.add(EHREndpoint(vendor="epic", name=org["name"],
                               fhir_base_url=org["fhir_base_url"], updated_at=now))
    await db.flush()
    logger.info("EHR directory refreshed: %d organizations", len(orgs))


@router.get("/organizations")
async def search_organizations(
    search: str = "",
    limit: int = 25,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Search connectable patient portals (Epic MyChart directory)."""
    await _ensure_directory(db)
    q = select(EHREndpoint).order_by(EHREndpoint.name)
    if search.strip():
        q = q.where(EHREndpoint.name.ilike(f"%{search.strip()}%"))
    rows = (await db.execute(q.limit(min(limit, 100)))).scalars().all()
    out = [
        {"id": r.id, "name": r.name, "vendor": r.vendor, "fhir_base_url": r.fhir_base_url}
        for r in rows
    ]
    # Test portal appears when enabled and matches (or empty search shows it last)
    if settings.EHR_ENABLE_SANDBOX and (
        not search.strip() or search.strip().lower() in SANDBOX_NAME.lower()
    ):
        out.append({"id": 0, "name": SANDBOX_NAME, "vendor": "sandbox",
                    "fhir_base_url": SANDBOX_FHIR_BASE})
    return out


# ── SMART OAuth: connect + exchange ──────────────────────────────────────


class ConnectRequest(BaseModel):
    endpoint_id: int              # 0 = sandbox test portal


class ExchangeRequest(BaseModel):
    code: str
    state: str


def _client_id_for(vendor: str) -> str:
    if vendor == "sandbox":
        return "alafia-local-dev"     # sandbox accepts any client id
    if not settings.EPIC_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Epic MyChart access is not configured yet (EPIC_CLIENT_ID missing). "
                   "Register the app at fhir.epic.com and set the client ID.",
        )
    return settings.EPIC_CLIENT_ID


@router.post("/connect")
async def start_connection(
    payload: ConnectRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Begin the SMART standalone launch: returns the portal's authorize URL."""
    if payload.endpoint_id == 0:
        if not settings.EHR_ENABLE_SANDBOX:
            raise HTTPException(status_code=404, detail="Unknown organization")
        vendor, org_name, fhir_base = "sandbox", SANDBOX_NAME, SANDBOX_FHIR_BASE
        endpoint_id = None
    else:
        ep = (await db.execute(
            select(EHREndpoint).where(EHREndpoint.id == payload.endpoint_id)
        )).scalar_one_or_none()
        if not ep:
            raise HTTPException(status_code=404, detail="Unknown organization")
        vendor, org_name, fhir_base, endpoint_id = ep.vendor, ep.name, ep.fhir_base_url, ep.id

    client_id = _client_id_for(vendor)
    try:
        smart = await smart_fhir.smart_discover(fhir_base)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not reach this portal: {e}")

    verifier, challenge = smart_fhir.make_pkce()
    state = secrets.token_urlsafe(32)

    # Purge stale in-flight states (>15 min) then record this one.
    await db.execute(delete(EHROAuthState).where(
        or_(EHROAuthState.created_at < datetime.now(timezone.utc) - timedelta(minutes=15),
            EHROAuthState.user_id == current_user.id)
    ))
    db.add(EHROAuthState(
        state=state, user_id=current_user.id, endpoint_id=endpoint_id,
        org_name=org_name, fhir_base_url=fhir_base,
        token_endpoint=smart["token_endpoint"], code_verifier=verifier,
    ))
    await db.flush()

    authorize_url = smart_fhir.build_authorize_url(
        smart["authorization_endpoint"], fhir_base, client_id,
        settings.EHR_REDIRECT_URI, state, challenge,
    )
    return {"authorize_url": authorize_url, "state": state, "org_name": org_name}


@router.post("/exchange", response_model=EHRConnectionResponse)
async def complete_connection(
    payload: ExchangeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Finish the SMART launch: exchange the authorization code for tokens."""
    st = (await db.execute(
        select(EHROAuthState).where(
            EHROAuthState.state == payload.state,
            EHROAuthState.user_id == current_user.id,
        )
    )).scalar_one_or_none()
    if not st or st.created_at < datetime.now(timezone.utc) - timedelta(minutes=15):
        raise HTTPException(status_code=400, detail="Sign-in session expired — please try connecting again.")

    vendor = "sandbox" if st.endpoint_id is None else "epic"
    client_id = _client_id_for(vendor)
    try:
        token = await smart_fhir.exchange_code(
            st.token_endpoint, payload.code, settings.EHR_REDIRECT_URI,
            client_id, st.code_verifier,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))

    expires_at = None
    if token.get("expires_in"):
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(token["expires_in"]))

    # Reuse an existing connection to the same portal, else create one.
    conn = (await db.execute(
        select(EHRConnection).where(
            EHRConnection.user_id == current_user.id,
            EHRConnection.fhir_base_url == st.fhir_base_url,
        )
    )).scalars().first()
    if conn is None:
        conn = EHRConnection(user_id=current_user.id, provider=vendor)
        db.add(conn)

    conn.org_name = st.org_name
    conn.status = "connected"
    conn.fhir_base_url = st.fhir_base_url
    conn.patient_id = token.get("patient")
    conn.scopes = token.get("scope")
    conn.token_endpoint = st.token_endpoint
    conn.access_token_enc = smart_fhir.encrypt_token(token.get("access_token"))
    conn.refresh_token_enc = smart_fhir.encrypt_token(token.get("refresh_token"))
    conn.token_expires_at = expires_at

    await db.execute(delete(EHROAuthState).where(EHROAuthState.state == payload.state))
    await db.flush()
    await db.refresh(conn)
    logger.info("EHR connected: user=%d org=%s patient=%s", current_user.id, st.org_name, conn.patient_id)
    return conn


# ── FHIR sync ────────────────────────────────────────────────────────────


async def _valid_access_token(conn: EHRConnection, db: AsyncSession) -> str:
    """Return a usable access token, refreshing it if expired."""
    token = smart_fhir.decrypt_token(conn.access_token_enc)
    expired = conn.token_expires_at and conn.token_expires_at <= datetime.now(timezone.utc)
    if token and not expired:
        return token
    refresh = smart_fhir.decrypt_token(conn.refresh_token_enc)
    if refresh and conn.token_endpoint:
        client_id = _client_id_for(conn.provider)
        fresh = await smart_fhir.refresh_access_token(conn.token_endpoint, refresh, client_id)
        if fresh and fresh.get("access_token"):
            conn.access_token_enc = smart_fhir.encrypt_token(fresh["access_token"])
            if fresh.get("refresh_token"):
                conn.refresh_token_enc = smart_fhir.encrypt_token(fresh["refresh_token"])
            if fresh.get("expires_in"):
                conn.token_expires_at = datetime.now(timezone.utc) + timedelta(
                    seconds=int(fresh["expires_in"]))
            await db.flush()
            return fresh["access_token"]
    raise HTTPException(
        status_code=401,
        detail="This portal connection has expired — please reconnect.",
    )


@router.post("/connections/{connection_id}/sync")
async def sync_connection(
    connection_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Pull the patient's records from the connected portal into ALAFIA."""
    from app.models.labs import LabResult
    from app.models.vitals import VitalsLog
    from app.models.medications import Medication
    from app.models.chronic_conditions import ChronicCondition

    conn = (await db.execute(
        select(EHRConnection).where(
            EHRConnection.id == connection_id,
            EHRConnection.user_id == current_user.id,
        )
    )).scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    if not conn.patient_id or not conn.fhir_base_url:
        raise HTTPException(status_code=400, detail="Connection is not authorized yet")

    token = await _valid_access_token(conn, db)
    base, pid = conn.fhir_base_url, conn.patient_id
    counts = {"labs": 0, "vitals": 0, "medications": 0, "conditions": 0}

    async def existing_markers(model) -> set[str]:
        rows = (await db.execute(
            select(model.notes).where(model.user_id == current_user.id,
                                      model.notes.ilike("FHIR:%"))
        )).scalars().all()
        return set(rows)

    # Labs
    labs = await smart_fhir.fhir_search(base, token, "Observation",
                                        {"patient": pid, "category": "laboratory", "_count": 100})
    seen = await existing_markers(LabResult)
    for obs in labs:
        row = smart_fhir.map_lab_observation(obs)
        if row and row["notes"] not in seen:
            db.add(LabResult(user_id=current_user.id, **row))
            seen.add(row["notes"])
            counts["labs"] += 1

    # Vitals (incl. BP panels)
    vitals = await smart_fhir.fhir_search(base, token, "Observation",
                                          {"patient": pid, "category": "vital-signs", "_count": 100})
    seen = await existing_markers(VitalsLog)
    for d, row in smart_fhir.map_vital_observations(vitals).items():
        if row["notes"] not in seen:
            db.add(VitalsLog(user_id=current_user.id, **row))
            counts["vitals"] += 1

    # Medications
    meds = await smart_fhir.fhir_search(base, token, "MedicationRequest",
                                        {"patient": pid, "_count": 100})
    seen = await existing_markers(Medication)
    for mr in meds:
        row = smart_fhir.map_medication_request(mr)
        if row and row["notes"] not in seen:
            # Tag portal-imported meds so the UI can distinguish them from ones the
            # patient entered (e.g. sandbox/test data must not read as a real Rx).
            db.add(Medication(user_id=current_user.id,
                              source=conn.org_name or "Imported (portal)", **row))
            seen.add(row["notes"])
            counts["medications"] += 1

    # Conditions
    conds = await smart_fhir.fhir_search(base, token, "Condition",
                                         {"patient": pid, "_count": 100})
    seen = await existing_markers(ChronicCondition)
    from app.models.chronic_conditions import ConditionCategory, ConditionSeverity
    for c in conds:
        row = smart_fhir.map_condition(c)
        if row and row["notes"] not in seen:
            row["category"] = ConditionCategory(row["category"])
            row["severity"] = ConditionSeverity(row["severity"])
            db.add(ChronicCondition(user_id=current_user.id, **row))
            seen.add(row["notes"])
            counts["conditions"] += 1

    conn.last_sync_at = datetime.now(timezone.utc)
    conn.status = "connected"
    await db.flush()
    return {"synced": counts, "org_name": conn.org_name,
            "last_sync_at": conn.last_sync_at.isoformat()}


@router.get("/connections", response_model=list[EHRConnectionResponse])
async def list_connections(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(EHRConnection)
        .where(EHRConnection.user_id == current_user.id)
        .order_by(EHRConnection.created_at.desc())
    )
    return result.scalars().all()


@router.post("/connections", response_model=EHRConnectionResponse, status_code=status.HTTP_201_CREATED)
async def create_connection(
    payload: EHRConnectionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    connection = EHRConnection(
        user_id=current_user.id,
        provider=payload.provider,
        status=payload.status or "pending",
        fhir_base_url=payload.fhir_base_url,
        patient_id=payload.patient_id,
        scopes=payload.scopes,
        notes=payload.notes,
    )
    db.add(connection)
    await db.flush()
    await db.refresh(connection)
    return connection


@router.put("/connections/{connection_id}", response_model=EHRConnectionResponse)
async def update_connection(
    connection_id: int,
    payload: EHRConnectionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(EHRConnection).where(
            EHRConnection.id == connection_id,
            EHRConnection.user_id == current_user.id,
        )
    )
    connection = result.scalar_one_or_none()
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")

    updates = payload.model_dump(exclude_unset=True)
    if "last_sync_at" in updates and isinstance(updates["last_sync_at"], datetime):
        connection.last_sync_at = updates.pop("last_sync_at")

    for field, value in updates.items():
        setattr(connection, field, value)

    await db.flush()
    await db.refresh(connection)
    return connection


@router.delete("/connections/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_connection(
    connection_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(EHRConnection).where(
            EHRConnection.id == connection_id,
            EHRConnection.user_id == current_user.id,
        )
    )
    connection = result.scalar_one_or_none()
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")

    await db.delete(connection)
    return None
