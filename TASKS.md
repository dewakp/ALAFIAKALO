# ALAFIA — queued work

Work that is agreed but not yet started. Completed work goes in `WORKLOG.md`.

---

## AI must answer against THIS patient's nutrient limits, not general advice

Asked "how well have I been meeting my daily nutrient in past week?", the
assistant returned generic dietary advice and told an ESRD patient to **increase
calories and protein**. That patient's most recent potassium is **6.0 mEq/L**.
Potassium was never mentioned.

Even with perfect data the answer would have been wrong: the context tells the
model what the patient ATE and never what they may HAVE. Fixing the fabrication
(separate issue) does not fix this.

### The real problem: dietary rules are hardcoded to six conditions

`nutrient_goals_service.detect_condition_flags()` returns a fixed dict —
`ckd, dialysis, diabetes, hypertension, cardiovascular, heart_failure` — set by
**substring matching on free text**. This is a tool for the world; a
hand-maintained list of six diagnoses cannot serve it, and adding "anaemia" and
"g6pd" to the list would just make it eight.

It is not merely incomplete. It is **wrong in both directions**:

| Input | Flag set | Reality |
|---|---|---|
| `Heartburn` | `cardiovascular` | substring "heart"; GERD is not cardiac |
| `Diabetes insipidus` | `diabetes` | a water-balance disorder — carb targets are clinically wrong |
| `Sickle cell disease` | none | |
| `G6PD deficiency` | none | |
| `Crohn disease` | none | |
| `Coeliac disease` | none | |
| `Malignant neoplasms of breast` | none | |
| `Gout` | none | |
| `Chronic liver disease` | none | |

Seven real conditions produce **no flags and no signal that nothing was
produced**. The patient gets generic targets that look authoritative. That is
§3aa again: an absent rule is being rendered as a normal answer.

### 1. Key dietary rules to the ICD-11 code, as DATA

Conditions now carry `icd11_code` (35,339 codes, generated catalog). Key the
rules to that, not to keywords:

- **Hierarchical lookup.** ICD-11 is structured — `GB61.5 → GB61 → GB6 →
  chapter 16. A rule attaches at any level, so a chapter-level renal default
  exists without enumerating every code, and `GB61.5` can override it.
- **A data file, not `if` branches.** Adding a condition must not be a Python
  deploy. Same shape as the ICD-11 catalog: generated/curated data, loaded at
  runtime, covered by a test that every rule's code resolves.
- Rules need at least two shapes: **numeric targets/limits** (K+, PO4, protein,
  fluid) and **absolute avoids** (fava beans for G6PD). An engine that only
  emits numbers cannot express a contraindication.

### 2. Never let "no rule" look like "no restriction"

For any active condition with no rule on file, the context must say so
explicitly — `no dietary rule on file for 3A51.1 Sickle cell disease` — so the
model states the gap instead of filling it. Silence here is how a G6PD patient
gets advice that never mentions fava beans.

Uncoded free-text conditions must be reported as uncoded, **not** keyword-matched.
Retire `detect_condition_flags()` once rules are code-keyed; keep it only as a
fallback for legacy rows with no `icd11_code`, and mark its output as low
confidence.

### 3. Put a limits section in the AI context

Add `=== NUTRIENT LIMITS & TARGETS (personal) ===` to
`_fetch_patient_context()` in `api/ai.py` — today there is none at all. State
each as limit, latest serum value, and direction, so the model can say "your
potassium is 6.0 against a 2,000-3,000 mg/day limit" instead of inventing a diet.

§3ac applies: **a treatment changes the day's TOTALS, never the LIMIT.** Do not
raise the potassium limit on a dialysis day.

### 4. Read the direction of each value, not the condition label

From the record (user 63 — verify, do not trust this table):

| | |
|---|---|
| Condition | End-Stage Renal Disease, severe, active |
| Taken | calcium carbonate ×477, calcitriol ×348, folic acid ×20 |
| K+ | **6.0 mEq/L** — hyperkalaemia |
| Phosphorus | 2.6 mg/dL — *below* the 3.5-5.5 dialysis target |
| Calcium | 8.3 mg/dL, on calcitriol *and* a calcium-based binder |
| Hb / ferritin / iron sat | 12.4 g/dL / 186 / 33% |

Phosphorus is LOW while on a binder, so "renal ⇒ restrict phosphorus" is wrong
here. Iron stores are adequate, so "anaemic ⇒ eat more iron" is wrong here. The
rule supplies the target; the serum value decides the direction.

Calcium carbonate is a **phosphate binder taken with meals** — timing is part
of the answer, not a footnote.

### 5. Some conditions are only known verbally

G6PD deficiency and anaemia are **not in this patient's `chronic_conditions`**,
so nothing downstream can act on them. The ICD-11 picker makes them recordable
— G6PD deficiency is `3A10.00`. Until they are recorded there is nothing to
personalise from, and the system should say that rather than imply health.

### 6. Prove it against the population

`scripts/board_sweep.py` is the pattern. Required: a patient with no labs
produces "not recorded" and never a fabricated limit; a condition with no rule
produces an explicit gap; and no condition silently sets an unrelated flag —
`Heartburn` must never be cardiovascular again.

### Watch

- Route conditions through `services/clinical_sources.py` — never
  `health_conditions`, which has no writer (§3aa).
- Group dose logs case-insensitively (§3aa).
- Rules are clinical content. Cite the source (KDOQI etc.) in the data file;
  do not let a model invent a limit at runtime.

---

## ~~Flowsheet housekeeping~~ — DONE 2026-08-20

Shipped on backend, web, iOS and Android. Kept here as the spec.
Queued and completed 2026-08-20. Three changes to new-treatment entry, all of which exist to
stop a patient re-entering data that has not changed since last time.

Canon §3 applies: web, iOS and Android each need this, verified by building.

### 1. Target weight from a 7-treatment moving average

Today's target (dry) weight should default to the **mean of the last 7
treatments' post weights**, not be typed in fresh.

- Source: `therapy_sessions.post_dialysis_weight_kg`, the 7 most recent
  *completed* sessions before today.
- Fewer than 7 on file → use what exists and say so; do not silently average 2.
- Show the value as a default the patient can override, with the basis visible
  ("average of your last 7 post weights").
- Watch: post weight is nullable and a session with none must not be counted as
  zero — that would drag the mean down and set an unsafe fluid-removal target.

### 2. Pre-populate the fields that rarely change

Carry forward from the most recent completed session, always editable:

- Physician, Nurse
- Machine type / make / model
- Dialysate type, dialysate volume, dialysate K⁺ and Ca²⁺ prescription
- Cartridge #, SAK #

Notes:
- These are *defaults*, never silently submitted values — the patient must be
  able to see and change each one.
- Bath potassium feeds the transfer model (`DIALYSIS_BALANCE.md`), so a
  carried-forward value that is stale would quietly skew the day's balance.
  Carry it, but re-validate against the plausible band (0–4 mEq/L) — 11 rows
  already carry 45, which is the lactate value in the wrong column.

### 3. Access type carry-forward, with fistula fields disabled for a catheter

- Default the access type to whatever the previous session used.
- If it is a **catheter**, gray out (disable, not hide) the fistula-only fields:
  **Needle Gauge, Needle Length, Buttonhole, Access Bruit**.
- A catheter has no needles and no bruit, so those fields being enabled invites
  meaningless data; disabling rather than hiding keeps the form recognisable
  and makes the reason visible.
- Switching the access type back to a fistula must re-enable them immediately.
- Existing rows that already carry needle data on a catheter session should be
  left alone, not blanked.

### Verification

- Backend: a "last session defaults" endpoint (or an extension of the existing
  session read) with tests for the empty case, the fewer-than-7 case, and the
  null-post-weight case.
- `docker compose --profile test run --rm backend-test` / `frontend-test` / `e2e`
- `xcodebuild -scheme ALAFIA` and `./gradlew :app:assembleDebug`
