<!-- Copyright © 2026 Wole Akpose / 6igma Health Inc.
     All rights reserved. ALAFIA — proprietary and confidential. -->

# Hospital & surgery history — as built

Admissions and operations, and what a past operation still means for a patient
today. Condensed canon: **CLAUDE.md §3bb**. Verbatim session record:
`docs/VERBATIM_LOG_2026-10-05.md` (local only).

Started 2026-10-05. Migration `ao001_hospital_history` is applied to **dev
only**; production remains on `an001_vital_thresholds`. Ask `alembic heads` —
never this line (§5).

---

## 1. Why it exists

A patient told the assistant:

> "I use it as calcium supplement after removal of parathyroid glands"

Measured 2026-10-05: **zero** rows mention a parathyroidectomy in
`chronic_conditions`, `symptom_logs`, or anywhere else in the database. The
record had nowhere to put it, so no amount of retrieval could reach it, and the
nutrient targets went on quoting a bone-health RDA.

A parathyroidectomy is not a historical curiosity — it permanently changes how
a patient handles calcium. The gap was not a missing field on a form; it was a
whole class of clinical fact the schema could not hold.

---

## 2. The data model, and the one decision everything follows from

Two tables, and **either row can stand alone.**

```
hospitalizations        26 columns   one hospital stay
surgical_procedures     21 columns   one operation
```

`surgical_procedures.hospitalization_id` is **NULLABLE on purpose.** Day-case
surgery, and anything a patient records years after the fact, arrives with no
encounter at all — so a required FK would have refused precisely the row these
models were written for. The parathyroidectomy that caused the work has no
admission attached to it.

That single decision is why there are two readers rather than one (§4), why the
API returns three lists rather than a tree (§5), and why the first test in
`tests/test_hospital_history.py` asserts the orphan case.

### Deliberate deviations, each with its reason

| Choice | Why |
|---|---|
| `admitted_at` is the ONLY required clinical date | A stay is meaningful before anyone knows when it ended. Requiring a discharge would refuse the current admission — the one that matters most. |
| Facility is **both** an FK and a free-text name | An imported record routinely names a hospital the directory has never heard of. Dropping the name loses the provenance. |
| `facility_id` is `ON DELETE SET NULL`, not `CASCADE` | `physician_facilities` cascades because that row only describes a relationship. An admission is the patient's own history: removing a hospital from the directory must never delete the record of having been in it. |
| `hospitalization_id` is `SET NULL` too | Deleting a mistyped admission must not erase an operation that happened. |
| `code` always travels with `code_system` | ICD-10-PCS, CPT, SNOMED CT and ICHI are different vocabularies under different licences (SNOMED's Affiliate Licence restricts redistribution, CPT is AMA-licensed). Nothing converts between them, and guessing which one a source used is §3ad's "never type a code from memory". |
| `icd10_code` and `icd11_code` both exist | Different facts, not duplicates — ICD-10 is what an import read off a document, ICD-11 is what someone selected in the app. Same rule as `chronic_conditions` (§3ad). |
| `is_readmission` is recorded, never computed | Date arithmetic over an incomplete history would manufacture a quality signal a clinician reads directly. |
| `ongoing_effects` is free text | It is the field that answers "why is this patient's calcium different", and it is a sentence, not a code. |

### The ORM had to be corrected to match the schema

`Hospitalization.procedures` shipped with `cascade="all, delete-orphan"`, which
an ORM delete would honour by **destroying** the procedures — contradicting the
`ON DELETE SET NULL` that is actually deployed. It is `passive_deletes=True`
now, and `DELETE /hospital/stays/{id}` detaches with explicit statements so the
outcome is stated at the call site rather than left to cascade configuration a
later edit could change.

### Enums persist by NAME

`Column(SQLEnum(AdmissionType))` with no `values_callable` stores the Python
member **name**, so the column holds `DISCHARGED` while
`AdmissionStatus.DISCHARGED.value` is `"discharged"`. The migration was first
written with lowercase labels and would have produced a type that refused every
row the ORM inserts.

```
admissionstatus       PLANNED, IN_PROGRESS, DISCHARGED, TRANSFERRED, CANCELLED
admissiontype         EMERGENCY, ELECTIVE, URGENT, OBSERVATION, DAY_CASE,
                      MATERNITY, REHABILITATION, OTHER
procedureoutcome      SUCCESSFUL, PARTIALLY_SUCCESSFUL, UNSUCCESSFUL,
                      COMPLICATED, ABANDONED, UNKNOWN
```

⚠️ **`notificationpriority` in the same schema is lowercase.** Both conventions
are live, so ask the database per enum rather than adopting a project-wide
assumption.

---

## 3. The migration

`alembic/versions/ao001_hospital_history.py`, hand-written and additive (§3ao:
autogenerate proposed dropping five live tables when asked for one).

- The three enum types are created with `postgresql.ENUM(..., create_type=False)`
  plus an explicit `.create(bind, checkfirst=True)` — the house pattern from
  `b5c6d7e8f9a1`, because a generic `sa.Enum` emits `CREATE TYPE` as a side
  effect of `create_table` and collides on a database that already has it.
- `server_default` is declared on `status`, `created_at` and `updated_at` in
  **both** the migration and the model. A default that exists only in the DDL
  is the unmodelled drift that makes `--autogenerate` propose destructive
  changes.

Verified against the database after applying — not against the file:

```
columns        26 + 21 = 47
indexes        22 (all index=True columns, plus two composites)
status default 'DISCHARGED'::admissionstatus
FKs            users CASCADE ×2; facilities SET NULL ×2; hospitalizations SET NULL
```

---

## 4. The canonical reader

`app/services/clinical_sources.py`. Both models are in the §3aa `GUARDED` set,
so `tests/test_clinical_sources.py` fails the build if anything queries them
outside the canonical module or a declared `ALLOWED` writer.

```python
async def hospitalizations(db, user_id, since=None) -> list[HospitalizationView]
async def procedures(db, user_id, since=None)       -> list[ProcedureView]
async def lasting_surgical_effects(db, user_id)     -> list[str]
```

- **`hospitalizations()`** returns stays newest-first with their procedures
  attached. `nights` is computed only when BOTH ends are known — a stay still
  in progress returns `None` rather than a length measured against today.
- **`procedures()`** returns **every** procedure, including those with no
  admission. This is the half a reader loses by starting from stays. An undated
  procedure sorts last (`.desc().nullslast()`) rather than being dropped: an
  undated operation is still a fact about the patient.
- **`lasting_surgical_effects()`** returns only rows that **state** an effect,
  formatted `"{name} ({date}): {effect}"`. Inferring "parathyroid glands
  removed → calcium must be supplemented" from a procedure NAME would be the
  system asserting a clinical fact nobody recorded (§0). It is deliberately
  **not** windowed by `since`: a 2019 operation governs today's calcium.

---

## 5. The API

Mounted at `/api/v1/hospital` (`app/api/hospitalization.py`). It is the WRITER
for these tables, which is why it carries an `ALLOWED` entry in the §3aa guard;
its one read surface goes through `clinical_sources`.

| Route | Notes |
|---|---|
| `GET /hospital/history` | The canonical read: `stays`, **every** `procedures`, `lasting_effects`. Three lists, not a tree. |
| `GET /hospital/stays` | Raw rows with ids, for an edit form. Unpaginated — §3ad's truncation failure is worse here than a larger payload. |
| `POST /hospital/stays` | Creates a stay, optionally with nested procedures — how a discharge summary arrives. |
| `PATCH`/`DELETE /hospital/stays/{id}` | Delete detaches procedures, never destroys them. |
| `GET`/`POST /hospital/procedures` | A procedure may be posted with no admission. |
| `PATCH`/`DELETE /hospital/procedures/{id}` | |

- **`procedures` is not derivable from `stays`**, which is why `history`
  returns both. A client walking stays→procedures silently loses the day-case
  and historical operations.
- **404, never 403**, for another patient's row — the status code must not
  confirm that someone else's admission exists (§3b). A procedure may not be
  attached to a stay the caller does not own.
- **`exclude_none=True` on create, `exclude_unset=True` on PATCH.** `status` is
  NOT NULL with a Python-side default, and SQLAlchemy applies that default only
  when the attribute was never SET — `model_dump()` emits `status: None`, which
  INSERTs NULL and 500s a create that merely omitted the field. PATCH keeps
  `exclude_unset`, because there an explicit null legitimately clears a value.
- **Plausibility lives on `*Create`, never on a response model.** A discharge
  before an admission is refused on input. §3at: response-model checks turned
  one implausible stored row into a 500 that rendered as "no sessions found".
- **Naive UTC is enforced in the schema validator**, not in each route — the
  columns are `timestamp without time zone` and a browser sends `...Z`, and
  comparing aware to naive makes asyncpg raise `DataError` (§3aa). A route added
  later cannot forget it.

> ⚠️ Responses carry a `Z` anyway: `normalize_datetimes_middleware`
> (`main.py:114`) rewrites every JSON body with `_NAIVE_ISO_DT.sub(rb'"\1Z"')`.
> **A test must assert on the column, not the response string.**

---

## 6. The FHIR import

`map_encounter` / `map_procedure` in `app/services/smart_fhir.py`, wired into
the sync in `app/api/ehr.py`. The dedupe marker goes in `external_ref` — unlike
`map_condition`, which parks `FHIR:{id}` in `notes` because
`chronic_conditions` has nowhere else to put it.

**Order matters:** encounters are imported first, then flushed so they hold
database ids, then procedures resolve their stay. The lookup is keyed over
**every** stay the patient has, not just this run's — a procedure arriving today
routinely belongs to an encounter imported weeks ago.

### What is refused, and why

| Input | Result | Reason |
|---|---|---|
| resource with no `id` | **no row** | The marker would be the literal `"FHIR:None"`, so two such stays would dedupe AGAINST EACH OTHER and the second real admission would vanish as a duplicate — §3ab's contradictory-copy failure, except this version deletes rather than duplicates. |
| `status: not-done` / `entered-in-error` | **no row** | They state the operation did not happen. Importing one asserts an operation the patient never had. |
| `Encounter.class` of `IMP`, `AMB`, `ACUTE` | `admission_type` left NULL | They state a SETTING, not a reason. Only `EMER` and `OBSENC` mean what our enum means; mapping the rest to the nearest-looking member would put a clinical claim in the record the source never made. |
| unknown `status` | key absent, column default applies | `entered-in-error` and `unknown` are not states of a stay. |
| unrecognised coding system longer than 40 chars | kept WHOLE in `notes` | Half a URI is not a vocabulary name, it is a wrong one, and a code attributed to the wrong system is worse than a code with no system. |
| no `performedDateTime` | falls back to `performedPeriod.start` | |
| anything at all | `ongoing_effects` **never set** | FHIR has no field for it. The value comes from a discharge summary, a clinician, or the patient — in words. |

Not wired: `document_import_service` and the two Firestore importers do not
write these tables. A confirmed PDF of a discharge summary still has to be
entered by hand.

---

## 7. The assistant

`get_surgical_history` in `app/services/record_tools.py`, with its label in
`TOOL_LABELS` beside `TOOL_SPECS` (the backend writes the label so a new tool
does not need three app releases to get a name).

It reports `lasting_effects` **first-class**, because that is what a question
about calcium, phosphate or bone actually needs — the operation list alone does
not explain it. Not windowed, for the same reason the reader is not.

> **It returns NO facility name, NO surgeon name, and not the reader's
> `admission` label either** — that label embeds the hospital's name. Whether an
> operation happened during an inpatient stay is clinical; WHERE it happened is
> identifying, and this module's contract is clinical rows only (§3al). The
> payload carries `during_hospital_stay: true|false` instead.

`nights` is reported only when it exists and is never turned into "still an
inpatient" — `status` is what states that, and inferring it from a missing
discharge date would invent a fact.

---

## 8. The clients

A feature is not done until web, iOS and Android have it (§3), and each was
verified by **building** it.

| Platform | Surface |
|---|---|
| **Web** | `pages/HospitalHistory.jsx` at `/hospital-history`, routed in `App.jsx` **and** linked from `Layout.jsx` — §3ad's failure is a finished page with no route *and* no link. 63 `t()` keys, all resolving. |
| **iOS** | `Views/Hospital/HospitalHistoryView.swift` + `Models/HospitalHistory.swift`, reached from `MainTabView`'s Profile section. |
| **Android** | `views/hospital/HospitalHistoryScreen.kt` + `models/HospitalHistory.kt`, a `composable("hospital-history")` route **and** a `MoreGridItem`. |

All three lead with **lasting effects**, before any list of admissions, and draw
stays and procedures as separate sections so the orphans are visible.
`loadError` is kept apart from the data on every platform: a failed fetch must
never render as "no hospital history recorded" (§3aa).

### Two client traps this feature walked into

- **A Swift file on disk is invisible to the build.** `ALAFIA.xcodeproj` is
  `objectVersion = 56` with zero `PBXFileSystemSynchronizedRootGroup` entries,
  so every source file is listed **four times** (build file, file reference,
  group children, Sources phase) and a new feature directory needs its own
  `PBXGroup` in the `Views` group. The two new files measured **0** occurrences
  before being registered. `plutil -lint project.pbxproj` validates the result;
  `xcodebuild -list` names the scheme.
- **`tests/test_ios_presentation_flags.py` SKIPS in the backend container** —
  the guard that fails the build on a `show…` flag set but never read. Run it
  from a repo-root mount with `--noconftest`, or its green says nothing.

---

## 9. How to verify it

```bash
# the readers, the orphan case, and the API — 34 tests across four files
docker compose --profile test run --rm -e TEST_DB_NAME=alafia_test_hosp \
  backend-test python -m pytest \
  tests/test_hospital_history.py tests/test_fhir_hospital_mapping.py \
  tests/test_fhir_hospital_sync.py tests/test_hospital_api.py \
  tests/test_clinical_sources.py -q

# the iOS dead-control guard, where it can actually see the sources
docker run --rm -v "$PWD":/src:ro -w /src python:3.12-slim sh -c \
  "pip install -q pytest && python -m pytest \
   WEB/backend/tests/test_ios_presentation_flags.py -v -rs --noconftest"
```

⚠️ **Never run two pytest processes against one test database.**
`conftest.setup_db` does `create_all`/`drop_all` per test, so a concurrent run
drops the other's tables mid-flight — it produced 16 setup/teardown errors in a
file that passed alone, and silently corrupted a suite chunk that then had to be
repeated. Pass `-e TEST_DB_NAME=…` per run.

What the tests pin that comments alone did not:

- a procedure with **no admission** is returned by `procedures()` while
  `hospitalizations()` returns `[]` — the orphan case, asserted first;
- `nights` is `None` while still an inpatient;
- only a **stated** effect appears in `lasting_surgical_effects()` — a
  nephrectomy with no recorded consequence does not;
- deleting a stay **keeps** its procedures, detached;
- `lasting_effects` survives a `since` filter that excludes the procedure;
- a procedure attaches to a stay imported in an **earlier** sync;
- a **second sync inserts nothing** — checked by counting rows, because a
  dedupe bug that reports 0 while inserting is the exact failure being guarded.

---

## 10. Known gaps

- **The nutrient quota this feature was meant to feed does not exist yet.**
  `lasting_surgical_effects()` can tell the targets engine that parathyroid
  glands were removed, and nothing consumes it: `compute_goals` is a
  hand-written ladder of literals, and `condition_nutrition_facts` can say
  avoid/favour a nutrient but carries **no amount, unit, basis or target/limit
  column**. See `OPEN_ITEMS.md` §8a — it needs a decision, not a renal `if`.
- **Unpaginated reads.** Correct at a patient's real volume and deliberate after
  §3ad, but unbounded if a record ever carries hundreds.
- **Only the FHIR path writes these tables.** No document-import or Firestore
  writer does.
- **Production does not have the tables.** `ao001` is dev-only.
