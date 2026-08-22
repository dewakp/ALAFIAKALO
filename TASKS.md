# ALAFIA — queued work

Work that is agreed but not yet started. Completed work goes in `WORKLOG.md`.

---

## AI must answer against THIS patient's nutrient limits, not general advice

Asked "how well have I been meeting my daily nutrient in past week?", the
assistant returned generic dietary advice and told an ESRD patient to **increase
calories and protein**. That patient's most recent potassium is **6.0 mEq/L**.
Potassium was never mentioned.

Even with perfect data the answer would have been wrong, because the context
tells the model what the patient ATE and never what they may HAVE. Fixing the
fabrication (separate issue) does not fix this.

### The gap

`services/nutrient_goals_service.compute_goals()` already derives personalised
targets from conditions, and **none of it reaches `_fetch_patient_context()` in
`api/ai.py`**. There is no limits section in the prompt at all.

`detect_condition_flags()` covers `ckd, dialysis, diabetes, hypertension,
cardiovascular, heart_failure`. It knows nothing about **anaemia** or **G6PD
deficiency**, and there is no G6PD dietary logic anywhere in the app — only a
comment in `models/chronic_conditions.py` and a risk-factor string in the
ICD-10 catalog.

### What the record actually holds (user 63, verify before trusting)

| | |
|---|---|
| Condition | End-Stage Renal Disease, severe, active |
| Taken | calcium carbonate ×477, calcitriol ×348, folic acid ×20 |
| K+ | **6.0 mEq/L** — hyperkalaemia |
| Phosphorus | 2.6 mg/dL — *below* the 3.5-5.5 dialysis target |
| Calcium | 8.3 mg/dL, on calcitriol + a calcium-based binder |
| Hb / ferritin / iron sat | 12.4 g/dL / 186 / 33% |

Note phosphorus is LOW while on a binder, and calcium is low-normal while on
calcitriol *and* calcium carbonate. Advice must read the direction of each
value, not assume "renal patient ⇒ restrict phosphorus".

### 1. Put a limits section in the AI context

Add a `=== NUTRIENT LIMITS & TARGETS (personal) ===` block to
`_fetch_patient_context()`, sourced from `compute_goals()` — never hardcoded.
State each as limit, latest serum value, and direction, so the model can say
"your potassium is 6.0 against a 2,000-3,000 mg/day intake limit" instead of
inventing a diet.

§3ac applies: **a treatment changes the day's TOTALS, never the LIMIT.** Do not
raise the potassium limit on a dialysis day.

### 2. Teach the goals engine anaemia and G6PD

- **Anaemia**: iron, B12, folate targets. Gate on ferritin and transferrin
  saturation — this patient's iron stores are already adequate, so "eat more
  iron" would be wrong.
- **G6PD**: an AVOID list, not a target — fava beans above all. This is the one
  case where the answer is a contraindication rather than a number, so it needs
  its own shape in the model.

### 3. Record what is only known verbally

G6PD deficiency and anaemia are **not in this patient's `chronic_conditions`**,
so nothing downstream can act on them. The ICD-11 picker now makes them
recordable — G6PD deficiency is `3A10.00`. Without the record there is nothing
to personalise from.

### 4. Prove it against the population, not one patient

`scripts/board_sweep.py` is the pattern. A patient with no labs must produce
"not recorded", never a fabricated limit, and never a blank (§3aa: an error is
not an empty state).

### Watch

- Route conditions through `services/clinical_sources.py` — never query
  `health_conditions`, which has no writer (§3aa).
- Group dose logs case-insensitively; "Calcium Carbonate" and "Calcium
  carbonate" are the same drug (§3aa).
- Calcium carbonate is a **phosphate binder taken with meals**. Timing advice is
  part of the answer, not a footnote.

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
