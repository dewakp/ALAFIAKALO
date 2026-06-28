# ALAFIA ⇄ FlowSheet Alignment — Plan & Prompts

> **Goal.** Fully align **ALAFIA Therapies (HHD + PD)** with **FlowSheet**, with FlowSheet as the
> **reference/superior** implementation. Pillars:
> 1. **Shared identity service, ZERO duplication** — a user that exists in either app is the *same* user;
>    unique `email`, `username`, one canonical `profile`. (Decision locked.)
> 2. **Co-located on ALAFIA** — the shared identity DB **and** the FlowSheet DB reside on **ALAFIA's**
>    Postgres cluster (schema-separated: `identity` / `flowsheet` / `alafia`).
> 3. **FlowSheet is the lightweight intro/on-ramp module** — users start in FlowSheet and **transition to
>    the full ALAFIA app with zero glitch** (feature-unlock, not a migration/re-login).
> 4. **FHIR R4 compliant** — both apps expose the same FHIR resources for therapy data.
> 5. **Blockchain compliant** — both anchor a tamper-evident audit trail to one ledger.
>
> **Generated:** 2026-06-27 · ALAFIA `LAFIAKALO/WEB/backend` ↔ FlowSheet `Developer/FlowSheet/src/6igma_health_backend`.
> Companion review: `docs/FLOWSHEET_REVIEW.md`.

---

## 0. Current state — what differs (read before planning)

| Concern | **FlowSheet (reference)** | **ALAFIA (to align)** |
|---|---|---|
| User PK | `users.id` **UUID** | `users.id` **int** |
| Email | unique (320) | unique (255) |
| **Username** | (none yet — add) | **none** |
| Auth | **bcrypt + JWT, email-verify (Postgres-native — this is the canonical IdP)** | Firebase Auth + JWT → **migrate to the Postgres IdP; retire Firebase** |
| Profile | `user_identity` + addresses + phones (normalized) | columns on `users` (`full_name`, dob, gender…) |
| **SID** | `S1·FN3·LN3·DOB8·GEN1·EPO10·**RND157**·**SHA256(64)**` (PG trigger) | `S1.FN3.LN3.DOB8.GEN1.EPOCH10.**RND93**.**SHA512(128)**` (Rust `alafia_crypto`) |
| Roles | `account_role` + `session_role` enums (patient/nurse/physician/care-partner/admin) | `UserRole` enum + `UserRoleAssignment` (richer clinician taxonomy) |
| Therapy data | `flowsheet_templates / submissions / field_data / treatment_monitoring / drug_administrations / treatment_equipment / clinical_notes / treatment_notes_log` | `therapy_sessions` + `intradialytic_readings` (HD), `pd_sessions` + `pd_exchanges` (PD) |
| Sign-off | submit→sign→countersign→review→note→audit | none (CRUD only) |
| FHIR | R4 Patient/Observation/Procedure/DiagnosticReport + CapabilityStatement | **none** |
| Blockchain | Ganache + append-only `blockchain_audit_log`, SHA-256 anchoring | anvil/Foundry + `blockchain` router (record/verify/trail) |
| Chain port | `8545` | `8546→8545` |

**Two hard conflicts to resolve first:** (a) the **SID algorithms both claim `S1` but are incompatible**;
(b) **int vs UUID** user PKs. Everything else is additive.

---

## Phase 1 — Unified Identity (the "same User DB")

**Decision (LOCKED): a shared "6IGMA Identity" service, ZERO duplication.** One canonical
users/identity/credentials/SID store (FlowSheet's identity schema is the seed) that *both* backends use
for registration, login (SSO), and profile. Identity **data** (email, username, password, profile, SID,
IdP links) lives **only** in the identity service. ALAFIA and FlowSheet keep their **domain** data in
their own DBs and hold, at most, a **reference key** (`identity_uid` UUID / `system_id`) for relational
FK integrity — never a copy of profile or credentials. Bidirectional user sync is explicitly rejected.
Design contract: `docs/IDENTITY_ARCHITECTURE.md` (Prompt 1.1).

### Prompt 1.1 — Lock the architecture decision  ✅ DONE
> Contract: `docs/IDENTITY_ARCHITECTURE.md`. Implemented as a runnable service in
> `WEB/identity_service/` (FastAPI, Postgres-native, RS256 JWT + JWKS), wired into `docker-compose`
> as `identity` (:8100), co-located on ALAFIA's Postgres in the `identity` schema. Smoke-tested:
> health, JWKS, register/login/refresh/me, lookup, sid/verify, users/{sid}.
```
Decide and document (docs/IDENTITY_ARCHITECTURE.md) the shared-identity approach:
  - Shared 6IGMA Identity service owns: users (UUID id), user_identity (profile), credentials, SID,
    account_role, email_verified, username. Exposes: POST /identity/register, POST /identity/login
    (issues a shared JWT), GET /identity/me, GET /identity/by-sid/{sid}, GET /identity/by-email.
  - Both ALAFIA and FlowSheet validate the shared JWT (same signing key / JWKS) → SSO.
  - Canonical user key across apps = system_id (SID). Domain tables FK/reference by SID.
Acceptance: a one-page diagram + the API contract both apps will implement against.
```

### Prompt 1.2 — Unify the SID algorithm (FlowSheet is canonical)  ✅ DONE (apply deferred)
> Implemented: `app/services/canonical_sid.py` (stdlib port of FlowSheet's algo), `sid_service.py`
> delegates to it (Rust SID path retired), 9 tests incl. a cross-app FlowSheet vector, and
> `scripts/remint_canonical_sids.py` (dry-run validated: 41 ALAFIA users would re-mint, 0 already
> canonical). `--apply` deferred to the Phase 1 identity backfill to avoid double-churn.
```
ALAFIA and FlowSheet both emit a "S1…" 255-char SID but with different RND length + hash (ALAFIA
RND93+SHA512, FlowSheet RND157+SHA256). Make FlowSheet's layout the ONE canonical algorithm:
  S1 · FN3 · LN3 · DOB8 · GEN1 · EPO10 · RND157 · SHA256(64)  (fixed-width, 255).
- Port FlowSheet's fn_generate_system_id / fn_verify_system_id to a shared library the identity service
  uses; ALAFIA's Rust `alafia_crypto` SID path is retired (or re-implemented to this exact layout).
- Migration: re-mint ALAFIA SIDs through the canonical generator (old ALAFIA S1 SIDs are NOT
  compatible). Keep a map old_sid → new_sid for any external references.
Acceptance: the SAME function verifies SIDs minted by either app; ALAFIA users carry canonical SIDs.
Caveat: RND157 is random, so the SID is a per-account credential, NOT a deterministic identity hash —
identity de-dup is by (email/username + identity segments), with the SID as the durable handle.
```

### Prompt 1.3 — Add `username` + reconcile profile + UUID keys  ✅ DONE (identity side)
> Identity schema live: `identity.users` (UUID id, unique email + unique username, bcrypt password,
> account_role, tier, canonical SID), `identity.user_identity` (single canonical profile),
> `user_identity_sid_log`, `legacy_auth_links`. Dup email/username → 409 "sign in instead". Profile is
> single-source (read via `/identity/me`). Remaining for full 1.3: add the ALAFIA `identity_uid` bridge
> column + repoint ALAFIA reads to `/identity/*` (Phase 1.4 wiring); addresses/phones tables deferred.
```
- Add a unique `username` to the shared identity (ALAFIA has none today). Enforce uniqueness of
  email AND username across the shared DB.
- Adopt UUID as the canonical user id in the shared identity. ALAFIA today uses int user_id; either
  (a) add a UUID `identity_uid` column to ALAFIA users mapped 1:1 to the shared user, keeping int PKs
  for ALAFIA's existing FKs, or (b) migrate to UUID. Recommend (a) to avoid rewriting every FK.
- One canonical profile: first/last name, dob, gender, addresses, phones live in the shared identity;
  ALAFIA reads them via the identity API and stops duplicating them on `users`.
Acceptance: registering in ALAFIA with an email/username already in FlowSheet is rejected as a dup and
offered SSO instead; profile edits in one app are visible in the other.
```

### Prompt 1.4 — SSO + cross-app provisioning (PostgreSQL-native IdP; retire Firebase)  ✅ DONE
> - ALAFIA verifies identity RS256 JWTs via JWKS (`services/identity_client.py`); `get_current_user` is
>   dual-path (identity-first, resolve-or-provision by identity_uid → SID → email; legacy HS512 fallback).
>   Bridge `users.identity_uid` (migration `cc001`).
> - **ALAFIA `/auth/register` + `/auth/login` now delegate to the identity IdP** — register provisions
>   the canonical identity user + links + unifies the SID; login returns an **RS256 identity token**
>   (Firebase off the live path; legacy fallback retained for transition).
> - **Backfill APPLIED:** 41 users provisioned into `identity` (passwords carried over) → **42/42 ALAFIA
>   users linked + SID-matched** with their identity record (one user, one SID, zero duplication).
> - **Password-reset flow** implemented in the identity service (request→reset→login verified).
> - **FlowSheet side (RUNTIME-VERIFIED):** JWKS verifier (`api/identity_verify.py`) + dual-path
>   `get_current_user` with **resolve-or-provision** (auto-creates a thin reference row from identity
>   claims — zero duplication). FlowSheet now **runs co-located on ALAFIA's Postgres** (database
>   `sigma_health`, compose service `flowsheet` :8101) and shares the identity IdP.
> - **ALAFIA frontend** already authenticates via `/auth/login` (no Firebase SDK; only UI comments
>   reference the reference design). Verified: `/auth/login` → RS256 identity token → `/users/me` 200.
> Verified live end-to-end: **one identity token returns 200 on BOTH ALAFIA (`/symptoms/`, `/users/me`)
> and FlowSheet (`/api/users/me`)**; the canonical SID is **byte-for-byte identical** in `identity.users`
> and `sigma_health.users`. ALAFIA register→identity (linked, SID match); password reset works.

---

## ✅ Phase 1 (Unified Identity) — COMPLETE & RUNTIME-VERIFIED
Canonical SID (1.2) + shared PostgreSQL-native identity IdP (1.1/1.3) + ALAFIA SSO/register/login
delegation/bridge/applied-backfill/password-reset (1.4) + **FlowSheet running co-located on ALAFIA's
Postgres and accepting identity tokens with auto-provisioning** + ALAFIA frontend confirmed on
`/auth/login`. Proven: one credential → one canonical SID → both apps, zero duplication.
Next: **Phase 4.1** (one audit chain) then **Phase 2** (therapy model).
```
- The IdP is the `identity` schema: credentials = email/username + bcrypt password_hash in Postgres
  (FlowSheet's model). NOT Firebase. Both backends verify the shared identity JWT via JWKS; a token
  issued for one app authenticates the other (SSO).
- ALAFIA migrates OFF Firebase Auth: its auth middleware switches to identity JWT; Firebase is removed
  from the live path.
- Backfill: import existing ALAFIA users (21 firebase-linked) + FlowSheet users into the identity by
  email; resolve email/username collisions; mint canonical SIDs; record the old firebase_uid in
  `legacy_auth_links` (traceability only). Firebase-era accounts have no password → mark password_unset
  and onboard via email password-reset on first login. Decommission Firebase after cutover.
Acceptance: one Postgres-native credential set works in both apps; no duplicate accounts by
email/username; no Firebase call in the live auth path.
```

---

## Phase 2 — Align ALAFIA Therapies (HHD + PD) to the FlowSheet flowsheet model

FlowSheet's normalized flowsheet model + clinical lifecycle is the reference. Bring ALAFIA's
`therapy_sessions`/`intradialytic_readings` (HD/HHD) and `pd_sessions`/`pd_exchanges` (PD) up to it.

### Prompt 2.1 — Adopt the flowsheet structure for ALAFIA therapies
```
Refactor ALAFIA HD/HHD + PD to mirror FlowSheet's shape: a submission header + typed field data +
time-series monitoring rows + drug administrations + equipment + clinical notes. Either:
  (a) reshape ALAFIA tables to match flowsheet_submissions/field_data/treatment_monitoring/…, or
  (b) treat FlowSheet as system-of-record for signed flowsheets and have ALAFIA store a normalized
      mirror keyed by SID (preferred — avoids divergence).
Map ALAFIA TherapyType {HD, HHD, PD} → FlowSheet template ids. Preserve PD-specific exchanges.
Acceptance: an ALAFIA HHD and a PD session round-trip to the FlowSheet flowsheet shape with no data loss.
```

### Prompt 2.2 — Clinical sign-off lifecycle in ALAFIA
```
Add FlowSheet's lifecycle to ALAFIA therapy sessions: draft → submit → sign (nurse) → countersign
(physician) → review → note → locked, with an immutable audit row per transition (Phase 4 anchors it).
Surface the state + actions in Hemodialysis.jsx / PeritonealDialysis.jsx, gated by role (Phase 3).
Acceptance: a nurse can sign and a physician countersign an ALAFIA HHD session; signed sessions are
read-only; every transition is audit-logged.
```

### Prompt 2.3 — Align roles/audience with FlowSheet
```
Map ALAFIA roles to FlowSheet account_role/session_role (patient, nurse, physician, care_partner,
admin) for therapy access control, and adopt FlowSheet's care-links (who may view/act on a patient's
flowsheets). Reuse the shared identity's account_role as the source of truth.
Acceptance: therapy endpoints enforce the same role matrix as FlowSheet; care-partner access works.
```

---

## Phase 3 — FHIR R4 compliance for ALAFIA

### Prompt 3.1 — Add a FHIR R4 export to ALAFIA mirroring FlowSheet
```
Port FlowSheet's api/routers/fhir.py contract to ALAFIA (new app/api/fhir.py): GET /fhir/metadata
(CapabilityStatement), /fhir/Patient/{id}, /fhir/Patient/{id}/$everything, /fhir/Observation
(vitals+labs), /fhir/Procedure (HD/HHD/PD procedures), /fhir/DiagnosticReport (flowsheet reports).
Source resources from ALAFIA's schema (vitals_logs, labs, therapy_sessions/pd_sessions). Use the same
US-Core profiles, content-type application/fhir+json, and Patient id = SID.
Acceptance: ALAFIA and FlowSheet return structurally-equivalent FHIR for the same patient (by SID);
a DiagnosticReport for an HHD session validates against R4.
```

### Prompt 3.2 — Shared FHIR contract + tests
```
Extract the resource-builder shapes into a shared spec (or shared package) so both apps stay in lockstep.
Add contract tests asserting both apps emit the same FHIR JSON for an equivalent therapy record.
Acceptance: a single test suite passes against both /fhir endpoints.
```

---

## Phase 4 — Blockchain compliance / one audit ledger

### Prompt 4.1 — Converge on one chain + one anchoring format
```
Pick one node (recommend ALAFIA's Foundry/anvil OR FlowSheet's Ganache — choose one, document why) and
one append-only audit format. Align ALAFIA's blockchain.py and FlowSheet's services/blockchain.py to:
  - the same SHA-256 payload-hash + hash-chaining scheme,
  - PHI never on-chain (hash anchoring only),
  - the same audit row schema (append-only; UPDATE/DELETE blocked at DB level).
Acceptance: an audit event written by either app is verifiable by the other's verify routine.
```

### Prompt 4.2 — Anchor therapy lifecycle transitions
```
Every Phase-2 lifecycle transition (submit/sign/countersign/review/lock) in BOTH apps writes an
append-only audit row and anchors its hash. Key the trail by SID so a patient's clinical (FlowSheet) +
self-reported (ALAFIA) therapy events share one tamper-evident timeline.
Acceptance: GET an SID's audit trail returns merged, hash-verified events from both apps.
```

---

## Phase 5 — Co-resident therapy surfacing + seamless transition (intro → full app)

Because the `flowsheet` and `alafia` schemas live on the **same** cluster (Phase 2 / co-location), this
is **not** cross-app sync — it's a **read across schemas** keyed by `identity_uid`/SID, plus the
feature-unlock that makes the FlowSheet→ALAFIA upgrade glitch-free.

### Prompt 5.1 — Surface co-resident flowsheets in ALAFIA Therapies (no copy)
```
ALAFIA Therapies reads SIGNED flowsheets directly from the co-resident `flowsheet` schema (or a view)
by identity_uid/SID, shown read-only with a "signed in FlowSheet" provenance badge. No ETL/sync; the
data already lives on the cluster. FHIR R4 (Phase 3) remains the export/interop format for outside
consumers.
Acceptance: a flowsheet signed in FlowSheet is visible in ALAFIA Therapies for the same SID with no
copy step and no sync lag.
```

### Prompt 5.2 — Seamless FlowSheet → ALAFIA upgrade ("no glitch")
```
Add an `entitlement`/`tier` on the identity user (flowsheet → full). FlowSheet is the on-ramp; opening
ALAFIA after FlowSheet requires NO re-registration and NO re-login (shared JWT, aud includes both), and
the user's flowsheets + profile appear immediately (already co-resident, keyed by SID). "Upgrade" flips
the tier to unlock ALAFIA surfaces — no account creation, no data migration.
Acceptance: a user who registered + logged dialysis in FlowSheet opens ALAFIA and is already
authenticated, sees their flowsheets + profile with zero re-entry, and unlocking full features is a
single tier flip. (See docs/IDENTITY_ARCHITECTURE.md §6b.)
```

---

## Phase 6 — Mobile parity + cleanup

### Prompt 6.1 — Mobile alignment
```
Reflect the unified identity (SSO), therapy lifecycle, and roles in both apps' iOS/Android clients.
Acceptance: a user logs into either mobile app with one credential set and sees consistent therapy state.
```

### Prompt 6.2 — Repo hygiene (FlowSheet)
```
git init FlowSheet; remove the stale duplicate files-3/6igma_health_backend; de-duplicate the
DaVita/Sigma forms (one source of truth); replace the committed .env with .env.example only.
Acceptance: FlowSheet is version-controlled with no duplicate trees and no committed secrets.
```

---

## Suggested execution order
1. **Phase 1** (identity is the foundation everything else keys off) — 1.1 → 1.2 → 1.3 → 1.4
2. **Phase 4.1** (pick the chain) early, since Phase 2 lifecycle anchors to it
3. **Phase 2** (therapy model + lifecycle + roles)
4. **Phase 3** (FHIR), then **4.2** (anchor transitions)
5. **Phase 5** (exchange), then **Phase 6** (mobile + cleanup)

## Cross-cutting guardrails
- **FlowSheet is the reference** — when shapes disagree, ALAFIA conforms to FlowSheet, not vice versa.
- **One canonical SID algorithm** (FlowSheet's) and **one user record** per person (unique email+username).
- **PHI never on-chain**; hash-anchor only. **No PHI** to external FHIR consumers without consent.
- **Additive migrations** with backfill + an old→new SID map; never silently drop identity data.
- Keep ALAFIA's int FKs working via an `identity_uid` bridge rather than a big-bang UUID rewrite.
```
