# Community Health Suite

The **Community Health** area of ALAFIA groups four population-health features in
the web app's sidebar:

- **Overview** — community alerts, recalls, advisories, reports, guidelines (`/community`)
- **Physician Directory** — clinician directory + ingestion + global map (`/physicians`)
- **Food & Drug Recalls** — multi-region recall search + coverage maps (`/fda-recalls`)
- **Disease Surveillance** — outward + inward drill-down choropleth (`/surveillance`)

All maps are dependency-free SVG (work with React 19, offline) and all data sources
are free / key-less public APIs. This document covers the architecture, data model,
APIs, and operations for the suite.

---

## 1. Disease Surveillance

A drill-down world choropleth that looks **outward** (authoritative sources) and
**inward** (de-identified ALAFIA patient data).

### Sources (live, key-free)
| Source | Scope | Notes |
|---|---|---|
| **WHO GHO** `ghoapi.azureedge.net` | Global, per country (ISO3) | OData; `SpatialDim`=ISO3, `TimeDim`=year, `ParentLocation`=WHO region. `Value` carries confidence intervals + space thousands-separators (e.g. `"419 332 [283 000-600 000]"`) — parse the leading number. |
| **CDC NNDSS** `data.cdc.gov/resource/x9gk-5huc.json` | US, per state, weekly | Current (updated weekly). `m2` = YTD cumulative; "Total" rows = national. |
| **Africa CDC** | Africa | No open API → served via WHO's `AFR` region rows (`region=Africa`). |
| **ALAFIA patients** | Wherever users are | Inward: `symptom_logs` (joined to `users.country`) + `community_health_reports`. De-identified counts only. |

Verified WHO indicator codes: cholera `CHOLERA_0000000001`, measles `WHS3_62`,
malaria `MALARIA_EST_CASES`, TB `MDG_0000000020`, pertussis `WHS3_49`,
diphtheria `WHS3_41`, polio `WHS3_57`.

### Endpoints (`/api/v1/surveillance`)
- `GET /diseases` — trackable diseases (each backed by a WHO indicator).
- `GET /global?disease=&view=outward|inward|both&region=&days=` — per-country level (0–4) for the choropleth.
- `GET /country/{iso2}?disease=&days=` — drill-down: WHO time series, CDC US states, stored alerts, inward symptom clusters.
- `GET /sources` — source attribution.

### Code
`app/services/surveillance_sources.py` (source clients + disease catalog, 6 h cache),
`app/api/surveillance.py` (endpoints + inward aggregation, quartile levels),
`app/services/iso_countries.py` (ISO3↔ISO2↔name + `resolve_country()` free-text resolver),
frontend `components/ChoroplethMap.jsx`, `pages/DiseaseSurveillance.jsx`,
`data/isoCountries.js` (numeric→ISO2 for the GeoJSON feature ids).

---

## 2. Clinician / Physician Directory

A robust directory of **clinicians** (physicians, specialists, nurses, NPs, PAs,
dietitians, pharmacists, therapists, …) and, separately, **facilities**, with
license-gated patient association, multi-source ingestion, a dedup worker, and a
global drill-down map.

### 2.1 Clinicians vs facilities — separate tables
**Physicians are humans; facilities are places they practice from.** They live in
separate tables:

- **`physicians`** — licensed *individuals* (CMS NPPES NPI-1). Subject to the license gate.
- **`facilities`** — *places* (hospital, pharmacy, clinic; e.g. from OpenStreetMap).
  A facility is never a licensed individual and **never a patient's clinician**.
- **`physician_facilities`** — the many-to-many "practices at" link between them.

See §2.8 for the facility directory (`/api/v1/facilities`). (`physicians` keeps an
`entity_type` column as a defensive guard, but it is always `clinician`.)

### 2.2 License-verification gate (safety-critical)
**Never associate an unverified/unlicensed clinician with a patient.** Mirrors
FlowSheet's `clinician_profiles` (admin-controlled `credential_verified`).

State machine (`verification_status`):

```
no license at all        → quarantined        (held in candidates; never in directory)
license, untrusted source→ license_on_record  → admin verifies → verified
license, trusted (CMS)   → verified (auto)                              ↑ admin may reject → rejected
facility                 → listed (entity_type=facility; not a clinician)
```

Only `credential_verified = true` **clinicians** can be saved to a patient's care
team (`POST /physicians/saved/` returns **403** otherwise, **400** for a facility).

**Decision (locked with the user):** CMS/NPPES + license → auto-`verified`; other
sources + license → `license_on_record` (await admin); no license → `quarantined`.

### 2.3 Sources
| Source | Yields | License? | Result |
|---|---|---|---|
| **CMS NPPES** `npiregistry.cms.hhs.gov/api` | Individuals (NPI-1): physicians, nurses, dietitians, … | Yes (per taxonomy) | Auto-`verified` clinicians |
| **OpenStreetMap (Overpass)** | Healthcare **facilities** (places) | n/a | → separate `facilities` table (§2.8), never clinicians |

The pipeline is **source-agnostic**: an adapter just emits normalized candidate
dicts carrying a `source` (+ `entity_type`) field. Adding a source = one small
adapter (e.g. state boards, NPPES bulk file).

### 2.4 Ingestion + dedup worker
`app/services/clinician_ingest.py`:
1. Upsert candidate (idempotent — unchanged content hash → skip).
2. **Facility** → listed (dedup by source id); never license-gated.
3. **Clinician**: dedup (NPI → name+location). No license → quarantine
   (`held_no_license`). Licensed + unique → insert (CMS auto-verifies, else
   `license_on_record`). Duplicate → record provenance, upgrade verification if a
   trusted source confirms a license.

Every transition is written to `clinician_verification_log`.

**Scale:** `start_background_seed()` pages NPPES across **40 NUCC taxonomies × 52
states** (`skip` 0–1000 × 200/page) as a background task — tens/hundreds of
thousands of clinicians. Idempotent + resumable (a restart resumes via dedup).
Verified live to **88k+** verified clinicians.

### 2.5 Approximate geocoding (for the map)
Coordinates are **never** required and never gate anything — they only place a pin.
`app/services/geo_approx.py` + bundled `app/data/us_zip_centroids.json` (~41k ZIPs
from GeoNames): **use real coords/address when available, else ZIP centroid, else
state centroid** (`location_precision` = `exact` | `approximate`). NPPES has no
coordinates, so CMS clinicians are placed by ZIP centroid (approximate).

**Exact street coordinates (US Census batch geocoder).** `app/services/census_geocode.py`
`bulk_geocode_practices()` uploads practice-facility addresses (up to 10k/call) to the
free US Census batch geocoder and upgrades matched rows to `location_precision='exact'`
(`lon,lat` parsed from the response), then moves each facility's primary-practice
clinicians to the resolved coordinates in one bulk `UPDATE`. It's **idempotent**: it only
scans rows still lacking precise coords and marks unmatched rows `zip_fallback` so they
are never re-scanned. This runs on a **scheduled worker** (see §5) — the last full pass
resolved ~44.6k of 51.4k practice facilities to exact coordinates (~87%).

### 2.6 Endpoints (`/api/v1/physicians`)
Public-ish (auth required):
- `GET /` — search/list **clinicians** (default `entity_type=clinician`), paginated `limit`/`offset` (UI: **10/page**).
- `GET /{id}`, `POST /`, `PATCH /{id}`, `DELETE /{id}` — directory CRUD.
- `GET /saved/`, `POST /saved/` (gated), `PATCH/DELETE /saved/{id}` — care team.
- `GET /directory/map?role=` — verified clinicians per country (choropleth).
- `GET /directory/country/{iso2}?role=` — drill-down list.
- `GET /directory/points?entity_type=&role=&bbox=&verified_only=` — map pins (clinicians or facilities).
- `GET /nearby`, `GET /geocode`, `GET /osm-discover` — geo / facility discovery.

Admin (`is_superuser`):
- `POST /admin/ingest/seed-all?pages=` — start the full background CMS seed.
- `GET /admin/ingest/status`, `POST /admin/ingest/stop`.
- `POST /admin/ingest/search?taxonomy_description=&state=&…` — one NPPES search.
- `POST /admin/ingest/osm?lat=&lon=&radius_km=&place_type=` — ingest OSM facilities.
- `POST /admin/ingest/reprocess-held` — re-check quarantined records for a now-present license.
- `POST /admin/backfill-coords` — geocode existing rows.
- `GET /admin/candidates?status=`, `GET /admin/stats`, `POST /{id}/verify` (`action=verify|reject`).

### 2.7 Maps
- **Global Map** tab — choropleth of verified clinicians per country (reuses `ChoroplethMap`), drill-down list, role filter.
- **Map View** tab (Leaflet) — verified **clinicians** as pins (filled = exact, hollow = approximate) **plus** OSM **facilities** as a separate purple layer. "Search Area" geocodes a place and loads clinicians (bbox) **and** facilities for that area.
- Verification badges in cards; "Save/Add" disabled unless `credential_verified`.

### 2.8 Facility directory (`/api/v1/facilities`)
Facilities are a **separate directory** from clinicians:
- `GET /facilities/` — search/list (name, `facility_type`, city, country), paginated.
- `GET /facilities/points?facility_type=&bbox=` — facility map points.
- `GET /facilities/{id}`, `GET /facilities/stats`.
- `POST /facilities/admin/ingest-osm?lat=&lon=&radius_km=&place_type=` (admin) —
  discover + upsert OSM facilities (dedup on `(source, source_uid)`, idempotent;
  OSM provides real coordinates → `location_precision=exact`).

Code: `app/models/facilities.py` (`Facility`, `PhysicianFacility`),
`app/services/facility_ingest.py`, `app/api/facilities.py`,
`app/services/osm_source.py` (Overpass adapter).

---

## 3. Food & Drug Recalls (`/fda-recalls`)
Multi-region food **and** drug recalls (US openFDA, Health Canada, UK FSA), with
food/drug + aggregate/per-recall toggles and dependency-free world + US-state
coverage maps. (`app/api/fda_recalls.py`, `components/WorldCoverageMap.jsx`,
`components/USCoverageMap.jsx`.)

---

## 4. Data model (PostgreSQL)
**`physicians`** (clinicians — humans) with: `clinician_role`, `license_number`,
`license_state`, `npi_number`, `primary_source`, `verification_status`,
`credential_verified`, `verified_by_user_id`, `verified_at`, `verification_notes`,
`held_reason`, `latitude`/`longitude`/`location_precision` (+ defensive `entity_type`).

Clinician satellite tables:
- **`clinician_source_records`** — provenance per source (`unique(source, source_uid)`).
- **`clinician_ingest_candidates`** — quarantine / dedup queue (no-license rows park here).
- **`clinician_verification_log`** — append-only audit of status transitions.

**`facilities`** (places — separate directory) + **`physician_facilities`** (the
"practices at" link between a clinician and a facility).

Surveillance reuses existing `community_health_alerts`, `community_health_reports`,
`symptom_logs`, `users.country` (no schema change).

Migrations: `ee001_clinician_directory`, `ff001_loc_precision`, `gg001_entity_type`,
`hh001_facilities`, `ii001_flagged_estimates`.
> ⚠️ `alembic_version.version_num` is `VARCHAR(32)` — **revision ids must be ≤ 32 chars**.

---

## 5. Operations
- Dev: Docker for everything; no hot reload — rebuild with
  `docker compose up -d --build backend frontend`, then `alembic upgrade head`.
- Seed the directory: `POST /physicians/admin/ingest/seed-all` (background; watch
  `/admin/ingest/status`). The seed runs in the web process — a restart stops it
  (data persists; re-run to resume). For unattended completion, move it to a
  dedicated worker/cron.
- Backfill map coordinates after a bulk import: `POST /physicians/admin/backfill-coords`.

### 5.1 Scheduled practice-facility geocoding (server-side worker)
The Census geocoder runs on a **server-side scheduled worker**, not a Claude cron —
an APScheduler job (`AsyncIOScheduler`, in-process with the backend) registered in
`app/main.py` at startup alongside the Firebase-sync job. Job: `_geocode_practices_job`
runs `census_geocode.bulk_geocode_practices` in up to `PRACTICE_GEOCODE_MAX_BATCHES`
idempotent passes per run, committing each pass.
- Cadence/toggles (in `app/core/config.py`, env-overridable):
  `PRACTICE_GEOCODE_ENABLED` (default **true**), `PRACTICE_GEOCODE_INTERVAL_HOURS`
  (default **24**), `PRACTICE_GEOCODE_BATCH_LIMIT` (5000), `PRACTICE_GEOCODE_MAX_BATCHES` (6).
- First run is delayed 5 min after boot (so restarts don't hammer Census); `coalesce`
  + `max_instances=1` prevent overlap/missed-run pileups. Logs `[scheduler] Practice
  geocode …` lines.
- The scheduler starts if **any** job is registered (independent of the Firebase toggle).
  Lifespan events don't fire under the test client, so the worker never runs in CI;
  set `PRACTICE_GEOCODE_ENABLED=false` when running **more than one** backend replica
  (or move it to a dedicated worker) to avoid duplicate Census calls.

## 6. Safety & privacy
- Unlicensed / unverified clinicians are **held** and never shown to patients or
  linked to a care team. Facilities are never clinicians.
- Inward surveillance is **aggregate, de-identified** (counts only, no PII).
- Admin-only ingestion/verification endpoints require `is_superuser`.
