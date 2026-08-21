# Conditions — the patient's problem list, ICD-11 coded

Diagnosed conditions are a cornerstone of the record: they drive the nutrient
limits, the clinician board, and what the AI coach believes about the patient.
This is where a patient records what they have.

---

## 0. What was actually wrong

The screen existed on iOS and Android and had **never been reachable on web**.
`WEB/frontend/src/pages/ChronicConditions.jsx` was 602 lines of working CRUD
with no `import` in `App.jsx`, no `<Route>`, and no link anywhere in the app —
from the initial commit onward. `git log -S"ChronicConditions" -- App.jsx`
returns nothing.

It did not regress. It was never wired.

The second half: there was **no ICD-11 anywhere in the codebase**. The column
was `icd10_code`, filled in by nothing the patient could reach — on production,
all four condition rows had it NULL.

---

## 1. Two coding systems, on purpose

| Column | Written by | Means |
|---|---|---|
| `icd11_code` / `icd11_title` | the patient, through the picker | what the patient says they have |
| `icd10_code` | the FHIR import (`services/smart_fhir.py`) and the PDF parser (`services/docparse/records_clinical.py`) | what a source document said |

**ICD-10 was kept, not migrated.** It is not a legacy duplicate — it is a fact
about an imported document, and dropping the column would discard what those
importers read. A condition can legitimately carry an ICD-10 off a discharge
summary and an ICD-11 the patient chose. The clinician board labels which
system a code came from, because the two look nothing alike for the same
disease: chronic kidney disease stage 5 is `N18.6` in ICD-10 and `GB61.5` in
ICD-11.

A patient can hold as many conditions as they have — one row each, each
independently coded. Comorbidity is the norm in this population: the production
ESRD record also carries obesity and an old ligament injury.

---

## 2. The catalog is generated, never typed

`app/data/icd11_mms.tsv.gz` — all **35,339 codes**, 370 KB gzipped — is built
from WHO's published Simple Tabulation of the MMS linearization by
`scripts/build_icd11_catalog.py`. **Do not hand-edit it**; edit the script and
re-run.

```bash
python scripts/build_icd11_catalog.py                    # fetches the current release
python scripts/build_icd11_catalog.py --zip ./file.zip   # when TLS is intercepted
```

> **Never type an ICD code from memory.** G6PD deficiency is `3A10.00`. That is
> not what anyone guesses, and a plausible-but-wrong code on a clinical record
> looks exactly as verified as a right one.

Why the whole catalog rather than a curated shortlist: a shortlist silently
lacks whatever the patient actually has, which is the same failure as reading
the wrong conditions table (CLAUDE.md §3aa). 370 KB is not worth curating away.

The official API (`id.who.int`) needs OAuth client credentials this deployment
does not have, and a type-ahead should not depend on an outbound call anyway.

---

## 3. Three things the WHO file does not give you

All three were real, measured gaps — each returned **zero results** before the
fix.

**Word order.** Titles are formal. ICD-11 calls it "Type 2 diabetes mellitus",
so a substring match on "diabetes mellitus type 2" finds nothing. Matching is
token-wise.

**Lay terms and abbreviations.** "ESRD", "G6PD", "heart attack" appear in no
ICD-11 title. `ICD11_ALIASES` maps them to verified codes, and
`tests/test_icd11_catalog.py` fails the build if any alias points at a code
that is not in the generated file.

**British spelling.** WHO writes `haemodialysis`, `tumour`, `anaemia`,
`oesophagus` — **867 titles** carry a spelling a US patient will not type.
`_fold()` normalises index and query alike, so either spelling finds the code.
"hemodialysis" used to return nothing at all.

### Ranking

Best first: exact code → code prefix → alias → exact title → title prefix →
all tokens as word prefixes → remaining matches. Within a tier, a real
diagnosis outranks a symptom or health-status code, non-residual beats
"…unspecified", and a shallower code beats a deeper one.

Two ranking rules exist because of specific bad results:

- **Residuals drop a whole tier.** Searching "kidney" led with *"Kidney
  failure, unspecified"* purely because that title starts with the query,
  burying chronic kidney disease.
- **Extension (X), functioning (V) and Traditional Medicine (26) chapters are
  excluded by default.** "kidney" returned `XA6KU8 Kidney` and `SG27 Kidney
  meridian pattern (TM1)` above the diagnosis. They stay reachable when a
  chapter is asked for by name.

Bare organ words ("kidney", "liver", "heart") are aliased outright. The WHO
file has no prevalence signal, so structure alone cannot rank them — inventing
a relevance heuristic that pretends otherwise would be a guess.

Search is ~1 ms against an inverted index built at first load.

---

## 4. The client never decides what a code means

`_apply_icd11()` in `api/chronic_conditions.py` runs on create and update:

- The code is uppercased and **verified against the catalog**. A stem code is
  four alphanumerics, so a typo is very often still code-*shaped* — format
  validation alone lets `ZZ99.9` through. Unknown codes are rejected 422.
- **`icd11_title` is set server-side and any client-supplied title is
  discarded.** Otherwise a record could show any text at all beside a real
  code, and the code would still look verified.
- An explicit `null` clears code and title together. A stale title beside a
  cleared code reads as a diagnosis nobody entered.
- A partial update that never mentions the field leaves it alone.

Coding is optional throughout — a patient who does not know their code must
still be able to record the condition by name.

---

## 5. Where it appears

| Surface | Entry point |
|---|---|
| Web | `/chronic-conditions`, linked from **Profile → Health Conditions** and the main nav |
| iOS | `MainTabView` → Section("Profile") → "Health Conditions" |
| Android | More grid → "Conditions" (`chronic-conditions` route) |
| Clinician board | Problem-list card and table, code labelled with its system |
| AI coach | `ai_engine` condition context carries `icd11` + title |

Endpoints (all authenticated, none rate limited — a type-ahead fires per
keystroke and there is nothing to enumerate in a public classification):

```
GET /api/v1/chronic/icd11/search?q=&chapter=&limit=
GET /api/v1/chronic/icd11/chapters
GET /api/v1/chronic/icd11/{code}
```

---

## 6. An error is not an empty state

Every surface here keeps `loadError` separate from an empty list, on both the
condition list and the code search. This is the §3aa failure in miniature: a
catalog that cannot be reached must never tell the patient their condition does
not exist, and a failed condition fetch must never render as "none recorded".

The list endpoint pages at **100 by default**; web, iOS and Android all request
`limit=1000` explicitly. A truncated page silently hides conditions — the same
shape as a `LIMIT` being reported as a count.

---

## 7. Verifying

```bash
docker compose --profile test run --rm backend-test python -m pytest \
  tests/test_icd11_catalog.py tests/test_conditions_icd11_api.py -q   # 125
docker compose --profile test run --rm frontend-test                  # 113

# e2e: recreate frontend-preview first — it builds at container start, so a
# long-running one serves a stale dist/ and a green suite proves nothing.
docker compose --profile test up -d --force-recreate frontend-preview
docker compose --profile test run --rm e2e                            # 22

# Board against real data, not the empty test DB — the documented command
# points at the test database and reports 0 users.
docker compose --profile test run --rm \
  -e DATABASE_URL="postgresql+asyncpg://alafia:alafia@db:5432/alafia" \
  backend-test python scripts/board_sweep.py
```

Mobile is verified by building it:

```bash
cd IOS && xcodebuild -project ALAFIA.xcodeproj -scheme ALAFIA \
  -destination 'generic/platform=iOS Simulator' build
cd Android && ./gradlew :app:assembleDebug
```

`IOS/ALAFIA.xcodeproj` lists source files individually — it does **not** use a
file-system-synchronized group, so a new Swift file must be added to
`project.pbxproj` or it silently will not build.

---

## 8. Migration state

`nn001_condition_icd11` adds `icd11_code`, `icd11_title` and an index. It has
been applied to **dev only**. Until it is deployed, `verify_parity.sh` will
report dev ahead of prod on `chronic_conditions` and on the alembic revision —
that is a pending migration, not drift to re-pull away.
