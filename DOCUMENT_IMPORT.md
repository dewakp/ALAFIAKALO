# Document import — parse any clinical PDF, review, then import

Source- and layout-agnostic reading of clinical documents, staged for review
before anything reaches a clinical table.

---

## 0. Why it works from coordinates, not text

`page.extract_text()` returns words in *reading order*. A reference range printed
beside a row therefore lands on a different line:

```
1.00 -
1051 A/G RATIO 1.8 Calc Final     <- the actual row
2.50
```

Any line-oriented regex sees a row with no range and two stray numbers. On the
13-document corpus in `ML/data/raw/pdf/` the previous extractor lost **489 of
853 reference ranges (43%)**, and **3 of 13 documents lost every single one**.

Everything here is built on `pdfplumber`'s per-word bounding boxes instead.
Column boundaries are read off *the document's own header row*, so a report
whose RESULT column sits at x=197 parses by the same code as one where it sits
at x=169 — the two DaVita variants in the corpus differ exactly that way.

**Current: 510/510 ranges recovered (100%), 0 regressions.**
Re-check after touching `layout.py` or `normalize.py`:

```bash
ML/.venv-health-ml/bin/python WEB/backend/scripts/docparse_corpus_check.py
```

It is not in CI — it reads real patient records (`ML/data/raw/` is gitignored
for that reason). Committed fixtures are synthesised in `tests/test_docparse.py`
and reproduce the geometry, not the PHI.

---

## 1. Pipeline

`app/services/docparse/` — each layer usable on its own. `extract` and `layout`
import nothing from the app, which is what lets the corpus harness run without a
database or settings.

| Module | Does |
|---|---|
| `extract.py` | pdfplumber → words with `(text, x0, x1, top)`. No text layer → `needs_ocr`, **not** an empty result |
| `layout.py` | visual lines → header detection → column x-boundaries → rows, de-wrapping continuation lines |
| `layout_matrix.py` | the other shape: analyte × period grids (flowsheets, IDT worksheets) |
| `classify.py` | document type from signature scoring; ambiguous → local model |
| `normalize.py` | values, flags, ranges, units, dates → `LabRecord` |
| `records_clinical.py` | the same tables read as medications / conditions |
| `metadata.py` | patient, collection date, lab, ordering provider + redaction |
| `pipeline.py` | orchestrates the above into a `ParseResult` |
| `dictionaries.py` | analyte vocabulary (seeded from `scripts/import_pdf_labs.py`) |

### How rows are found

A real row puts content in **two or more columns**; a wrapped fragment occupies
exactly one. Fragments attach to the vertically nearest row and rejoin in
top-to-bottom order — which is how `1.00 -` and `2.50` become `1.00 - 2.50`, and
how `x 10^6` + `cells/uL` become one unit.

### Two shapes, tried in order

1. **labelled columns** — the common lab report
2. **trend matrix** — analyte × period, several grids side by side and
   *vertically offset from each other*, so a visual line is not a row
3. neither → reported as unreadable, never as empty

### The intelligence layer

Deterministic first. The local model (`alafia_chat_detailed`, task `doc_*`) is
asked only when signature scoring is unsure, and only with an
identifier-stripped excerpt — the model is local, but prompts get logged and a
log is a second copy. Clients never name a provider (canon §3).

---

## 2. Nothing is written until the patient agrees

`document_imports` + `document_import_items` (migration `ll001_document_imports`).

```
upload → parse → staged items → patient reviews → confirm → clinical tables
```

A parser is sometimes wrong, and `lab_results` is the wrong place to find that
out: once a bad reading is in there it is indistinguishable from one a lab
reported, and every average, trend and clinician card inherits it.

- `content_hash` is indexed per user, so re-uploading a file returns the
  existing import instead of staging the readings twice.
- `dedupe_status` is `new` | `duplicate` | `conflict`. **Duplicates arrive
  unticked** — confirming must never silently write a second copy of a reading.
- Each item keeps `source_label` (what the document literally said) next to
  `canonical_name`, so a wrong normalization is visible rather than buried.

### Where each document type lands — canon §3aa

| Type | Table | Not |
|---|---|---|
| lab report, flowsheet | `lab_results` | — |
| medication list | `medications` (a document states a *prescription*) | `medication_dose_logs`, which is what was actually taken |
| discharge summary | `chronic_conditions` | `health_conditions`, which has **no writer** — anything put there is invisible forever |

Dedupe **reads** go through `app/services/clinical_sources.py`. Querying those
models directly would both miss half the data and fail
`tests/test_clinical_sources.py`.

`ChronicCondition.category` and `.severity` are NOT NULL enums. An unrecognised
condition is filed as `other` / `moderate` **and says so** on the staged item, so
a reviewer corrects a guess instead of inheriting it.

---

## 3. API (`/api/v1/pdf`)

| Route | |
|---|---|
| `POST /parse-document` | read + stage. `parse-lab-report` is an alias |
| `GET /imports` · `GET /imports/{id}` | review |
| `POST /imports/{id}/confirm` | write accepted rows |
| `POST /imports/{id}/reject` | discard |
| `POST /generate-flowsheet` | `{session_type, days}` → JSON incl. text `content` |
| `GET /reports/flowsheet.pdf` | the same report as a real PDF |

Field names are the ones web, iOS and Android already decode. They were
previously served as `doctor_name` / `raw_text` / `items[].name`, so a successful
parse still rendered blank on every platform; and `generate-flowsheet` demanded a
`session_id` while all three clients sent `{session_type, days}`, so it 422'd
everywhere.

**`pdfplumber` must stay in `WEB/backend/requirements.txt`.** Without it
`extract` cannot read a PDF at all — the endpoint used to fall through to
decoding PDF bytes as UTF-8.

---

## 4. Report generation

`app/services/docreport.py` — one `ReportSpec`, two renderers:

```python
render_pdf(spec)  -> bytes   # reportlab
render_text(spec) -> str     # the `content` clients preview
```

Both come from the same spec on purpose: the clients show text and download a
PDF, and with two independent renderers the document a clinician receives stops
matching what the patient saw.

Sections are `KeyValueSection`, `TableSection` (with a `highlight` predicate) and
`TextSection`. Empty sections are dropped — a heading with nothing under it reads
as missing data.

---

## 5. Verification

```bash
cd WEB
docker compose --profile test run --rm backend-test    # includes 66 docparse/import/report tests
docker compose --profile test run --rm frontend-test
docker compose --profile test run --rm e2e
```

Plus the corpus harness in §0, and — because canon §3 means all three clients —
`xcodebuild -scheme ALAFIA` and `./gradlew :app:assembleDebug`.

### Known gaps

- **No OCR.** A scan is detected and reported as `needs_ocr`; there is no
  tesseract in the image.
- **Medication and condition mappers are covered by tests but not by the real
  corpus** — every PDF in `ML/data/raw/` is a lab report, so those two paths are
  verified against synthesised documents only. The lab path is the one confirmed
  end to end on real data (85 readings from a 6-page DaVita report → staged →
  imported → rolled back).
- `scripts/import_pdf_labs.py` still points at port **5432** (dev is **5435**;
  5432 belongs to a different project on this machine).


---

## Re-importing does not repair a bad row

Dedupe is keyed on `(test_date, lower(test_name))`. `existing_row_id` is stored
on the staging item but **never read back** — the commit path only constructs
`LabResult(...)`, an insert. So:

| Case | What happens |
|---|---|
| same name+date, same value | `DEDUPE_DUPLICATE` — unticked, nothing added |
| same name+date, **different** value | `DEDUPE_CONFLICT` — ticked, **inserted as a second row** |
| name changed by a parser fix | `DEDUPE_NEW` — inserted beside the old, wrong row |

That last case is the trap. A fix that corrects `WEIGHT - PRE DAY` (value 1) to
`WEIGHT - PRE DAY 1` (value 57.5) changes the key, so re-importing the same PDF
leaves the patient with **two contradictory weights on one date**.

**Delete first, then re-import.** `scripts/db/cleanup_docparse_artifacts.sh`
dry-runs by default and prints exactly the rows `--apply` would remove — the same
statements inside a transaction that is rolled back, so the preview cannot drift
from the action.

## Two artefacts this parser produced in production

**Boilerplate as a result.** The DaVita reports end with "disciplinary action, up
to and including termination of employment with DaVita." It parsed into a name
and a value: 30 rows across 5 dates on one record, shown to a clinician among
real labs. `looks_like_prose()` rejects prose by shape, not by a list of phrases.

**Name overflow eating the value.** Column boundaries come from the header
labels, so a name wider than "LAB TEST NAME" spills into RESULT:

```
1715 WEIGHT - PRE DAY 1   57.5 kg Final
                    ^^^ x_mid 165.5, boundary 162.0
```

The "1" won and 57.5 was discarded — 1 kg displayed for a 57 kg patient.
`_reclaim_name_overflow()` decides on geometry: the gap inside a name is a word
space (2.0 pt), the gap to the value is a column gap (29.0 pt).

Both were invisible to the corpus harness, which measures **range recovery only**
— 510/510 both before and after. Recall says nothing about what a parser
*invented*.
