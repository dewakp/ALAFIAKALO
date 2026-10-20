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

## 9-13. Recipes

Added 2026-10-10. ⚠️ **Two of these five are already built** — measured before
writing, because documenting shipped work as "future" is the drift this canon
exists to stop.

### 9. Recipe analyzer — LARGELY EXISTS

`POST /nutrition/recipe-analyze` (`api/nutrition.py:988`) parses a recipe,
prices its ingredient list through the believability-guarded estimator, and
returns `RecipeAnalyzeResponse`. Covered by `tests/test_recipe_ingest.py`.

**What is NOT there** is analysis against THIS patient: a recipe is priced for
nutrients but never checked against their conditions. The machinery for that
exists and is unused here — `food_safety.build_guidance`, the
`condition_nutrition_facts` avoid/favour store (§3an), the declared allergies
with their RxNorm-resolved aliases (§3az), and now the cited per-condition
quotas in `condition_nutrient_quotas` (§3bd). A recipe analyzer that cannot
say "this has 980 mg of potassium and your limit is 2,200" is a calculator,
not an advisor.

### 10. Recipe from URL — EXISTS

`services/recipe_ingest.py`. It reads **schema.org/Recipe JSON-LD only** — no
HTML scraping heuristics, deliberately — with an SSRF guard
(`_assert_public_http`, pinned by `test_ssrf_guard_blocks_private`), and when
the page publishes its own nutrition it converts that per-serving figure to
per-100 g and records it in `learned_food_nutrients` with `source="recipe"`,
so later *descriptions* of the same dish price correctly.

**Its real limit, already pinned by a test:** a page with no JSON-LD yields
nothing (`test_parse_non_recipe_page`). Most blogs and many restaurant pages
are that. Widening it means either a second extraction path or accepting the
gap — and §3ab's lesson applies if a parser is added: measure what it ADDS as
well as what it recovers, because a recall-only metric scored boilerplate as a
lab result for five dates.

### 11. Recipe from video — NOT BUILT

**Anchors:** `alafia_infer("vision", …)` with `OLLAMA_VISION_MODEL=llava`
(**not** moondream — it is a grounding model and answers the food schema with
bounding boxes, so every photo fails, §3a), and `whisper_adapter.py` for
narration.

⚠️ **Two privacy facts have to be settled first, and §3al already states
both.** Images are NOT redacted — `scrub_payload` returns a dict untouched, so
`VisionCapability.infer` never passes through it — and audio has **no guard at
all**: `whisper_adapter._post` uploads to `api.openai.com`, with a local server
used only when `WHISPER_BASE_URL` is set, which production does not set. A
kitchen video carries faces, a home, and a voice. Redaction is a text
instrument; whether this may reach a third party at all is a product decision.

**And the cost shape is different from a photo:** a video is many frames. Which
frames are read, and whether anything is retained, needs the §3a consent answer
(`allow_collective_insights`, default false, absent row = no consent).

### 12. Recipe recall — ⚠️ NEEDS A DEFINITION BEFORE IT CAN BE BUILT

Two readings, and they are different features:

1. **Recall a recipe the patient used before** — retrieval over their own
   history. Today `nutrition_logs.recipe_url` holds the link, so the data is
   there and nothing surfaces it.
2. **A recipe is recalled because an INGREDIENT is** — the safety reading,
   which joins straight onto item 8. If an ingredient appears in a recall feed,
   every stored recipe containing it should raise a notification.

Reading 2 is a safety feature and would use `services/active_response.py`,
which already turns a new row into a notification and already states that
nothing retroactive fires. Reading 1 is a convenience. **Confirm which is
meant** — building the wrong one is a wasted cycle, and building 2 without
saying so would put a clinical alert behind a convenience label.

### 13. Five or more recipes in one meal

**The concrete gap is measured:** `NutritionLog.recipe_url` is a single
nullable column (`models/nutrition.py:90`), and the request schemas carry one
`recipe_url` each. A meal already holds `components: list[MealComponentResult]`
with `aggregate_nutrients`, so the *component* side is plural already; the
*recipe* side is not.

⚠️ **This collides with §3c head on.** Multi-item meals MUST go through
`estimate_meal_nutrients()`, never `estimate_nutrients()`: the single-food path
merges matches by SUMMING per-100 g densities, which for a list yields
**1978 kcal/100 g — above pure fat** — which the plausibility band then
rejects, sending the request to the slow AI fallback. Nesting five recipes
multiplies the component count and points straight at that path.

⚠️ **And §3am's writer bug is the one that actually reaches the patient:**
`estimate_meal_nutrients` had ALREADY judged a 3,892 kcal / 394 g-fat meal
`believable = False`, and `nutrient_enrichment.py` stored it anyway because it
never read the flag. Five recipes is five chances to produce an impossible
aggregate. Whatever is built must honour `believable`/`warnings`, and the
per-recipe provenance has to survive into the aggregate — otherwise an
implausible total cannot be traced to which recipe caused it.


---

## 14. The PDF importer must recognise and route ANY document

Operator, 2026-10-11: *"PDF documents may be disparate, what they show are often
same data: lab, medication, visit summary, recipe, food list, pantry list,
imaging, flowsheets data etc. We must recognize data type from the upload and
route to the correct db table or tables. That is the flexibility"* — and, on the
five hand-typed document types: *"5 types is grounding tens or even hundreds of
variations in 5 hard-coded type. what coul go wrong there. everything. so we are
not hard-coding but being flexible."*

Landed 2026-10-11 (see WORKLOG): claim-based routing replaces
`TARGET_FOR_DOC_TYPE`, so one document may now feed several tables, and
`doc_type` is a stored hint rather than a switch. What is QUEUED is below.

### 14a. ~~A field extractor~~ — BUILT 2026-10-11, but see the scope limit

`claims.classify_table` reads TABLES: rows with column roles. The DaVita
Treatment Details Report is mostly a **form** — labelled values scattered across
a page (`Ordered Target Weight 50.0 kg`, `BFR 300 mL/min`, `Close Treatment
Reason …`) plus ONE table of timed readings. Measured: that report scores **1
point out of a possible 41** against the signature table, and `classify_table`
sees almost none of its fields.

`app/services/docparse/fields.py` does label→value extraction by coordinate,
with NO vocabulary of labels — replacing the ~40 hand-typed literals in
`metadata.py`'s six tuples as the mechanism (that reader is unchanged and is now
the oracle). Measured over the 13-document corpus: **165 fields discovered,
~12.7 per document against a ceiling of 6**, and it recovers every labelled
field the tuned reader finds — collection date 12/12, lab 12/12, ordering
provider 13/13.

⚠️ **STILL UNVALIDATED on an actual form.** There is no form-shaped clinical PDF
on this machine — 304 PDFs, 13 clinical, all table-shaped lab reports — so the
geometry is proven only against those reports' header block. A real treatment
report would exercise the no-colon case, and it cannot be obtained without 14e
(no OCR, and the reports arrive as photographs). So 14b remains blocked in
practice even though its extractor now exists.

⚠️ **`patient_name` is deliberately NOT discoverable.** These reports print the
name with no label at all, so it stays with `metadata._guess_patient_name`'s
name-shape regex. A form extractor cannot find an unlabelled field, and
stretching it to try would be the wrong fix.

### 14b. The treatment stager (`therapy_sessions` + `intradialytic_readings`)

Straightforward once 14a exists, and the mechanics are already verified:

- `_build_row` returns `TherapySession(..., intradialytic_readings=[...])` and
  the relationship cascade inserts parent and children on one `db.add`.
  `confirm()` needs NO change; discard cascades at the FK.
- `TherapySession` is **not** in `test_clinical_sources.GUARDED`, so no §3aa
  exemption is needed. ⚠️ But `SessionDrug` IS, and `session_drug_sync` fires on
  the API save path only — a session created through `_build_row` would carry
  `drugs_administered` text with no structured rows, which is exactly the
  ten-month staleness §3av records.
- `_naive_session_payload`'s overnight rollover is also on the API path, not
  `_build_row`. A treatment crossing midnight imported this way would store the
  end before the start — the bug §3av measured on 4 production rows.

### 14c. `pantry_items` and `nutrition_logs` stagers — the easy wins

Both are list-shaped and fit the detector as it stands. `pantry_items` already
stores name / category / quantity / unit / location / expiration_date, so a
photographed pantry list or grocery receipt maps on almost directly, and
`PANTRY_ITEM` detection (a counted quantity in `cans`, `lbs`, `cups`…) is
already written and tested.

### 14d. Imaging and recipes have NO destination table

Measured 2026-10-11: `facilities.imaging` is a facility TYPE enum value and
`recipe_url` is a column on a meal plan. There is no imaging table and no
recipes table anywhere in the 130-table schema. Both are named in
`claims.NO_TARGET_YET` so a reviewer is told "read, cannot be filed" instead of
the rows landing somewhere plausible — but giving either a real target means a
model plus a HAND-WRITTEN migration (§3ao: `--autogenerate` would propose
dropping live tables).

Recipes overlap items 9-13 above; whatever is built should serve both.

### 14e. OCR / image input — NEEDS A DECISION

`extract.py` accepts a PDF with a text layer, or plain text. A scan returns
`needs_ocr`, `usable` is False, and the import stops. **There is no OCR path at
all** — so a photographed document cannot be imported in any form, and the
operator has been sending document PHOTOS (the 10/09 treatment report arrived as
six).

The decision is not technical, it is egress: local OCR (tesseract/PaddleOCR in
the image — no third party, weaker on phone photos) versus a hosted vision model
(far better on photos, but §3al records that the vision path is NOT redacted and
a lab-report photo carries the patient's printed name and record number). Do not
send document images to a vendor without that call being made.

### 14f. Persist the lab's own test code, and hang LOINC off it

Measured 2026-10-11 over the 13-document corpus:

    records carrying a numeric test code     939 of 1014  (92.6%)
    1 name -> MANY codes                       0 of 142
    1 code -> MANY names                      56 of  83

The code UNITES the spellings §3ax still lists as unresolved — `1001` = ALK PHOS
+ ALP, `1007` = CHLORIDE + CL, `1010` = CREATININE + CRE, `1016` = POTASSIUM +
K+, `2244` = HEMOGLOBIN + HGB — while correctly keeping `1004` BUN SEPARATE from
`1023` BUN-POST (§3ac's post-dialysis BUN). §3ax says each of those splits "is a
clinical identity claim, so add them deliberately"; the lab has been stating
them on every row.

`LabRecord.code` is already populated (`normalize.py:450`) and
`document_import_service` **never reads it** — §3ay's never-plugged-in sink, on
the best identity signal in the document. Queued:

1. an additive column for the source test code (no dedupe change — §3ab: a fix
   that changes the NAME makes a re-import land BESIDE the wrong row);
2. identity anchored on `(lab, code)` ALONGSIDE the verbatim printed name, which
   §3ax requires stay exactly as the document printed it;
3. LOINC attached per code **under review** (§3ab's two-reviewer shape), never
   per name, and `loinc_code` left NULL rather than defaulted — the column is
   shared with real codes from the FHIR import.

⚠️ **Resolving LOINC from NAMES is a dead end and the audit says so.** Over 411
production names: 143 resolve, **68 decided by a rank tiebreak between tests
LOINC itself separates**, and only **5 determinate (1.2%)**. `Platelet` resolves
to mean platelet VOLUME while `Platelets` resolves to the count. The unblock
named in `document_import_service.py`'s removal comment — "a specimen read off
the report" — **is not available**: measured, these reports print no specimen at
all (the only `blood` is the dialysis BLOOD FLOW parameter, the only `sample` is
prose about aged samples).

### 14g. Smaller, measured, carried forward

- **The classifier breaks ties on dict order.** `discharge_summary=20,
  imaging_report=20` is resolved by declaration order in `SIGNATURES`, so adding
  a type silently reclassifies existing documents.
- **`target_table` is a single string on the wire** and web, iOS and Android all
  decode it as one. `_primary_target` now reports the LARGEST target, which
  under-reports a genuinely multi-target document. Widening it is a client
  change across three platforms (§3).
- **The medication and condition extractors still have no shape guard of their
  own.** `records_from_medication_table` and `records_from_condition_table`
  append a record for every named row; unguarded they stage **1115 false
  medications and 1115 false conditions** against 1014 true lab rows.
  `claims.py` gates them from outside — correct today, and a trap for anyone who
  calls those functions directly.
- **Claim detection is per DOCUMENT, not per row.** 928 of 1014 records are
  claimed as measurements; the gate decides only WHETHER `_stage_labs` runs, so
  nothing is dropped. Per-row claiming would let one PDF route row-by-row, which
  is what a true mixed document (a visit summary) actually needs.
- **Three of the five declared types have never met a real document.**
  `medication_list`, `discharge_summary` and `imaging_report` are untested
  against anything real — the corpus is 13 lab reports, exactly as §3ab warns.

---

## 15. Every aggregator must see every domain

Landed for the INSIGHT surface 2026-10-11 (OPEN_ITEMS 14). The same scan says
the other aggregators are still partial, and the operator's instruction covers
all of them: *"All data must be visible and used by the various anaytytes,
aggregators and AI queries. This cannot be compromised."*

Measured per aggregator, 2026-10-11 — domains read of the nine named:

| aggregator | covered | missing |
|---|---|---|
| ~~`api/wellness.py` (trends)~~ | **9** | DONE 2026-10-11 — now consumes `collect_signals`: 3 streams → **110 across 8 domains** |
| `api/wellness.py` (score) | 7 | hospitalisation, conditions |
| `api/chart_dashboard.py` ⚠️ **confirmed in the UI 2026-10-11: Systolic BP shows 9 points over 90 days** | **2** | nutrition, medication, eliminations, vitals, lifestyle, hospitalisation, conditions |
| `services/diagnostics_engine.py` | 4 | flowsheets, nutrition, eliminations, lifestyle |
| `services/ai_engine.py` | 4 | flowsheets, eliminations, labs, hospitalisation |
| `services/patient_board.py` | 7 | hospitalisation, conditions |

`chart_dashboard.py` is the worst and is the "trends" surface — flowsheets and
labs only, so a chart of this patient's weight or pressure draws the 0.8% /
0.23% slice measured in OPEN_ITEMS 14.

**Hospitalisation reaches NO aggregate.** `clinical_sources` is its only reader;
§3bb built `hospitalizations` + `surgical_procedures` on 2026-10-05 and nothing
has aggregated them since. An admission is the event a relationship engine most
needs on the timeline, because what changed around it is the clinical question.

The cheapest route is for these to consume `health_signals.collect_signals`
rather than each growing its own queries — one substrate, one place where a
domain can be forgotten, and the guard in
`tests/test_signals_cover_every_domain.py` already fails the build when a named
domain has no signal.

---

## 16. Render findings in the BACKGROUND, not on the read

`finding_text.render` works and is proven — ALAFIA wrote this, locally,
verified against the facts:

> Blood pressure reading of 86/60 mmHg, taken by the patient themselves, shows
> systolic below the reference low of 90.

But measured 2026-10-12 on `gpt-oss:20b`:

    cold (13 GB model load)   65 s
    warm, ONE finding       14-17 s
    warm, FIVE findings       > 20 s   (the real card)

`/wellness/score` carries the client's 30 s axios default (§3ae), so **no
synchronous bound can work**: 20 s clears one finding and not a card, and the
cold path clears nothing. Today every finding on the real card falls back.

The shape is §3c's, already proven on nutrition: *persist and return
immediately; fill in afterwards with the worker's OWN session.*

1. compute the score, store it, return the deterministic wording **now**;
2. render in the background, keyed by a hash of the findings' facts so the
   same observation is never re-rendered;
3. store the sentences on the daily `wellness_scores` row (it already carries
   `explanation` and `recommendations`, and is already one row per day);
4. serve the stored sentences when the facts hash matches.

⚠️ The worker must never raise and must never block a clinical write (§3c),
and the render stays `local_only=True` regardless of where it runs (§3al).
⚠️ A facts hash is required, not optional: without it a changed measurement
would be described by yesterday's sentence, which is worse than a plain one.

---

## 17. Nothing stops an analysis being written into a clinical field

OPEN_ITEMS 26 repaired one row by hand. The shape that produced it is intact.

- **17a. A guard on what may enter `patient_notes` and its siblings.** The
  tell-tales are mechanical and were all present: a column name
  (`fluid_removed_ml`, `duration_minutes`), the product's own name describing
  its database ("ALAFIA held no record"), an imperative to the reader ("Raise
  with the care team"), and shouting caps. A staging-time check that REFUSES
  those — or at minimum separates them into an import log — costs nothing and
  cannot be forgotten the way a habit can. §3ab's staged-review path is where
  it belongs for documents; a manual write needs the same door.
- **17b. There is no provenance field on `therapy_sessions`.** `clinical_notes`
  is the wrong home — it requires an `author_id` referencing a user, so an
  import note filed there is attributed to a person and reads as a clinician's
  observation. Which document a row came from, and which of its values could
  not be read, is real metadata with nowhere to live. Decide: a column, a
  side table, or `document_imports` linkage for manual imports too.
- **17c. The prose duplicated rows that already existed.** Six
  `intradialytic_readings` were re-typed as a sentence. Before writing a
  narrative, check whether the fact already has a column — a value in prose is
  a value no query reaches, and the two copies drift.
- **17d. Sweep the rest of the corpus.** This was found by eye on one screen.
  Nothing has looked at the other 2,000+ `patient_notes` for the same pattern,
  or at `complications` / `side_effects`.
- **17e. The finding only examines the LATEST dry weight.** An excursion that
  has since been corrected is in the record and reported nowhere. Whether a
  historical outlier deserves a surface of its own is open.

---

## 18. Ω is a memoryless function of 23 scalars. The construct it claims to measure is not

Two operator questions, verbatim, 2026-10-12:

> *"is trapezoidal (mean) the appropriate arithmetic for modeling the
> multi-modal, multi-disciplinary construct of the human system? I'm not
> convinced."*

> *"how does the model understand and factor in leading and lagging factors such
> as relationship between high rdw (new blood cells) and iron levels in blood
> and iron intake (medication and nutrion) and ferretin, and iron binding
> capacities, and drug taken (when) such as folate, epogene, venofer, vitamin B
> and also multi-vitamins from nutrion and nutrient loss due to medication or
> elimination and so on. i only provided one dimension and there are thousands
> via various pathways -- kreb cycle, neuro pathways, etc"*

And the definition this is measured against, from the same session:

> *"HEBCS is human biologics that measures (analyzes) the
> electro-biochemical-neurophysical composition of a person using all known
> pathways degenerated into mathematical construct."*

**The answer to the second question is: it does not, and it structurally
cannot.** Measured, not argued — `/wellness/omega` queries exactly three
tables, and two of them only to derive nPCR from urea kinetics:

    LabResult            23 analytes, ONE timepoint each
    TherapySession       urea kinetics only
    IntradialyticReading urea kinetics only

Zero medications, zero nutrition, zero elimination, zero timing, no derivative.

### The worked example is in this patient's own record

Operator named the iron axis. It is the clearest possible demonstration, and
the engine gets it exactly backwards.

    date         RDW    Hgb   Ferritin  TSAT   MCV    TIBC  UIBC   MCH
    2026-01-05   13.8   13.2      78     19    92.2    291   236   28.9
    2026-02-09   14.1   12.0      57      —    94.8    314   264   29.5
    2026-04-08   16.4   10.4     102     20    92.1    300   240   28.4
    2026-09-11   15.4    9.0      24      6    78.0    331   310   23.2
    2026-10-01   21.3   11.3     197     14    82.1    302   260   24.2

Between those last two draws, from `therapy_sessions.drugs_administered`:

    2026-09-15   Epogene (3000); Venofer (200 mg)
    2026-09-19   Epogene (3000); Venofer (200 mg)
    2026-09-23   Epogene (6000)
    2026-09-25   Epogene (3000); Venofer (200 mg)

**600 mg of IV iron and 15,000 units of ESA.** Ferritin ×8, TSAT 6→14, Hgb
+2.3, MCV 78→82.1 rising, MCH 23.2→24.2 rising, TIBC 331→302 and UIBC 310→260
both falling — iron repletion, then a burst of erythropoiesis.

**RDW 15.4 → 21.3 is the signature of that response.** A cohort of new,
larger cells entering a microcytic population widens the distribution. It is
what the treatment working looks like.

**The engine scores RDW 21.3 as 0.000, in two pathways, and names it twice
under "critical biomarkers".** It penalises the patient for recovering, because
it sees one scalar against one band with no exposure, no lag and no neighbour.

### What the trapezoid assumes, and why each is false of a physiology

- **Separability.** `trapezoidal_score(x, b)` is a function of ONE variable, so
  no interaction is expressible. Ferritin 197 scores 0.98 while the same panel's
  TSAT of 14% says the iron is not available — functional iron deficiency is the
  PAIR, and ferritin is an acute-phase reactant besides. TIBC 302 and UIBC 260
  are on that same panel and the engine **never reads either**, nor MCH, MCHC,
  reticulocytes, B12 or folate.
- **Indifference inside the band.** Every value in [opt_low, opt_high] scores
  exactly 1.0, so a patient falling 12.0 → 10.1 shows no change at all, then
  drops off a cliff. A score that cannot see movement cannot see a trend.
- **Linear ramps.** Mortality against potassium is U-shaped and steep; 6.5 is
  not "twice as bad" as 6.0, it is arrhythmic.
- **No time.** No derivative, no lag operator. Ferritin fell 1,033 → 24 across
  this record (§3av). 197 rising and 197 falling score identically.
- **Reduction happens too early.** Once Ca is 1.0 and PTH is 0.067 the Ca×PTH
  relationship is unrecoverable. Collapsing to [0,1] per marker destroys exactly
  the information an interaction term would need.
- **The modalities are not there.** "Electro-" (16,236 intradialytic readings, a
  pulse series, K 5.3), "neuro-" (nothing), symptom burden and functional status
  are all absent. Seven pathways of a chemistry panel is not a multi-modal
  construct.
- **The weights are hand-assigned.** Glucose 0.30, Metabolic 0.20 — none fitted
  to an outcome.

### Honest assessment

The trapezoid is a defensible **rubric**: transparent, auditable, checkable by a
clinician with the guideline in hand, which is real value and is why it was
chosen. It is **not a model of a coupled system**, and the gap between those two
things is what the operator is pointing at.

### 18a-18f — what closing it needs

- **18a. Named clinical constructs first, because they are citable.** Corrected
  calcium, Ca×P (present), anion gap, **TSAT-with-ferritin as functional iron
  deficiency**, retic-with-RDW as an erythropoietic response. These are
  interactions medicine already defines, so they need no fitting and carry an
  authority — the §3bc shape. This is the cheapest real step and it fixes the
  RDW misread above.
- **18b. A trajectory term.** 9.8 years of series exist. Level and slope are
  different findings and only one is scored. Needs a stated window per analyte
  (§3an: lab recency is already defined — do not invent a second).
- **18c. Exposure must reach the score.** Venofer, Epogene, Doxercalciferol live
  in `therapy_sessions.drugs_administered` (§3aa's THIRD medication source,
  1,248 / ~1,900 / ~788 administrations) and Ω reads none of them. §5 already
  records that none of that iron reaches nutrient tracking either. Dose AND date
  — the lag is the point.
- **18d. Losses.** Dialysis clearance (DIALYSIS_BALANCE.md) and elimination
  remove solute between draws. Neither is in Ω.
- **18e. Replace plateau-plus-linear with an outcome-derived shape** where one
  can be derived. ⚠️ **The trap is already in this repo**: the 12 risk
  classifiers report AUC 1.000 because every target is a same-day threshold on a
  feature inside its own input (§3av). Fitting weights or shapes needs a
  non-tautological outcome, and we do not currently have one. Do not swap in a
  fancier aggregation and call it a model.
- **18f. Admit the other modalities** — BP/pulse series, symptom burden,
  functional status — or stop describing Ω as whole-person. Today's text already
  says it measures biological state only; the name does not.


### 18g. The implementation is not the published framework — measured 2026-10-12

Operator: *"Bone mineral is not just PTH but also calcium, phosphorous and
vitamin D."* Correct, and it is in their own Table 3: **Vitamin D appears in TWO
published pathways and in ZERO implemented ones.** So do ALP and Magnesium.

`docs/HEBCS_medRxiv_draft.md` §2.3 defines **7 pathways over 48 biomarkers**.
The engine scores **23**, and four published pathways do not exist in it at all:

| published pathway | w | n | in the engine |
|---|---|---|---|
| Metabolic | 0.20 | 10 | 4 of 10 (no Creatinine, Chloride) |
| **Endocrinology** | **0.15** | 6 | **absent** |
| **Digestive** | **0.12** | 10 | **absent** |
| **Immunological** | **0.11** | 7 | **absent** |
| Hemolytical | **0.22** | 13 | as `Hematologic` at **0.15**, 9 of 13 |
| Bone Formation | 0.10 | 7 | as `Bone_Mineral` at **0.15**, 4 of 7 |
| **Neurological** | **0.10** | 6 | **absent** |

The four absent pathways carry **0.48 of the published weight — nearly half the
construct.** The engine instead invents `Cardiovascular`, `Nutritional`,
`Dialysis_Adequacy` and `Inflammatory`, which appear nowhere in the paper, and
gives the heaviest published pathway (Hemolytical 0.22) the third-largest weight.

**All 28 missing analytes are ALREADY IN THE DATABASE** — nothing is blocked on
collection:

    Creatinine, Chloride, Vitamin D, HbA1c, Total Protein, Cholesterol, HDL,
    LDL, Triglycerides, ALT, AST, B12, Folate, Neutrophils, Lymphocytes,
    Monocytes, Eosinophils, Basophils, Platelets, MCH, MCHC, TIBC,
    Reticulocyte, Vitamin D (again), ALP, Magnesium, Magnesium (again), B12

The four Hemolytical gaps — **MCH, MCHC, TIBC, Reticulocyte** — are exactly the
markers §18's iron worked-example needed and could not reach.

> ⚠️ **Do NOT restore these into the scalar engine as a first move.** Four more
> pathways of independently-scored scalars collapsed by a weighted mean is more
> of the thing 18a-18f says is wrong. Settle the representation first.

### 18h. "tensor of tensors of tensors" — the representation, in the operator's words

> *"omega cannot be derived from scalars. it is a multi-dimensional vector
> (tensor)"*

> *"every pathway constitute amulti-dimensional pathway and the human sysytem is
> a tensor of pathways so we are dealing with tensor of tensors of tensors"*

**The published paper's own results support this and measure the loss.** §3.1:
PCA on the 7-pathway score matrix needed **4 components for 90% of variance**
(PC1 only 42.2%), and H1 (Decomposability) was REJECTED — *"at least four
independent health dimensions exist."* So Ω, one number, is a projection of a
≥4-dimensional object, and the paper quantifies how much it cannot carry. §3.1
also measured **Bone Formation ↔ Endocrinology r = 0.85** — the coupling through
shared Ca, PO₄, PTH and Vitamin D — and the implementation deleted Endocrinology,
so the strongest measured coupling in the framework is not even observable.

What each level actually holds, against what the engine keeps:

| level | the object | what `trapezoidal_score`/`pathway_score` keeps |
|---|---|---|
| **0 · marker** | value, unit, band, provenance (pre/post/fasting), assay, Δ since last, time since last, uncertainty | one float in [0,1] |
| **1 · pathway** | markers × time × their regulatory relations — 25(OH)D → 1,25(OH)₂D → Ca absorption → PTH suppression → PO₄ handling is a directed graph with lags, not a bag of seven numbers | one weighted mean |
| **2 · system** | pathways × their measured coupling (|r| = 0.122 mean, 0.85 Bone↔Endocrine) ≥ 4 independent dimensions | one scalar Ω |
| **— · drive** | exposure E[drug, dose, time], nutrition, dialysis and elimination losses | nothing at all |

**The reduction happens too early, and that is the core defect.** Once Ca is 1.0
and PTH is 0.067 the Ca×PTH relationship is unrecoverable; no aggregation chosen
afterwards can put it back. A tensor formulation keeps the axes and contracts
LAST, reporting Ω as one projection beside the structure rather than instead of
it.

### 18i. The within-pathway change is a CORRECTION, not a deviation

Operator, 2026-10-12: *"the paper can be erronous"* / *"we are attempting to
correct much of the fallacies in the paper"* / *"the paper was reductive but the
human sysytem is broader in scope"*. **The paper is therefore not the
authority — it is one of the things being corrected.** This section was first
written as "a deviation I introduced, for the operator to rule on"; that framing
was wrong and is kept visible rather than silently replaced.

OPEN_ITEMS 27 changed the within-pathway aggregation from arithmetic to
geometric. The published §2.5 specifies a weighted ARITHMETIC mean
(`O_p = Σ w_b·O_b / Σ w_b`), so it departs from the paper — and it departs from
it because **the paper's stated justification for the between-pathway product is
unreachable under the paper's own within-pathway formula.**
§2.5 argues for the product because *"a near-zero score in any single pathway
drives the overall score toward zero … uncontrolled hyperkalemia (Metabolic = 0)
poses immediate mortality risk irrespective of excellent bone health."* But
Metabolic holds 10 biomarkers, so with equal within-pathway weights a potassium
scoring 0 moves Metabolic to 0.9 and Ω by 0.9^0.20 ≈ **0.979 — about 2% for a
lethal potassium.** `Metabolic = 0` cannot occur.

So the change serves the paper's stated INTENT by correcting its stated
FORMULA. The engine and the paper now disagree, deliberately; §18j is the list
of what else needs correcting.

Also deviating, and pre-existing: the paper's aggregation is the weighted
PRODUCT `∏ O_p^{w_p}`; the engine computes the weighted GEOMETRIC MEAN
`exp(Σ w ln s / Σ w)`. These coincide when all seven pathways score (Σw = 1.00)
and diverge whenever one is missing — the geometric mean renormalises over what
remains and so **inflates** Ω, which with four pathways absent is doing
substantial work.


### 18j. Fallacies in the published paper, measured

Operator: *"the paper can be erronous"*, *"we are attempting to correct much of
the fallacies in the paper"*, *"the paper was reductive but the human sysytem is
broader in scope"*. Each item below is evidenced from the paper's own text or
from the record — not asserted.

**F1 — AUC = 1.000 is label leakage, and the paper reports it as validation.**
§3.7 publishes **8 of 10 classifiers at AUC ≥ 0.999** and glucose regression at
**R² = 1.000**. Every one of those targets is, by §2.7.2's own definition
table, a **same-day threshold on a feature that is inside the 141-feature
input**:

    Low hemoglobin       Hemoglobin < 10        AUC 1.000
    Hypokalemia          post-dialysis K < 3.5  AUC 1.000
    Low calcium          Calcium < 8.5          AUC 1.000
    Calcification risk   Ca×P > 55              AUC 1.000
    High PTH             PTH > 600              AUC 0.999
    Hypotension          post-systolic < 90     AUC 1.000
    Glucose level        (the glucose value)    R²  1.000

The models restate their input. They carry **no lead time at all**, so nothing
built on them can answer a question about cause or about what comes next. §3.7's
own SHAP paragraph corroborates the leak without naming it — *"intradialytic
blood pressure statistics … among the top predictors"* for a target defined by
intradialytic blood pressure.

> **The paper contains its own control.** The one target that is NOT definable
> from an input feature — post-session vomiting, an event 12 hours later —
> scores **0.842**. That is what a real model looks like here. The gap between
> 0.842 and 0.999 is the leak, measured by the paper itself.

(§3av recorded this independently from the notebooks in 2026-10-02; this is the
same finding in the publication.)

**F2 — the motivating example cannot occur under the formula it motivates.**
See §18i. `Metabolic = 0` for uncontrolled hyperkalemia is unreachable when
Metabolic is a 10-biomarker arithmetic mean; the real move in Ω is about 2%.

**F3 — §2.4 sanctions a function that asserts perfect health.** *"For
biomarkers with only an upper limit … the function reduces to a right-
trapezoidal or monotonically decreasing form."* Under the published piecewise
`O_b(x)`, that returns **1.0 for the entire low side**. Operator: *"high or low
rdw are not sign of health. one suggests hemolysis or worse."* Measured on the
record: RDW 0.1 scored 1.000. Fixed in the engine (`closed_band`); the paper
still specifies the defect.

**F4 — the paper's own §3.1 contradicts the sufficiency of a scalar Ω.** PCA on
the 7-pathway matrix needs **4 components for 90% of variance** (PC1 42.2%), and
H1 is REJECTED: *"at least four independent health dimensions exist."* A single
number is then reported as the construct. The paper measures the loss and does
not account for it.

**F5 — reductive scope.** 48 laboratory analytes, one timepoint each. No
exposure (drug, dose, timing), no nutrition, no elimination, no derivative — and
"electro-" and "neuro-" appear in the construct's own definition with nothing
measuring them. The strongest coupling the paper found (Bone↔Endocrine
r = 0.85) is left as a correlation rather than modelled.

**F6 — cross-platform agreement is not correctness.** §3.8 reports MATLAB and
Python agreeing at r = 1.0000. That validates reimplementation fidelity. Two
implementations of the same formula agreeing perfectly says nothing about
whether the formula is right, and it is cited in the Discussion as if it did.

> ⚠️ **F1 is the one that must not be repeated in the product.** §18e already
> says fitting shapes or weights needs a non-tautological outcome. The paper
> demonstrates exactly what happens without one, at AUC 1.000, in print.

---

## 19. "Chat with Alafia" — TELL performs, ASK answers

> ✅ **19a and 19b are done, 2026-10-14.** The rename shipped across web, iOS
> and Android (OPEN_ITEMS 43), and the gap it opened was closed the same day:
> elimination, mood, sleep, symptoms and activity have gated write tools, and
> the write gate — which had NO READER — is wired and fails closed
> (OPEN_ITEMS 44). **19c and 19d remain**: Ω and Α are still unreachable by the
> assistant, and nothing has yet confirmed a real model calls the new tools.


Operator, 2026-10-13, verbatim:

> *"change AI prompt message to "Chat with Alafia". This is more
> representative. So user can tell (prompt for action) or Ask (query for
> information). Tell call tools to "actually" perform tasks such as log
> medication, elimination, food, mood, and anything else that is actionable.
> Ask uses user's data as foundation to offer user spicific/tailored precision
> response."*

**Why the rename is not cosmetic.** The entry point is labelled `Ask ALAFIA`
(`Layout.ask_alafia`, web sidebar and two more catalog entries), and that label
is an accurate description of what the surface can mostly do — which is the
problem. §3am already records the failure it caused: asked to *"log this meal"*
the assistant answered *"I don't have the ability to log meals into your
record"* and handed the work back, holding the meal, the times and an explicit
instruction. `log_meal` and `log_medication` were opened afterwards; the NAME
still says the assistant only answers.

### Measured 2026-10-13 — what TELL can actually do

    WRITE_TOOLS   log_meal, log_medication                         2
    READ tools    get_meals, get_medications, get_eliminations,
                  get_vitals, get_labs, get_surgical_history       6

Loggable domains with an API and **no write tool**: `elimination`, `mood`,
`sleep`, `symptoms`, `vitals`, `fitness`. The operator names elimination and
mood explicitly, and both are read-only to the assistant today — it can tell a
patient what their eliminations show and cannot record the one they just had.

### 19a — the label, everywhere it appears

`Layout.ask_alafia` in eleven web locales, plus iOS and Android. One string per
platform, but §3aw's guard means all ten translations move with it, and the
catalog test fails if they do not.

### 19b — TELL: finish the write surface

Per §3am's existing rules, which already govern `log_meal` and must govern the
rest:

- **Only what the patient named**, in their words and quantities — no adding,
  rounding or completing.
- **A repeat call does not double-count.** A tool loop retries; a duplicated
  meal doubles a day's nutrients. Each write returns `already_logged` with the
  original id.
- **Every written value states its provenance**, so a figure the patient never
  spoke cannot read as one they did.
- **Inference proposes; it never writes.** No dose stated and none in history →
  nothing is written, and it asks (§3aj).
- **The patient's date, not the server's** — `patient_today` threads through
  the loop into the write (§3am).
- ⚠️ **Vitals and labs stay READ-ONLY**, deliberately. A blood pressure or a
  lab value spoken into a chat and stored as measured is a clinical record
  nobody took. `WRITE_TOOLS` is the declaration, and widening it is a decision,
  not a convenience.
- Each new writer touching a §3aa-guarded model needs its `ALLOWED` entry with
  a stated reason, or `test_clinical_sources` fails the build.

### 19c — ASK: the data is the foundation, and mostly is already

The tool loop exists and works (§3am): the model asks for rows and reasons from
them, rather than the backend guessing the question. What is NOT yet true of
"user specific / tailored precision":

- **Ω and Α are not reachable by the assistant.** There is no tool returning
  the wellness or management score, its pathways, or its findings — so "how am
  I doing?" is answered from raw rows while the product's own composite sits
  unseen.
- **Surgical history, hospital stays and declared therapies** are partly
  wired (`get_surgical_history`) and partly not.
- **The patient's own goals** (`compute_goals`, with the cited quotas of §3bc)
  are in the framing prompt but have no tool, so a question about a specific
  nutrient target cannot fetch its authority.

### 19d — the two modes must not become two code paths

One loop, one provider order, one redaction point. §3am records what two copies
cost: `stream_chat` was implemented BESIDE `stream_events` and the Anthropic
streamer silently dropped every `role="tool"` message on the path the product
actually uses, while the fix sat in `chat()` next door. TELL and ASK are a
difference in what the model decides to call, not a fork in the code.

---

## 20. The therapy axis has no consumer — a switch nothing scores

> ✅ **20a, 20b and 20d DONE 2026-10-14.** Α reads `condition_therapies`, the
> dates are collected on all three clients, and the navigation re-asks. Detail
> and verification: **OPEN_ITEMS 41**. **20c and 20e remain**, and 20e is a
> decision rather than work — see the note at the end of each.


Raised by the work in OPEN_ITEMS 39, 2026-10-14. The switch's stated purpose,
in the operator's own words, is *"a comprehensive list with items zeroed out
(no impact) when not present"* — i.e. **an axis with the same dimensions for
every patient**, most of them zero, so that two records are comparable. That
is built. Nothing reads it.

### 20a — Α must read `condition_therapies` ✅ DONE

`compute_alpha` resolves indications from conditions and measures them against
labs. A patient's declared therapies are the other half of management: being ON
dialysis, transfusion and IV iron is what Α's targets are a function of, and a
patient who states they are NOT on a therapy their condition normally indicates
is a finding, not a gap. Today Α cannot tell those apart because it never looks.

> A stated zero must not be scored as a failure. "Not on erythropoietin" is a
> fact about the regimen, and whether it SHOULD be is a clinical judgement
> (§3an). The axis reports; the scoring question is which cells are evidence
> about management and which are evidence about nothing.

### 20b — a therapy that STOPPED ✅ DONE

`started_on` and `ended_on` exist in the table and on the API and **no client
collects them**. So "I came off PD in March" can only be said by flipping a
switch to false, which loses the date — and the date is exactly what makes a
history interpretable. Needs a date field on all three clients, and a decision
about what `receiving=false` WITH an `ended_on` means versus without one.

### 20c — `regimen` is free text, deliberately, and that bounds 20a ⏳ OPEN

Two patients on the same compound will spell it differently, so grouping is
per-patient and nothing aggregates across records. That is the right call for
now — a controlled vocabulary of regimens is a clinical claim and WHO does not
publish one (checked: the QB branch codes therapies, not combinations). But any
cross-patient use of compounding needs that resolved first, the same
resolve-cite-store shape as §3bc's quotas.

### 20d — the navigation does not re-render ✅ DONE

37b, 38c and 39b are one bug and it is now the most visible one: the nav
fetches `/users/me/surfaces` once on mount, so a patient who states *"not on
this"* watches the screen they just retired stay on screen until they reload.
Three clients, one fix each — refetch surfaces after a condition or therapy
write, or have the write response carry the new surface set.

### 20e — a non-coded therapy ⏳ OPEN — an operator DECISION, not work

Phototherapy and generic infusion therapy have **no Q code** (measured, 38a),
so they cannot be declared at all, and the hand-typed enum this replaced could
express them. The fix is a decision about whether a non-coded therapy may be
declared beside coded ones — and if so, how it is stored so it can never be
mistaken for a WHO code (§3ad). Not a silent re-addition of the list.

---

## 21. Nutrition believability must stand on FACT or HISTORY — never on typed numbers

Operator, 2026-10-20, on finding that plain tea was refused against a
"tea_coffee" band of 22-110:

> *"Who created this band? is that from FDA or something we made up from our
> model? tea is not coffee and not all tea or coffee are even same thing."*
> *"FDA lookup checking the first 'tea' is irrational, if there are 100 tea
> lower in rank but number 70 is a better fit. Lookup must be intelligent, not
> first seen."*
> *"hand written is even worse because it is made up not based on history or
> fact."*

The energy check is **done** (§54b in OPEN_ITEMS): the expectation is now the
spread of the authority's own entries for the name, and where the authority is
silent nothing is rejected on energy. What follows is the rest of the same
principle, none of it started.

### 21a. HISTORY is the other half, and it is unused

The operator's sentence names two sources: *fact* and *history*. Only fact is
wired. `learned_food_nutrients` already holds what THIS record has established
about a food, and it is the only thing that can judge a dish no public
catalog knows:

    suya 589 kcal/100 g (a peanut mismatch)  — USDA holds no entry for suya,
      so there is no range and nothing refuses it. The old typed `fatty_meat`
      band (200-420) caught it, by luck rather than by evidence.

A learned row for this patient's suya IS a fact about this patient. Comparing a
fresh estimate against it is the fix, with the same rule as everywhere else:
**only refuse what the evidence contradicts**, and say nothing when there is no
evidence. This also gives the system a way to IMPROVE — every confirmed meal
tightens its own expectations, which a typed table can never do.

### 21b. The remaining typed numbers in `nutrition_reference`

`_CATEGORIES` still supplies `serving` grams and plausible `units` per
category, used by `typical_serving_g` and `validate_parse`. Those are typed
too. The portion ceiling (`max(2000, typical × 15)`) is a second invented
figure sitting on top of the first. They were not touched because the operator
asked about the BAND and because a portion default is a different kind of
claim from a believability verdict — but the same question applies, and the
answer is probably the authority's own serving sizes plus this record's own
portion history.

### 21c. A category is cached once and never revisited

`food_category_cache` fills the first time a name is seen and is never
re-examined, which is why *"numb earl grey tea"* is permanently **dairy**. A
category learned from one bad match is a fact about nothing, and it outlives
every improvement to the matcher.

### 21d. The parser still prices words that are not food

`carton`, `pasteurized`, `nonfat` all became components with grams and
calories. No band can save a system that is pricing adjectives; this belongs
in the splitter, not in the guard.

### 21e. Where a value is UNJUDGED, say so

The change in §54b means many values now pass with no check at all. That is
honest and it is invisible: nothing distinguishes "checked and sound" from
"nobody could check this". `nutrients_excluded` gave partial totals a voice
(§54a); unchecked components have none yet.
