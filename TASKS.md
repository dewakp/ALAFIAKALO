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
