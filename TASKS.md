<!-- Copyright © 2026 Wole Akpose / 6igma Health Inc.
     All rights reserved. ALAFIA — proprietary and confidential. -->

# ALAFIA — queued work

Work that is agreed but not yet started. Completed work goes in `WORKLOG.md`.

---

## AI must answer against THIS patient's nutrient limits, not general advice

Asked "how well have I been meeting my daily nutrient in past week?", the
assistant returned generic dietary advice and told an ESRD patient to **increase
calories and protein**. That patient's last recorded potassium is **6.0 mEq/L** — and it was measured
**369 days ago**. Potassium was never mentioned, and neither was the fact that
nothing has been measured since.

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
| K+ | 6.0 mEq/L — but measured **2025-08-18, 369 days ago** |
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

### 7. Model drivers and leading indicators, not just labels

"Anaemic → eat more iron" treats the label. "Iron stores are adequate, so this
anaemia has a different driver" reasons about cause — and only the second is
useful. In ESRD the usual driver is EPO deficiency, and the iron indices are
what discriminate between them. This patient has **no ESA prescribed or taken**,
which is the finding; dietary iron is the wrong lever entirely.

An analysis layer needs three things a target table cannot express:

**Candidate drivers per abnormal value, with discriminators.** For K+ that is
intake, missed sessions, metabolic acidosis, ACE-i/ARB/K-sparing agents,
catabolism, or a haemolysed sample — distinguished by interdialytic weight
gain, session adherence, bicarbonate, and the medication list. The output should
name which driver the data supports, not restate the number.

**Leading indicators.** Rising interdialytic weight gain predicts fluid
overload before the weight is dangerous; falling transferrin saturation predicts
functional iron deficiency before Hb moves. Acting on a lagging value means
acting late.

**Direction over category — worked example.** Phosphorus here is **2.6, below
the 3.5-5.5 target, while on a phosphate binder**. Label-driven logic says
"ESRD ⇒ restrict phosphorus". Driver-driven logic asks why it is low on a
binder and points at over-binding or poor intake — the opposite intervention.
Getting this backwards is not a missed nuance; it is harm.

`services/diagnostics_engine.py` already does exactly this shape for
**symptoms** (differential + discriminators, ICD coded). Nothing does it for
**values**. Extend the pattern rather than inventing a second one.

### 8. Evidence has an age, and staleness is itself a finding

The record above is the case in point, and it caught the author of this task:
K+ 6.0 was quoted as current. It is 369 days old. **All 422 labs are ≥369 days
old, while the patient dialysed 7 days ago** — actively treated, unmonitored.
For a dialysis patient whose labs should be monthly, that gap is a more
actionable finding than any single value in it.

So every derived statement must carry the age and provenance of what it rests
on:

- "your potassium is 6.0" is wrong. "your last potassium, a year ago, was 6.0
  and nothing has been measured since" is right.
- Staleness must **degrade confidence**, not be silently quoted as current.
  A stale value may still be the best evidence available — it must not be the
  unmarked evidence.
- **"Not known" is a first-class answer.** A driver that cannot be
  discriminated from available data must be reported as undetermined, with what
  would settle it. Guessing is what the model already does badly (§3ae).

This is the same rule as §3aa's "an error is not an empty state", applied to
time rather than to failure.

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

---

# Future work — agreed direction, not yet started

Eight items, recorded 2026-10-10. None is greenfield: each already has surface
in the codebase, and each has at least one constraint this canon has already
paid for. The anchors below are measured, not assumed — so the next person
starts from what exists rather than rediscovering it.

## 1. Restaurant integration

Log a meal eaten out, with nutrients, without the patient typing a recipe.

**What exists:** `services/meal_parser.py`, `services/nutrient_estimator.py`,
and the resolve-once-remember-after caches `learned_food_nutrients` /
`food_nutrient_cache` (§3c).

**The trap is already written down.** §3c: *"do not add aliases"* — a branded
match answered **80 kcal / 1.6 g protein** for a goat curry because
`vindaloo` hit *Vindaloo Simmer Sauce*, and the same meal logged twice returned
108 kcal and 520 kcal. A restaurant menu is a catalogue of branded items
pointed straight at that failure. Relevance must stay two-directional
(Jaccard, not `overlap / query_tokens`) and an all-zero row must keep counting
as a MISS.

**Open questions:** which menu source is authoritative and under what licence;
whether a chain's published nutrition is per-item or per-serving; and how a
restaurant dish reaches the §3an condition guard, whose allergen matching is
deliberately English-only (§3aw — a translated "cacahuète" walks past a peanut
allergy).

## 2. Meal kit integration

Turn a generated plan into something orderable.

**What exists:** `api/planners.py` already produces a 7-day plan AND a
`SHOPPING_LISTS` shopping list per pattern; `models/pantry.py` tracks what the
patient has.

**Constraint:** the renal template exists because a general one is unsafe
here — swapping in a vendor's catalogue must not quietly reintroduce
potassium and phosphorus a dialysis patient cannot clear (§3ac, §3an). A kit
substitution is a clinical change, not a shopping one, and needs the same
avoid/favour guidance the planner already consults.

## 3. Enhanced UI, generated from an AI prompt

Let the model compose the surface rather than shipping a fixed screen per task.

**What exists:** the provider router (`alafia_chat` / `alafia_infer`), the tool
loop in `services/ai_conversation.py`, and `TOOL_SPECS` / `TOOL_LABELS`.

⚠️ **The hard rule this collides with is §0 and §3am: a model handed a record
invents plausible rows.** The tool loop exists *because* of that — asked which
food drove today's sugar, a model on the old prose path named a food from the
previous day and reported **15.0 g, a number in no row of the record**. A
generated UI must render values the tools RETURNED, never values the model
composed, and the provenance has to survive into the rendered component. A
chart with a fabricated axis is worse than no chart.

**Also:** every generated string still has to reach the catalogs (§3aw) or the
feature ships English-only by construction, which is the gap
`test_every_language_carries_every_source_key` now fails the build on.

## 4. Voice enhancement

**What exists:** `ML/src/alafia_model/adapters/whisper_adapter.py` and
`IOS/ALAFIA/Core/SpeechRecognizer.swift`.

⚠️ **Do not expand this before closing the privacy hole §3al already names.**
`whisper_adapter._post` uploads the recording to `api.openai.com` **with no
guard at all** — `scrub_payload` redacts a message only when its `content` is
a string, so audio bypasses it entirely, and a local server is used only when
`WHISPER_BASE_URL` is set, which production does not set. **A patient saying
their own name is on that file.** Redaction is a text instrument; whether a
recording may reach a third party at all is a product decision, not something
`scrub_pii` can make safe. Any voice work widens this surface, so it is the
first thing to settle, not the last.

## 5. Full-feature telemedicine consult

**What exists:** `models/telehealth.py`, `schemas/telehealth.py`,
`api/telehealth.py`, `api/ws_telehealth.py` — so the data model and the socket
are already there.

**Constraints:** §3e — finding a clinician is deliberately not browsing a
directory (a complete identifier resolves anyone; a partial name resolves only
a shared contact), and a consult feature must not become the directory that
rule exists to prevent. `is_user_entitled` already gates the sockets, which
were once open to unpaid accounts with a valid token.

## 6. Physician subscription

**What exists:** `models/subscription.py`, `models/physicians.py`,
`services/subscription_service.py`, `SubscriptionRail.md`.

**Constraints:** Stripe is the ONLY web rail — PayPal was advertised and
unbuyable for weeks and was withdrawn 2026-08-23 (§3ah), and
`CheckoutRequest.provider` is now `Literal["stripe"]` so an unsupported rail is
refused at the boundary. A physician tier needs its own entitlement question:
`_ENTITLING_STATUSES` currently includes CANCELED-with-a-future-period-end, and
whatever a physician's lapse should mean has to be decided rather than
inherited.

## 7. Paid telemedicine consult

**The question to settle first is not technical.** §3au: Apple and Google
require *digital* subscriptions to go through their IAP, which is why the
mobile price is $14 against web's $12 — the differential IS the commission. A
real-time consult with a human clinician is plausibly a *physical-world
service*, which store policy treats differently and which may be billed
directly. Getting that wrong means either a rejected build or a needless 30%.

**Then:** a consult is a one-off charge, and every billing path here so far has
been a recurring subscription. §3ah's lesson applies directly —
`client_reference_id` does not survive a declined card, so a one-off must stamp
its own identifier on the object that survives failure, or a paid consult with
no attributable user is the next `user_id NULL` audit row.

## 8. Global food and medicine recall

**What exists:** `api/fda_recalls.py` and `IOS/ALAFIA/Views/FDARecalls/` — and
it is **US-only today**, measured: it queries `api.fda.gov/food/enforcement.json`
and `api.fda.gov/drug/enforcement.json`, and parses coverage against a
hardcoded `_US_STATES` table. "Global" is precisely the part that does not
exist.

**Verify the authority before building** (§3ad, and the RxNorm/SNOMED/LOINC
probe that saved `_ROUTES` from deletion): every regulator publishes
differently — EU RASFF, UK FSA, Health Canada, Nigeria's NAFDAC — with
different formats, licences and update cadences, and some with no machine
-readable feed at all. Measure coverage per source before promising the word
"global". ⚠️ And note the NLM precedent: **the RxNav Drug Interaction API was
retired on ~2 Jan 2024 with no replacement.** A feed that exists today is not a
feed that will exist; whatever is built needs to notice when a source goes
quiet rather than silently reporting no recalls, which is §3aa's *an error is
not an empty state* on a safety surface.

