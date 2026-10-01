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
| `POST /imports/{id}/reject` | abandon an import **nothing was written from** |
| `POST /imports/{id}/discard` | delete the rows a CONFIRMED import wrote — §3ab's "delete first, then re-import", which had no route through the product until 2026-09-30. 409 if the import was never confirmed |
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

---

## 2026-09-30 — the name-only guard was not enough, and one row was never a lab's

Found from a real 3-page Quest report (`results - Jan 2022.pdf`). Everything
below is measured against that document and the 13-PDF PHI corpus, not inferred.

### A lab's street address was imported as a result

`looks_like_prose()` judges the **name** cell. These all passed it, because each
name is short, capitalised and free of connective words — the prose sat in the
cells the guard never inspected:

```
01: Quest Diagnostics-Houston = Lab, 5850 Rogerdale   <- the lab's postal address
Director: Dr Robert L         = Breckenridge          <- the lab director
Performing Laboratory         = Information:          <- a section heading
Martin SS et al. JAMA.        = 2013;310(19):2061-68  <- a journal citation
Desirable range <100          = mg/dL for primary…    <- four lines of LDL footnote
```

`row_is_prose(cells)` in `normalize.py` judges the row **as the document drew
it**. Three signals, all structural:

1. a closed-vocabulary result (`DNR`, `NEG`, `NONE SEEN`) is always a finding;
2. a **bare number is a measurement**, whatever else the row contains;
3. otherwise the row is rejoined and judged as prose, and a row occupying only
   `name`+`value` with no digit is furniture.

**Measured: 14 rows removed, 92 kept on the real report; 0 of 939 corpus rows
removed.** Harness unchanged at 510/510, 0 regressions.

> ⚠️ **The obvious rule would have deleted a neutropenia.** "A real row has a
> number in its value column" removes **49 of 106** rows on that report, and most
> are real: `WBC = NONE SEEN`, `RBC = 0-2`, `BACTERIA = NONE SEEN`,
> `ABSOLUTE BLASTS = DNR`, `BUN/CREATININE RATIO = NOT APPLICABLE` — an entire
> urinalysis microscopy panel and half a differential. The **corpus scores that
> rule as free (0 rows lost)**, because every corpus document is a DaVita report
> with no microscopy. A green corpus run is not evidence about precision.

> ⚠️ **And the first version of the fix DID delete real results.** Rejoining the
> cells inflated ordinary rows past `looks_like_prose`'s 10-word ceiling — a
> figure calibrated for NAMES — so it removed `CBC (INCLUDES DIFF/PLT) WHITE
> BLOOD CELL COUNT = 2.4` (the patient's neutropenia), both eGFRs, the sed rate,
> and 6 real rows per corpus document. Caught by measurement before shipping.
> `_is_plain_measurement` short-circuits ahead of the prose test, and
> `tests/test_docparse_rowguard.py::test_a_long_row_with_a_real_value_is_not_prose`
> pins every one of those rows.

### A value that cannot be true is no longer pre-ticked

`plausibility.review_lab_value()` — physically impossible, deliberately **not**
"abnormal". Nothing is ever deleted: an implausible row arrives **unticked with
its reason**, because the failure being guarded against is a reviewer in a hurry
ticking through what the system already ticked for them.

> **Why not a multiple of the reference range.** On the reference record
> creatinine reads **11.91 against 0.7–1.3** — 9.2× over, and exactly what
> end-stage renal disease looks like. Fifteen legitimate creatinines sit between
> 5× and 9.2×. A guard that cries wolf over a dialysis patient's creatinine
> teaches its reader to tick past it. The suspect threshold is **20×**, chosen so
> that creatinine passes and PTH-I 8,478 (106×) does not.

### The row that started it: a fabricated haematocrit

A record carried `HGBX 338.4 %` against a printed range of 42–52, rendered with
a green tick. **The true value is 38.4 %.** The analyte is `HCT CALC (HGBX3)` —
haematocrit calculated as haemoglobin × 3 — and that day's haemoglobin was 12.8,
so 12.8 × 3 = 38.4 exactly. A literal `3` had migrated from the **end of the
name** to the **front of the value**, leaving the figure exactly 300 too high.
Three rows carry that signature, each confirmed against the source PDF:

| date | stored | true | HGB × 3 |
|---|---|---|---|
| 2025-01-27 | 327.3 | 27.3 | 9.1 × 3 |
| 2025-03-21 | 324.6 | 24.6 | 8.2 × 3 |
| 2025-07-17 | 338.4 | 38.4 | 12.8 × 3 |

**Not our parser.** The value arrives that way in the Firestore export
(`ML/data/raw/api/lab_results.csv:101`), where the analyte is stored as bare
`HGBX` with the `3` missing from the name. `Records.xlsx` sheet `Lab` is clean —
it covers 2016-04-28 → 2023-03-09 and holds no value over 100. What was ours is
accepting it in silence, which `import_unified_labs.py` admits in its own
docstring: *"They are imported and counted in the report so a human can look."*

### Discarding a whole import — `POST /pdf/imports/{id}/discard`

§3ab's remedy ("delete first, then re-import") previously had **no route through
the product**: `/reject` only marks an import nothing was written from, and all
three clients hid even that once an import succeeded — which is exactly when a
misread document gets noticed.

- Deletes **only** the rows this import created, by the `imported_row_id` stamped
  on each staged row at confirm time. Hand-entered readings and other documents'
  readings are untouched; `lab_results` carries no foreign keys pointing at it.
- Every delete is scoped by `user_id` as well as row id — verified by a test in
  which two patients import the **same** document and one discards.
- `find_existing_import` skips discarded imports, or the patient would be handed
  back the import they just deleted and the re-import could never happen.
- Refuses a non-confirmed import with **409** rather than reporting "removed 0".
- Web, iOS and Android all offer it after an import, with a confirm step.

### `is_abnormal` is a TRI-STATE and every client read it as a boolean

`Labs.jsx` rendered `{r.is_abnormal ? '⚠️ Abnormal' : '✅ Normal'}`. On this
database **9,417 of 9,745 stored results have `is_abnormal` NULL** — never
compared to a range — so nearly every row displayed **"✅ Normal"**, including
**137 that numerically contradict their own printed reference range**:

```
Potassium  6.7  (3.5–5.5)   ✅ Normal      <- hyperkalemia
Hemoglobin 12.8 (14–18)     ✅ Normal
LDH        378  (120–246)   ✅ Normal
HGBX       338.4 (42–52)    ✅ Normal
```

§3at's thrill/bruit checkbox, on the most dangerous surface in the product. All
three clients now distinguish **abnormal / in range / not assessed**, and "not
assessed" is never green. iOS and Android showed no abnormality at all before
this — they drew `status` ("Final"), and Android coloured it green.

### Learning from what the reviewer decided — `document_row_judgments`

The reviewer's ticks already exist (`document_import_items.accepted`) and
nothing ever read them back. `al001_import_judgments` stores a row **shape** —
normalised name, which roles were populated, whether the value was a number or a
word — never a measurement, so one patient's review helps the next patient's
import without either seeing the other's data. One row per signature with
`times_confirmed`, so re-seeing a shape sharpens the judgment instead of
inserting a contradictory one beside it.

A verdict is **advisory**: it can untick a row and say why. It can never delete
one, and never overrules a row the deterministic guard judged a real
measurement.

### Derived values: a report checks itself, if you let it

A lab report is full of internal redundancy, and the parser threw all of it
away. The 338.4 % haematocrit was caught by doing arithmetic by hand — HGB 12.8
× 3 = 38.4 — and then patched with a `%>100` ceiling, which is the dumb version
of the insight. The analyte is *named* `HCT CALC (HGBX3)`: the lab is stating
the derivation.

Measured across production, these identities hold to a median absolute error of:

| identity | n | median err |
|---|---|---|
| `Globulin = TotalProtein − Albumin` | 97 | **0.00 %** |
| `TIBC = Iron + UIBC` | 140 | **0.00 %** |
| `CaxPhos = Ca × Phos` | 109 | 0.04 % |
| `MCV = HCT/RBC × 10` | 152 | 0.09 % |
| `URR = (pre−post)/pre × 100` | 126 | 0.22 % |
| `MCH = HGB/RBC × 10` | 153 | 0.27 % |
| `MCHC = HGB/HCT × 100` | 151 | 0.29 % |
| `IronSat = Fe/TIBC × 100` | 123 | 1.01 % |
| `A/G = Albumin/Globulin` | 107 | 1.44 % |

Two distinctions the data itself forced, neither of which was obvious:

- **Exact vs approximate.** `HCT CALC (HGBX3)` is ratio **3.0000** to four
  decimals across 165 pairs — the lab computes it. Measured `Hematocrit` is
  **3.144 ± 0.103** — physiology. An exact identity tolerates ~0; an
  approximation needs a band. Conflating them is the whole bug.
- ⚠️ **The "rule of three" must NOT be enforced.** Literature is explicit that
  it holds only for normocytic, normochromic samples and breaks down in
  microcytosis — and the patient whose report prompted this work has **MCV 68**.
  A naive ±2 band would flag her every draw, and a checker that cries wolf gets
  ticked past, which is how 338.4 was approved. `MCHC = HGB/HCT × 100` at 0.29 %
  is the rigorous form of the same relationship.

> **`NeutAbs = WBC × Neut%` measured at 99904 % error — that was a unit bug in
> the probe, not the lab.** WBC is thousands/µL against an absolute in cells/µL.
> Read the stored units; never assume them. It is exactly the failure this
> feature exists to catch, committed while building it.

Formulas are cited, not recalled: Payne (1973) for corrected calcium
(`Ca + 0.8 × (4.0 − albumin)`, a population average that fails in acid-base and
globulin disorders), Martin-Hopkins for LDL (adjustable TG:VLDL factor 3.1–11.9
versus Friedewald's fixed /5, which is invalid above TG 400 and biased low under
LDL 100), and Daugirdas second-generation for Kt/V.

### Known residue, recorded rather than claimed as fixed

Three footnote fragments still import from that report and are refused by no
shape rule — `Martin SS et al. JAMA. = 2013;310(19): 2061-2068`,
`<70 mg/dL for patients = with CHD or diabetic`, `calculation, which is = a
validated novel method`. Shape cannot separate them from a terse real row, and
inventing a threshold that could would start eating real ones.
`test_a_citation_with_digits_still_survives_this_layer` pins the current
behaviour so a change that fixes it fails loudly and gets its own measurement.
