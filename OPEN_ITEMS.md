<!-- Copyright © 2026 Wole Akpose / 6igma Health Inc.
     All rights reserved. ALAFIA — proprietary and confidential. -->

# Open items

Raised and **not yet resolved**. Everything here was found or requested during a
working session and deliberately not actioned — either because it needs a
decision that is not mine to make, or because it was out of the scope being
worked at the time.

The rule: nothing leaves this file because it got old. It leaves when it is
done, or when it is explicitly declined with a reason.

Status: `OPEN` · `NEEDS DECISION` (blocked on a product/privacy call) · `DONE`

---

## 1. Clinical correctness of AI answers — LARGELY ADDRESSED by item 2a

Raised 2026-08-29 from a real answer in the AI Health Assistant.

Asked whether a meal was safe, the assistant told a dialysis patient to **skip
the plantain** because ~430–450 mg of potassium "exceeds the 2-day target
(≈200–300 mg)".

**That limit is fabricated and roughly 10x too strict.** CLAUDE.md §3ac:
KDOQI is **2,000–3,000 mg/day**, and that figure is already the one for a
patient on dialysis. 430–450 mg is 15–20% of a day's allowance — an ordinary
meal. The advice to drop a staple food was built on a number the model invented.

It also conflates **lab values with dietary intake**, repeatedly:

| In the answer | What it actually is |
|---|---|
| "Sodium 145 mg on 2026-08-26" | serum sodium 145 **mmol/L**, not dietary mg |
| "phosphorus is 4.8 mg/dL … target <1,200 mg/day" | a serum level compared against a *dietary* target |

And it is self-contradicting: opens with a concern, analyses the meal as
acceptable, closes with the concern again.

What it does NOT use, though the platform holds all of it: the last dialysis
session (§3ac — a treatment changes the day's totals), current nutrient totals,
elimination, or medication history.

Not a prompt-tuning problem. The model is being handed a context that does not
distinguish a lab result from an intake, and no grounding that a limit is a
limit. See also item 2.

## 2. The App Review answer does not match the code — FIXED IN CODE, not yet deployed

`APP_REVIEW_RESPONSE.md` tells Apple, under Guideline 2.1:

> "ALAFIA routes AI requests to established third-party model providers
> (**currently Anthropic**, with OpenAI, DeepSeek and Moonshot configured as
> fallbacks). We also run our own inference servers, which serve as a
> **fallback**."

For the AI Health Assistant — the flagship AI surface — that is **inverted**.
`/ai/chat/stream` calls Ollama directly and always; Anthropic is never reached.
Verified in production: every provider call in a 3-hour window went to
`alafia-ollama…/api/chat`, `gpt-oss:20b`. Zero Anthropic, OpenAI or DeepSeek
calls, with all three keys mounted.

The non-streaming paths DO use the router, so the statement is true of them. It
is the chat that contradicts it.

§3al is explicit that this is the failure mode to avoid: *"Every user-facing
claim … states third-party processing plainly. They were all rewritten once
already … When the data path changes, the copy is part of the change."* Here the
copy was written ahead of the code instead.

### The landmine underneath it

`ai.py` contains **no reference to the privacy scrubber** — no import, no
`scrub_pii`, no `try_hosted`. The chat assembles context that begins:

```python
lines.append(f"Name          : {user.full_name}")     # ai.py:1095
```

…and posts it raw. Today that is acceptable: Ollama is ALAFIA-operated
infrastructure, so the patient's identity has not left our systems, exactly as
§3al allows for `local_only`.

**But it means the second answer to Apple — "No personal data is sent. The user
is never identified to a provider" — holds today only because chat never reaches
a third party.** Point this function at Anthropic to make the first answer true,
without routing through `try_hosted()`, and the patient's real name goes to a
vendor and the second answer becomes false.

So the two claims are currently kept honest by the very bug we are trying to
fix. Any migration MUST go through the router's egress point, never by swapping
the URL in `token_generator`.

## 2a. `/ai/chat/stream` bypasses the provider chain — DONE

The chat endpoint bypasses the ALAFIAModel router and calls Ollama directly. Its
own comment says so ("the one LLM path still calling Ollama directly … the
router has no streaming capability yet"). `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`
and `DEEPSEEK_API_KEY` are all mounted in production and none is used for chat.

Measured 2026-08-29: every AI call went to `alafia-ollama…/api/chat`. Cold
18.3s (the GPU service sleeps, §5), warm ~2.2s.

Migrating it changes which vendor sees patient text, so it also touches the
§3al egress story and the consent copy.

## 3. AI chat has no client timeout — OPEN, small

`AIChat.jsx` calls `fetch('/api/v1/ai/chat/stream')` with no `AbortController`
and no timeout, so §3ae's ladder (client 285s < OLLAMA_TIMEOUT 290s < Cloud Run
300s) is bypassed. A stalled stream hangs forever with no error — an empty
assistant bubble and no way to know it failed. There is also no "thinking"
indicator, so an 18s cold start is indistinguishable from a hang.

## 3a. AI answers render as a wall of text — DONE

`AIChat.jsx:458` renders `{msg.content}` as raw text. The model replies in
markdown — bold, bullets, and a full `| What | Why it matters |` table — and all
of it is dumped verbatim, pipes and dashes included. No markdown renderer exists
anywhere in the frontend.

Two halves, and both are needed:

- **Render it.** Bold, headings and bullets should display as such.
- **Stop asking for tables.** A multi-column markdown table cannot fit a narrow
  chat bubble even when rendered. The answer format should suit the surface.

## 4. `ai_engine` crashes for anyone with an active prescription — FIXED 2026-08-29

`_get_current_medications` reads `m.medication_name`; the `Medication` model has
`name`. `AttributeError`, so `/personalization/health-score` **500s** for any
user holding an active prescription. It currently appears to work only because
the reference account has none — and `POST /medications/promote-logged` creates
exactly those rows, so using that feature breaks the health score.

§3ag's static guard was built to catch this class and missed it: its regex
`\b([A-Z][A-Za-z]+)\.([a-z_]+)\b` matched class-level references
(`Medication.is_active`) but not instance reads (`m.medication_name`).

Fixed: `m.name`, plus an AST check in
`tests/test_ai_endpoints_availability.py` that resolves each loop variable back
to the model its `db.query()` named and verifies every attribute read off it.
It refuses to run vacuously — it asserts it resolved at least 20 reads, so a
resolver that silently stops tracking fails instead of passing.

## 4e. Classification is a lookup now, not a keyword guess — 2026-08-30

Raised directly: *why is there a hardcoded fruit search keyword outside a
learning model?* There should not be, and there no longer is.

`classify()` decided a food's plausibility band and default portion by matching
its NAME against a hand-written keyword list — spelling, not knowledge. USDA
FoodData Central publishes a `foodCategory` for every food it holds and we were
**discarding the field**.

`services/food_category_service.py` implements the loop:

    know it?  food_nutrient_cache.band_category, written by an earlier run
    check     USDA generic (Foundation / SR Legacy / FNDDS)
    check     USDA Branded — packaged foods absent from the generic tables
    store     written back to the cache row with the authority's own wording
    learn     every later meal with that food resolves without a lookup

Keywords survive only for foods no authority knows, recorded as
`category_source="keyword"` so a guess is never mistaken for a lookup.
Migration `ss001_food_category`.

Measured on the reported dinner:

| food | keyword said | now | via |
|---|---|---|---|
| `ripe plantain boiled` | unknown (was oil_fat) | **fruit_fresh** | usda |
| `hard boiled eggs` | egg | **egg** | usda |
| `cherry tomatoes` | vegetable | **vegetable** | usda |
| `pitted olives` | unknown | **vegetable** | usda |
| `black teabag` | unknown | **tea_coffee** | usda Branded |

**`black teabag` was the case that proved the point** — no generic USDA entry
exists, and the Branded catalogue answers it directly with `foodCategory:
"Tea Bags"`. The generic tier alone would have left it unknown forever.

Two matching rules were needed to stop confident wrong answers, both measured
rather than assumed:

- **Preparation words are ignored on the query side.** Boiling a plantain does
  not stop it being a fruit, and keeping "ripe"/"boiled" left one shared token
  in five against "Plantains, green, raw" — the right answer rejected as
  coincidence.
- **A colour cannot carry a match.** "black teabag" scored 50% coverage against
  "Olives, black" on the word "black" alone and was filed as a vegetable.
  Colours are dropped from the QUERY only, so "Beans, black" still answers a
  query for black beans.

### The band itself now comes from the food, not its category

Wiring the above surfaced a real limit: USDA files olives under "Olives,
pickles, pickled vegetables", and olives are ~289 kcal/100 g against a
`vegetable` band of 8-130 built for lettuce. A correct estimate was reported as
a wrong match.

A category band is a coarse stand-in for a figure we can simply look up.
`reference_kcal_per_100g()` takes the matched USDA food's own energy and
`plausibility.review()` prefers it, falling back to the band only when no food
matches. The dinner now estimates with **no warnings at all**.

> **What is still a table, and why.** `_USDA_TO_BAND` bridges USDA's ~30
> published food categories to our band names. That is a taxonomy bridge
> between two authorities — the same shape as ICD-10 ↔ ICD-11 — and no food
> appears in it. The per-food keyword list is what has been demoted to last
> resort.

## 4i. Ultrafiltration: the weights were never the source — 2026-08-30

Two corrections, both clinical, both mine to have got wrong.

### A session CAN have negative net fluid

I rejected `fluid_removed_ml = -1000` as a data fault. It is not: **saline goes
back into the patient** — boluses for intradialytic hypotension, and the
rinse-back at the end. That is **365 of 1775 sessions here (21%)**, and the 1st
percentile of the whole distribution is -1426 ml. Routine.

It belongs in the arithmetic too: returning fluid makes Daugirdas' convective
term `(4 - 3.5R) x UF/W` negative, which lowers Kt/V — correctly, because saline
returned is clearance not delivered. The 2025-01-27 session now computes 1.24
instead of being silently dropped.

### -59,800 ml is garbage, and the weights are where it came from

`fluid_removed_ml` is exactly `(pre - post) x 1000`, so it inherits every
weighing error:

| date | pre kg | post kg | fluid ml |
|---|---|---|---|
| 2018-12-09 | 61.2 | **0.3** | 60900 |
| 2018-08-24 | **4.7** | 64.5 | -59800 |
| 2018-07-14 | **3.5** | 62.4 | -58900 |

A 0.3 kg post-dialysis weight is not a person. **Nothing validated these
fields** — the schema was `Optional[float] = None` — and the damage is live: the
clinician dashboard averages `fluid_removed_ml`, so it reports **608 ml against
a true 663 ml**, with nine rows of garbage inside the mean.

`TherapySessionBase` now bounds both weights and cross-checks fluid against the
patient's own body mass in both directions. These are PHYSICAL plausibility
bounds — is this a human being — not clinical reference ranges, which are
resolved from reported data (§4h).

### UF is machine removal minus saline, not pre-minus-post weight

The instruction, and it is right. `intradialytic_readings` holds both:
`uf_volume_removed` and `saline_amount`.

Two traps in reading them:

- **`uf_volume_removed` COUNTS DOWN.** It is the volume still to remove, despite
  the name — verified across the record, **6,423 reading-to-reading transitions
  decrease against 166 that rise**. So what came off is `first - last`; taking
  `max()`, as my first attempt did, reads the target rather than the result and
  gave a mean UF of 3 ml.
- **`saline_amount` is free text** — "100 ml", "100 mL", "20 ml", "~". A tilde
  means "some, unspecified" and must not become a zero: absent is not
  none-given. Return is capped at 2 L, beyond which the entry is a
  transcription error.

Measured across 362 sessions with derivable readings:

| source | mean net UF |
|---|---|
| machine removal minus saline | **+0.87 L** (median +0.80) |
| pre-minus-post weight | **-0.02 L** — noise |

Kt/V now takes the readings-derived figure, falling back to `total_uf_liters`
and only last to the weight-derived one.

`tests/test_dialysis_weight_validation.py` (8) and the UF cases in
`tests/test_urea_kinetics.py`.

> ✅ **Cleaned in production 2026-08-30**, `scripts/db/cleanup_impossible_weights.sh`
> (dry-run by default; the dry run executes the identical statements and rolls
> back, so what it prints is what `--apply` writes).
>
> It found **10** rows, not the 9 previously reported: id 869 carries a
> pre-dialysis weight of 6.9 kg with no fluid figure, which a fluid-based count
> missed. The weights and the fluid derived from them are set to NULL — the
> SESSION stays, because the treatment happened and only the weighing was wrong.
>
> Selection is by physiology, using the same bounds `TherapySessionBase` now
> enforces on the way in, so it cleaned exactly what the validation would refuse
> today. Verified by reading the rows back, not by the COMMIT line:
> **0 impossible weights remain**, and the clinician dashboard average is
> **663.2 ml** where it read 608.2.

## 4h. Clinical thresholds are DATA now — CANON 2026-08-30

Stated as canon: **no hardcoded data, no exception.** At the scale this runs at,
a constant is not an approximation — it is wrong for most patients. The evidence
was already in this one record:

| HEBCS constant | what the patient's lab reported |
|---|---|
| Albumin `4.0 - 5.0` | **3.2 - 4.8** |
| Potassium `3.5 - 5.5` | **3.5 - 5.1** |
| BUN — briefly `21` | **9 - 23** (and 21 is the adult FEMALE ceiling, on a male) |

Every trapezoid bound lived as a constant in `hebcs_engine`. Resolution is now,
most specific first:

1. the range **this patient's lab reported** (`lab_results.reference_range_*`)
2. the range **most commonly reported for that analyte** across the population
3. a row in **`clinical_thresholds`** — guideline targets, for the values a lab
   never prints a range for (Kt/V, URR, Ca×P), each carrying its `source`
4. a range **LEARNED from the central 95% of observed values**, written back to
   `clinical_thresholds` so the next request is a lookup, not a recomputation
5. only then, nothing

**"Unscored" was the wrong answer** — the correction was: *look it up and learn
it.* If an analyte has been measured enough times, the central 95% of observed
values IS a reference range; that is how reference ranges are established, and
it improves as patients arrive rather than going stale like a constant. No step
invents a number.

> ⚠️ **A range must come from many PATIENTS, not many observations.** 20 draws
> from one person describes that person's disease, not a population. Without
> that guard this database would have adopted **21 ranges from a single dialysis
> patient's values** as everyone's normal — measured, by relaxing the guard to
> see what it prevents. With it: zero learned here, correctly, because there is
> one patient's labs. At scale it is where the ranges come from.

### Kt/V and URR are calculated, not looked up

Also corrected: these are computed, and the lab reports them only when it
chooses to — 6 of 12 dates on this record. Both come from the two BUN draws the
lab does report, plus the session:

    URR  = (pre - post) / pre x 100
    Kt/V = -ln(R - 0.008t) + (4 - 3.5R) x UF/W        (Daugirdas 2nd generation)

Validated against every date holding both the inputs and a reported value —
the point of computing something you can check:

| date | Kt/V computed | reported | URR computed | reported |
|---|---|---|---|---|
| 2025-10-16 | 1.61 | 1.62 | 73.8 | 74 |
| 2025-11-03 | 1.34 | 1.35 | 70.0 | 70 |
| 2026-01-05 | 1.44 | 1.44 | 73.1 | 73 |
| 2026-04-08 | 0.90 | 0.90 | 55.7 | 56 |

It then fills dates the lab never reported (2025-05-16 → 1.37, 2025-06-16 →
1.52), and **refuses** where the data is faulty: 2025-01-27 carries
`fluid_removed_ml = -1000`, and a session cannot remove negative fluid.

`services/reference_ranges.py` does the resolution; `clinical_thresholds`
(migration `tt001`) holds the guideline targets, seeded FROM the published bands
so the migration is behaviour-preserving. Correcting a threshold for a lab, a
population or a guideline revision is now a row change, not a deploy.

**Measured on the reference record: 26 of 26 scored biomarkers resolve from
data, none from a source constant.** Omega moves 69.45 → 65.51 and Hematologic
0.83 → 0.54, because the patient's own haemoglobin range is stricter than the
constant was.

Each biomarker reports `band_source` — `"reported"` or `"published_band"` — so a
constant can never pass for a range someone measured, the same way `source`
distinguishes measured from derived values (§4g).

`tests/test_no_hardcoded_thresholds.py` (6) fails the build if the ordering is
broken, if a seeded threshold has no provenance, or if the population range is
allowed to beat the patient's own.

> **Why the data can carry this:** 63.5% of `lab_results` rows already report a
> reference range, covering 120 of 219 analytes. The ranges were there the whole
> time; the engine was ignoring them in favour of its own numbers.

## 4g. nPCR was never reported, so it is now derived — 2026-08-30

The gap flagged under §4f: nPCR carries **40% of HEBCS's `Nutritional`
pathway**, and the lab prints it as `N/A` on **all seven dates** it appears —
the row exists, with unit `G/KG/D`, and no value. Not a parser fault: the lab
never measured it. So that pathway has scored on albumin and BUN alone, at 60%
coverage, for the patient's entire history — and read **100%**.

It does not need to be measured. Every input is already in `lab_results`, and
`services/urea_kinetics.py` computes it from urea kinetics (Daugirdas
second-generation, mid-week):

    nPCR = C0 / (36.3 + 5.48·Kt/V + 53.5/Kt/V) + 0.168

with C0 the **pre**-dialysis BUN and Kt/V the delivered spKt/V. Derived across
the record:

| date | pre-BUN | spKt/V | nPCR |
|---|---|---|---|
| 2025-08-18 | 98 | 1.61 | 1.42 |
| 2025-10-03 | 78 | 1.50 | 1.14 |
| 2025-10-16 | 84 | 1.62 | 1.24 |
| 2025-11-03 | 80 | 1.35 | 1.13 |
| 2026-01-05 | 52 | 1.44 | **0.81** |
| 2026-04-08 | 70 | 0.90 | **0.86** |

The last two sit below KDOQI's 1.2 g/kg/day target — **a falling protein
intake**, tracking the Kt/V decline found in §5a. `Nutritional` for the latest
draw moves from **1.0 on 60% coverage** to **0.89 with full coverage**.

### Derived is scored, never counted as measured

- Each biomarker carries `source`: `"measured"` (a lab reported it) or
  `"derived"`. A computed marker must never reach a clinician as though a lab
  had reported it.
- `coverage` keeps meaning *what was reported*; `coverage_with_derived` is
  reported alongside it rather than replacing it.
- `NpcrEstimate.describe()` renders the provenance in one line: *"0.86 g/kg/day
  — estimated from pre-dialysis BUN 70 mg/dL and spKt/V 0.90, not measured"*.
- **Out-of-range or missing inputs return None, never a fallback number.** A
  fabricated nutritional marker is worse than a missing one, because it would be
  scored as though it were real.
- The **pre**-dialysis BUN is used deliberately, while §4f made the BUN
  *biomarker* prefer the post draw. Different questions: intake vs clearance.

> ⚠️ **Two assumptions travel with the estimate.** The equation assumes a
> thrice-weekly schedule sampled mid-week; this patient dialyses roughly every
> other day (~4 distinct session days/week), so it is approximate. And it shares
> an input with Kt/V, so the two are not independent readings — a falling Kt/V
> drags the estimate with it, which is clinically real but worth knowing when
> reading them side by side.

`tests/test_urea_kinetics.py` (13).

## 4f. BUN: two wrong bands before the right one — FIXED 2026-08-30

Raised directly, and correct: `Biomarker("BUN", crit_low=None, opt_low=0, …)`
meant `trapezoidal_score` returned **1.0 for any BUN from 0 to 80**.

BUN appears in exactly one pathway — `Nutritional` — so it is read as PROTEIN
INTAKE, not clearance. In a patient whose kidneys are not clearing urea, a low
BUN means little protein is being eaten. Producing almost no urea is starvation
scored as health.

**Three wrong bands preceded the right approach**, each caught on review:

| band | claim it made |
|---|---|
| `crit_low=None, opt_low=0, opt_high=80` | any BUN 0-80 is perfect — a BUN of 5 is starvation |
| `opt_low=23, opt_high=80` | a PRE-dialysis 70 is optimal — 70 is uraemia |
| `opt_high=23`, then `21` | named a single optimum at all |

The last was the real error, and it is conceptual rather than numeric: **no
optimal BUN is defined — there is only a range, and which range depends on the
person.** 7-20 in children, 6-21 in adult females, 8-24 in adult males, with a
tighter functional target of 10-16. Writing 21 into the engine picked the adult
FEMALE ceiling and applied it to a male patient whose lab reports 9-23.

So the engine no longer names one. `apply_reference_range()` takes the range the
**reporting lab stated on the patient's own row** as the optimal window and
scales the critical bounds with it; the static band is a general-adult fallback
used only when no range was reported, and is documented as such. `/wellness/omega`
now reads `reference_range_low/high` off each lab row and passes them in.

    fallback 7-20   lab 9-23      adult male 8-24
    21 -> 0.950     21 -> 1.000   21 -> 1.000
    24 -> 0.800     24 -> 0.957   24 -> 1.000
    31 -> 0.450     31 -> 0.652   31 -> 0.708

The data settles which draw the range applies to:

| | mean | range | lab reference |
|---|---|---|---|
| `BUN` (pre-dialysis) | **71.6** | 15-115 | 7-23 |
| `BUN Post` / `BUN-P` | **20.4-22.6** | 14-31 | 7-23 |

`resolve_biomarkers` **prefers the post draw**, with an explicit preference
rather than dict order, which had been silently deciding whether the score saw
71.6 or 22.0.

> ⚠️ **I claimed the post value "normalises — that is what dialysis is for".
> It does not.** Checked against the record: **8 of 11 post-dialysis draws are
> above 21** (17, 15, 24, 24, 22, 25, 22, 22, 24, 14, 31).
>
> **Pre-minus-post measures CLEARANCE; it does not mean the residual is safe.**
> URR and Kt/V already score the reduction in `Dialysis_Adequacy`. A session can
> hit its adequacy target and still leave the patient toxic — 2025-08-18 had
> **URR 74% and a post-dialysis BUN of 25**. The residual is what the patient
> lives with between sessions, so it is scored on its own terms rather than
> credited for the drop.

Scoring the PRE value against a normal range would mark every dialysis patient
critically abnormal for not yet having been dialysed, and would double-count
clearance — URR and Kt/V already measure that in Dialysis_Adequacy.

Measured: 5 → 0.500 (undernutrition), 15 → 1.000, 20 → 1.000, 40 → 0.779,
**70 → 0.390**, 110 → 0.000. `Biomarker` gained `low_is_deficiency` so the
intent is explicit rather than implied by a number.

> One existing test asserted `Nutritional == 1.0` for `BUN: 70` — it was
> encoding the bug. Corrected to use a genuinely normal BUN, so it still tests
> what it was written for (coverage reporting) without asserting that uraemia is
> health.

> ⚠️ **Still yours to decide:** BUN sits in `Nutritional`, but pre-dialysis urea
> is dominated by clearance rather than intake. **nPCR is the real nutritional
> marker** — and it is the one that is NULL on every row of this record (§5a).
> Whether raw BUN belongs in that pathway at all is a question about your
> published framework, not a bug I should settle.

## 4d. Nutrient list, mobile edit, and the estimator's category matching — 2026-08-30

Three asks, one thread: the diary could only ever show 15 nutrients, mobile
could not correct a meal, and the estimator judged foods against the wrong band.

### Pagination over the real catalog, not a literal in the page

`MealsDiary.jsx` rendered `MACRO_PILLS` — 15 nutrients hand-listed in the page,
with fixed colour thresholds (`phosphorus danger: 1000`, `sodium 2300`) applied
to every patient regardless of dialysis. Meanwhile the backend already held a
**116-nutrient catalog** (`NUTRIENT_CATALOG + EXTENDED_NUTRIENTS`) carrying each
nutrient's USDA FoodData Central id, and a log carries ~109 values across its
typed columns and `extended_nutrients`. Ninety-odd were unreachable, and
`GET /nutrient-catalog` existed with **no client calling it**.

- The endpoint is now paginated (`page`, `page_size`, `category`, `search`) and
  attaches **this patient's** `goal`/`goal_kind` from `compute_goals` — the same
  figures the Nutrition screen and health score use.
- `components/NutrientPanel.jsx` pages through every nutrient present on a meal,
  grouped by category, coloured against the patient's own goal. Names, units and
  categories come from the API, so adding a nutrient upstream needs no frontend
  change. Collapsed by default — a day holds several meals.

### A hand-written key map was silently dropping potassium

Found while wiring goals into the catalog. `health_score._INTAKE_KEYS` mapped
`"potassium"` → `"potassium_mg"`, but `compute_goals` **already emits
`potassium_mg`** — the same canonical key the catalog and the columns use. The
lookup missed, so potassium, phosphorus, sodium, cholesterol, iron and vitamin D
were **never scored**. The unit tests passed because their fixture invented the
short key shape the map expected.

The map is deleted; goal keys are used directly. Scored nutrients went from a
handful to **13**, and which nutrients get averaged is now derived from the
patient's goals rather than a second list. `test_health_score.py` gained a guard
that fails if the fixture drifts from what `compute_goals` actually emits.

### Mobile could not edit a meal at all

Flagged in §4c and now closed. iOS had no update call; Android's
`updateNutritionLog` was declared and never wired.

- iOS: `NutritionLogUpdate`, `vm.updateLog(id:description:)`, and a leading
  swipe action opening `EditMealSheet`.
- Android: an edit icon on the card opening `EditMealDialog`.
- Both send only the description, so the server clears the old nutrients and
  re-estimates (§4b) — and both prompt with the `0.25 x (…)` form.

### `hard boiled eggs` was classified as an oil

`classify()` matched raw substrings, and it decides both the plausibility band
and the default portion:

| food | coincidence | was |
|---|---|---|
| `ripe plantain boiled` | b-**oil**-ed | oil_fat, 700-902 kcal/100 g |
| `hard boiled eggs` | b-**oil**-ed | oil_fat, not egg |
| `broiled chicken` | br-**oil**-ed | oil_fat, not meat |
| `2 teaspoons of canola oil` | **tea**-spoons | tea_coffee |

A keyword must now **end a word**, with any prefix and an optional plural —
the line between morphology and coincidence: `peanuts` (pea+NUT+s) and
`tomatoes` (TOMATO+es) match; `boiled` and `teaspoons` do not. Requiring a whole
word lost the first pair; allowing any substring caused the second.

Declaration order still decides priority, because it encodes intent — pure
longest-match made "boost fiber chocolate" a confection and "pineapple juice" a
fruit. Only a strictly more specific phrase may displace an earlier rule, which
is what makes `peanut butter` a nut rather than the butter it contains.

Measured on the real corpus, not asserted: **28 of 571 parsed components change,
every one an improvement** — 7 variants of boiled egg, broiled chicken, broiled
oranges, `.3 teaspoon of peanut oil`, `dates` → fruit_dried. The one loss is
`black teabag` → unknown. `tests/test_food_classification.py` (18).

## 4b. A portion multiplier was ignored, and stale nutrients stayed — FIXED 2026-08-30

Reported: editing a dinner to `0.25 x (1 ripe plantain boiled, 2 eggs fried …)`
returned **identical** nutrients — 413 kcal, K 697 mg, cholesterol 372 mg.

Two independent faults, and the first hid the second:

- **`0.25 x (…)` did not parse AT ALL** — not "went unscaled". The wrapping
  parenthesis made `_split_top_level` yield **zero** components, so every
  nutrient came back `None` and `total_weight_g` was 0.
- **`PATCH /nutrition/{id}` applied fields and stopped.** No re-estimation. So
  the empty result overwrote nothing and the PREVIOUS meal's numbers stayed
  attached to the new description, displayed as though recalculated. A quarter
  portion recorded 697 mg of potassium and 372 mg of cholesterol for 174 and 93
  — a fourfold overstatement of potassium on a dialysis patient.

Fixes:

- `_extract_meal_multiplier()` handles `0.25 x (…)`, `×`, `2x`, `1/2 x`, and the
  no-parenthesis form. It requires an explicit `x`/`×` token and is anchored to
  the start, so "6 cherry tomatoes" and "2 teaspoons" are untouched; factors of
  0 or >100 are ignored as typos rather than applied.
- The factor scales **grams**, once, at the end. The estimator computes
  per-100 g × qty_g, so one multiplication gives 0.25 of all 150+ nutrients with
  no second code path that could disagree. Measured: every nutrient ratio 0.250.
- PATCH now clears the enriched columns and sets `nutrient_status="pending"`
  when the food name changes and no nutrients were supplied, then re-enriches in
  the background — the path create already used. The column list is derived FROM
  THE MODEL, because a hand-written one would go stale and the stale value is
  exactly what would be left behind.
- Server-side on purpose: web, iOS and Android all PATCH this route.

Proved over real HTTP end to end: 412.6 kcal → *pending, values cleared* →
103.16 kcal, K 174.175, chol 93.0. `tests/test_meal_multiplier.py` (17).

## 4c. The route checker was blind to every Android path parameter — FIXED 2026-08-30

Found while checking whether mobile shared the bug above.

`check_client_routes.py` skipped a call when
`raw.count("${") != raw.count("}")` — a guard against partial JS template
literals. For a Kotlin path that is `0 != 1`, so **every Android route written
`"nutrition/{id}"` was silently discarded**: mood, labs, fitness, lifestyle,
medications too. The script reported *"every client call resolves to a real
route"* having never looked at them.

It also compared paths only, never methods. With both fixed it immediately found
**six Android `@PUT` declarations against routes served only as PATCH** —
fitness, labs, lifestyle, medications, mood, nutrition, i.e. every "edit a log"
endpoint, all of which would 405. Switched to `@PATCH`.

Counts moved once the blind spot closed: 243 → **250** distinct client paths,
uncalled 109 → **103**. The §9 orphan analysis above was computed from the
incomplete set.

> ⚠️ **Still open — mobile cannot edit a meal at all.** iOS has no update call
> for `/nutrition/{id}`, and Android's `updateNutritionLog` is declared but
> never called from any screen. So the portion fix reaches web only; a phone
> user still cannot record "I ate a quarter of this". Per §3 this is a parity
> gap, not a finished feature — it needs an edit UI on both clients.

## 5. Health score measured diligence, not health — DONE 2026-08-29

Decision: *"Logging frequency is not clinically useful — that's why we track
adherence (nutrition compared to limits/requirements). Current heuristics are
false and misleading. Fix in ML analysis; the whole score. ML must be the
foundation of the score, not the LLM."*

`app/services/health_score.py` is the replacement — arithmetic over measured
values, deterministic and explainable. No model decides a number; the AI layer
may narrate a score, it does not compute one.

- **Nutrition is adherence.** Mean daily intake scored against the limits and
  requirements `compute_goals` already derives from the patient's biology and
  conditions (KDOQI 2020 for CKD) — the same figures their Nutrition screen
  shows. `_summarize_nutrition` never carried the renal four, which is *why* the
  old code could only count days; it now returns sodium, potassium, phosphorus,
  calcium, fibre and saturated fat, averaged over days WITH data.
- **Aggregated by weighted GEOMETRIC mean**, as HEBCS does across pathways and
  for the same reason. Arithmetically, staying under the potassium and
  phosphorus limits scored 100 twice and paid for a 50% protein deficit — the
  malnourished patient still read 78. Now: well-nourished 100, malnourished
  **72.8** naming `protein, calories`, double-limit potassium **7.2**.
- **Unknown is unknown.** Domains with no data are excluded and NAMED; weights
  renormalise over what was measured, and `confidence` says how much of the
  picture was available. Nothing measured returns `overall_score: None` — a 0
  for a patient we know nothing about is a claim we cannot support.
- **The free-points bug is gone.** `(10 - avg_stress)` with `avg_stress`
  defaulting to 0 awarded 30 of 100 points for never recording stress.
- **Vitals leads on blood pressure, and BMI is not scored on dialysis** — weight
  there varies with fluid between sessions, so it is not body composition.

`tests/test_health_score.py` (13) pins each of those, including that omitting
stress cannot improve a score and that unknown domains do not cap a patient who
tracked two well.

## 5a. HEBCS never matched seven of its own biomarkers — FIXED 2026-08-29

Found while rebuilding the score above, and the more serious of the two.

`compute_hebcs` looked up `Biomarker.name` verbatim in a dict the caller keys by
the raw `lab_results.test_name`. **Seven of 23 biomarkers could never match** —
the values were in the table the whole time under a different spelling:

| HEBC expects | actually stored |
|---|---|
| `KtV (Dialysis Adequacy)` | `spKt/V`, `eKt/V`, `stdKt/V …`, `KT/V PRESCRIBED` |
| `URR (Urea Reduction Ratio)` | `URR`, `URR%` |
| `nPCR (Protein Catabolic Rate)` | `nPCR`, `NPCR` |
| `CO2 (Bicarbonate)` | `CO2` |
| `Iron (Serum)` | `Iron` |
| `Iron Saturation (TSAT)` | `Iron Saturation` |
| `CaxP Product` | never stored — it is a product, now derived |

**`Dialysis_Adequacy` therefore matched nothing at all.** Omega is a weighted
geometric mean over the pathways that score, so on a patient with 730 sessions
the one pathway that says whether dialysis is working silently vanished from a
number still presented as whole-patient. On the reference record it now scores
**0.48**, because the delivered `spKt/V` on 2026-04-08 was **0.9** — against a
prescription of 1.1 and a KDOQI target of ≥1.4, down a trend of
1.61 → 1.5 → 1.62 → 1.35 → 1.44 → 0.9.

And `Nutritional` lost nPCR — 40% of its weight — leaving albumin and BUN to
renormalise to **100%**, which is the "HEBC always gives Nutrition 100% even
when I'm malnourished" complaint, exactly.

- Matching is by SHAPE (letters and digits, plus the pre-parenthesis base and
  the parenthetical), not a per-name list. Only genuinely different words need
  an alias — TSAT, HCO3, PCR.
- **`KT/V PRESCRIBED` is deliberately NOT matched.** It is the prescription, not
  what the patient received — the same trap as `therapy_sessions.blood_flow_rate`
  being a flat 350 (§3ac). `eKt/V` and `stdKt/V` are excluded too: different
  adequacy targets on different scales.
- Every pathway now reports `coverage`, `measured`/`expected`, and the response
  carries `unscored_pathways`. The interpretation text says what could not be
  assessed and what rests on limited results.

`tests/test_hebcs_biomarker_matching.py` (9).

> ⚠️ **Not changed, needs your call:** `Biomarker("BUN", opt_low=0, opt_high=80)`
> scores any BUN under 80 as perfect. In ESRD a LOW BUN can indicate poor protein
> intake, so the band cannot distinguish good clearance from undernutrition — on
> the reference record BUN 70 scores 1.0. Those bands are your published J-BHI
> framework, so I have not touched them.

> ⚠️ Verified against the DEV copy, whose parity is unverified since the ICD-11
> work (§5 of the canon). The lab rows are not something this work wrote, but
> re-run `verify_parity.sh` before quoting the Kt/V trend clinically.

## 6. Journal invents a mood score — DONE 2026-08-29

Decision: "AI should determine proper score using some intelligence."

`Journal.jsx` pre-set `mood_score: 7` ("Good"), so a patient who typed
"exhausted and fatigued" and never touched the slider had **7/10 Good** recorded
as their own self-report, with a clinician reading it beside that sentence.

Two changes:

- **The resting position is now 5 (Neutral), not 7 ("Good").** Web only — iOS
  and Android already defaulted to 5. A slider nobody moved should sit in the
  middle of the scale, not claim a good day on the patient's behalf.
- **`POST /mood/suggest-score` reads the entry and proposes a score**, with the
  reason it chose that number. Temperature 0, JSON mode, through `alafia_chat`
  so it uses the ordinary provider chain (§3ak) rather than naming a provider.

It PROPOSES only (§3aj): the number lands on the slider with its rationale
beside it and the user still presses save, so a wrong read is visible and
correctable. On web the user's own slider always wins — the auto-suggest fires
on notes-blur only while the slider is untouched, and there is an explicit
"Score this from what I wrote" button on all three clients.

**Unavailable is not a score.** `available=False` (provider unreachable, or
output that will not parse) returns no number at all and the client says so
rather than filling one in — §3aa applied to inference.

⚠️ This sends a NEW kind of free text to the provider chain. Central redaction
(§3al) strips name/email/phone/DOB, but a bare first name in passing is
pattern-undetectable and stays documented as such — a journal entry is the
surface most likely to contain one.

`tests/test_mood_score_suggestion.py` (6) pins the low-entry read, prose-wrapped
JSON, clamping, and both no-invention paths.

**Not done:** `mood_score` is still `nullable=False`, so an entry cannot carry
*no* score at all. That remains a migration if it is ever wanted.

## 7. Meal photos: retained and viewable — DONE 2026-08-29

Decision: "opt-in for data includes images, so no special opt-in is required for
retention. Retention ensures that when patient/clinician clicks on a past meal
they also see images if captured."

The old code conflated two different questions. It now separates them:

- **The photo is always stored.** It is part of the patient's own record.
  `record_prediction` stores it regardless of consent, under category
  `meal_photo`.
- **`allow_collective_insights` governs TRAINING use only** — a consented photo
  is filed under `food_training` and `training_consented=True`, which is the
  corpus flag. `may_retain_images` was renamed `may_use_for_training` so the
  name says which question it answers.

> **"Retained" and "stored" mean the same thing**, so using one for "kept at
> all" and the other for "kept for training" was a contradiction sitting in the
> schema — if an image is retained, it is stored. The column `image_retained`
> is now `training_consented` (migration `rr001_training_consented`). Storage is
> `media_asset_id` and is unconditional; permission is the flag. No client read
> the old name, so the rename is clean.

Retrieval, which did not exist at all:

| Route | Who | Authorization |
|---|---|---|
| `GET /media/{media_id}` | the patient | owner-scoped in the lookup; another user's id is a 404 |
| `GET /clinician-dashboard/patient/{pid}/media/{mid}` | a clinician | `_permissions_for` + the grant must cover `nutrition` |

The clinician route is deliberately NOT on `/media`: routing through
`_permissions_for` keeps one authorization path, so the patient is still told
their record was opened. A `labs` grant does not reach meal photos, and the
category is checked so a nutrition grant never yields an unrelated image.

Wired on all three clients plus the clinician board: `/ai/vision` returns
`image_url`, each client saves it to `food_image_uris`, and the meal row offers
the photo (web modal, iOS `MealPhotoView` sheet, Android `MealPhotoDialog`,
board `Photo` column). A failed fetch states the error rather than rendering as
"no photo" — §3aa.

`tests/test_meal_photo_retention.py` (8) pins retention without consent, the
ownership 404, both grant refusals, and that a storage failure still records the
sample.

**Still open, unchanged:** every `image-ai/*` endpoint (medication labels,
elimination, symptom, verify-dosage) persists nothing. The privacy policy
authorises **meal photos** specifically, so retaining those categories needs the
policy and both consent screens changed in the same commit as the code — the
§3al failure otherwise.

## 8. Photos are base64 in Postgres — OPEN

`VISION_TRAINING.md` already flags it: fine for accumulating, wrong at scale.
Move to GCS and populate `media_assets.storage_url`.

## 9. 109 backend routes have no client caller — INVESTIGATED 2026-08-29

Decision: *"Don't delete — find out why there is no UI."* Done, by prefix. The
count is one number covering four unrelated situations, which is exactly why
deleting on it would have been guessing.

`scripts/check_client_routes.py` scans web, iOS **and** Android, so "no caller"
means no client anywhere.

### (a) Operator tooling — correct as is, 9 routes

Every uncalled `/physicians/*` route is `/physicians/admin/…`: ingest seed,
stop, status, reprocess-held, backfill-coords, candidates, stats. These are
operator commands run deliberately, not patient screens. They belong with
`/auth/signup/*` (gated off in DEPLOY.md) as **dormant by design**. Nothing to
do.

### (b) A second implementation of a wired feature — 8 routes

**`/personalization/*` duplicates `/wellness/*`.** `/personalization/health-score`
is the one no client calls; the score every client actually shows is
`/wellness/score` (Dashboard.jsx:145, Wellness.jsx:208, plus both mobile
Wellness screens). That mattered directly: it is why item 5 above had to be
fixed in `wellness.py` and not only in `personalization.py`.

This is also why §3ae's outage was invisible for 27 days — the dead surface had
no UI to go dead. **Recommend: pick one.** They are now both correct (they share
`services/health_score.py`), but two implementations of one score will drift
again.

### (c) A live feature whose management API has no screen — 12 routes

`/blockchain/*`. The model is NOT dead: `clinician_dashboard.py:713` reads
`BlockRecord` for the therapy-session audit trail, so the data reaches a
clinician. What has no UI is the chain management API — record, verify, batch,
chains, trail-by-entity. **Recommend: keep**, it backs a surfaced feature.

### (d) Genuine gaps where the backend is ahead of the UI

- **`/telehealth/*` (11)** — the page exists and is routed, but the session
  machinery is not wired: WebRTC `signal`, `participants`, `admit`,
  `recordings`, `availability`, `history/summary`. A telehealth page that cannot
  admit a participant or exchange signalling is a shell. This is the largest
  real gap.
- **`/privacy/*` (8)** — `export`, `export/{id}/download`, `access-logs`,
  `consent`, `delete-account/status`, `translations`. `PrivacySettings.jsx`
  exists and calls none of them. Data export and account deletion are
  **compliance surfaces**, and shipping a privacy page that cannot export or
  delete is a claim we do not honour.

  > ⚠️ **`/privacy/access-logs` is the one to wire first.** This session added a
  > notification when someone other than the patient opens their record — but
  > that tells them once, in passing. The endpoint that lists *every* access
  > already exists and no screen shows it.

- **`/diagnostics/*` (13)** — the ICD-**10** catalog (search, chapters, body
  systems), assessments and screening. §3ad wired the patient-facing ICD-**11**
  screen, and canon is explicit that `icd10_code` stays: it is what the FHIR
  import and the PDF parser read off a source document. So this is not
  superseded — it is the lookup API for the other coding system, with no screen.

### What was NOT found

No case of §3ad's exact shape — a complete page sitting unrouted in `App.jsx`.
Every area with a page has it imported and linked; the uncalled routes are
endpoints those pages do not call.

## 10. An overridden dose leaves no trace — DONE

`acknowledge_unusual` is a request flag only; nothing is persisted. A clinician
cannot tell a force-logged dose from a routine one.

## 11. `Calcium Calcitriol 1000 mg` in production — CORRECTED 2026-08-29

Row 1441, 2026-08-17 — the original ~1000x record that prompted the dose guard.
The guard stops new ones; it does not repair that row.

## 12. Smaller, carried forward

- **Crash reports have no server-side ingest** (§3al: a stack trace can carry
  user data — a deliberate decision, not a bug fix). Reports stay local, capped.
- **Camera captures live in `cacheDir`**, which Android purges under storage
  pressure — observed doing exactly that. `filesDir` would close the window.
- **No `DELETE /planners/meal-plans/{id}`**, though meal plans are persisted like
  exercise plans. No client calls one, so it is a gap, not a broken call.
- **iOS camera path is unverified on a device** — the simulator has no camera, so
  only the library fallback was exercised.
- **Mobile artifacts are stale**: the IPA/AAB were built at `b70793d` and do not
  contain the orphaned-endpoint or camera work.
- **`WRITE_EXTERNAL_STORAGE`** is declared on Android and has been a no-op since
  API 29.
- **Dev carries test residue**: `last_login` stamps and a seeded demo patient.
  Re-pull before trusting parity.


---

## Resolved 2026-08-29

- **2a** streaming now goes through the router: hosted providers first (Anthropic,
  OpenAI, DeepSeek/Kimi/Mistral via the compat adapter), Ollama as the terminal
  fallback when one is unreachable or out of credit. Five tests pin the order and
  the redaction.
- **PII** — `full_name` appears zero times in `ai.py`; it was in the context block
  AND the system prompt. DOB is reduced to age. The scrubber's `[dob]` pattern ran
  after `[phone]` and never matched ISO dates; both fixed.
- **3a** `AssistantMarkdown` renders replies without `dangerouslySetInnerHTML` —
  model text is untrusted. Tables become label/value lines, because a
  multi-column table cannot fit a chat column even rendered correctly.
- **1** the fabricated "2-day potassium limit" came from `gpt-oss:20b`. The same
  question through Anthropic cites the record correctly and invents no limit.
  Item 1 stays open only for the deeper grounding work (last treatment, current
  nutrients, elimination), which no provider swap addresses.

## 7. Wellness score: one-sided bands, missing domains, prose findings — 2026-10-04

Reported: *"The vital scores for these patient are far from clinical optimal yet
you show 100!"* and *"HEBCS of 76% for this patients is the biggest joke."*
Full detail in CLAUDE.md §3ba. What was measured, and what remains.

### Fixed and verified on the dev copy

| | before | after |
|---|---|---|
| overall | 59.6 | **46.1** |
| vitals | **100.0** | 54.2 |
| dialysis | — | 74.8 |
| symptoms | — | 10.0 |
| elimination | — | 62.6 |

- `vitals_component`'s band was `systolic < 130 and diastolic < 80 -> 100`, one
  sided. Proven against the stashed old code: `vitals_component(81/62) -> 100.0`.
- Peri-dialysis pressure was never read: **25 of 32 treatments below 90 mmHg
  systolic, lowest 54**. Heart rate (96-109 every reading) was never scored.
- `overall_score` is a weighted GEOMETRIC mean now, so one good domain cannot
  pay for the rest.
- `/wellness/improvements` 500'd on `TypeError: '<' not supported between
  instances of 'NoneType' and 'int'`, captured from Cloud Run.
- `/wellness/score` inserted a row on EVERY GET: 117 rows across 49 days, which
  is why the history chart repeated dates. One row per day, updated in place.
- Ω: `critical_biomarkers` names what a pathway average hides (Glucose 273
  scoring 0.000, TSAT 6% scoring 0.048). The false "J-BHI 2026 Table 3" citation
  is corrected in the code AND in all 11 locale catalogs.

### Elimination history imported — DEV ONLY, prod outstanding

Applied to the dev copy and verified row by row:

    bowel_movements   648 -> 2,425   (1,777 inserted, 2022-06-01..2024-11-17)
      blood_present true 552          (417 from the sheet's Blood? column,
                                       135 from prose incl. the "Blooy" typo)
    vomiting_logs     1,991 unchanged — 607 rows ENRICHED, 0 inserted
      time_since_last_meal_hours  0 -> 568   (§3av said 0 of 1,994 — its source
                                              was the Vomit Log tabs all along)
      contains_bile 0 -> 50   contains_blood 0 -> 3   pre/post weights 13 -> 615/624

> ⚠️ **This is on DEV, which `pull_prod.sh` erases.** The data only becomes real
> against Cloud SQL, and that is 1,777 clinical inserts plus 607 updates into a
> live patient record. Not done: it needs the operator's explicit word, and
> `PROD_DB_PASS` out of the `alafia-database-url` secret. The proxy is reachable
> on 5436 from a `--network host` container (NOT from the macOS host — that
> distinction cost a wrong "prod unreachable" call).

### Still open

- **`import_firestore.py` and `migrate_all_firebase.py` still drop the
  structured columns.** They were not changed. Any patient migrated through
  either path arrives with findings in prose and NULL flags, so the next import
  recreates exactly the gap this work closed. They should write
  `blood_present` / `contains_blood` through `elimination_text`, or be retired.
- **`detect_condition_flags` is still six hardcoded keywords.** Its own test
  file says that cannot be the mechanism for a 35,339-code catalog and carries
  strict xfails for G6PD, sickle cell, coeliac and gout. Nothing here changed
  it; weights deliberately do not depend on it.
- **`/personalization/health-score` scores vitals differently** from
  `/wellness/score` — 77.5 vs 54.2 on the same patient, because it passes no
  peri-dialysis readings. Legitimate (different inputs available) but it is the
  drift OPEN_ITEMS §5 already warned about for this pair. Pick one.
- **`urination_logs` is empty** (0 rows) and no workbook carries a urine tab, so
  "blood in urine" has a column, a reader and no data anywhere.

---

## 8. Hospital & surgery history — 2026-10-05

`hospitalizations` + `surgical_procedures` were added because a patient said
they take calcium *"after removal of parathyroid glands"* and the record had
nowhere to hold it (measured: zero mentions anywhere in the database). Models,
migration `ao001_hospital_history`, the canonical reader, the FHIR
Encounter/Procedure import, the API, an AI tool and all three clients are in.
What follows was deliberately NOT actioned.

### 8a. The calcium target was a generic RDA — BUILT 2026-10-05, the clock is what is left

`services/nutrient_goals_service.py` emitted, for every patient alive:

    calcium = 1200 if (age and age >= 50 and not male) or (age and age >= 70) else 1000
    add("calcium_mg", "Calcium", "mg", calcium, "target", 130,
        "Bone health RDA (1,000-1,200 mg/day by age/sex).")

Every other renally-relevant nutrient branched — sodium on
hypertension/CKD/heart failure, potassium with dialysis/CKD/general arms,
phosphorus flipping to a **limit** for CKD. **Calcium had no branch at all**,
and it was a `target` to aim FOR: wrong for a dialysis patient whose calcium
load is mostly their binder, and wrong the other way after a
parathyroidectomy.

> ⚠️ **CORRECTED the same day, 2026-10-05.** The first version of this item
> asked for "the number for CKD G3-G5D" and whether a parathyroidectomy
> "changes the direction". All three questions were **one-patient,
> one-disease framing** — a 16th branch bolted onto a ladder of 15. Operator:
> *"you are again turning this into a one patient solution. It is not."* The
> standing instruction that framing violates: *"this project while using data
> from one patient must not be generalised to one patient but must recognize
> patterns for millions as data and users grow. this is why we avoid hard
> coded. Also hard capping to one disease is meaningless."* The wrong framing
> is kept because it is the error worth not repeating.

**What the literature actually says, measured rather than recalled.** Calcium
alone, across conditions:

| scope | figure | basis |
|---|---|---|
| healthy adult | 1,000-1,200 mg/d | dietary RDA |
| CKD 3-4, no vitamin D analog | 800-1,000 mg/d | **total elemental, incl. calcium-based binders** (KDOQI 2020) |
| CKD G5D (dialysis) | **no figure exists** | KDOQI says "adjust to avoid hypercalcemia"; KDIGO 2009/2017 state none at all |
| CKD any stage (EU consensus) | 800 floor, **1,500 ceiling** | total elemental; authors call these "clinical practice points without high-level evidence" |
| hungry bone, post-PTX | **6-16 g/d**; 3.2 g wk 1 → 2.4 g wk 6 | **a taper**, often IV initially |
| chronic hypoparathyroidism | 2-3 g/d | **and <=500 mg PER INGESTION** (absorption saturates) |
| calcium oxalate stones | 1,000 mg/d, **do NOT restrict** | low-calcium diets *raise* stone risk (CARI) |
| sarcoidosis + hypercalcaemia | restrict Ca and vitamin D | contested; restriction may raise nephrolithiasis risk |

One nutrient, ~0 to 16,000 mg/day, and three of those are not a daily dietary
number at all: one counts a MEDICATION toward itself, one is a per-dose
ceiling, one changes week by week. **No `float` called `goal` can express
any of them**, which is why the fix was never a branch.

**There is nothing to import.** EFSA's DRVs are 32 healthy-population
opinions plus an interactive tool; ESPEN ships 14 disease guidelines as prose;
the Academy's EAL has ~40 projects. What is machine-readable is research-grade
and single-disease (a COPD ontology DSS, OnT2D-DSS). There is no LOINC or
RxNorm for condition→nutrient quotas.

**And combinations are the hard half, with numbers on it.** ESPEN's polymorbid
guideline exists because "guidelines are largely created for individual
diseases". Formalising 12 guidelines into symbolic logic and running a SAT
solver found **90.6% of conflicts arise only at the intersection of
comorbidities**, frontier LLMs failed to detect them, and a neuro-symbolic
check reached F1 0.861 — *logical verification must precede retrieval*
(Xie & Du, AAAI 2026). NutriOrion (330 multimorbid patients, agents, guideline
grounding, FHIR R4 output) still reports a **12.1% drug-food interaction
violation rate**. That is the honest ceiling for a pure-LLM resolver, and the
reason the conflict check here is deterministic code rather than a prompt.

Scale, from our own catalogs: **35,369 ICD-11 MMS codes x 116 catalog
nutrients ~ 4.1M single-condition cells** before any combination; age, sex,
weight and height are continuous.

#### What was built

`condition_nutrient_quotas` (migration **`ap001_nutrient_quotas`** — read as
`dev only` here until 2026-10-14, when the live `alembic_version` said
`ap001_nutrient_quotas`: it shipped in the 2026-10-10 deploy of `2a96a38`):
amount + unit + **basis** (`absolute` | `per_kg` | `per_1000_kcal` |
`per_dose`) + **kind** (target | limit) + **includes_supplements** +
**time_course** + scope, and **`source` / `cited_text` NOT NULL**. A quota
with no citation is REFUSED, not downgraded — §3az's own history is a
hardcoded potassium limit of 4,700 mg sitting looser than the patient's real
2,200 mg cap.

- `app/services/nutrient_quota_service.py` — `stored_quotas` (one SELECT, no
  network), `resolve_for_patient` (pure: basis applied, scope filtered,
  tensions detected), `quotas_for_conditions` (read path, **no**
  `resolve_missing` flag to leave in the wrong position), `resolve_quota` (the
  write path, refuses anything uncited/malformed, sharpens on re-resolution).
- `compute_goals(quotas=...)` — the override lives in the `add()` closure, so
  it reaches **all 13 nutrients and every one added later**, not just calcium.
  Passing quotas IN rather than making the function async is deliberate: it is
  synchronous with **18 call sites**, and going async would change every
  nutrition surface at once.
- Wired at **all five live call sites** (nutrition x2, wellness,
  personalization, ai x2), with a static guard that fails the build if a
  `compute_goals` call in those modules omits `quotas`.
- Each goal now carries **`authority`** (None = the general ladder) so a
  generic reference can never read as the patient's own figure (§3am).
- Seeded with the seven calcium rows above, each with its own sentence.
  **No G5D row is seeded** — the absence is the answer.

**Two faults of mine, caught by the tests rather than shipped:** the AST guard
flagged the resolver PROMPT (which names dialysis precisely to tell the model
an absent recommendation is real) — classifying before acting changed the
guard, not the prompt (§3ar); and the stones row was seeded with
`scope_key="age_max=70"`, a key `scope_key_for()` can never produce, so a
re-resolution would have computed `""`, missed the row and inserted beside it:
§3ab's contradictory duplicate, created by the column added to prevent it.

#### What is still open

1. ~~There is no clock.~~ **BUILT 2026-10-06 — `_quota_resolve_job` in
   `main.py`**, gated on `QUOTA_RESOLVE_ENABLED` which defaults to **False**
   because every pass makes real model calls, and a deploy must not start
   provider traffic nobody chose (the `FIREBASE_SYNC_ENABLED` precedent).
   Bounded by `QUOTA_RESOLVE_MAX_PER_RUN` (default 5), first run delayed 10
   minutes so a restart loop cannot become a traffic burst, `max_instances=1`
   and `coalesce=True`.

   It iterates users and asks `clinical_sources.conditions()` rather than
   touching `ChronicCondition` — so it needs **no** §3aa `ALLOWED` exemption,
   confirmed by running that guard (7 passed). It skips any condition that
   already has a quota, since re-resolution is for sharpening deliberately and
   not something a timer should spend a model call on daily. The nutrient list
   is read from `compute_goals` rather than typed, so a nutrient added to the
   ladder is asked about automatically.

   ⚠️ **It is still OFF in every environment**, so `times_confirmed` remains 1
   until someone sets the flag. The mechanism now exists; the decision to spend
   on it does not. `tests/test_quota_resolve_job.py` guards the default
   precisely because flipping it is a cost regression no behavioural test
   would notice.
2. **The drug axis is unmodelled, and its authority is gone.** NLM retired the
   **RxNav Drug Interaction API on ~2 Jan 2024** with no replacement (ONCHigh
   and DrugBank went with it); RxNorm/RxClass/RxTerms remain. Drug→nutrient
   effects exist only as prose (PPIs: B12 down 12-18% over 12 months;
   hypomagnesaemia at a median 5.5 years, reversing in 4 days off-drug), so
   they need the same resolve-cite-store treatment. §3aa's third medication
   source still contributes nothing to nutrient tracking either.
3. **Cited AND schema-valid cannot be one provider call.** Per the API
   contract, document citations are **incompatible with
   `output_config.format` (400)**, so resolution has to be cited extraction
   then structured normalisation. ⚠️ **Not verified on the wire** — §3al's
   rule is that only the wire proves the system. And nothing is wired for it:
   the adapters carry only `response_format: {"type": "json_object"}`
   (`openai_adapter.py:116`, `openai_compat_adapter.py:175`), with no
   structured outputs, no citations and no server-side search anywhere,
   including `anthropic_adapter.py`. The 18 `openai_compat` providers cannot
   do server-side search at all, so a cited resolver runs on the Anthropic
   path specifically.
4. **The figure reaches every client; the citation does not.** Web, iOS and
   Android render `goal` and `goal_kind`, so the corrected calcium value and
   its flip from target to limit show up with no client change. The new
   `authority`, `quota.cited_text` and `quota.tension` fields are returned and
   **nothing draws them yet** — so a patient sees the right number without
   seeing which guideline set it, or that two of their conditions disagree.
5. **Production is not migrated.** Dev is at `ap001_nutrient_quotas`; prod is
   behind it. Ask `alembic heads`, never this line (§5).

### 8b. The response serialises `Z` — ANSWERED 2026-10-05, not a defect

**Resolved the same day it was raised.** The cause is
`normalize_datetimes_middleware` (`app/main.py:114`): a global middleware that
rewrites every `application/json` response body with
`_NAIVE_ISO_DT.sub(rb'"\1Z"', body)`, declaring stored naive datetimes as UTC
on the wire. Deliberate, app-wide, and documented in its own comment.

Why it took three attempts to find, kept because the habit is the point: I
grepped for the mechanisms I imagined (`json_encoders`, `isoformat`,
`default=`, `ORJSONResponse`) rather than for the behaviour I had measured, and
a byte-level regex matches none of them. Full detail and the three app-wide
consequences are in CLAUDE.md §3bb. The original framing below is left intact.

**Original entry, which was wrong to call this unexplained:**

Measured both sides: the column is `timestamp without time zone` and holds a
tz-**naive** value (`tzinfo is None`, exact instant), while the POST response
renders `"2024-03-02T14:00:00Z"`. On pydantic 2.10.4 a naive datetime renders
without a suffix and an aware one with `Z`, and **no** global JSON encoder or
key strategy exists anywhere in the app. So something makes the value aware at
serialisation time and I could not find it.

Harmless — a `Z` declares UTC unambiguously — and the §3aa asyncpg DataError
hazard is absent because storage is naive. Recorded rather than explained away.
`tests/test_hospital_api.py` asserts on the COLUMN, not the response string;
asserting the string was the wrong instrument and is what surfaced this.

### 8c. Smaller, carried forward

- ~~Migration `ao001` is applied to DEV ONLY.~~ **Shipped 2026-10-06.**
  Production is on `ap001_nutrient_quotas` (verified against the database, not
  this file). The line above sat here claiming prod was on
  `an001_vital_thresholds` for three days after it wasn't — which is the stale
  revision number §5a records as having halted a good release three separate
  times. Ask `alembic heads`, never this line (§5).
- **No import writes these tables yet except FHIR.** The PDF/document path and
  the two Firestore importers do not, so a discharge summary still has to be
  entered by hand. Wiring a bulk import to notify or to dedupe against
  `external_ref` was not attempted.
- **`procedures()` and `hospitalizations()` are unpaginated.** Correct at a
  patient's real volume, and deliberately so after §3ad's truncation failure,
  but it is an unbounded read if a record ever carries hundreds.
- **The AI tool returns no facility or surgeon name** (§3al), so the assistant
  cannot answer "which hospital was that?" even though the column holds it.
  That is the privacy trade, not an oversight — revisit only deliberately.

---

## 9. The elimination history was imported into PRODUCTION — 2026-10-06

Recorded because a production data import with no audit trail is the §5b
failure ("the comp that had no audit trail"), and because §1 says prod changes
only through *migration + deploy* — this is the documented exception, taken
deliberately by the operator.

**Why.** `verify_parity.sh` reported drift in which **dev was AHEAD of prod**
on `bowel_movements`: prod held 660 rows starting 2025-06-01 with
`blood_present` true on **zero**, while dev held 2,431 from 2022-06-01 with
**552** structured blood-positive findings. 1,777 of those rows — the entire
2022-06-01 .. 2024-11-17 window, 417 blood-positive — existed **only in dev**,
imported there and never shipped. Re-pulling would have deleted the only copy;
pushing dev up is forbidden. The operator chose to put the history into prod
first, then re-pull.

**How.** `WEB/backend/scripts/import_elimination_history.py` (committed; reads
the workbooks on the host and **writes no rows**, emitting SQL for a separate
visible step). Source was `~/Developer/data/Records.xlsx` — the NEWEST of the
five copies, 1,777 rows / 417 blood-positive; the path `import_food_bowel.py`
hardcodes is the iCloud copy with 1,155 rows / 206 positive, which would have
lost more than half the finding.

    import SQL   sha256 d1678e2fdc2c8b804c3efa0a4d0224a7ae373b9d081af9cac8feeb67344be5ea
    rollback     sha256 9ffda89bb1a9f03ba5c7fd377f901357c54b2cc174b0309e78df6f0b7305cc71

**What made it safe, each verified rather than assumed:** one transaction with
`ON_ERROR_STOP`; a `RAISE EXCEPTION` if the target email does not resolve, so
it cannot silently write nothing; every insert guarded by
`WHERE NOT EXISTS (same user, log_date, log_time)` so a re-run cannot
duplicate; every update `COALESCE`-only, preserving the 13 existing
pre-weights and 25 post-weights; **zero** literal user ids — all 2,386 writes
resolve through a temp table keyed on `lower(email)`; and measured overlap of
**zero** (prod held 0 rows before 2025-01-01).

**Measured, before → after** (target user, resolved by email):

| | before | after |
|---|---|---|
| `bowel_movements` | 654 | **2,431** |
| pre-2025 rows | 0 | **1,777** |
| `blood_present` set | 0 | **1,767** (417 true, 1,350 false, 10 not stated stay NULL) |
| `vomiting_logs` with meal-gap | 0 | **568** |
| `pre_event_weight_kg` set | 13 | **615** (+602, exactly what the importer reported) |
| other 4 users | 6 rows | **6 rows** — untouched |

Then `pull_prod.sh --yes`: **✅ PARITY OK**, 134 tables, dev byte-identical to
prod across `public` and `identity`.

> ⚠️ **The rollback is exact but SESSION-SCOPED.** The inverse is a scoped
> `DELETE FROM bowel_movements WHERE user_id=<target> AND log_date <
> '2025-01-01'` plus four id-scoped `UPDATE … = NULL` over the 1,992 / 1,979 /
> 1,967 / 66 rows that were blank beforehand — the id sets matter because the
> updates were COALESCE-only, so a blanket NULL would also erase the 13 and 25
> weights that predate the import. Those id files lived in a scratchpad and are
> gone. To rebuild the inverse, the pre-state is in the table above; the
> `DELETE` half needs nothing but the date bound.

**Still true after this:** prod's own 2025+ rows carry `blood_present` NULL
with the finding in `notes` — §3ba's "a finding written in prose is still a
finding" is unchanged for them, and `services/elimination_text.py` remains the
only reader that sees it. The import filled the structured column for the rows
it inserted, not for the 654 that were already there.

---

## 10. Nutrient effects are display-only by construction — 2026-10-06

Reported from the live screen: the Calcium row said *"Calcium Carbonate would
count in your favour here, so it needs a recent blood test to confirm it.
There isn't one, so it is shown and not counted."* — on **10/1, 10/2, 10/3 and
10/4**, while the record held a panel drawn 2026-10-01 carrying
**Calcium 8.9 mg/dL**.

### 10a. The notice was false — FIXED 2026-10-06

`apply_effects_to_totals` took a single `measurement_fresh: bool`, and its one
production caller (`api/nutrition.py`) passed the literal **`False`**. The gate
never consulted the record at all, so the sentence was emitted unconditionally
for every gated in-favour effect, for every patient, forever. §3ar's dead
control inverted: not a flag nothing observes, but a flag nothing *sets* —
defaulting to the pessimistic branch and then stating it as fact about a
patient's own chart.

The call site defended itself in a comment: *"No serum draw exists in this
system for the nutrients this layer covers."* True of the **data structure**,
false of the **record**. `SerumLevels` has five hardcoded fields — potassium,
phosphorus, magnesium, calcium, glucose — and `_SERUM_TESTS` is a hand-typed
alias table of their spellings. Iron, Ferritin and Iron Saturation are all on
the same 10/1 panel and cannot be represented at all. **This record holds 376
distinct analytes; production holds 411; that layer could see 5.**

Fixed by asking the record per analyte:
`nutrient_effects_service.measured_dates_for()` strips the unit suffix from a
goal key (`calcium_mg` → `calcium`) and matches it against `analyte_key()` —
the §3ax vocabulary that already folds `ALP`/`Alk Phos` and `K+`/`Potassium` —
with **no second alias table**. Measured on the reference record: **7 of 15
goal keys resolve** (sodium, potassium, phosphorus, cholesterol, calcium,
iron, magnesium) and 8 correctly do not, because there is no blood test for
fibre. The notice now names the nutrient it lacks a result for rather than
claiming the record has no blood test.

`measurement_fresh` is kept as the fallback for callers supplying no mapping,
so the 24 existing tests are unchanged. A static guard fails the build if any
caller passes it as a literal again.

### 10b. Nothing in this layer can EVER be counted — NEEDS DECISION

The deeper finding, and the reason 10a changes no number:

    calibrated = (row.provenance in ("clinician", "measured"))
                                     nutrient_effects_service.py:242

Measured on the store: **all 26 rows are `llm` or `literature_prior`**, and
**no code path anywhere sets `provenance` to `clinician` or `measured`** —
the grep returns empty. The only writers are `resolve_nutrient_effects.py`
(LLM) and `seed_nutrient_effects.py`. So `calibrated` is False for every row
and can never become True, and the branch below the freshness gate withholds
everything regardless:

    elif not effect.calibrated and effect.provenance == "llm":

**The entire agent-effects layer is therefore decoration.** Fixing the blood
test changes the sentence; the number cannot move until a calibration path
exists. Also measured: **21 of the 26 rows have `magnitude = NULL`**, so they
cannot be counted even in principle — that is the honest "how much it changes
has not been established" notice on Phosphorus, Iron and Magnesium.

This is the same shape as §8a's quota store: the mechanism exists, the thing
that would make it earn its place does not. What has to be decided, because
none of it may be invented:

1. **Where a measured coefficient comes from.** The §3ac discipline is the
   precedent: fit per patient against their own serial labs, and adopt only
   when it beats predict-the-previous-value on a **chronological** hold-out.
   `dialysis_solute_coefficients` already has exactly that shape — 5 rows, one
   user, one run, 2026-08-20 — and is itself frozen.
2. **What a `clinician` provenance means operationally.** There is no surface
   for a clinician to confirm a magnitude, so that value is currently
   unreachable by any route.
3. **Whether a literature prior should count.** `Hemodialysis → protein_g
   9 g/session` is `literature_prior` with confidence 0.8 and is excluded by
   the same test as an LLM guess. If a named guideline figure is good enough
   to credit, `calibrated` is the wrong question and the gate should read
   provenance ∈ (clinician, measured, literature_prior).

Until one of those is answered, every effect in the store stays "shown, not
counted", and the layer's only function is to explain itself.


---

## 11. The PDF importer routed on a label, not on the data — PARTLY FIXED 2026-10-11

Raised by the operator after a real document had to be imported by hand:
*"the pdf importer must be able to recognize, parse, categorize and allow import
of varied pdf documents and formats"*, then *"5 types is grounding tens or even
hundreds of variations in 5 hard-coded type. what coul go wrong there.
everything."*

The trigger was concrete. On 2026-10-10 a DaVita Treatment Details Report
(10/09, Frederick Dialysis) was imported as **hand-written SQL** — production
session 2776 plus six intradialytic readings — because nothing in the pipeline
could read it.

### What was wrong, and it was the AXIS not the coverage

`TARGET_FOR_DOC_TYPE` mapped one `doc_type` to **one** destination table. Real
documents are not one thing: that treatment report carries a session, six timed
BP/UF readings, pre/post vitals, a dialyser prescription and a close reason —
five kinds of clinical fact in one PDF. **No value of `doc_type` could ever have
imported it.** A visit summary is the same shape (conditions AND medications AND
measurements). `DIALYSIS_FLOWSHEET: TABLE_LABS` is the line that proves it: a
flowsheet is not a lab report, and the mapping was only harmless because both
entries pointed at the same table.

### FIXED — claim-based routing

`app/services/docparse/claims.py` reports every kind of data a document holds
with the evidence for each; `stage()` runs the stager for each kind present.
`doc_type` is still stored and shown to a reviewer, and routes nothing. Verified
on the real corpus: **0 false medications, 0 false conditions** where a naive
"run every extractor" router stages **1115 of each** against 1014 true lab rows.
`228 passed` across all eleven docparse/import suites. Detail in WORKLOG.

### STILL OPEN — the measurements, so these are not re-derived

**11a. Recognition is blind to FORM documents.** `OPEN` — `classify_table` reads
tables. The treatment report is mostly labelled values scattered across a page
and scores **1 point out of 41** against the signature table. Needs label→value
extraction by coordinate. This is what still blocks treatment-report import; see
TASKS 14a/14b.

**11b. LOINC cannot be resolved from names, and the stated unblock does not
exist.** `OPEN` — over 411 production names: 143 resolve, **68 by a rank
tiebreak between tests LOINC itself separates**, **5 determinate (1.2%)**.
`Platelet` → mean platelet VOLUME, `Platelets` → the count. The removal comment
in `document_import_service.py` names "a specimen read off the report" as what
would make it safe; measured, **these reports print no specimen** — the only
`blood` is the dialysis BLOOD FLOW parameter and the only `sample` is prose about
aged samples. The route forward is the lab's own test code (TASKS 14f), not a
better resolver.

> ⚠️ **Two of my own statements in this round were wrong and are corrected
> here.** I said LOINC was blocked on the operator downloading a zip:
> `app/data/loinc_core.tsv.gz` has been on disk since 2026-09-30 — LOINC 2.83,
> 62,148 terms — so nothing was blocked. And I said the test code was being
> dropped by the parser; it is **captured** on 939 of 1014 records and dropped
> later, by the import service, which never reads `LabRecord.code`. Both were
> asserted before measuring (§0).

**11c. Imaging findings and recipes have nowhere to go.** `NEEDS DECISION` —
measured: no imaging table and no recipes table exist in the 130-table schema
(`facilities.imaging` is a facility TYPE enum; `recipe_url` is a meal-plan
column). Named in `claims.NO_TARGET_YET` so they are reported as unfileable
rather than misfiled. A target means a model plus a hand-written migration.

**11d. No OCR, so a photographed document cannot be imported at all.**
`NEEDS DECISION` — `extract.py` takes a PDF with a text layer or plain text; a
scan returns `needs_ocr` and `usable` is False. The operator has been sending
photos (the 10/09 report arrived as six). The decision is egress, not
technology: local OCR versus a hosted vision model that §3al records as an
unredacted path carrying the patient's printed name. See TASKS 14e.

**11e. The classifier resolves ties by dict order.** `OPEN` — a discharge
summary quoting an imaging study scores `discharge_summary=20,
imaging_report=20`, and the winner is whichever is declared first in
`SIGNATURES`. Adding a type reclassifies existing documents.

**11f. Three of five declared types have never met a real document.** `OPEN` —
`medication_list`, `discharge_summary`, `imaging_report`. The corpus is 13 lab
reports, which is §3ab's "the corpus cannot see what it does not contain" still
true a fortnight later.

---

## 12. 120 lab rows imported the word "Error" as a result — FIXED 2026-10-11

Found while building the claim detector, not reported. Measured over the 13
corpus documents — the COMPLETE vocabulary of result texts carrying no digit:

    'N/A'     60    the lab states no result exists
    'Error'   60    the assay failed
    'NEG'     11    NEGATIVE — a real qualitative finding

Every one of the 120 `Error`/`N/A` rows had `has_result` true, confidence
**0.75**, `is_abnormal` NULL and an **empty `notes`** — so a reviewer saw rows
claiming Albumin, ALP, AST/SGOT, BUN and Calcium were resulted on that date with
"Error" as the value, and nothing said otherwise. `is_abnormal` NULL puts them in
§3ab's 9,417 not-assessed rows.

Worse than cosmetic: dedupe is keyed `(test_date, lower(test_name))` and §3ab
records that `existing_row_id` is **never read back**, so when the lab re-issues
a corrected panel the real Albumin lands BESIDE the Error row and the patient
holds two contradictory results for one date.

`review_lab_value` could never have caught it — it is handed the numeric value
and never sees `value_text`.

Fixed in `_stage_labs`: such a row stages **UNTICKED with its reason**, never
deleted (§3ab). **`NEG` is an explicit exclusion**, recorded as data in
`claims.NOT_A_FAILURE_EXAMPLES` — §3ab measured "a real row has a number in its
value column" deleting 49 of 106 rows on a Quest report, including
`WBC = NONE SEEN` and `RBC = 0-2`. Negative is a result; "Error" is not.

---

## 13. Field discovery is validated against lab headers, not against a form — OPEN 2026-10-11

`docparse/fields.py` (TASKS 14a) discovers label→value pairs by coordinate with
no vocabulary, and recovers everything `metadata.py`'s hand-typed reader finds:
collection date 12/12, lab 12/12, ordering provider 13/13, 165 fields across the
corpus against a hand-typed ceiling of 6.

**But the documents it was built FOR cannot be tested.** Measured: 304 PDFs on
this machine, 13 clinical, and all 13 are table-shaped lab reports. The DaVita
treatment report — the document that motivated the whole change — exists only as
photographs, and there is no OCR path (item 11d), so it cannot be parsed at all.

So the header-grid and inline-colon forms are proven on real geometry and the
**no-colon form field** case (`Ordered Target Weight   50.0 kg`, with no colon
and the value in a neighbouring cell) is **unproven**. A synthetic fixture would
only prove the fixture — §3ab, and this round has already paid for that twice,
below.

Consequence: TASKS 14b (the treatment stager) is blocked in practice even though
its extractor exists. The unblock is one real treatment-report PDF, or OCR.

> **Both bugs in this module were found by MEASURING, and the unit tests passed
> through both.** They are recorded because the shape recurs:
>
> - **A colon is also a clock.** A naive `([A-Z]…)\s*:` returns
>   `DaVita Inc. 01/12/2026 14` (7×) and `EDT 23` (24×) — footer timestamps
>   matched up to the colon in `14:23`. §3av's `parseInt("7:27") == 7`.
> - **Geometry cannot say which label a value belongs to.**
>   `DOB: 03/15/1974  MPI: 1934716` packs the date 3pt from `MPI:` — one cell —
>   so a purely geometric backward walk produced the label `03/15/1974 | MPI` on
>   **all 13 documents**, while every unit test passed because the fixtures had
>   put those fields in separate cells. The date is equidistant from the label
>   it follows and the label it precedes; only TOKEN SHAPE separates them, which
>   is what `metadata._NEXT_LABEL` already assumed by matching letters only.
> - ⚠️ **The first fix was worse than the bug.** Flooring the backward walk at
>   the previous colon made `MPI`'s span start at the date, which truncated
>   `DOB`'s value to empty — and BOTH fields were lost. Caught only by
>   re-measuring the corpus after the change, not by the suite.

---

## 14. Every domain must reach the aggregates — FIXED for insight 2026-10-11, PARTIAL elsewhere

Operator, 2026-10-11: *"Contibutor to weight, vitals data are from flowsheets,
nutrition, medication, eliminations, vitals, labs, lifestyle, hospitalization
records and events, therapies. But right now they are not included in the
aggregates (overview, trends and insight). They MUST! This is canon and have
been repeated multiple times. This is not a set of isolated data points but a
collection of data for integrated viewing, advising and decisioning. All data
must be visible and used by the various anaytytes, aggregators and AI queries.
This cannot be compromised."*

**They were right, and this was the THIRD surface with the same fault.** §3am
found it in the AI tool (`get_vitals` read `vitals_logs` alone — 41 rows on a
patient with 16,236 intradialytic readings); §3ba found it in the wellness score
("read one row of `vitals_logs` and never opened `therapy_sessions`").

### What was measured on the reference record, before any change

`health_signals.collect_signals` is the single substrate under
`/insights/signals`, `/insights/relationships` and `/insights/forecast`. It read
nine sources — nutrition, vitals, lifestyle, fitness, mood, sleep, symptoms,
env/social, labs — and queried none of the rest:

    weight     read 41 (vitals_logs)   ignored 5,221 (pre 2,003 / post 1,798
                                       / dry 1,420)            -> 0.8% seen
    systolic   read 43                 ignored 18,526 (intradialytic 15,016
                                       / pre 1,860 / post 1,650) -> 0.23% seen

    never queried at all: bowel_movements 2,436 · therapy_sessions 2,035
                          vomiting_logs 1,993 · medication_dose_logs 1,029
                          hospitalizations · surgical_procedures

So `vital.weight_kg` was forecast from 41 points while 5,221 existed, and no
relationship could involve dialysis, medication or eliminations — they were not
on the timeline at all.

### FIXED — 17 new signals, measured after

One year of user 63: **6,705 daily points across 120 signals**.

| | before | after |
|---|---|---|
| weight | 16 days | 172 pre · 168 post · 169 dry (+16 self-recorded) |
| systolic | 18 days | 161 nadir · 148 pre · 146 post (+18 self-recorded) |

Four design points that are canon rather than preference:

- **The BP sources stay SEPARATE signals.** §3am: post runs well below pre by
  design, so averaging them manufactures a number no instrument read.
- **The nadir is reduced with MIN**, and `MIN`/`MAX` are now declared
  aggregations. A treatment reading 150 then 59 has a mean of 104 — ordinary —
  and a nadir of 59, which is intradialytic hypotension. ⚠️ The reducer
  previously hardcoded `if signal == "symptom.severity_max": reducer = max`,
  so a new MIN signal would have been silently MEANED.
- **There is NO duration signal.** §3av: `duration_minutes` is the wall clock
  from the app and the machine's time from the 2026-06-04 import, with no way
  to tell which from the row. `machine_total_time_minutes` is used instead.
- **Guarded models go through `clinical_sources`** — dose counts and
  administration days (the THIRD medication source: Epogene ×1,962,
  Venofer ×1,248, none of it in dose logs), stays and procedures.

### STILL OPEN

**14a. The other aggregators are not all covered.** `OPEN` — scanned
2026-10-11, by domain:

    wellness.py          7 of 9   missing hospitalisation, conditions
    chart_dashboard.py   2 of 9   flowsheets + labs only
    diagnostics_engine   4 of 9   missing flowsheets, nutrition, eliminations, lifestyle
    ai_engine.py         4 of 9   missing flowsheets, eliminations, labs
    patient_board.py     7 of 9   missing hospitalisation, conditions

Hospitalisation reaches **no aggregate at all** — `clinical_sources` is its only
reader. §3bb built those tables on 2026-10-05 and nothing aggregates them.

**14b. Five lab signals are all WEIGHT.** `OPEN` — surfaced by this work:
`lab.weight (kg)`, `lab.weight - pre`, `lab.weight - pre day`,
`lab.weight - pre day 1`, `lab.weight - post day 1`. These are the §3ab
name-overflow variants and the dialysis machine parameters no lab vocabulary
covers, so `analyte_key()` has no entry and each spelling is its own series.
Same class as §3ax's remaining `Cl`/`Chloride` and `TRIG`/`Triglycerides` split,
which this change inherits rather than introduces.

**14c. `dialysis.post_diastolic` has a stored minimum of 5 mmHg.** `OPEN` — not
introduced here; §3at records that implausible stored rows exist and that a
response model states shape, never plausibility. Worth a repair pass.

---

## 15. The TRENDS surface showed 3 streams on a 2,035-session record — FIXED 2026-10-11

Operator: *"recent tasked not reflected in dev."* Correct, and the diagnosis
matters more than the fix because three of the four suspects were innocent.

**Measured, in order:**

- **The dev backend was NOT stale.** `WEB/backend` is bind-mounted to `/app`
  with `--reload`, and the logs show `WatchFiles detected changes in
  'app/services/health_signals.py'. Reloading...` on every edit. A plausible
  theory — §4 records that macOS bind mounts deliver no inotify events, which
  is why vite needs `VITE_POLL=1` — and it was wrong here. §0.
- **`/insights/*` WAS already live on dev.** Over real HTTP with a dev token:
  `200`, **120 signals**, domains `dialysis 12 · diet 9 · elimination 3 ·
  lab 84 · medication 2 · mood 3 · symptom 2 · vital 5`.
- **`/wellness/trends` was the stale surface, and not because of a container.**
  It returned *"Analyzing 3 health data streams over the past 90 days"* —
  Daily Calories 83 points, Mood 6, **Weight (kg) 9** — on a patient holding
  2,035 dialysis sessions, 2,436 bowel movements, 1,029 dose logs and 5,221
  recorded weights. OPEN_ITEMS 14 fixed the SUBSTRATE; this endpoint never read
  it, because it hand-wrote one query per stream: calories, mood, weekly
  workouts, weight-from-`vitals_logs`. Four, enumerated.
- **The `frontend` container WAS 3 weeks old**, serving an nginx `dist/` baked
  then — §4's documented trap. Rebuilt, and verified the way §4 requires: the
  served asset went `index-BC8Coh0T.js` → `index-DwRP4Lv3.js`. It was not
  hiding this work (no frontend file changed in the last 10 commits) but it was
  genuinely stale.

**Fixed:** `/wellness/trends` now builds its streams from
`health_signals.collect_signals` — **110 streams across 8 domains**, including
*Lowest systolic during treatment* (36 points), pre/post/dry weight, treatments,
doses taken and bowel movements. A new signal appears with no change to the
endpoint, which is the point.

> ⚠️ **The first version asserted three clinical claims it could not support.**
> Defaulting to "rising is improving" for anything unlisted, the real record
> immediately produced **"Carbs improving"**, **"Fat improving"** and
> **"Bowel movements improving"**. §3az is the precedent: that surface's
> thresholds were population constants LOOSER than the patient's own limits, so
> a judgement with no authority behind it is worse than none because it reads as
> one. Direction is now ALLOW-LISTED per signal and claimed on **4 of 110**.

**Nutrient directions are deliberately absent**, and that is the remaining gap:
whether this patient's sodium should fall depends on `compute_goals` (2,000 mg
for them, potassium capped at 2,200), which is a TARGET, not a slope. Judging a
nutrient against its own last fortnight says nothing about whether it is safe.
Wiring the nutrient streams to the quota is queued in TASKS 15 rather than
guessed at here.

---

## 16. The dialysis score said 94 beside "26 of 33 treatments ended below 90" — FIXED 2026-10-11

Operator, from the running dev app: *"(still mesuring frequency of log) nothing
has changed"*, against a Wellness page showing **Dialysis 94** in the same view
as *"26 of 33 treatments ended below 90 mmHg systolic (lowest 54)"*.

`dialysis_component` scored exactly two things: **attendance** against the
patient's own baseline rate, and Kt/V. Nothing about how the treatments WENT. So
a patient who turns up reliably scores 94 no matter what happens once they are
on the machine. That is an event count presented as a clinical state — the
operator's phrase exactly, and OPEN_ITEMS §5 ("Health score measured diligence,
not health") returning in a domain that did not exist when it was written.

**Measured over 90 days on the reference record — 38 sessions:**

    ended below 90 systolic                26  (68%)
    intradialytic nadir below 90           30  (79%)
    nadir below 70                         14  (37%)
    lowest nadir                           39

**Fixed:** a third input, *tolerance* — the FRACTION of treatments whose nadir
fell below the floor — at weight 0.4, with attendance dropping 0.5 → 0.3 and
Kt/V 0.5 → 0.3. **Dialysis 94 → 58.6; overall 49 → 44.4.** The dialysis domain
now carries its own finding: *"35 of 37 treatments (95%) dropped below 90 mmHg
systolic during dialysis (lowest 39); 16 fell below 70."*

- **Not double-counting `vitals_component`.** That scores the nadir VALUE — how
  low it got once across the window. This scores the BURDEN — in what fraction
  of treatments it happened. One dip to 39 and four-in-five treatments going
  low are different clinical pictures and one number cannot hold both.
- **Both thresholds come from the `Post-Dialysis Systolic BP` band** —
  `opt_low` 90 and `crit_low` 70 — the same band `vitals_component` reads, so
  the two cannot disagree. ⚠️ I first wrote `below 70` as a literal, two
  paragraphs under a docstring citing §3az for that exact mistake.
- **Session nadir is the least of the intradialytic readings AND the post
  pressure.** Reading post alone gives 26 of 33; including the readings gives
  35 of 37, because a treatment can run the pressure down and partly recover
  before the final measurement.

### STILL OPEN from the same report

**16a. Chart Dashboard drew `Systolic BP` from `vitals_logs` alone.** `FIXED 2026-10-11` — the screenshot shows **Points: 9** over 90 days. `chart_dashboard.py`'s
`DATASETS` is a hand-typed catalogue of one-model/one-column entries, and
`bp_systolic` names `VitalsLog`. A `weight_all` VIRTUAL dataset already proves
the multi-source pattern works; pressure never got one. The fix is to generate
datasets from `SIGNAL_META` and serve them through `collect_signals`, as
`/wellness/trends` now does — TASKS 15.

**16b. Health Insights is thin to the point of unhelpful.** `OPEN` — operator:
*"the health insight is meaningless"*. The page shows ONE relationship —
*"Target dry weight ↔ Fluid intake, 1-day offset, r=-0.70, n=27"* — and a
forecast of **Calories**. Both are artefacts of ranking rather than clinical
judgement: the forecast picks the most data-rich signal, which is whatever the
patient logs most, and dry weight is a PRESCRIPTION set by the unit rather than
anything the patient does, so correlating it with intake is not a finding. With
120 signals now on the timeline the candidate set is far larger, so the ranking
is what needs work, not the inputs.

---

## 17. "some data on dev still stopped on 9/24" — it had not — FIXED 2026-10-11

The report was right about the symptom and wrong about the cause, and the cause
is the interesting part.

**Dev was not stale.** Measured against production the same minute: dev trailed
by FOUR rows, every one of them that day's logging since the morning's
`pull_prod` (bowel_movements 2436/2437, nutrition_logs 1046/1047,
medication_dose_logs 1029/1030, vomiting_logs 1993/1994). Nothing anywhere ended
on 9/24 — the "Sep 24" in the screenshot is the chart's hover cursor.

**`vitals_logs` ends 2026-09-26, and it ends there in PRODUCTION too.** That is
not staleness, it is the record: the patient stopped self-recording vitals. What
makes it look like data loss is which source the charts read:

    vitals_logs — what the chart drew          last 2026-09-26        43 systolic
    therapy_sessions pre/post — not drawn      last 2026-10-09     3,510 systolic
    intradialytic_readings — not drawn         last 2026-10-09    15,016 systolic

    measured SINCE vitals_logs stopped: 6 more days, 20 readings, lowest 59

So the pressure never stopped being measured. The line ended in September
because the chart was reading the one source holding 43 readings instead of the
two holding 18,526 — OPEN_ITEMS 16a, seen from the user's side.

**Fixed:** `chart_dashboard.py` gains `SIGNAL_DATASETS`, generated from
`SIGNAL_META` and served through `collect_signals`, alongside the hand-typed
`DATASETS` and the existing `weight_all` virtual pair. Wired into `/datasets`,
`/data` and `/summary`. The picker now offers, with real day counts:

    bp_systolic               Systolic BP                        43
    dialysis.pre_systolic     Pre-dialysis systolic             148
    dialysis.post_systolic    Post-dialysis systolic            146
    dialysis.nadir_systolic   Lowest systolic during treatment  161

and charting the last of those gives 36 points ending **2026-10-09** against
`bp_systolic`'s 9 ending 2026-09-26.

- **Signals are NOT re-aggregated here.** `collect_signals` has already reduced
  each day per its declared aggregation — MIN for a nadir — and averaging it
  again would destroy exactly what that declaration protects (§3am).
- **`min`/`max` come back NULL for signal datasets**, because the day is already
  one figure and inventing a spread would be fabricating one.
- **Only signals that HOLD data are offered.** A picker listing 120 empty
  metrics is worse than one listing the dozen a patient has.
- **The `/summary` trend splits the series by POSITION, not by date.** These
  series are irregular — a treatment series has no points on non-treatment days
  — so a midpoint DATE puts wildly different counts either side.

> **A surface that reads one source of a measurement will always look like the
> data stopped.** Three screens have now shown this on the same record — the AI
> tool (§3am), the wellness score (§3ba) and the chart. The fix each time was
> the sources, never the window.

---

## 18. The API offered the data and the PAGE never asked for it — FIXED 2026-10-11

Operator, after a hard reset: three screenshots, *"all these after a hard reset
so it's not browser data."* Correct, and the reset proved the opposite of what
it looked like — **Wellness had moved 49 → 44 and Dialysis 94 → 59**, and the
narrative carried the new finding, so the backend was reaching the browser
perfectly. The Chart Dashboard still showed `Systolic BP · Points: 9` because
**the page was still asking for `bp_systolic`.**

OPEN_ITEMS 16a added the datasets to `/chart-dashboard/datasets` and changed
nothing about what the frontend requests. §3ar in its purest form: a capability
nothing reaches.

**`ChartDashboard.jsx` auto-selected the best dataset of each of the FIRST
THREE DOMAINS in the response**, in whatever order the backend serialised them
— nutrition, fitness, mood, vitals — and stopped. That is how a page opens on a
series with 43 readings ending 2026-09-26 while one with 161 days ending
2026-10-09 sits unlisted below the fold.

**Fixed:** rank across ALL domains by count, then take one per domain. The page
now opens on **Weight (All Sources) 1600 · Calories 736 · Drugs given at the
unit 348**, with **132 selectable datasets** including all twelve dialysis
series.

**Two flaws in what 16a shipped, found by looking at the ranking it produced:**

- **The counts were not comparable.** Hand-typed datasets counted ALL-TIME
  rows; signal datasets counted DAYS IN THE LAST 365; `weight_all` counted
  all-time observations across sources and reported **7,235**, ranking first
  on a comparison of three different units. All three now use the same
  365-day window.
- **`calories` and `diet.calories` are the same measurement from the same
  table**, so the picker listed "Calories" twice and the auto-selection chose
  both — one series charted as two. A signal whose LABEL a hand-typed dataset
  already shows is no longer offered. Deduping on the label rather than a key
  mapping keeps it honest: if two entries present the same words to the
  patient, showing both is the bug wherever they came from.

**`Dashboard.jsx`'s "Historical Vitals Trend" had the same fault** — `GET
/vitals/` then `.slice(-7)`, which is `vitals_logs` alone, 43 readings ending
2026-09-26. It now draws self-recorded systolic/diastolic/HR **plus**
pre-dialysis, post-dialysis and lowest-during-treatment as SEPARATE lines over
14 days. Separate, not merged: §3am, post runs well below pre by design, so one
averaged line shows a pressure no instrument read.

Frontend rebuilt and verified by the served asset — `DwRP4Lv3` → `Dd8_iRhX`
(§4: ask the asset, never the build log). 279 frontend tests, 59 backend.

> **Shipping an API capability is not shipping a feature.** This is the third
> time in two days the backend was correct and the surface was not — the trends
> endpoint reading its own four queries, the chart's dataset catalogue, and now
> the chart's default selection. Each time the evidence that it was fixed came
> from curling the API, which was true and did not answer the question the
> operator was asking.

---

## 19. "81 mmHg? how?" — one fifteen-day-old reading, called "resting" — FIXED 2026-10-11

Operator, on *"Resting systolic 81 mmHg is below the 90-120 mmHg reference
band"*: **"81 mmHg? how?"**

The VALUE was real and everything around it was wrong. Measured:

    2026-09-26 07:00   81/62  HR 96   "Just woke up after an 8 hr sleep"
    2026-09-15 10:55   91/58  HR 104  "Just after poop"
    2026-09-09 04:30   79/60  HR 99

    44 rows total · 43 with a systolic · range 55-136 · mean 97

`wellness.py` took `.order_by(VitalsLog.log_date.desc()).limit(1)` — ONE row —
and the self-recorded half of the vitals domain was scored on it. Three faults
in one sentence:

- **n=1.** §3an says "windows, not lifetimes"; a single reading is the same
  error from the other end. This patient's 43 readings average 97, so 81 is the
  low end of their own distribution reported as their blood pressure.
- **Fifteen days old, with no date shown.** §3an: lab recency is already
  defined and "a 147-day-old draw is reported as ABSENT, not as latest".
- **Called "resting" with nothing to support it.** Nothing in `vitals_logs`
  records posture or activity. The row that produced the 81 happens to say
  "Just woke up"; the one before it says "Just after poop". Asserting a
  condition the record does not state is §0 in a sentence a clinician reads.

**Fixed:** the component takes the 30-day window's MEDIAN with its sample size
and age. The finding now reads:

> Self-recorded systolic 86 mmHg (across 2 self-recorded readings) is below the
> 90-120 mmHg reference band — but the most recent was 15 days ago
> (2026-09-26), so this may not be current.

Vitals 54 → 63, overall 44.4 → 45.8 — not because anything improved, but
because one unusually low reading is no longer standing in for the window.

- **MEDIAN, not mean**, for self-recorded vitals: these are a handful of
  readings taken in whatever circumstances the patient was in, so one unusual
  value must not drag the figure the domain is scored on. §3am argues the
  opposite for intradialytic readings — there the NADIR is the finding and a
  mean hides it. Which statistic is honest depends on what the series is, and
  neither is a default.
- **The staleness bound is `dialysis_day_adjustment.FRESH_DAYS` (14)**, not a
  number chosen here — §3an forbids inventing a second recency window.
- **The 30-day window is kept, not widened.** It holds two readings on this
  record, which is precisely why the count now travels with the figure.

---

## 20. "how could the most recent day be 9/26?" — it could not — FIXED 2026-10-11

The staleness note I added in item 19 said *"the most recent was 15 days ago
(2026-09-26), so this may not be current"*. Measured:

    self-recorded (vitals_logs)        2026-09-26
    treatment pre/post                 2026-10-09
    during treatment (intradialytic)   2026-10-09

**The patient's blood pressure was last measured two days before the card
claimed a fortnight's silence** — and the SAME card said "35 of 37 treatments
(95%) dropped below 90 mmHg systolic during dialysis". It contradicted itself
two sentences apart.

§3aa in a single sentence: I scoped the measurement to `vitals_logs` correctly
and then WORDED it as though it covered blood pressure. Fixed by passing the
most recent pressure from ANY source into the component:

> Self-recorded systolic 86 mmHg (across 2 self-recorded readings) is below the
> 90-120 mmHg reference band — last self-recorded 15 days ago (2026-09-26),
> though pressure was measured at treatment on 2026-10-09.

> **Three rounds, three versions of one sentence, each wrong differently** —
> "Resting systolic 81" (one stale row, called resting), then "most recent was
> 15 days ago" (true of one table, false of the patient). The facts under it
> were right every time; the PROSE was what kept being wrong, which is the
> argument for item 21 below.

---

## 21. Three shipped features fail as "Unknown LLM task" — OPEN 2026-10-11

Found while wiring `finding_text`: my own `task="finding_text"` returned
`ALAFIAModelError` and I first read that as a provider outage. It was not —
`llm.py:183` answers `Unknown LLM task` for any name it does not dispatch, and
that arrives at the caller looking exactly like the model being down.

Swept every `task=` passed to the LLM capability against the ones it handles
(`health_chat`, `nutrition_guidance`, `chat`/`raw_chat`/`health_coaching`,
`complete`, and the two declared unimplemented):

| passed | handled? | consequence |
|---|---|---|
| `doc_classify` | **NO** | `classify.classify_with_model` has NEVER run — §3ab's model fallback for an ambiguous document returns the deterministic answer every time |
| `nutrient_quota_resolution` | **NO** | §3bc's quota resolver cannot resolve anything, even once `QUOTA_RESOLVE_ENABLED` is turned on |
| `mood_score` | **NO** | silently falls back |
| `health_chat` | yes | |
| `vision` ×4 | n/a | different modality (`alafia_infer("vision", …)`) |

Every one is caught by a broad `except` and logged at INFO or not at all, so
each reads as "the model was unavailable" rather than "this task name was never
registered". §3ar's dead control, three times, inside the dispatcher — and §3ae's
exact lesson: *a setting that is configured, documented and ignored is worse
than one never offered.*

**Not fixed here, deliberately.** Pointing them at `chat` would start real
provider traffic on document upload and on quota resolution, which is a cost
decision and the operator's call (§3ae: warming a model is a standing cost
decision, not a code change). The one-line fix per site is known; what is
needed is the decision. ⚠️ `nutrient_quota_resolution` must additionally go
`local_only` or not at all — it resolves clinical quotas from patient
conditions.

**The durable fix is a guard**, not three edits: the capability should REFUSE
an unknown task loudly at import or the service should validate the name
against the dispatch set, so a new caller cannot invent a task and get silence.

---

## 22. Findings are written by ALAFIA now, and only by a LOCAL model — 2026-10-11

Operator: *"do not hard code messages, let our own LLM model do write messages
that reflect the actual observation"*, then *"message must be written by LOCAL
LLM not third party providers like Anthropic. This ensures PII do not bleed
out."*

The argument is items 19 and 20: **one sentence about this patient's blood
pressure was wrong three times running while the numbers under it were right
every time.** Each fix edited an f-string, and each new f-string was a fresh
chance to assert something the data did not support — "resting" from nothing,
then a staleness claim true of one table and false of the patient.

**The split** (§3am's, pointing the other way — there the model extracts the
drug name and the backend resolves the dose):

    deterministic   the metric, value, band, counts, dates, provenance, and
                    WHETHER it is a finding at all
    the model       the sentence

`Component.critical` is now `list[Finding]` — facts plus a REQUIRED
deterministic `fallback`. `finding_text.render` asks ALAFIA to word them at
read time.

**What makes it safe, each from something already in this canon:**

- **Every number in the facts must survive into the sentence, and none may be
  invented.** Verified per finding; a sentence that fails is discarded for its
  fallback. §3am: handed a dump, a model once reported **15.0 g — a number in
  no row of the record**.
- **LOCAL ONLY** (`local_only=True`) — §3al's hard guarantee, no hosted
  fallback. ⚠️ The service wrapper never exposed `local_only` at all, though
  the capability has always honoured `payload["local_only"]`, so §3al's one
  guarantee for text that must not leave was **unreachable from the backend**.
  Now exposed and asserted by a test.
- **Never on the write path.** Rendering happens on READ; a model timeout
  delays prose, never a saved row.
- **Language follows the patient** (§3aw) — the English f-strings could never
  do this, so a patient who chose Yoruba read their findings in a language
  they did not pick.

⚠️ **With no local runtime, every finding reads as its deterministic fallback**
— which is what should happen, and is what dev shows today because Ollama is
not running. Prose degrades; nothing leaves. To see ALAFIA's own wording:
`OLLAMA_HOST=0.0.0.0:11434 ollama serve` (§4).

---

## 23. The findings card: three faults in one sentence — FIXED 2026-10-12

Operator, on *"Self-recorded systolic 86 mmHg (across 2 self-recorded
readings)…"*: **"systolic and dystolic are different readings. what is
self-recorded? this all reek of hard-coded messages not LLM crafted"**

All three correct.

**1. Half a measurement.** 86 is not a blood pressure; 86/60 is. §3an already
says *"print a blood pressure as a blood pressure"* — and the diastolic was
already SCORED (weight 0.15) and simply never stated. The facts now carry the
pair and both bands, and name which side breached.

**2. "Self-recorded" is our schema, not the patient's language.** It is the
distinction between `vitals_logs` and the flowsheet, and it reached the screen
raw. The facts now say *"readings the patient took and logged themselves"*.

**3. It WAS hardcoded** — the fallback, because no local model was running.
Ollama was installed with `gpt-oss:20b` pulled and simply not started.

Started it (§4: `OLLAMA_HOST=0.0.0.0:11434`, never the default bind, or
`host.docker.internal` cannot reach it) and ALAFIA now writes them:

> Blood pressure reading of 86/60 mmHg, taken by the patient themselves, shows
> systolic below the reference low of 90.

### Two faults in the guard itself, found by running it

- **Requiring EVERY fact number made the guard self-defeating.** Once a finding
  carried systolic, diastolic, two bands, a count, a window and two dates, no
  readable sentence could contain all eleven — so every finding failed
  verification and fell back. A guard strict enough to disable the feature it
  guards. Split: **invention absolute, omission bounded** to keys a finding
  names `essential`.
- **The model did ARITHMETIC and the guard caught it.** It wrote *"below the
  reference low of 90 by 4 mmHg"* — 4 is 90 − 86, derived, not given. Correctly
  rejected. §3av's *"run the scan, never the arithmetic"*, now aimed at a model:
  the instruction forbids computing differences, percentages or sums outright,
  rather than leaving the guard to catch each one.

⚠️ **Still falls back on the real card** — five findings exceed any bound a
30 s client allows. The fix is the §3c background render, queued as TASKS 16
rather than half-built here.

---

## 24. Two findings that read as a contradiction — FIXED 2026-10-12

Operator: *"26 of 33 treatments ended below 90 mmHg systolic (lowest 54). / 35
of 37 treatments (95%) dropped below 90 mmHg systolic during dialysis (lowest
39); 16 fell below 70. — these two statements are contradictory. likely reading
from different sources?"*

Different MEASUREMENTS over different denominators, worded so alike that the
only reasonable reading was that one was wrong. Verified in raw SQL:

    sessions with a post-treatment reading   33     of which below 90:  26
    sessions with ANY pressure               37     of which below 90:  35
    the other 4 have intradialytic readings and no post value

`vitals_component` narrated the first and `dialysis_component` the second. The
score stays where it was; the SENTENCE moved, so one clinical story gets one
statement carrying both denominators.

**And neither said its WINDOW.** Operator: *"what dates are these numbers
referencing? 30 days? 2 days?"* Both are 90 days (`cutoff_90`), as are the
symptom, bowel-movement and vomiting findings — and none of them said so. A
count with no period is not a finding: "26 of 33 treatments" could be a week or
a year. The window now travels in the facts and in the wording.

**"readings they took themselves"** — operator: *"who else is supposed to take
bp reading?"* Fair. The distinction that matters is not WHO holds the cuff but
WHERE: a pressure away from dialysis is a different measurement from one taken
mid-treatment with fluid coming off, which is exactly why §3am forbids
averaging the sources. Now "taken away from dialysis".

> **The numbers were challenged as invented and they are not.** Re-derived in
> raw SQL independently of the application: 37 / 35 / 95% / 39 / 16 / 33 / 26 /
> 54, window 2026-07-15 → 2026-10-09. Every figure matches.

---

## 25. "you've been lying about not hard coding messages" — fair — FIXED 2026-10-12

The operator was right, and the distinction I was drawing did not survive
contact with the screen.

`finding_text` genuinely has ALAFIA write the sentences. But the local model
needs 14-17 s warm for ONE finding and over 20 s for a card, while
`/wellness/score` allows 30 s — so **the render always fell back, and every
sentence on screen was a hand-written fallback I kept hand-editing.** An
architecture where a model writes the prose, and a screen that never shows a
word of it, are not the same thing, and only the first was true.

**Fixed with §3c's shape** — the one this product already uses for nutrition:

1. the read path renders within its 20 s bound and returns whatever it has;
2. a background pass (`finding_text.warm`, 180 s, nothing waiting on it)
   renders properly and caches the result;
3. the next read serves ALAFIA's words.

Keyed by a **hash of the exact facts**, never by user or date: if a measurement
changes the key changes, so a cached sentence can never describe a new number.
That is the property that makes serving a cached clinical sentence safe at all.

Measured after the background pass, written locally by `gpt-oss:20b`:

> Worst symptom reported was twisted abdominal pain with severity 9 out of 10.
> Seven of 102 bowel movements over 90 days contained blood, a 7% occurrence.

⚠️ **Two of four still fall back, deliberately.** When the model dropped the
diastolic ("Median systolic blood pressure 86 mmHg") and dropped the nadir and
the below-70 count, those facts were made `essential` — so the two
number-dense findings now fail verification rather than lose a clinical
figure. A mechanical sentence carrying every number beats a readable one
missing the 39. Making those render faithfully is real work, not a wording
tweak.

> **The in-process cache leaked between tests**, and a real failure found it:
> one test cached a sentence for the same facts another used, so the slow-model
> test got a cache HIT and never exercised the timeout. §3aj's shape — a suite
> that passes without reaching the thing it checks. An autouse fixture clears
> it now.

---

## 26. An analysis was typed into the patient's chart — FIXED 2026-10-12

Operator, with the Hemodialysis screen open on session 2776: *"this is not
patient notes but your own debate. You combined the clinical notes and your
debates into one extra long statement when reading from the PDF."*

`therapy_sessions.patient_notes` held **2,103 characters**, of which roughly
half was not the document and not the patient:

| In the field | What it actually was |
|---|---|
| "ALAFIA held no record of this session; the preceding stored treatment is 10/06" | our own bookkeeping, about our database |
| "Course: 99/65 at 14:34, 89/59 at 14:53 …" | a prose re-typing of six `intradialytic_readings` rows that were already stored with their times and the nurse's own remarks |
| "ORDERED TARGET WEIGHT 50.0 kg, RECORDED AS THE DOCUMENT STATES IT AND NOT RECONCILED … Raise with the care team rather than treating either figure as settled." | a derived comparison plus an instruction, written in the voice of the unit's report |
| "NOT RECORDED, because … `fluid_removed_ml` is left NULL rather than derived … `duration_minutes` is the report's own stated 2h 17m" | the importer reasoning about its own column choices, naming columns, in a clinical field |

**Three things are wrong with that, and only the first is about tidiness.**

- **A chart field cannot be queried.** Every structured value in the prose
  already had a column — `blood_flow_rate` 300, `dialysate_flow_rate` 500,
  `dialysate_potassium_meq` 2, `dialyzer_appearance` Streaked, the pre/post
  pressures, and all six readings as rows. Two copies of one fact is §3ai's
  "two computations of one quantity must not disagree", in a text field.
- **It reads as the unit's words.** Nothing separated what DaVita printed from
  what ALAFIA concluded. A clinician reading "raise with the care team" would
  attribute it to the facility.
- ⚠️ **The arithmetic in it was WRONG, and nothing could check it.** It said
  *"3.3-4.4 kg below"* while citing the range it was measured against —
  53.2-54.8 against 50.0, which is **3.2 and 4.8**. Both ends. A figure nobody
  can recompute is a figure nobody can correct (§3av: run the scan, never the
  arithmetic).

**The note is now 933 characters**, holding only what the report states and has
no column of its own: the close reason as printed, the prescription detail with
no column (dialyser model, bath composition, bicarbonate, base sodium,
temperature, max UF rate), the access history, the verbatim 14:25 nursing note,
and mobility. Applied to PROD first and then dev; `md5` identical in both
(`b940dedb…`).

> **One sentence about absence stays, and it is not bookkeeping.** Four values
> the unit DID record are blank here because they could not be read from the
> source. §3at records that a printed "—" means NOT RECORDED, so leaving them
> silent tells a clinician the unit never measured them. The line says which
> four and that the unit recorded them; it does not name a column or explain a
> decision.

**The safety signal moved to where it is re-derived, not retyped.**
`_dry_weight_disagreement` in `health_score.py` reports an ordered dry weight
the rest of the record disagrees with, from the rows, on every read. Measured
live on user 63: *"The dry weight ordered on 2026-10-09 is 50 kg, 3.2 kg below
the lowest of the 33 recorded over the last 90 days (53.2-54.8 kg)."* ALAFIA
renders it locally — *"Ordered dry weight 50.0 kg on 2026-10-09 is below the
usual lowest of 53.2 kg by 3.2 kg"*, every number preserved.

- **No threshold is invented** (§3az). The figure must fall outside the full
  range of every other dry weight in the window AND be further out than that
  range's own width — both measured from this patient. A deliberate taper moves
  in steps well inside its historical spread and stays silent; pinned by
  `test_a_DELIBERATE_TAPER_is_silent`.
- **It does not move the score.** A prescription disagreeing with a record says
  nothing about how well the patient is. `critical_findings` already reaches
  web, iOS and Android, so no client change was needed — verified by reading
  the three call sites.
- **Only the LATEST order is examined**: it is what the next treatment's
  ultrafiltration is computed from, and a figure since corrected does not need
  to keep shouting.

> ⚠️ **Not generalised.** This repaired one row and added one finding. Nothing
> stops the next manual or automated import writing commentary into
> `patient_notes` again — see TASKS 17.

---

## 27. "HEBCS (a wellness score) is 78%?" — four arithmetic faults, FIXED 2026-10-12; the modelling question is OPEN

Operator, with the HEBCS Ω card open on user 63, verbatim:

> *"The patient is terminally ill, the blood results show severe anemia and
> nutrition is hardly ever adequate and HEBCS (a wellness score) is 78%? What
> happens to someone in perfect health? The underlying HEBCS ML model is
> fundamentally wrong. Frequency of logging data is completely irrelevant to
> wellness. Wellness (HEBCS) is impacted by the actual data. We must surface and
> fix the underlying mathematics. HEBCS is human biologics that measures
> (analyzes) the electro-biochemical-neurophysical composition of a person using
> all known pathways degenerated into mathematical construct."*

Then, on being shown the first analysis: *"show me the maths"*.

### What the screen said

    Ω 0.781   "Critical"      78% Score (0-100)      100% Data coverage
    Metabolic 58%  Hematologic 70%  Bone Mineral 100%  Cardiovascular 92%
    Nutritional 94%  Dialysis Adequacy 97%  Inflammatory 55%
    Latest labs: 9/30/2026

    "3 marker(s) sit at or below the bottom of their own reference band:
     Glucose 273, RDW 21.3, RDW 21.3. A pathway score is an average, so these
     do not show in it."

All three named markers are above the **top** of their band, not below the
bottom; RDW is printed twice because it sits in two pathways; and that whole
paragraph is a hardcoded f-string (see item 4 below, still open).

### The three levels, and where the contradiction was

    1. biomarker -> score   trapezoid on (a, b, c, d)
                            0 at x<=a or x>=d; 1 for b<=x<=c; linear ramps
    2. pathway   s_p = Σ wᵢ·sᵢ / Σ wᵢ            <- ARITHMETIC mean
    3. overall   Ω = exp( Σ w_k·ln(s_k) / Σ w_k ) <- GEOMETRIC mean

Level 3 is geometric for one published reason: `ln(0) = -∞`, so **failure in
any single pathway cannot be masked**. Level 2 was arithmetic, so inside a
pathway it was masked freely.

**Metabolic, worked:**

    Glucose   273   band  74-106   score 0.000   w 0.30
    Sodium    132   band 136-145   score 0.750   w 0.25
    Potassium 5.3   band 3.5-5.1   score 0.784   w 0.25
    CO2        27   band  22-28    score 1.000   w 0.20

    arithmetic  0.30(0) + 0.25(.750) + 0.25(.784) + 0.20(1)  = 0.584
    geometric   exp(0.30·ln(.001) + 0.25·ln(.750) + …)       = 0.110

### FAULT 1 — the values were not the patient's

`/wellness/omega` deduplicated on the raw `test_name`, so `FERRITIN` and
`Ferritin` were two analytes (§3ax) and `resolve_biomarkers`' `setdefault` then
picked by dict order. Its docstring claimed *"callers hand us the most recent
value per analyte already"* — false of the only caller.

| scored | from | age | actual latest (2026-10-01) |
|---|---|---|---|
| Glucose 273 | 2026-02-09 | 245d | 230 |
| Potassium 5.3 | 2026-02-09 | 245d | 4.3 |
| Haemoglobin 12.0 | 2026-02-09 | 245d | 11.3 |
| Haematocrit 38.6 | 2026-02-09 | 245d | 38.3 |
| Ferritin 57 | 2026-02-09 | 245d | **197** |
| Iron 50 | 2026-02-09 | 245d | 42 |
| Phosphorus 5.1 · Calcium 9.5 · Albumin 4.1 | 2026-02-09 | 245d | 3.6 · 8.9 · 4.2 |
| **PTH 24** | 2025-09-03 | **404d** | **17** |
| **BUN 20** | 2025-09-03 | **404d** | **53** pre / 14 post |
| **Kt/V 1.65** | 2025-09-03 | **404d** | **1.47** |
| **URR 81** | 2025-07-17 | **452d** | **74** |

**13 of the 23 scored biomarkers.** `lab_date_used` was the maximum over EVERY
row the patient holds, so the date printed belonged to no part of the
computation. It now names the newest draw actually scored, and
`oldest_lab_date_used` travels beside it.

> ⚠️ **Fixing recency alone broke the pre/post rule, and that is why both live
> in `select_latest_per_analyte` now.** `BUN` 53 and `BUN Post` 14 are drawn the
> same day and mean different things — uraemia before the session versus the
> residual the patient lives with between them. A newest-wins rule has no
> opinion between two same-day rows, took the pre draw, and crashed Nutritional
> to 0.237 for the wrong reason. **Provenance beats recency**; recency breaks
> ties among equals.

### FAULT 2 — a population reference interval replaced a treatment target

`apply_reference_range` overwrote every band with the reporting lab's interval,
unconditionally. A reference interval describes where 95% of **healthy people**
fall; a treatment target says where **this patient** should be held. On ESRD
they diverge sharply — **and in both directions**, which is what proves the
mechanism was wrong rather than the numbers:

    PTH   KDIGO 2017 CKD-MBD, stage 5D:  150-600     lab's healthy adult: 18-80
          band becomes (1.8, 18, 80, 400)
          PTH 24 -> 1.000      KDIGO -> (24-15)/(150-15) = 0.067
          24 pg/mL on dialysis is ADYNAMIC BONE DISEASE. Bone Mineral read 100%.

    Hgb   KDIGO 2012 anaemia:  10-12      lab's healthy adult male: 14-18
          Hgb 12.0 -> 0.524 instead of 1.000, and chasing 14-18 on ESA is what
          TREAT and CHOIR showed raises mortality — the lab band is the
          DANGEROUS one here.

Seven bands are now declared `is_treatment_target=True` with their guideline in
`authority`: PTH, haemoglobin, ferritin, TSAT, phosphorus, Kt/V, URR. Everything
else still takes the lab's own interval, which remains the better evidence —
there is no single optimal sodium. §3am's *"a generic RDA must never be handed
over as the patient's target"*, in the biological score.

### FAULT 3 — a zeroed pathway was SKIPPED by Ω

    if s is None or s <= 0: continue

Unmeasured and catastrophic shared a branch, so total failure of an organ system
**raised** Ω by removing the worst term from the mean. It never fired because
nothing reached 0 while level 2 was arithmetic — making the level-2 fix the
thing that would have activated it. Only `None` is skipped now.

### FAULT 4 — bands open on one side asserted health nobody measured

Operator: *"high or low rdw are not sign of health. one suggests hemolysis or
worse."*

`crit_low=None, opt_low=0` makes `trapezoidal_score` return **1.0 for the entire
low side**. Measured 2026-10-12 with the lab's own 11-15 already applied:

    RDW   0.1 -> 1.000        RDW  5.0 -> 1.000        RDW 21.3 -> 0.000
    Albumin 9.0 -> 1.000      Kt/V 9.0 -> 1.000        LDH 0 -> 1.000

Five markers across six pathway slots. This is **§3ba's one-sided band**, which
that section measured on blood pressure — *"it can only penalise HIGH pressure
… 54/30 would also have scored 100"* — alive inside HEBCS the whole time.

`low_is_deficiency` was declared on `Biomarker`, set on BUN, and **read
nowhere** (§3ar) — a dead control on the one field written to prevent this exact
bug. `closed_band()` is its first reader. **The replacement bound is the band's
own declared margin, mirrored** (`crit_high/opt_high = 20/14.5` → the same ratio
below), not a number chosen here; a marker with no margin to mirror is left
open, and a marker not flagged keeps its open side, because a low LDH really is
unremarkable.

### Result

| | Ω | |
|---|---|---|
| before | **0.781** | 78% |
| + latest values only | 0.800 | 80% |
| + targets not overridden | 0.767 | 77% |
| + geometric within pathway | **0.489** | **49%** |

    pathway            before   after
    Metabolic           0.584   0.474
    Hematologic         0.695   0.519
    Bone_Mineral        1.000   0.186     <- PTH 17 vs KDIGO 150-600
    Cardiovascular      0.917   0.847
    Nutritional         0.944   0.941
    Dialysis_Adequacy   0.972   0.970
    Inflammatory        0.550   0.170

**15 new guards** in `tests/test_hebcs_mathematics.py`; 91 passed across the
surrounding slice; `ruff --select F,E9` clean.

### STILL OPEN

- **4a. The Ω explanation paragraph is hardcoded and factually wrong.** It says
  three markers *"sit at or below the bottom of their own reference band"* for
  three values above the top, and prints RDW twice. It must be ALAFIA-written
  from facts through `finding_text`, like the wellness findings (OPEN_ITEMS 22,
  25). Not done.
- **4b. Stored Ω history is now non-comparable.** Every `wellness_scores` row
  written before today was computed the old way. Nothing has been re-based and
  the charts do not say so.
- **4c. `data_coverage` still reports 1.0** while two pathways show
  `measured 2/3`. The headline uses `coverage_with_derived`; the two numbers
  disagree on screen.
- **4d. The modelling question is untouched** — see TASKS 18.

---

## 28. Ω and Α were ONE number — the core failure — PARTLY FIXED 2026-10-12

Operator, verbatim:

> *"The HEBCS and wellness score MUST not be how well a condition is being
> managed. Management can have it's own measurement, but wellness is about the
> state of health. Someone with perfect overall conditions, perfect genetics,
> nutrition, blood test results, urine results, bowel state and currently on
> zero medication or therapy etc will score 100% (meaning they will live
> forever). A dead person scores 0 (they are dead). So we need a different
> measure for how well condition is managed (say Alpha) from Overall
> wellness/health (Omega). So far this work has been conflating both. That is
> the core failure."*

> *"A healthy person with zero conditions and demonstrated health records need
> no management score. A cancer patient or someone with luekamia require
> management score. Primary goal == patient specific surfacing. for example
> someone who has listed no condition need not see therapies. they still do
> despite my repeated request. HD patient need not see PD in navigation. Also
> omega must be responsive to patient and not force people without conditions to
> be measured as if they have conditions. This is the wheelhouse of adaptive,
> intelligent mathematical modeling"*

### The conflation was stated outright, in the product's own words

`wellness.py:680` shipped this sentence to the patient:

> *"A good score here describes how well that is being managed, not its
> absence."*

and the comment above it argued FOR the blend — *"a number that mixed 'managed
well' with 'has a terminal illness' could answer neither question"*. Right
observation, wrong conclusion: the answer is **two numbers**, not one with a
caption.

> ⚠️ **OPEN_ITEMS 27 made it worse.** It moved seven bands from population
> reference intervals onto KDIGO/KDOQI **treatment targets** so Ω would stop
> calling adynamic bone disease normal. Those are MANAGEMENT bands. The effect
> was that Ω — a score called *wellness* — started answering the management
> question on seven markers. A fix aimed at one half of a conflated pair
> deepens the conflation unless the pair is split first.

### The same panel, two questions

| marker | Ω — health band | Α — guideline target |
|---|---|---|
| Haemoglobin 11.3 | **0.614** anaemic | **1.000** on KDIGO's 10-12 |
| PTH 17 | 0.923 | **0.015** vs 150-600 |
| Kt/V 1.47 | **no band exists** | 1.000 |
| URR 74 | **no band exists** | 1.000 |
| **Creatinine 8.23** | **0.000** | not a target |

A patient can be gravely ill AND impeccably managed. That pair is the only
thing a clinician can act on, and one number reported neither.

**Measured on the reference record: Ω 42.14% health · Α 38.18% management.**

### What was fixed

- **`Biomarker.target_band` + `authority`** hold the guideline band; the
  primary band is the HEALTH band again, lab-anchored.
- **`Biomarker.scope` / `Pathway.scope`** — `health`, `management`, `both`.
  Kt/V and URR are management-only: a well person has no Kt/V, they have
  kidneys. `Dialysis_Adequacy` is a management PATHWAY and left Ω entirely —
  it had been contributing **97%** to "wellness" for a patient on dialysis six
  days a week, and still scored 0.86 off nPCR alone until the pathway itself
  was scoped.
- **`scoring_marker(b, band)`** is the whole separation in one function.
- **`compute_alpha()`** scores Α only where a guideline states a target, and
  returns `None` — never 0 — when there is nothing to manage.
- **CREATININE is scored at last.** It is in the published Table 3, on every
  panel in the record, and was absent from the engine. 8.23 against a well
  adult's 0.6-1.3 is **0.000** — the largest health fact about this patient,
  and Ω had no term for it while the treatment for it scored 97%.

> ⚠️ **A bug introduced and caught in the same session:** `compute_hebcs`
> rebuilds every `Pathway` when a lab range is supplied — which is every real
> call — and the rebuild dropped `scope=`, silently resetting it to "health".
> `Dialysis_Adequacy` would have walked straight back into Ω. §3ar one layer
> down: a field set in one place and reset in another. Pinned by
> `test_rebuilding_a_pathway_must_not_lose_its_scope`.

### Patient-specific surfacing — the repeated request, now honoured

`app/services/patient_surfaces.py` + `GET /users/me/surfaces`. The web sidebar
was a **static 62-entry list**, so every account saw HD Flowsheet, PD Report and
Therapy History whatever their record held. Measured on production 2026-10-12:

    2,035 therapy sessions — every one HEMODIALYSIS, one user
    ZERO peritoneal sessions for any account on the platform

So "PD Report" had never been a live screen for anybody, and sat one row under
the screen the single dialysis patient uses daily.

Verified: user 63 → 20 surfaces, `hemodialysis` offered (2,035 sessions),
**`peritoneal_dialysis` not offered**. Users 168/158/53 (no conditions, no
therapy) → 16 core surfaces, **therapies hidden entirely**.

- **The backend decides, the clients render** (§3). A surface rule is a
  clinical statement; three clients each applying their own would drift.
- **Data beats the absence of a diagnosis.** A surface holding the patient's own
  records is never hidden, whatever their conditions say (§3aa).
- **A therapy the map does not name still opens the group** — chemotherapy,
  infusion, phototherapy — so a cancer patient's sessions cannot be dropped by
  an incomplete lookup.
- **`CORE` is never gated**: you cannot hide the screen where a condition would
  be added.
- **`null` ≠ "offer nothing" on the client.** Until the answer arrives every
  entry shows, so a slow or failed request can never strand a patient in a
  sidebar missing their own records.

**7 new surfacing guards, 18 HEBCS guards, 122 passed across the slice; 279
frontend tests pass; ruff F,E9 clean.**

### STILL OPEN

- **28a. Α is gated by a BOOLEAN, not by the patient's actual conditions.**
  `has_managed_condition` defaults True and the endpoint does not yet pass it,
  so Α is still computed from ESRD pathways for everyone. Mapping
  condition → which pathways Α should score is the adaptive modelling in
  TASKS 18, not a flag.
- **28b. Ω still measures everyone against an ESRD decomposition.**
  *"omega must be responsive to patient and not force people without conditions
  to be measured as if they have conditions."* Not done. `ESRD_PATHWAYS` is a
  module constant applied to every account.
- **28c. Α is not exposed by any endpoint or client.** `compute_alpha` exists
  and nothing calls it. §3ar, deliberately recorded rather than left to be
  discovered.
- **28d. Mobile surfacing is NOT done.** The endpoint serves all three clients;
  only web filters on it. iOS and Android still show every entry.
- **28e. The Ω explanation paragraph is still hardcoded** and still says "how
  well that is being managed" — the conflation, in the sentence the patient
  reads (OPEN_ITEMS 27 §4a).

---

## 29. "Ω must be responsive to patient" — FIXED 2026-10-12 (step 1 of 3)

Operator: *"Also omega must be responsive to patient and not force people
without conditions to be measured as if they have conditions. This is the
wheelhouse of adaptive, intelligent mathematical modeling."*

Measured first (§0). Three production accounts, before anything changed:

    user 63    9,820 labs, 4 conditions, coverage 1.000   Ω 42.14%
    user 60       46 labs, 0 conditions, coverage 0.276   Ω 27.38%
    user 158       5 labs, 0 conditions, coverage 0.069   Ω 99.90%

The two condition-free accounts fail in **opposite directions**, and neither
failure was the pathway set.

### ⚠️ A healthy person's best possible urine result scored as a fatal one

User 60's `RBC = 0`, no reference range, drawn beside AMORPHOUS SEDIMENT,
BACTERIA, GRANULAR CAST, NITRITE, SPECIFIC GRAVITY, LEUKOCYTE ESTERASE and
SQUAMOUS EPITHELIAL CELLS. **It is a urinalysis.** Zero red cells per
high-power field in urine is the ideal finding.

It resolved to the Hematologic `RBC` biomarker — a blood count, band 4.6-6.2 —
and scored **0.000**: no red blood cells in the body. Being the only
Hematologic value present it carried the whole pathway to 0.001, and **a well
person's normal urine test reported them at 27% wellness** while four other
pathways sat at 1.000.

§3ab names the authority and it is not available: LOINC `SYSTEM` *"separates
serum from urine glucose"*, and `loinc_code` is populated on **34 of 9,871**
rows (0.3%), `category` on 1,018 and holding panel names rather than specimens.
So the **panel is the evidence**: two or more urinalysis-only markers on one
draw (specific gravity, nitrite, leukocyte esterase, casts, crystals, epithelial
cells) identify it, and an ambiguous analyte drawn with them is not scored as
the blood one. The quorum is two, not one — a lone "BACTERIA" could be a stray
row, and mis-identifying a blood panel would DISCARD a real haemoglobin.

### Coverage was computed, reported, and never used

User 158: **Ω 99.9% from five labs and two markers.** "You will live forever",
on 6.9% coverage. A score built on a fourteenth of its evidence was presented
identically to one built on all of it (§3aa).

- **`evidence_weight`** scales a pathway's share by how much of it was measured,
  so one marker cannot speak for a pathway of nine — user 60's Hematologic
  carried the full 0.15 off 1 of 9.
- ⚠️ **That is not sufficient on its own, and nearly shipped as though it
  were.** The geometric mean renormalises by `w_sum`, so scaling every weight
  by the same factor **cancels out**: user 158 still read 99.9% after it. Ω is
  now **WITHHELD** when the evidenced weight is not a MAJORITY of the declared
  construct — the same decision already taken for a patient with no labs, where
  returning 0.5 described nobody. Not a tuned threshold (§3az): "more than
  half", expressed in the framework's own weights. Exactly half is withheld
  too, and pinned — at a dead heat, whether the unknown half would change the
  answer is a coin flip.

### `pathways_for(conditions)` — what adapts, and what deliberately does not

- **The pathway set and the weights do NOT vary.** Ω is an absolute scale and
  the operator fixed both ends — *"perfect … will score 100% (meaning they will
  live forever). A dead person scores 0."* Two people with identical biology
  must score the same, so a decomposition that re-weighted itself per diagnosis
  would make Ω incomparable between two patients and between one patient and
  their own past. Weighting by disease is what Α is for. Pinned by
  `test_the_WEIGHTS_do_not_vary_by_condition`.
- **What adapts is which markers are EXPECTED.** PTH, ferritin, TSAT, nPCR and
  Ca×P are renal monitoring tests carrying `indicated_by=("renal",)`. A patient
  with no renal condition has no reason to have them drawn, and counting their
  absence as missing evidence reported a healthy record as incomplete — and,
  once coverage began bounding Ω, would have withheld their score for not
  holding tests nobody should have ordered.
- **A marker present is ALWAYS scored.** `indicated_by` governs absence only.

### After

    user 63    coverage 1.000   Ω 42.68%   unscored []
    user 60    coverage 0.208   Ω 99.90%   unscored [Hematologic, Inflammatory]
    user 158   coverage 0.083   Ω None     — withheld, a minority of the construct

**105 passed across the slice**, 9 new guards, ruff F,E9 clean.

> Three existing tests failed and **none was a regression** — each asserted the
> old behaviour: that two labs produce a score, and that half a construct is
> enough. Updated with the reason recorded in each, not silently widened.

### STILL OPEN — steps 2 and 3 of the operator's queue

- **29a.** Α is still gated by a boolean the endpoint does not pass, and
  `compute_alpha` has no caller (OPEN_ITEMS 28a, 28c).
- **29b.** Mobile does not filter on `/users/me/surfaces` (28d).
- **29c.** The specimen guard covers the urinalysis panel only. Other
  same-name-different-specimen pairs — serum vs urine protein, serum vs urine
  creatinine on a 24-hour collection — are not identified, and the real fix is
  the LOINC catalog §3ab already specifies and gates on a free-account
  download.

---

## 30. Α had no caller and its gate was a boolean — FIXED 2026-10-12 (step 2 of 3)

`compute_alpha` shipped in OPEN_ITEMS 28 and **nothing called it** — §3ay's
never-plugged-in sink, in the same session that cited it. Its gate was
`has_managed_condition: bool = True`, so Α scored anyone holding a haemoglobin
and the endpoint had only to forget one argument for a well person to be
measured against ESRD guidelines. **A default that is wrong when forgotten is
the §3ar shape.**

### A guideline applies to the population it was written for

`Biomarker.target_for` now names the disease each target belongs to. All seven
present targets are renal — KDIGO Anemia in CKD, KDIGO CKD-MBD, KDOQI
Hemodialysis Adequacy — so a patient with no renal condition has **no Α at
all**, which is the correct answer and never a zero.

Applying KDIGO's dialysis targets to someone without renal disease is §3am's
error pointed the other way: there, a renal patient was handed potassium's
4,700 mg general adult RDA.

`indications_for(conditions)` is now **one rule serving both scores** — it
decides which markers Ω EXPECTS and which targets Α may apply. Two rules would
drift, and the drift would be a patient scored against a guideline for a
disease they do not have.

### Measured live

    user 63  (ESRD)          Ω 42.68%   Α 38.18%
                             Hematologic 0.851 · Bone_Mineral 0.090 ·
                             Dialysis_Adequacy 1.000
                             OFF TARGET: PTH 17 -> 0.015, target 150-600
                                         (KDIGO 2017 CKD-MBD, 4.2.1)
    user 60  (0 conditions)  Ω 99.90%   Α None — "no condition on record has a
                                                  guideline target"
    user 158 (0 conditions)  Ω None     Α None

Ω and Α travel on one payload because they are meant to be read as a pair, and
the web card now draws both — with the REASON printed in Α's place when it is
absent, so a gap cannot read as a bad score (§3aa).

> ⚠️ **Two mistakes of my own, caught by guards rather than by me.**
>
> 1. I added the two new UI strings to `en.json` as **flat** keys
>    (`"Wellness.alpha_management"`) while every locale file is **nested**
>    (`{"Wellness": {"alpha_management": …}}`). `translate_catalogs.py` then
>    wrote the other ten languages correctly nested — so French, Yoruba and
>    Arabic would have rendered the label while **English showed the raw key**.
>    Found by spot-checking the written file rather than trusting the
>    translator's "2 translated" report (§0).
> 2. `test_every_language_carries_every_source_key` failed the moment English
>    gained a key the others lacked — §3aw's guard doing exactly its job, on the
>    exact mistake §3aw was written about (`37edcc7`, 96 web keys English-only).

**133 passed across the slice, 279 frontend, 44 i18n catalog tests, ruff clean.**

Two existing tests failed and neither was a regression: both called
`compute_alpha` with no conditions, which now correctly returns no score.

### STILL OPEN — step 3

- **30a.** Mobile does not filter on `/users/me/surfaces`, and iOS/Android do
  not render Α (28d).
- **30b.** `RENAL` is the only indication axis. A leukaemia or cancer patient
  gets no Α, because no oncology target exists yet — the mechanism is there and
  the guidelines are not.
- **30c.** The Ω explanation paragraph is still a hardcoded f-string and still
  says "how well that is being managed" — now provably the wrong sentence, as
  that is Α's job (27 §4a).

---

## 31. Mobile had neither the surfacing nor Α — FIXED 2026-10-13 (step 3 of 3)

§3: *"A feature is not done until web, iOS, and Android all have it… Verify each
platform by building it, not by reasoning that the change should compile."*
Both of the previous two steps shipped web-only.

### Navigation

`GET /users/me/surfaces` already served all three clients; only web filtered on
it. Now:

- **Android** — `MoreGridItem` gained `surface: String?` beside the
  `clinicianOnly` flag that was already there, and the Therapies tiles carry
  `hemodialysis` / `peritoneal_dialysis` / `therapy_other`.
- **iOS** — `HealthHubView` gates the Hemodialysis and Peritoneal Dialysis
  `NavigationLink`s on `offers(_:)`, loaded in `.task`.
- **Both treat "not yet known" as SHOW EVERYTHING.** A slow or failed request
  must never hide the screen holding a patient's own records (§3aa).

### Α beside Ω

`alpha_pct`, `alpha_off_target` and `alpha_reason` decode on both clients and
render next to Ω and coverage, with the off-target markers and the guideline
that set each. **Absent Α prints its REASON in place of the number**, never a
zero.

### What the builds and guards caught, that reading the code did not

- ⚠️ **Kotlin: `Smart cast to 'Set<String>' is impossible, because 'surfaces'
  is a delegated property.`** The filter lambda needed a local binding. A
  compile error, so only building found it.
- ⚠️ **Swift: `the compiler is unable to type-check this expression in
  reasonable time`** on the concatenated off-target line. Extracted to
  `offTargetLine(_:)` — and the first extraction landed in the WRONG STRUCT
  (`type 'HEBCSSection' has no member 'offTargetLine'`), which only the second
  build revealed.
- ⚠️ **Android lint `MissingTranslation`** and
  `test_every_language_carries_every_source_key` **independently** caught
  `condition_management` existing in English only — §3aw's exact failure, twice
  in two days. Filled through `translate_catalogs.py` for all ten languages
  (`Ìtọ́jú Àìsàn`, `إدارة الحالة الصحية`, `Gestion des conditions`).

### Verified

    iOS        ** BUILD SUCCEEDED **, 0 error: lines (iPhone 17 Pro simulator)
    Android    BUILD SUCCESSFUL, app-debug.apk 32,757,741 bytes at 07:47
               — the size CHANGED from 30,845,358 before the Α render, which is
                 what proves the rebuild carried the new code rather than a
                 cached one (§3bb)
    backend    90 passed
    frontend   43 files, 279 passed
    guards     51 passed — iOS presentation flags, typed decimals, i18n catalogs
               (run from a REPO-ROOT mount; inside backend-test they skip,
               saying so, and banking that green proves nothing — §3bb)

### STILL OPEN

- **31a.** `RENAL` is the only indication axis, so a leukaemia or cancer patient
  still gets no Α — the mechanism is built and the guidelines are not (30b).
- **31b.** The Ω explanation paragraph is still a hardcoded f-string and still
  says *"how well that is being managed"*, which is now provably Α's sentence
  (27 §4a, 30c). It also still reads "at or below the bottom of their own
  reference band" for values ABOVE the top.
- **31c.** Surfacing covers the Therapies group only. Pharmacy, Telehealth and
  the rest are still shown to everyone.
- **31d.** Production is many commits behind and none of this is deployed.

---

## 32. The hardcoded trap, measured — PARTLY FIXED 2026-10-13

Operator, on a screenshot of two nutrient-effect lines: *"highlighted message
stating effect has not been established or amount comes from automated sources
help no one and creates confusion."* Then, after I fixed that one message:
**"this is not about a particular medication or therapy --- the hard coded
trap"**.

Right, and I had walked into it: I replaced one hardcoded template with a map
of five.

### The message that prompted it

    "<agent> affects this, but how much it changes has not been established,
     so it is shown here and not added to your total."

Calcitriol and Calcium Carbonate both carried it against phosphorus — and
**those two push phosphate in opposite directions**. Calcitriol raises
intestinal absorption; calcium carbonate binds it in the gut. The patient read
one identical non-statement for both. The sentence described OUR uncertainty
about the MAGNITUDE while hiding the DIRECTION, which is known, stored, and the
only part they can act on. Measured: **21 of 26** `nutrient_effects` rows carry
a NULL magnitude, so that was the common path.

> ⚠️ **`INCREASES_REQUIREMENT` is now deliberately left unstated**, and that is
> a safety decision. It is the stored direction for **Calcitriol → phosphorus**
> and **Doxercalciferol → phosphorus**, whose own mechanisms read *"increases
> intestinal phosphate absorption; in renal disease, hyperphosphatemia must be
> prevented through dietary restriction"*. Rendering it as "you need more
> phosphorus" would tell a dialysis patient to eat MORE of the thing their
> limit exists to restrict — §3ac's *"a treatment changes the day's TOTALS, it
> never changes the LIMIT"*. The rows are mis-classified; it is latent only
> because every one has a NULL magnitude. **Not fixed — recorded (32a).**

### The trap, measured

A scan of every prose literal reaching a patient-facing field in `app/`:

    109   OBSERVATION — prose + a runtime value. Describes THIS patient, goes
          stale when the computation changes. The ratchet's subject.
    255   FIXED COPY — a constant. "Invalid or expired verification link".
          Routing those through a language model would be absurd; they belong
          in the i18n catalog, which §3aw already governs.

`tests/test_patient_prose_ratchet.py` holds it at 109 with **slack 0**, in the
shape `test_parser_hardcoding_ratchet.py` uses for the parser's 290 literals.

> ⚠️ **My first baseline was 96, and it was wrong — by the exact mistake §3ab
> warns about, one layer in.** The scan judged each f-string FRAGMENT:
> `f"Your potassium reached {v} today"` arrives as `"Your potassium reached "`
> (23 chars) and `" today"`, neither long enough to count, so every sentence
> built that way was **invisible to the thing counting them**. Caught by this
> file's own `test_the_scan_can_actually_see_an_observation` failing on its own
> example — not by reading the code. Joined first, the measured figure is
> **109**. §3av: run the scan, and then prove the scan sees what it claims to.

### Three wrong sentences removed from the Ω card

1. *"A good score here describes how well that is being managed, not its
   absence."* — **that is Α's job, stated inside Ω.** The conflation, printed
   for the patient.
2. *"N marker(s) sit at or below the bottom of their own reference band:
   Glucose 273, RDW 21.3, RDW 21.3"* — all three were **above the top**, and
   RDW appeared twice because it sits in two pathways. A sentence naming the
   wrong side tells a patient to raise a value that is already too high.
3. *"A pathway score is an average, so these do not show in it."* — stopped
   being true when that mean became geometric (OPEN_ITEMS 27). **A score that
   has changed and a caption that has not is how a true number acquires a false
   explanation.**

The paragraph now goes through `finding_text` — ALAFIA writes it locally, every
figure verified against the facts, with the corrected deterministic text as the
fallback. Live:

    Overall biological state from laboratory values shows omega 0.427, 43%,
    6 pathways scored; creatinine 8.23 and RDW 21.3 are above reference bands.

> ⚠️ **`/wellness/omega` took no language header at all**, so that paragraph
> was English for every patient whatever they chose (§3aw). Found by the render
> raising `NameError: language`, not by reading the signature.

### Verified

    backend    118 passed (incl. the new ratchet, 4 tests)
    frontend   43 files, 279 passed
    iOS        ** BUILD SUCCEEDED **
    Android    BUILD SUCCESSFUL, app-debug.apk 32,757,741 bytes
    ruff       F,E9 clean

A row carrying only a MECHANISM now renders on all three clients — gating on
`withheld` alone would have hidden it the moment the server stopped asserting a
direction it could not support.

### STILL OPEN

- **32a.** `INCREASES_REQUIREMENT` on a LIMIT nutrient is mis-modelled for four
  rows (Calcitriol and Doxercalciferol × phosphorus/calcium). Latent only
  because their magnitudes are NULL.
- **32b.** 109 observations remain hand-written. The ratchet stops growth; it
  does not lower the count. `notification_engine` (12), `wellness` (13),
  `nutrient_effects_day` (8), `active_response` (6) are the largest.
- **32c.** `_DIRECTION_LINE` is itself five hardcoded templates. They are
  labels for an enum rather than composed prose — the clinical content is the
  resolver-written `mechanism` — but the distinction deserves a decision rather
  than my assertion.

---

## 33. Α has a card of its own — 2026-10-13

Operator: *"since we are measuring A alpha, we need to surface the card in
wellness"*.

Α had been a third column beside Ω's score and data coverage, which reads as a
sub-measure of Ω. It is not one — it answers a different question, and the
layout said otherwise.

**A card of its own on all three clients**, after the pathway breakdown:

- the Α figure against its guideline targets,
- its own pathway bars (web),
- every off-target marker with its value, its target band, **and the guideline
  that set it** — a target with no authority is a number someone typed (§3bc),
- and when Α is absent, **the reason in words** rather than an empty gauge.
  Nothing to manage is not bad management, and a blank dial reads as a zero
  (§3aa).

The subtitle states the distinction the layout now carries: *"How well what you
live with is being held to the guidelines written for it. A different question
from how you are."*

> **Two dead controls removed on the way.** `Wellness.alpha_management` (web,
> 11 locales) and `condition_management` (Android, 11 locales) were the labels
> for the column Α no longer occupies, and nothing read either. Left in place
> they would be §3ar in the i18n catalog — a string translated into ten
> languages for a surface that does not exist. The Android orphan also had to
> be cleared from the ten `values-*` files, not just the source one.

### Verified

    web        bundle check: `alpha_card_title` present in the SERVED
               dist/assets/Wellness-*.js and index-*.js, not just in source
               (§4 — ask the served asset, never the build log)
    frontend   43 files, 279 passed
    backend    40 passed (ratchet still 109, slack 0)
    iOS        ** BUILD SUCCEEDED **, 0 error: lines
    Android    BUILD SUCCESSFUL, app-debug.apk 32,763,421 bytes
               (32,757,741 → 32,759,581 → 32,763,421 across the three builds,
                so each rebuild demonstrably carried its change)
    i18n       44 catalog tests + Android lint MissingTranslation clean;
               5 new keys translated into all ten languages on both platforms
    guards     51 passed from a repo-root mount

### STILL OPEN

- **33a.** The card's copy is fixed UI text in the catalog, which is the right
  home for it (§3aw) — but the SENTENCE a patient reads about their own Α is
  still the deterministic off-target line, not ALAFIA's. The Ω paragraph goes
  through `finding_text`; Α's does not yet.
- **33b.** Α has no trend. Ω has history on `wellness_scores`; nothing stores Α,
  so "is management improving?" cannot be answered — which is the question a
  management score exists to answer.

---

## 34. Every recommendation card rendered twice — FIXED 2026-10-13

Reported from the live screen: *"every card here is duplicated"*. Nutrition
showed **4** for two real recommendations, Fitness 2 for one, Sleep 2, Medication
2 — and the section counts agreed with the duplicates, so the doubling was
upstream of the layout.

**The API was innocent; the schema was not.** `/wellness/recommendations`
returned the same eight items twice:

    recommendations  [8]        the flat list, every item carrying `category`
    nutrition        [2]  ┐
    fitness          [1]  │
    sleep            [1]  ├─ the SAME eight items, split by category
    medication       [1]  │
    mood             [1]  │
    hydration        [1]  │
    general          [1]  ┘

Both mobile clients decode only `recommendations` and ignored the mirrors. The
single reader of those seven fields was `Wellness.jsx`, which pushed the flat
list and *then* looped the category keys — so **the duplicate field's only
reader was the code it broke.** §3ai's "two computations of one quantity must
not disagree", in the case where they agreed and were summed.

> The web loop also asked for a category the API never sent — `medical` — while
> missing two it did: `hydration` and `general`. A hand-written list of keys
> standing beside a payload that already names them, wrong in both directions
> and invisible because the extra copies merely looked like more cards.

Fixed in all three places rather than only the one that showed: the schema
carries one list, the endpoint stopped splatting `**recs`, and the client reads
`data.recommendations` alone. Measured after: `payload keys: ['date',
'recommendations']`, 8 items, **duplicates: NONE**.

> ⚠️ **The guard tripped over its own documentation.** The first version of
> `test_the_endpoint_does_not_splat_a_second_copy` grepped the function source
> for `"**recs"` — and failed, because the COMMENT explaining the removal
> contains that string. It now walks the AST for a real `**` keyword on the
> response construction. §3av: a scan is evidence only once it is shown to see
> what it claims to, and that one was reading prose rather than code.

**Verified:** 4 new guards (incl. one end-to-end against a seeded user counting
ROWS, because a dedupe bug that reports the right fields while returning the
same title twice is exactly the failure); 51 backend passed; 279 frontend;
ruff F,E9 clean.

### STILL OPEN

- ✅ **34a — CLOSED.** Removing seven response fields is a wire change, so §3's
  standard is to verify by BUILDING rather than by reasoning that both clients
  ignore them. Run 2026-10-13: iOS `** BUILD SUCCEEDED **`; Android
  `BUILD SUCCESSFUL` with `app-debug.apk` **byte-identical at 32,763,421** and
  its earlier timestamp intact — Gradle recompiled nothing, which is itself the
  evidence that no Android source references the removed fields. Together with
  both models declaring only `date` and `recommendations`, that is measurement
  rather than inference.

---

## 35. The patient declares the therapy; the app stops guessing it — 2026-10-13

Operator: *"Only PD patients must see PD. Let user add Therapy types in
Condition and profile. Same as other health conditions. use condition to
determine the Therapy switch."*

Surfacing decided which therapy screens to offer from two things, and **both
failed the patient who most needs them**:

1. **Sessions on record** — correct evidence, useless to someone starting
   dialysis next week. They need the flowsheet BEFORE their first session,
   which is exactly when the record holds none.
2. **A hand-typed keyword dict.** `_CONDITION_HINTS` matched condition text
   against `("peritoneal", " pd ", "capd", "ccpd")` and `("hemodialysis",
   "haemodialysis", "end-stage renal", "esrd", "dialysis")`. §3an's forbidden
   shape — *"covers only the condition someone happened to think of, cannot say
   why, has no source, never improves, and goes stale silently"* — **deciding
   which clinical screen a patient could reach.** A condition recorded as
   "ESKD" or "renal replacement therapy" matched nothing; one reading "history
   of dialysis" matched everything.

`chronic_conditions.therapy_types` (migration `aq001`, additive, dev only) is
the declared fact, entered the same way the condition is. Put on the CONDITION
rather than the user because a therapy treats something: `users.therapy_types`
would say a person "is a hemodialysis patient" with no statement of what for,
and could not express someone on dialysis for ESRD who later has chemotherapy
for a cancer.

> ⚠️ **`ConditionView` had no such field, and nothing failed.** `for_user` read
> `getattr(condition, "therapy_types", None)` off the canonical view —
> `getattr` with a default cannot raise — so **every declaration was silently
> dropped** and a patient who had said they are on PD was offered no PD screen.
> §3am's *"wrong column names, for the third time"*: `get_medications`
> serialised with dose-log column names against a `MedicationView` and reported
> "no medications taken" for a patient with four. Caught only because a test
> asserted the outcome rather than the plumbing.

> **A behaviour CHANGE, not just a fix.** A condition that declares no therapy
> now opens no therapy screen, where the keyword dict used to open HD for
> anything whose name contained "dialysis". Sessions still win when nothing was
> declared — data beats a missing declaration exactly as it beats a missing
> diagnosis (§3aa) — so no existing patient loses the screen holding their own
> history. Pinned by `test_sessions_still_win_when_nothing_was_declared`.

Validation lives in `_normalise_condition`, which **create and update share**,
so the rule cannot land on one path and miss the other — the half-wiring that
left `session_drugs` ten months behind (§3av). Unrecognised names are dropped,
never repaired: correcting what someone wrote about their own treatment invents
a clinical fact.

> ⚠️ **The response schema declares a list and the column stores a string**, so
> `from_attributes=True` would hand pydantic a `str` and fail every row —
> 200ing only for a user with NO conditions, the one case with nothing to
> validate. That is §3ai precisely, where `metadata` raised one
> ResponseValidationError per row and the page told a user holding 18
> notifications that they had none. A `field_validator(mode="before")` splits it.

### Verified

    backend    73 passed across surfaces, clinical_sources, clinician board,
               condition flags, HEBCS and the prose ratchet
    frontend   279 passed
    i18n       44 catalog tests; 10 new keys in all ten languages
    migration  `alembic heads` reports ONE head (aq001_condition_therapies),
               applied to dev; 5 existing conditions all NULL — nobody has
               declared anything, and inventing a modality from their condition
               text is the guess this column exists to replace
    ruff       F,E9 clean

> ⚠️ **Two guards tripped over their own documentation, in one day.** The
> recommendations guard grepped for `"**recs"` and matched the comment
> explaining its removal; this one grepped for `"_CONDITION_HINTS"` and matched
> the docstring explaining ITS removal — twice, because I wrote a comment about
> the first mistake and then repeated it. Both now ask the module (AST /
> `hasattr`) rather than reading prose. §3av.

### STILL OPEN

- **35a. Profile does not expose it.** The operator asked for "Condition and
  profile"; only the Conditions form has the control.
- **35b. Mobile cannot set it.** iOS and Android render the surfacing but have
  no therapy selector, so a phone-only patient cannot declare a modality.
- ✅ **35c. Shipped 2026-10-14** — `aq001` and `ar001` both applied. See 39a.

---

## 36. Profile and mobile can declare a therapy — 2026-10-13 (closes 35a, 35b)

OPEN_ITEMS 35 shipped the declared-therapy field web-only, so a phone-only
patient could not say what they are on — and therefore could not reach the
screen for it. §3: a feature is not done until web, iOS and Android have it.

- **iOS** — `ConditionFormView` gains a Therapies section; `ChronicCondition`
  and its form model carry `therapyTypes`, with the coding key added to BOTH
  `CodingKeys` blocks (the struct and the form each declare their own — missing
  one would decode silently as nil, §3av's field that the form submits but
  never declares).
- **Android** — a checkbox group in `ChronicConditionsScreen`, with
  `therapyTypes` on the model.
- **Profile** surfaces the declared therapies READ-ONLY and links to the one
  screen that edits them. A second edit form for one field is two forms to keep
  in step — §3as's *"two front doors is worse than one broken one"*, where the
  signup flow shipped beside the old one and nobody could tell which they
  wanted. The line also says what the setting DOES, so the connection between
  declaring a therapy and seeing its screen is not left invisible.

> ⚠️ **Android sends `therapy_types` even when EMPTY.** A field the form shows
> but only ever sends when non-empty cannot be UNSET: ticking a box, saving, and
> then unticking it would leave the old value stored and the screen still
> offered. That is §3av's "a field the form submits but never declares erases
> itself", from the other side — and the asymmetry is why the clearing path
> needs stating rather than assuming.

### Verified

    iOS        ** BUILD SUCCEEDED **, 0 error: lines
    Android    BUILD SUCCESSFUL — APK 32,763,421 → 32,767,801 → 32,771,425
               across the model, selector and translation builds
    frontend   279 passed
    backend    26 passed
    i18n       51 guards + 44 catalog tests; Android lint MissingTranslation = 0;
               10 Android and 2 web keys translated into all ten languages
    ruff       F,E9 clean

### STILL OPEN

- ✅ **36a. Shipped 2026-10-14.** `aq001` + `ar001` applied; `/api/health`
  reports `7cb62da`. It was indeed one decision and not a routine push — Ω/Α
  went with it, so **every patient's wellness number moved today** and stored Ω
  history is no longer comparable with what follows it (32b).
- **36b.** Nothing BACKFILLS. The 5 existing production conditions will arrive
  with NULL, so a current dialysis patient keeps their screens through their
  sessions (data beats a missing declaration) but sees no therapy declared
  until they set one. Inventing it from their condition text is the guess this
  work removed.

---

## 37. "no change occured" — dev was serving a two-day-old bundle — 2026-10-13

Operator, with the sidebar still showing PD Report: *"i'm looking at dev no
change occured"*.

**§4, exactly as written.** `docker compose ps` reported
`frontend  Up 47 hours (healthy)` — the container keeps serving the image it
started with, so the build succeeds, the status says `Up`, and :8080 serves the
old bundle for days. Proven by asking the SERVED ASSET rather than the build
log:

    before   /assets/index-Dd8_iRhX.js   "users/me/surfaces" -> 0 occurrences
    after    /assets/index-sDguN3Yh.js   "users/me/surfaces" -> 1

`docker compose build frontend` **and** `docker compose up -d frontend`. The
build alone is the trap, and I had been verifying backend behaviour through
`docker compose exec` the whole time, which never touches the served bundle.

### And the rule underneath it was wrong

Operator: *"user can choose the therapy or therapies they undergo and only
those therapies are surfaced in navigation."*

Measured on user 63 once the bundle was current: declaring **only** peritoneal
dialysis still offered the HD flowsheet, because 2,035 HD sessions opened it
regardless. **A declaration the navigation overrules is not a choice.**

    declared anything  ->  the DECLARATION decides which treatment screens
                           appear — it states what the patient undergoes NOW
    declared nothing   ->  fall back to the sessions on record; we cannot tell,
                           and stranding a patient away from their own
                           flowsheet is the worse error

Verified across every combination on the reference record:

    nothing declared                  hemodialysis (2,035 sessions)
    "peritoneal_dialysis"             peritoneal_dialysis ONLY — HD retired
    "hemodialysis"                    hemodialysis
    "hemodialysis,peritoneal_dialysis" both
    "chemotherapy"                    therapy_other — both dialysis screens gone

> **Therapy History is offered either way, and that is the half that keeps this
> safe.** A patient who moved from haemodialysis to PD stops needing the HD
> flowsheet and never stops owning their HD record. Losing the screen you work
> in daily and losing your past are different harms, and only the first is what
> a declaration should cause (§3aa). The history line cites the SESSIONS, not
> the declaration that replaced them.

### Is hemodialysis in ICD-11? Yes — and I nearly said no

Asked while looking at the therapy selector. `search_icd11("hemodialysis")`
returns one row — *Haemodialysis-associated pruritus* — and I was about to
conclude ICD-11 cannot express the modality. **A full scan of the bundled WHO
catalog (35,370 rows, 71 mentioning dialysis) says otherwise:**

    QB94      Care involving dialysis
    QB94.0    Preparatory care for dialysis
    QB94.1    Care involving extracorporeal dialysis      <- haemodialysis
    QB94.2    Care involving peritoneal dialysis
    QB42      Dependence on renal dialysis
    QB95.1    Physical rehabilitation
    QB95.7    Occupational therapy or vocational rehabilitation
    QB96      Contact with health services for radiotherapy session
    QB97      Contact with health services for chemotherapy session for neoplasm

So hemodialysis is not a DISEASE code — there is no "Hemodialysis" condition —
but the QB branch is a coded vocabulary for *care involving* a therapy, and it
covers most of `TherapyType`. **I built the option set as a hand-written enum
without checking whether WHO already codes it**, which is §3ad's own rule
(`never type an ICD code from memory`; the catalog is the authority) applied to
the wrong half of the problem — I obeyed it for conditions and not for the
therapies beside them.

Searching a truncated result set and generalising from five rows is §0 twice in
one answer: the first search was evidence about the search, not about ICD.

### STILL OPEN

- **37a. `therapy_types` carries no ICD code.** `QB94.1` / `QB94.2` / `QB96` /
  `QB97` / `QB95.x` exist and the stored value is ALAFIA-private, so a declared
  therapy is not interoperable the way a condition's `icd11_code` is. Whether
  to carry the code alongside the enum — the enum also covers immunotherapy,
  infusion and transfusion, which QB does not — is a design decision, not a
  cleanup.
- **37b.** Nothing re-renders the nav when a therapy is declared in the same
  session; `/users/me/surfaces` is fetched once on mount. Declaring PD then
  navigating shows the old set until reload.

---

## 38. The therapy option set is WHO's, not mine — 2026-10-14 (closes 37a)

Operator, on my own admission that I had built the option set as a hand-written
enum without checking WHO: **"against the rule"**.

Correct, and it is the rule I had been citing all day. §3ad: *"Never type an
ICD code from memory. The catalog is GENERATED from WHO's published MMS
linearization… `tests/test_icd11_catalog.py` fails the build if a hand-written
alias points at a code that is not in the file."* I obeyed that for conditions
and ignored it for the therapies sitting beside them — then mirrored the
hand-typed list into **four files**: the backend, web, iOS and Android.

WHO codes it. Verified against the bundled 2025-01 MMS linearization before a
single line was written on top of them:

    QB94.1   Care involving extracorporeal dialysis            -> hemodialysis
    QB94.2   Care involving peritoneal dialysis                -> peritoneal_dialysis
    QB96     Contact with health services for radiotherapy session
    QB97     Contact with health services for chemotherapy session for neoplasm
    QB98     Blood transfusion without reported diagnosis
    QB95.1   Physical rehabilitation
    QB95.4   Psychotherapy
    QB95.5   Speech therapy
    QB95.7   Occupational therapy or vocational rehabilitation
    QB9C     Allergen immunotherapy

**`GET /chronic/therapy-options`** serves the set, reading every TITLE out of
the catalog at runtime. So no therapy name is typed anywhere in this codebase,
and the three clients stopped carrying copies:

- the backend enum mirror is gone (`TherapyType` still records what a SESSION
  was — a different fact from what a patient declares they undergo),
- `THERAPY_TYPES` deleted from `ChronicConditions.jsx`,
- `ConditionFormView.therapyOptions` deleted from iOS,
- the Android `therapyOptions` list deleted,
- and with them **22 label strings across 11 web locales and 11 Android
  locales** — translations of names WHO already publishes. The APK shrank
  32,771,425 → 32,765,929, which is the removal showing up as bytes.

Stored values are codes now. Anything written during the one day the enum
existed still READS (`_LEGACY_TO_CODE`), because a declaration made yesterday
must not stop working, and nothing writes those forms any more.

> **Selecting WHICH codes offer a surface stays in the source, and that is a
> different kind of decision.** `THERAPY_CODE_SURFACE` maps a code to a SCREEN
> NAME — routing, not vocabulary. Inventing what a code MEANS would be the
> violation; choosing which of WHO's codes this product has a screen for is
> not.

### Guards

`test_every_offered_therapy_code_EXISTS_in_the_WHO_catalog` is the same check
`test_icd11_catalog` already applies to condition aliases, now applied to these.
`test_the_LABELS_come_from_WHO_and_are_not_written_here` compares every served
title against the catalog, so a title typed beside a code — a second source of
truth that drifts from the first — fails the build.

### Verified

    backend    147 passed (23 surfacing, incl. 4 new catalog guards)
    frontend   279 passed
    iOS        ** BUILD SUCCEEDED **, 0 error: lines
    Android    BUILD SUCCESSFUL; lint MissingTranslation = 0
    i18n       44 catalog tests + 51 cross-platform guards
    served     dist carries BOTH calls, checked inside the container rather
               than from the entry bundle — ChronicConditions is a LAZY chunk,
               so grepping index-*.js alone reported 0 and would have read as
               "not shipped" (§4: ask the served asset, and know which asset)

### STILL OPEN

- **38a.** Phototherapy and generic infusion therapy have **no Q code** —
  measured, not assumed — so they cannot be declared at all. The previous
  hand-typed enum could express them. That is a real loss, and the fix is a
  decision about whether a non-coded therapy may be declared alongside coded
  ones, not a silent re-addition.
- ✅ **38b.** Shipped 2026-10-14 with `ar001`. See **39a** for what was
  verified in the production schema.
- **38c.** The nav still fetches `/users/me/surfaces` once on mount, so
  declaring a therapy does not re-render it until reload (37b). → **39b**,
  where it is now worse: a patient who states "not on this" watches the screen
  they just retired stay on screen.

> **38 itself was not the end of it.** The operator's reply to this item —
> *"hard-coded enum for therapy will need a comprehensive list with items
> zeroed out (no impact) when not present (like a switch)"* — named two faults
> this item introduced: the set above is **10 of the branch's 31 codes**, and
> membership cannot express a stated zero. Both fixed in **39**.

---

## 39. A set cannot hold a zero — the therapy switch — 2026-10-14 (closes 38, closes 35's enum line)

Operator: **"hard-coded enum for therapy will need a comprehensive list with
items zeroed out (no impact) when not present (like a switch) and a mechanism
for compounded therapies. current model lacks comprehensive list and does not
include switch mechanism."**

Both faults are real and both were measured before anything was written.

### Fault 1 — the list was CURATED, not comprehensive

Item 38 replaced a hand-typed enum with WHO's codes and then named **10** of
them. Asked of the bundled 2025-01 MMS linearization, the branch those ten came
from holds **31**:

    QB4   (7)   Dependence on aspirator / respirator / renal dialysis /
                artificial heart / wheelchair, + other and unspecified
    QB94  (6)   Care involving dialysis — preparatory, extracorporeal,
                peritoneal, other, unspecified
    QB95  (12)  Cardiac, physical, alcohol, drug, psychotherapy, speech,
                orthoptic, occupational/vocational, tobacco, + other and
                unspecified
    QB96  (1)   radiotherapy session        QB97 (1)  chemotherapy session
    QB98  (1)   blood transfusion           QB99 (1)  apheresis
    QB9A  (1)   preparatory care            QB9B (1)  palliative care
    QB9C  (1)   allergen immunotherapy
    --------------------------------------------------------------------
    32 codes derived from the catalog, against 10 written down

**Picking ten of thirty-one is typing them with extra steps.** It covers the
therapies someone happened to think of (§3an), and a patient on apheresis,
cardiac rehabilitation, tobacco rehabilitation or palliative care could not say
so at all. `THERAPY_BRANCHES` now declares ten ROOTS, each with a stated reason,
and `therapy_codes()` asks the catalog for the members. Adding a therapy means
WHO published one — not that somebody edited this file.

> ⚠️ **The first predicate silently dropped six of them.** `_in_branch` tested
> `code.startswith(root + ".")`, which is right for `QB94 -> QB94.1` and wrong
> for `QB4 -> QB40`: ICD-11 children are `ROOT.N` for a stem code and `ROOTx`
> for a block. The "comprehensive" set quietly lost every dependence code and
> reported a confident 26. Found by PRINTING the derived set and counting it,
> not by reading the predicate (§3av). Pinned by
> `test_a_three_character_root_still_matches_its_children`.

> **Four of the ten "reasons" were labels, and a test refused them.**
> `"apheresis"`, `"palliative care"`, `"blood transfusion"` restate WHO's own
> title, which the catalog already supplies. A reason nobody can audit is a
> curation decision in disguise, so each root now says why it is care the
> patient RECEIVES. The test asserts a length, which is crude and caught it.

> **`QB9Y`/`QB9Z` are excluded at the TOP level and the `.Y`/`.Z` members
> INSIDE a root are kept.** Not a contradiction: "Care involving dialysis,
> unspecified" is a real statement — on dialysis, modality not recorded — and
> refusing it would force a guess between two screens. A bare `QB9Z` says only
> that a contact happened.

### Fault 2 — absence meant two things at once

`chronic_conditions.therapy_types` is comma-separated membership. A code was
present or absent, and **ABSENT MEANT "not receiving this" AND "nobody ever
asked"**. That is §3at's checkbox exactly — *"A checkbox cannot record three
states… 'absent', the finding that needs to shout, was indistinguishable from a
box nobody had touched"* — applied here to a patient's whole therapy picture,
on the axis that decides which clinical screen they can reach.

`condition_therapies` (migration `ar001`, additive, **dev only**) is the third
state's home:

    no row                never asked          -> unknown, nothing inferred
    receiving = false     explicitly not on it -> a measured ZERO, no impact
    receiving = true      undergoing it        -> contributes, opens its screen

`receiving` is `NOT NULL` deliberately: a row exists only because somebody
answered, so the column never has to carry "unknown" as a third value — the
absence of the row carries it. A nullable boolean would recreate the confusion
one level down.

A stated zero **overrules the legacy column**, which could never say "no".
Precedence in `for_user`: the switch table where it has an answer, the legacy
column only where the switch is silent, sessions only when nothing was
declared. Therapy History is offered either way — losing the screen you work in
daily and losing your past are different harms, and only the first is what a
declaration should cause.

### The compounding mechanism

`regimen` — therapies sharing a label are given as ONE treatment, so a reader
can tell a combination from a coincidence. `regimens()` groups them.

> ⚠️ **It asserts nothing about effect, and that is the point.** Which
> combinations have clinical MEANING is not decided here: naming an interaction
> is a clinical claim, and inventing one is what §3an forbids. A zeroed member
> is never part of a current regimen — a compound is what the patient is
> actually given.

### The three clients

All three had a checkbox, so all three could express only the third state.
Each now draws three choices per therapy, grouped by branch, with the regimen
field appearing only on a therapy that is ON.

`group`/`group_title` travel on the option payload so **no client reads a code
prefix to decide which branch a code belongs to** — that would be the client
deciding what a code means, the §3ad violation this whole item exists to undo.
`QB4` is a block and carries no title of its own in the linearization, so its
heading is the shared word-prefix of its own members ("Dependence on") rather
than a phrase anyone typed.

> **The therapy write is a SECOND request and deliberately not fatal to the
> first.** A switch belongs to a condition that must exist first. Losing a
> therapy answer is bad; losing the condition the patient just typed because a
> therapy write failed is worse (§3c's argument for saving the meal before
> estimating it). Its failure is REPORTED on all three — web keeps the form
> open, iOS and Android say so — because silence would leave the patient
> believing they declared a treatment the navigation will not reflect (§3aa).

> **An OMITTED entry is left alone, never cleared.** The client may be editing
> one switch, and reading an absent key as "not receiving" would turn every
> partial save into a silent retraction of everything else on the condition —
> §3av's "a field the form submits but never declares erases itself", from the
> other side. Returning to *Not answered* REMOVES the key, because a client
> cannot express "unknown" by sending false.

> **Nothing writes `therapy_types` any more.** Two homes for one fact is the
> drift this codebase keeps paying for, so all three clients stopped sending
> the key — and stopped CARRYING it: it is gone from web's `formData`, from
> iOS's `ChronicConditionCreate`, and from Android's payload. Not sending it
> leaves what is stored, which is what keeps a declaration made yesterday
> readable. The RESPONSE models keep the field; it is what the server returns.

### Guards

`tests/test_condition_therapy_switch.py` (12, over real HTTP) and 9 added to
`tests/test_patient_surfaces.py`. The ones worth naming:

- the comprehensive set is branch-derived, ≥30 codes, and includes four the
  curated ten could not express;
- a three-character root still matches its children (the `QB4` bug);
- `receiving=false` retires a screen while an absent row leaves it unknown —
  the two states are distinguishable in the payload, not merely in the table;
- a stated zero overrules the legacy column;
- `receiving=true` on ANY condition wins (on dialysis for ESRD is on dialysis);
- a code outside the WHO catalog is refused BY NAME, and `GB61.5` — a real
  code that is not a therapy — is refused too, so format checks alone cannot
  put a diagnosis on the therapy axis;
- `receiving` is required with no default, because a default of false would
  make an omitted field read as a measured zero;
- a switch is upserted, never duplicated (the unique constraint is real
  protection: two rows for one code would let whichever was read first win);
- another patient's condition is **404 on both routes**, not 403;
- and the end-to-end one: the switch reaches `/users/me/surfaces` and a stated
  zero retires the screen. Without it the table is something nothing reads
  (§3ar).

### Verified, 2026-10-14

    backend     197 passed — 32 surfacing (9 new), 12 switch (new), plus the
                §3aa guard, readable-sessions, clock rollover, ICD-11 catalog,
                condition-nutrition and no-hardcoded-thresholds
    frontend    279 passed (43 files), incl. the hardcoded-text extractor
    i18n        44 catalog tests; lint MissingTranslation = 0
    ruff        F,E9 clean on every changed backend file
    iOS         ** BUILD SUCCEEDED **, 0 error: lines
    Android     BUILD SUCCESSFUL; app-debug.apk 32,774,929 bytes (was
                32,765,929 — the size CHANGING is what proves the rebuild
                carried the new code rather than reporting a cached one)
    mobile      7 passed from a repo-root mount — the iOS presentation-flag
      guards    and typed-decimal guards SKIP inside backend-test (§3bb)
    served      /assets/index-l6xnaVqb.js on :8080 carries the new strings,
                after `build` AND `up -d` (§4: a running container keeps
                serving the image it started with)
    route       PUT /chronic/conditions/1/therapies answers 403, not 404 — it
                is mounted. Not exercised against dev PHI on purpose; the
                suite is the behavioural evidence

### Translation

8 web keys and 8 Android strings, translated into all ten languages through
`translate_catalogs.py` (0 refused), and the retired `therapy_types_help`
removed from all 11 catalogs on both platforms so no entry survives without an
English source behind it.

> **The iOS export surfaced a 65-string backlog nobody had noticed.** iOS
> catalogs are only refreshed when somebody runs `xcodebuild
> -exportLocalizations`, so `i18n/ios/en.xliff` was stale and
> `test_catalogs.py` was comparing against it — green, while 65 literals from
> earlier work shipped English-only in ten languages: the whole hospital-history
> screen (§3bb), the Α card's "Condition management (Α)", the labs tri-state
> ("Abnormal", "In range", "Not assessed"), "Given during treatment — already
> on your record." All 65 are now translated and imported, and iOS rebuilt
> clean afterwards. **A catalog test can only see what the export last put in
> front of it** — §3aw's "a matching language LIST is not a matching CATALOG",
> one layer further out.

### STILL OPEN

- ✅ **39a. SHIPPED 2026-10-14.** Deployed `7cb62da`; the migration job
  (`alafia-migrate-2sbf7`) took production `ap001_nutrient_quotas` →
  `ar001_therapy_switch`. Asked of the database afterwards, not of the log:
  `condition_therapies` carries `receiving boolean NOT NULL default false`,
  `UNIQUE (condition_id, therapy_code)` and `FK … ON DELETE CASCADE`;
  `chronic_conditions.therapy_types` exists and is nullable. **0 rows in each**
  — correct, because nothing backfills (36b) and inventing a modality from a
  patient's condition text is the guess this replaced.

  ⚠️ **This item ALSO claimed `ao001` and `ap001` were dev-only, and they were
  not.** The live `alembic_version` read `ap001_nutrient_quotas` *before* this
  deploy: both shipped on 2026-10-10 with `2a96a38`, and these notes went stale
  the moment that deploy ran. DEPLOY.md §3 warns about exactly this — *"a
  revision in prose goes stale the first time anyone deploys and nobody
  notices, because the deploy still works"* — and it has now happened in
  OPEN_ITEMS as well as in DEPLOY.md. **Ask the database.**
- ✅ **39b. FIXED 2026-10-14** — one signal per platform, announced by every
  writer and keyed into the fetch. Closes 37b and 38c with it. See **41d**.
- **39c. Phototherapy and generic infusion therapy still have no Q code** (38a)
  — the comprehensive list does not fix that, because the catalog does not hold
  them. Whether a non-coded therapy may be declared beside coded ones is a
  decision, not a silent re-addition.
- ✅ **39d. FIXED 2026-10-14** — Α reads `condition_therapies`, and so does Ω's
  expected-marker set. A declared therapy GRANTS an indication axis; a stated
  zero is reported and never enters the arithmetic. See **41a** and **41b**.
  What remains is that only the renal axis exists to score against (**41f**).
- **39e. `regimen` is free text.** Two patients on the same compound will write
  it differently, so grouping is per-patient and nothing can aggregate across
  records. Correct for now — a controlled vocabulary of regimens is a clinical
  claim and WHO does not publish one — but it bounds what 39d can do with it.
- ✅ **39f. FIXED 2026-10-14** — all three clients collect both dates, each
  with an idiom that leaves an untouched field EMPTY rather than stamping
  today. One limit remains stated rather than guessed: `receiving = false` with
  no `ended_on` cannot tell "never was on it" from "stopped, date unknown".
  See **41c**.

---

## 40. The deploy of 2026-10-14 — what reached patients, and what did not

`7cb62da`, 13 commits, `680863a..7cb62da` on main. Production had been on
`2a96a38` (built 2026-10-09, deployed 2026-10-10), so this release carried
**everything since** — it was never a routine push.

### Verified, by asking rather than reading

    migration job   alafia-migrate-2sbf7   successfully completed
    prod DB         ap001_nutrient_quotas -> ar001_therapy_switch
    code head       alembic heads = ar001_therapy_switch        ← equal, as §4 requires
    /api/health     version 7cb62dabd585658ea705967933a0ae62d645e5c0
    /api/ready      database ok, 13.9 ms
    revisions       backend 00239-v9p, identity 00118-6ml, frontend 00115-56n
    public          subscription/plans 200, auth/csrf-cookie 204
    new routes      chronic/therapy-options 401, users/me/surfaces 401,
                    conditions/{id}/therapies 401 GET / 403 PUT (CSRF)
                    — 401/403 and never 404 is what proves them MOUNTED
    served bundle   /assets/ChronicConditions-BjibXQPz.js on alafia.app carries
                    the `/therapies` call and `therapy_unanswered`, and no
                    longer carries the retired `therapy_types_help`
    schema shape    condition_therapies: receiving NOT NULL default false,
                    UNIQUE (condition_id, therapy_code), FK ON DELETE CASCADE
    row counts      condition_therapies 0, chronic_conditions.therapy_types 0

### What this changed for every patient on the platform

- **Ω and Α are now two numbers.** Ω is health; Α is how well a condition is
  managed. The reference record's Ω moves **0.781 → 0.421** with Α at 0.382.
  **Stored Ω history is not comparable with anything computed after today** and
  nothing on the screen says so (32b, still open).
- **Navigation is patient-specific.** A patient with no condition no longer
  sees therapy screens; an HD patient no longer sees PD.
- **Five Ω arithmetic faults** are corrected (§3be): stale analytes, a
  population reference interval used as a treatment target, an arithmetic mean
  inside each pathway, one-sided bands, and a zeroed pathway that raised the
  score.

### What did NOT reach patients, stated rather than implied

- ⚠️ **The mobile SWITCH is in the repo and not in anybody's hands.** The
  shipped TestFlight build and the distributed APK still draw the old checkbox
  and still post `therapy_types`. That is why the legacy path was kept and why
  `for_user` reads the column where the switch is silent: an old client's
  declaration still lands, still resolves through `_LEGACY_TO_CODE`, and still
  opens the right screen. What a shipped app **cannot** do is state a zero.
  Closing it needs an App Store build and an APK, not a backend change.
- **Nothing backfills, deliberately** (36b). All 5 production conditions arrive
  with every therapy UNANSWERED, which is the honest state: nobody has asked.
- **The smoke script's AI checks were SKIPPED, not passed** — they need a
  bearer token for `dew@6igma.com`, which this session does not hold. The
  script says so itself rather than printing green, which is the whole reason
  it says it (§4: a token-less green run is what missed a month-long AI
  outage). **`/api/v1/admin/health` was not called**, so the vision-corpus
  size, the configured AI backends and the email provider are unverified on
  this release.
- **`QUOTA_RESOLVE_ENABLED` is still false** (§3bc), so the quota clock did not
  start and `times_confirmed` stays 1.
- **39b–39f are untouched** by shipping: the nav still fetches surfaces once on
  mount, nothing scores a therapy, `started_on`/`ended_on` have no client,
  `regimen` is free text, and phototherapy still has no Q code.

---

## 41. The switch has a consumer — Α reads it, and the nav re-asks — 2026-10-14

Closes TASKS 20a, 20b and 20d; closes **39b**, **39d** and **39f**. The switch
shipped that morning as a table nothing consulted — §3ar's dead control on the
axis the operator asked for, so the stated zeros had nowhere to go.

### 41a — a DECLARED therapy is better evidence than a diagnosis's spelling

`indications_for` decided the axis from condition TEXT against a hint list:

    RENAL = ("renal", "kidney", "dialysis", "esrd", "ckd", "nephro")

**"ESKD" matches none of those**, so a patient on dialysis for end-stage kidney
disease could be refused every renal guideline over four letters. That is the
same §3an shape as the `_CONDITION_HINTS` dict this whole line of work began by
deleting — it had simply moved one function along.

A therapy is a STATEMENT, and WHO titles it. So the therapy's own catalog title
goes through the SAME hints:

    QB94.1  Care involving extracorporeal dialysis   -> renal
    QB42    Dependence on renal dialysis             -> renal
    QB96    …radiotherapy session                    -> no axis, correctly

**No code→axis table was added, deliberately.** A second hand-typed clinical
mapping is one more thing to keep in step (§3an), and WHO's wording is an
authority where mine is not. It follows that adding an axis means adding a key
to `_INDICATION_HINTS` and the therapy half comes free — or does not come at
all, which is right while nothing is tagged to score for it.

> ⚠️ **A stated zero must NEVER remove an axis, and getting this backwards
> would be the harm.** A patient with ESRD who says they are not on dialysis is
> pre-dialysis CKD — still renal, because the condition says so. The zero is a
> fact about the REGIMEN, not about the disease. Therapies therefore only ever
> ADD: the failure mode of adding is measuring a marker the patient holds, and
> the failure mode of subtracting is withholding a guideline from the person
> being worked up for it.

**Ω gets the same evidence.** `pathways_for` takes `therapies` too, because
`indications_for` is deliberately one function serving both scores and handing
it to one caller only would reinstate the drift it exists to prevent — KDIGO
applied to a patient whose PTH the same request calls unexpected. Measured: a
declared `QB94.1` makes exactly `CaxP Product`, `Ferritin`,
`Iron Saturation (TSAT)` and `PTH (Intact)` expected, and removes nothing.

### 41b — the regimen is REPORTED, never scored

Α alone is a verdict with no statement of what is being managed, and a reader
cannot then tell a poorly-managed patient from one whose treatment nobody
recorded. `compute_alpha` now returns `therapies_receiving`,
`therapies_stated_zero`, `regimens` and `indication_because` — and they travel
**even when `alpha` is None**, because a patient on apheresis has no Α today
and drawing nothing would read as "no treatment on record" for someone under
active treatment (§3aa).

> **Nothing here enters the arithmetic, and a test pins it.** Α is identical
> with two stated zeros present and absent. Whether a patient SHOULD be on a
> therapy they declined is a clinical judgement; asserting it would be the
> §3an violation. The zero is reported beside Α so a clinician can draw that
> conclusion themselves — the arithmetic never draws it for them.

**All three clients draw it**, which is the half §3bc got wrong on the quota
work (*"the figure reaches all three clients; the citation does not"*). A
payload no client draws is a dead payload, so the Α card on web, iOS and
Android shows what is being given, what was declined, the regimen label, and
why the guideline applies at all.

### 41c — the dates, and a limit stated rather than papered over

`started_on`/`ended_on` existed on the API with no client collecting them, so a
therapy that STOPPED could only be expressed by flipping a switch — losing
WHEN, which is what makes a history interpretable.

- **Web** `type="date"`, which leaves itself blank — nothing stamps today onto
  a clinical field nobody filled in.
- **iOS** `Toggle` then `DatePicker`, the house idiom for an optional date
  (§3bb). A `DatePicker` alone cannot be empty, so it would record a date
  nobody supplied on every row.
- **Android** a typed `YYYY-MM-DD`, matching the diagnosis-date field already
  on that form. A half-typed value **refuses the save and names it** rather
  than being discarded (§3av) or sent as a 422 the patient cannot act on, and
  `isIsoDay` rejects `2026-02-31` — shaped like a date and not one.

> ⚠️ **`receiving = false` with no `ended_on` cannot distinguish "never was on
> it" from "stopped, date unknown."** That is a real limit of a switch plus two
> optional dates, and it is recorded rather than guessed: an absent date means
> NOT RECORDED. Inventing a fourth state to hold it would be §3at's collapse
> pointing the other way.

> **The date format is pinned, not localised.** iOS formats with
> `en_US_POSIX` + Gregorian + UTC: §3aw records that the app's language is a
> SwiftUI `\.locale` choice and NOT `Locale.setDefault`, so a formatter reading
> the ambient locale would render an Arabic-Indic or Buddhist-calendar date
> into an API payload. §3bd measured what the same mistake costs on a typed
> number.

### 41d — the navigation re-asks (closes 37b, 38c, 39b)

Open through three deploys, and the switch made it worse: a patient could state
*"I am NOT on this"* and watch the screen they just retired stay on screen,
which reads as a control that did nothing (§3ar).

One idiom per platform, each with precedent in this codebase, and all three
carry **no payload** — the surface rule is the SERVER's (§3), so the only
correct response to "something changed" is to ASK AGAIN. A client that
recomputed the set locally would be a second implementation of a clinical
decision.

    web       window event `alafia:surfaces-changed` -> Layout refetches
    iOS       NotificationCenter `.alafiaSurfacesChanged` (as §3ah's 402 does)
    Android   SurfaceRefresh.epoch, a StateFlow the LaunchedEffect keys on

> **A counter, not a one-shot event, on Android.** `MainTabView` keys a
> `LaunchedEffect` on the epoch, so a bump re-runs the fetch and a collector
> that was not listening at the moment of the write still converges. A
> `SharedFlow` emission would be dropped while the Conditions screen is in
> front — which is exactly when every one of these writes happens.

Announced from **create, update, the therapy write AND delete** on all three.
Deleting the last condition retires screens as surely as adding one opens them,
and its therapy rows go with it (FK CASCADE).

### Verified, 2026-10-14

    backend     91 passed — 18 NEW in test_alpha_reads_therapies.py, plus
                surfacing (32), the switch over HTTP (12) and the Ω maths (29)
    schema      the four new fields survive HEBCSScoreResponse end to end,
                checked by building the response from a real compute_alpha
    frontend    279 passed (43 files)
    i18n        51 — catalogs plus the iOS presentation-flag and typed-decimal
                guards, run from a repo-root mount (§3bb: they SKIP inside
                backend-test and say so)
    ruff        F,E9 clean on hebcs_engine, wellness api + schema, the new test
    iOS         ** BUILD SUCCEEDED ** ×3 (model, card, after the l10n import)
    Android     BUILD SUCCESSFUL; lint MissingTranslation = 0; APK
                32,774,929 -> 32,782,021 bytes (the size CHANGING is what
                proves the rebuild carried the code)
    translated  web 2 + android 7 + iOS 6 new strings × 10 languages, 0 refused
    served      dev :8080 rebuilt (`build` AND `up -d`): the ENTRY carries the
                surfaces event (it lives in services/surfaces.js, a shared
                module), ChronicConditions-Ca5ASfPf.js carries the /therapies
                PUT and started_on, Wellness-B3Dk39cM.js carries
                therapies_stated_zero. Checked per chunk — §4's "ask the served
                asset" plus knowing WHICH asset (§38 paid for that once)

> ⚠️ **One of my own assertions measured nothing, and the test caught it.**
> `test_BOTH_scores_read_the_same_evidence` first read
> `assert gained & renal_markers or gained` — which passes on ANY gain. The
> four marker names are now pinned exactly, read out of the container. §3av,
> again, in the test written to prove the thing works.

### STILL OPEN

- **41e. `regimen` is free text** (39e, TASKS 20c). Two patients on the same
  compound will spell it differently, so grouping is per-patient and nothing
  aggregates across records. Correct for now — a controlled vocabulary of
  regimens is a clinical claim and WHO codes therapies, not combinations — but
  it bounds any cross-patient use of compounding.
- **41f. Only the RENAL axis exists.** `_INDICATION_HINTS` has one key, so a
  leukaemia patient on chemotherapy still gets no Α: the mechanism now reads
  their declared therapy and there is nothing tagged for it to score. That is
  the honest state and it is a guideline-sourcing job (§3bc's resolve-cite-store
  shape), not a code gap.
- **41g. Phototherapy and generic infusion therapy still have no Q code** (38a,
  TASKS 20e) — an operator decision about whether a non-coded therapy may be
  declared beside coded ones, and how it is stored so it can never be mistaken
  for a WHO code.
- **41h. Not deployed.** This is dev only; production is on `7cb62da`.

---

## 42. Two eliminations at 00:40 and 10:30 both read "08:00 PM" — 2026-10-14

Reported with a screenshot: the dashboard's Elimination Events showed two bowel
movements at the SAME time, beside an Elimination Log on the next screen
showing the true 00:40 and 10:30.

**Three faults in one line of `Dashboard.jsx`, and the first is why the other
two were never visible:**

    time: e.time || e.log_date,  …  ...e

1. **The API sends `log_time`.** There has never been a `time` field on
   `BowelMovement` or `VomitingLog` — both declare `log_date` and `log_time`.
   So `e.time` was always `undefined` and every row fell back to its DATE.
2. The render then did `new Date("2026-10-14").toTimeString()`. An ISO
   **date-only** string is parsed as **UTC midnight**, and `toTimeString`
   prints **local** — so in EDT every event read `20:00` → "08:00 PM".
   **The time shown was a function of the VIEWER'S TIMEZONE, not of the
   event.** In a UTC browser the same rows would have read 12:00 AM.
3. `...e` came AFTER the computed keys, so had the API ever grown a `time`
   field it would have silently overruled them. The spread goes first now.

**Reproduced before changing anything** (§0), running the exact old expression
against the real row shape in a node container at `TZ=America/New_York`:

    log_time 00:40:00 -> merged.time "2026-10-14" -> RENDERED 08:00 PM
    log_time 10:30:00 -> merged.time "2026-10-14" -> RENDERED 08:00 PM
    new Date("2026-10-14").toTimeString() = 20:00:00 GMT-0400

> ⚠️ **It is in the INITIAL COMMIT**, measured with `git log -L`. It did not
> regress and no deploy introduced it — production has rendered every
> elimination event at the viewer's midnight since the app shipped. **I said
> mid-investigation that the in-flight deploy would "ship the wrong times" and
> offered to kill it; that was wrong**, and asking git rather than inferring
> from "the bug is in the tree I am deploying" is what settled it. §3ad's shape:
> *it did not regress; it was never right.*

**iOS and Android bind `log_time` correctly and always have.** §3av again:
when one platform eats data and two do not, the two are the specification.

### What changed beyond the field name

- **A row with NO time now says so.** §3av measured the cost of the opposite
  choice on **3,662** `intradialytic_readings`, where an import defaulted a
  missing timestamp to midnight and "the measurement is real and the time is
  not" had to be reconstructed from the population afterwards.
- **Sorting is by the real time**, and untimed rows go last rather than
  claiming the top of the day. The old sort compared the DATE, so every event
  on one day was in arbitrary order — a third consequence nobody had noticed
  because every row also displayed the same time.
- **`buildEliminationEvents` and `fmtTime` are exported** so a test can reach
  them. The defect lived in the COMPOSITION of the two — a correct transform
  meeting a formatter that turned a date into a time — so a test of either
  alone would pass on a half-fix. The end-to-end assertion pins
  `['12:40 AM', '10:30 AM']` and rejects `'08:00 PM'` by name.

> **My own patch script broke the file first.** The anchor consumed `=>` and
> the replacement gave back `=`, so `const fmtTime = (t) = {` reached esbuild.
> Three test files went red including the i18n extractor, which is the suite
> doing its job — and the reason to run it before believing a scripted edit.

### Verified

    web         290 passed in 44 files (was 279/43 — 11 new)
    i18n        44 catalog tests; 3 web strings × 10 languages, 0 refused
    served      dev :8080 rebuilt (`build` AND `up -d`) and ASKED:
                Dashboard-BWdE0kfi.js reads `log_time` and contains ZERO
                `toTimeString`; the entry carries "Chat with Alafia"

### STILL OPEN

- **42a.** The same dashboard renders meals, medications and appointments
  through their own time paths, and **none of them was audited here**. Only
  elimination was reported and only elimination was measured; a sweep of every
  `time`-shaped field the dashboard reads against the column each model
  actually declares is a separate job, and the static-check shape of §3ag
  (every `Model.attribute` must exist on that model) is what would catch it.
- **42b.** `GET /elimination/*` returns `log_time` as `"HH:MM:SS"`. Nothing
  states which timezone a patient's wall-clock entry belongs to, so the same
  row means different instants for a patient who travels. Today every client
  treats it as local wall clock, consistently — which is right for a diary and
  wrong for anything that correlates it with a lab draw or a dialysis session.

---

## 43. "Ask ALAFIA" became "Chat with Alafia" — TASKS 19a only — 2026-10-14

Operator, 2026-10-13: *"change AI prompt message to 'Chat with Alafia'. This is
more representative. So user can tell (prompt for action) or Ask (query for
information)."* Raised again 2026-10-14 with a screenshot of the sidebar still
reading "Ask ALAFIA".

**"Ask" understated a surface that WRITES.** §3am records that `log_meal` and
`log_medication` are live tools — a patient can tell it to do something, not
only ask it a question — so the label described less than the product does.
That is §3ar's dead control pointed the other way: the capability exists and
nothing tells the patient it is there.

    web      Layout.ask_alafia, Help.ask_alafia   -> "Chat with Alafia"
    iOS      PromptView .navigationTitle          -> "Chat with Alafia"
             MainTabView tab label "Ask"          -> "Chat"
             AIChatView placeholder               -> "Ask a question, or tell
                                                     Alafia to log something"
    Android  R.string.ask_alafia                  -> "Chat with Alafia"
             R.string.ask (tab label)             -> "Chat"
             R.string.ask_about_your_health       -> as iOS

A tab bar cannot hold "Chat with Alafia", so the short label carries the same
correction in one word. `R.string.ask` was checked for other callers first —
it has exactly one.

> **The KEY stays `ask_alafia`.** A key is an identifier; renaming it would
> churn 11 locale files and every review file for nothing the patient sees. The
> translator keys off the English SOURCE text, so changing the VALUE is what
> triggers retranslation in all ten languages — which is what was wanted.

### STILL OPEN — this is the label, and TASKS 19 is not the label

- ✅ **43a. 19b — CLOSED the same day.** All five domains have gated write
  tools, and the gate itself — which had no reader at all — is wired and fails
  closed. See **44**. The label and the capability now agree.
- **43b. 19c — Ω and Α are unreachable by the assistant.** No tool returns the
  wellness or management score, so "how am I doing?" is answered from raw rows
  while the product's own composite sits unseen.
- **43c. 19d — one loop, not two code paths.** TELL and ASK must remain a
  difference in what the model decides to call, never a fork (§3am: two copies
  is how the Anthropic streamer silently dropped every tool turn).

---

## 44. A gated, secure set of write tools — TASKS 19b — 2026-10-14

Operator, on the five domains that had none: **"a gated, secure set of write
tools."** Raised the moment the label became "Chat with Alafia" — which invites
a patient to TELL the assistant things it could not then record (43a).

### ⚠️ The gate mattered more than the tools, and it was not wired

`WRITE_TOOLS` has existed since the write path shipped, declaring which calls
may alter a patient's chart. Measured across the repo: **its only reader was
its own test.** `run_tool` dispatched `log_meal` for any caller that named it.

That is §3ay's never-plugged-in sink on the most consequential switch in the
module, and §3ar's dead control in the place it is worst — a thing that looks
like a safeguard. **Adding five more writers behind it would have multiplied
the defect by five**, so the gate was wired first.

    run_tool(..., allow_writes=False)        ← the default, and it FAILS CLOSED

A caller that does not ask gets a read-only assistant. Forgetting the flag
makes the product less capable; it can never silently make it able to write.
That is §3at's lesson about which way a default fails, applied to a capability
rather than a checkbox — and the opposite of what was there, where forgetting
to consult the set left every write open.

**Exactly one place opens it**: the patient's own conversation, on BOTH the
buffered and the streaming path. A static guard pins that — by AST, not grep,
because a string search matches the comment that explains the flag, which is
the mistake two guards here have already made (§3av). A second guard asserts
that **nothing else in `app/` turns writes on**, the same shape as
`test_clinical_sources`'s ALLOWED set.

### What "gated" means, enforced rather than hoped for

| | |
|---|---|
| **capability** | `allow_writes` defaults False; the gate fails closed |
| **contract** | each tool declares the exact columns it may set (`_WriteSpec`). No `**kwargs`, no `setattr` loop over whatever the model invented |
| **validation** | scales and lengths checked at the boundary and **refused by name**, never clamped |
| **idempotence** | every write checks for the row it is about to insert, scoped to this patient and day |
| **scope** | `user_id` comes from the session and is never an argument the model supplies |
| **closed set** | `NEVER_WRITABLE = {vitals, labs}`, declared with the reason |

> **Refused, never clamped.** Turning a severity of 50 into 10 records a
> clinical value nobody stated — §3am's *"a bad argument that becomes a wrong
> clinical number is worse than an error, which the model can act on and
> retry"*. Same for a text longer than its column: truncating stores a clinical
> sentence with its end cut off, which reads as a complete statement.

> **Vitals and labs stay read-only, and the asymmetry is the point.** A reading
> comes off a device the patient read; a result comes from a laboratory with a
> reference range and a provenance this path cannot supply. Writing either
> would make the assistant a measurement source, and a transcription slip would
> become a clinical observation nobody can trace back to a cuff.

### The tools do not INTERPRET — that is the subtle half

`log_elimination` stores the patient's words and **does not set
`blood_present`**, even when the description says "bloody". `elimination_text`
already reads those words for every consumer, and §3ba's rule is that a SET
column wins while only NULL falls through to the text. Writing the boolean too
would put a second interpreter beside the first, which §3ai forbids: two
computations of one quantity must not disagree.

Likewise `log_sleep` does **not** derive `total_hours` from bedtime and wake
time — a night crossing midnight is exactly the §3av case where every client
rolled over for display and none for storage, and four production dialysis
sessions stored a negative duration as a result. And `log_fitness` derives no
calories: that needs weight, heart rate and a formula nobody here has cited
(§3az).

**A number is written only where the patient stated one.** The instructions say
so outright — *"NEVER choose a number for them"* — because a mood score, a
severity, a Bristol number and an hours-slept figure are the patient's to give,
and §3am's "inference proposes; it never writes" was written for a far less
subjective field than mood.

### Verified

    backend     105 passed across the two AI suites; 142 across the wider slice
    guards      3 of the 26 new tests FAIL with the gate opened and pass with
                it closed — proven by temporarily flipping the default and
                running. The other 23 are coverage of new code; calling all 26
                guards would be §3al's mistake
    ruff        F,E9 clean on record_tools, ai_conversation, api/ai
    consistency all 13 tools carry a spec, a label and a dispatch entry, and
                every `log_*` is in WRITE_TOOLS — asked of the module, not read

> **An existing test was a change detector, not a guard.**
> `test_only_meals_and_medication_are_writable` asserted the exact membership
> `{"log_meal", "log_medication"}`, so it went red the moment the set grew and
> said nothing about the property that matters. It now asserts invariants that
> hold however many writers exist: every writer is a `log_*`, no reader is ever
> a writer, and vitals and labs are absent.

### STILL OPEN

- ✅ **44a. NOT REQUIRED — operator decision, 2026-10-15:** *"Patient consent
  for write is not necessary."* The capability stays a CALLER property. No
  column, no migration, no Profile control. Recorded so the next session does
  not re-propose it as an oversight.
- ⚠️ **44b. I described this wrongly, and the operator corrected it.** I wrote
  that "nothing is reversible" and implied a delete TOOL was the missing piece.
  **Correction and deletion already exist in the product.** Measured across the
  routers afterwards — all six domains carry both:

        elimination  PATCH/DELETE per type (bowel, urination, vomiting)
                     plus DELETE /all/{event_type}/{entry_id}
        mood         PATCH/DELETE /{entry_id}
        sleep        PATCH/DELETE /{entry_id}
        fitness      PATCH/DELETE /{log_id}
        nutrition    PATCH/DELETE /{log_id}
        medications  PATCH/DELETE /{med_id}, DELETE /dose-logs/{log_id}

  Operator: *"Delete tools already existing within the logs, so no new delete
  is required."* So the record IS correctable; what the conversation lacks is a
  route to those screens, and **no delete tool is wanted**. Stated as a
  decision rather than a gap. §0 again: I reported an absence I had not
  measured.
- **44c. The write is not announced anywhere but the reply.** A row appears in
  the record with no marker saying the assistant put it there. `log_meal` has
  had this since it shipped; five more writers make it worth a provenance
  column rather than a convention.
- ✅ **44d. VERIFIED 2026-10-15** — and it found a real defect. See **45**.

---

## 45. The model DOES call the write tools — and the run found a real defect

Operator, 2026-10-15: *"test/verify model can call."* Closes **44d**.

`tests/test_ai_write_tools_live.py` drives the REAL loop against a REAL model
with writes enabled, exactly as `/ai/chat` does, and asserts both the tool that
was called and the row that landed. **Deliberately not in CI** — every case is
a live generation, so it is opt-in like the docparse corpus harness (§3ab):

    docker compose --profile test run --rm -e VERIFY_AI_WRITES=1 \
        backend-test python -m pytest tests/test_ai_write_tools_live.py -q -s

It runs against the TEST database with a user it seeds itself, so no patient
record is near it — never the dev copy of production, which is real PHI.

### What answered, and what it did

**8 passed**, provider `anthropic / claude-haiku-4-5`, 1-2 rounds each. The
production order, which is the one worth verifying.

    "I slept badly last night, only about four hours. Log it."
        -> log_sleep          total_hours 4.0
    "record that I've been dizzy since this morning, about a 6 out of 10"
        -> log_symptom        severity 6, symptom kept whole
    "Log a bowel movement at 3pm today, it was loose."
        -> log_elimination    log_time 15:00, blood_present NULL
    "I walked for twenty minutes this morning — please log it."
        -> log_fitness        20 min, calories_burned NULL
    "Record my mood as a 3 out of 10 today, I feel low."
        -> log_mood           mood_score 3

**The three negative cases are the ones that matter:**

    "I've been feeling really low today. Can you note that?"
        -> NO tool call. "I need a mood score from 1 to 10 — where would you
           rate your mood today?"      ← it did not invent a number
    "My blood pressure was 150 over 95 this morning, log it."
        -> NO tool call. "I can't log blood pressure readings — vitals come
           from devices and are read-only."
    "How much did I sleep last night?"
        -> a READ, not a write

### ⚠️ The defect the run found: writable but not readable

That last case did **not** pass on the first run. The model called
**`log_sleep`** — because it was the only sleep-shaped tool that existed. The
write guard refused it (*"no sleep detail given — nothing was logged"*), so no
row landed and the final answer was correct, but the cause was an asymmetry
nobody had looked for:

    writable                          readable
    log_meal                          get_meals        ✓
    log_medication                    get_medications  ✓
    log_elimination                   get_eliminations ✓
    log_sleep                         —
    log_mood                          —
    log_symptom                       —
    log_fitness                       —

**Five domains gained a writer and four of them had no reader at all.** An
assistant that can record a patient's sleep and cannot tell them what it
recorded is §3am's failure in a new place: *the model does not lack
understanding, it lacks DATA* — and given only a write tool, it reaches for the
write tool.

`get_sleep`, `get_mood`, `get_symptoms` and `get_fitness` close it, and the
same question now calls **`get_sleep`**. That behavioural change is the proof,
not the reasoning. `test_every_writable_domain_can_also_be_READ` pins the pair
list so the next write tool cannot arrive alone.

> **A unit test could not have found this.** Everything was individually
> correct — the gate worked, the tool refused properly, the guards were green.
> The fault was in what the model could REACH, which only appears when a real
> model is asked a real question. §3al's "a unit test proves the function; only
> the wire proves the system", on tool selection rather than on a payload.

### A second find, from the guard written for the first

Extending `test_every_field_a_tool_reads_exists_on_its_model` to cover the four
new field tuples, I made it assert that **every** `*_FIELDS` constant appears
in its own pair list. It immediately named one nothing checked:
`_CORE_MEAL_FIELDS`. `NutritionLog` had been IMPORTED by that test since it was
written and never used — so the meal fields had never been compared to the
table. All ten are valid (measured), but they were unguarded the whole time.

> §3ag's lesson is that a static check beats behavioural tests here. The
> refinement: **it only beats them over what it actually reads.** A
> hand-maintained list inside a guard is a guard that silently stops covering
> new things.

### STILL OPEN

- **45a. One model, one run.** `claude-haiku-4-5` answered every case. §3am
  measured that `llama3.2:3b` cannot drive the tool loop at all and
  `gpt-oss:20b` can, so a dev run on Ollama is a different test and has not
  been done. The file prints the provider and model with every case precisely
  so a failure can be attributed.
- **45b. Nine phrasings is not coverage.** These are the obvious forms. "I
  didn't sleep at all", "my mood is in the gutter", "I was sick twice" and
  anything in another language are untested — and §3aw ships eleven languages.
- **45c. The negative cases depend on the PROMPT, not on a guard.** Nothing
  structurally prevents a future model from inventing a mood score; the
  instruction says not to and this run confirms the current model obeys. The
  tool requires the number, so the failure mode is a wrong number rather than
  an unasked question — which is the weaker protection of the two.

---

## 46. Several PDFs at once, each routed on its own — 2026-10-15

Operator: **"PDF import must support multiple PDF imports at the same time and
route them properly."**

Measured first: `parse-document` took one `UploadFile`; the web input had no
`multiple` and read `files[0]`; iOS pinned `allowsMultipleSelection = false`
and took `urls.first`; Android used `GetContent()` (singular). One document at
a time on every client.

### Each file becomes its OWN import, and that is the whole design

`POST /pdf/parse-documents` loops the existing single-file logic per file.
Merging a batch into one `DocumentImport` is the shorter code and breaks three
things that already work:

- **`discard` deletes exactly the rows ONE import created**, by the
  `imported_row_id` stamped on each staged row. Share a record between two
  reports and discarding the bad one deletes the good one's rows.
- **the content-hash check** resolves a re-uploaded file to the import it
  already made — §3ab's dedupe, which exists because re-importing after a
  parser fix produces contradictory duplicates.
- **`confirm` is per-import**, with the reviewer ticking rows per document.

Row routing is untouched: every staged row already carries its own
`target_table` (per-claim since 2026-10-11), so a visit summary feeding
conditions AND medications routes the same way in a batch as alone.

> **In-batch hash dedupe is separate from the stored one.**
> `find_existing_import` queries the database, and a row staged a moment
> earlier in the same transaction is not reliably visible to it — so the same
> PDF twice in one request would stage twice. A per-request map closes it.

> **One unreadable file never sinks the others.** Each result carries its own
> `ok`/`error`, and the batch reports `parsed`/`failed`/`duplicates` counted on
> the server — three clients deriving a summary is three ways to disagree.

### ⚠️ The defect a batch exposes: dedupe was a STAGE-TIME snapshot

Raised as a lead by a peer session reading the code; **verified by running it
before fixing** (§0). Two documents in one batch, both reporting albumin for
2026-03-14 with different values, both confirmed:

    albumin on 2026-03-14 was written 2 times: [4.1, 4.4]

Two contradictory readings for one date — exactly what §3ab describes and what
the dedupe exists to prevent. `_existing_labs` and the two `known` sets are
read when a document is STAGED, so a second document staged before the first
was confirmed saw a table that did not yet contain the first document's rows.
Both were marked `DEDUPE_NEW`.

**Sequential uploading mostly hid it** — confirming A put A's rows in
`lab_results` before B was ever staged. Multi-file import makes staging two
documents before confirming either the normal path, so the window stops being
an edge case.

`confirm()` now re-reads the live keys and checks each row immediately before
writing, updating the map as rows land (so a document repeating an analyte
within itself is caught too). All three targets, by the same keys their stage
steps use — analyte identity for labs (§3ax), folded name for medications and
conditions, so the two computations cannot disagree (§3ai).

> **Skipped, never overwritten.** Which of two readings is right is a clinical
> judgement, and §3ab's own instruction for a genuine correction is to delete
> first and re-import. The item records why so the reviewer can see it.

### ⚠️ A photo was parsed as text and reported as an empty document

The peer also noted the operator's screenshot had `IMG_0551.jpeg` selected — a
filename I could not read off the image. Verified by running a real JPEG
through the pipeline:

    doc_type: unknown   records: 0   error: None

So a patient who photographs their lab report got an **empty table and no
explanation** — §3aa on the surface where it means "this document contained no
results". `_refuse_unreadable` now answers **415** naming what the file is and
what to do instead, detected by **magic bytes** rather than extension or the
browser's content type (§0: read the bytes). In a batch the photo is refused on
its own and the PDFs beside it still import, which is what someone who picked a
whole folder actually needs.

### The clients

All three keep reviewing ONE document at a time with a switcher above it.
Reviewing five documents' rows in one scroll is worse to use, and it reuses the
existing review UI unchanged — only which document is active moves.

> **Ticks are keyed by import id on all three.** A single shared set would
> carry one document's selections onto the next one opened — confirming rows
> against the wrong report, which is the whole hazard of batching. Pinned on
> web by a test that switches documents and asserts the rows swap rather than
> stack.

> **Android recorded every import as `"report.pdf"`.** The filename was a
> constant in `createFormData`. Wrong on its own — the record keeps a filename
> so a row can be traced back to the paper it came from — and useless in a
> batch, where attributing a result to its file is the point. It reads
> `OpenableColumns.DISPLAY_NAME` now.

### Verified

    backend     88 passed across five import suites — 19 new, including the
                cross-document duplicate (which FAILED before the fix) and the
                photo refusal
    frontend    295 passed (was 290) — 5 new multi-document tests
    i18n        44 catalog tests; 2 strings × 10 languages, 0 refused
    ruff        F,E9 clean on every changed backend file
    iOS         ** BUILD SUCCEEDED **
    Android     BUILD SUCCESSFUL, lint MissingTranslation = 0, APK 32,782,817

### STILL OPEN

- **46a. A dialysis flowsheet parses and has nowhere to go.**
  `DIALYSIS_FLOWSHEET` is a recognised `doc_type`, but the only targets are
  `lab_results`, `medications` and `chronic_conditions` — there is no
  `therapy_sessions` target, so a flowsheet PDF ends in "read but cannot be
  imported". Whether a parsed flowsheet should create a `TherapySession` is a
  clinical decision, not a gap to fill quietly: §3at shows how much structure
  those rows carry (two clocks, two fluid figures, a tri-state thrill/bruit),
  and inventing a mapping would be the §3an violation. **Raised, not
  implemented.**
- ✅ **46b. CLOSED 2026-10-16 — and NOT via the vision path.** I proposed
  routing photos to §3a's vision model; the implementation went to local OCR
  instead, precisely because of the privacy surface named here. Tesseract runs
  in the container, so the question of whether a lab-report photo may reach a
  third party does not arise. See **47**.
- **46c. The batch is sequential on the server.** Twelve documents are parsed
  one after another in one request. Fine for a clinic visit's handful; a larger
  batch would want a job and a progress channel rather than a longer wait.
- **46d. iOS and Android were not run.** Both BUILD, and §3 is explicit that a
  build is not a verification. The multi-select, the switcher and the per-import
  ticks are unexercised on a device or simulator.

---

## 47. A photo of a report is a document now — 2026-10-16

Operator, on the upload screen refusing five JPEGs: **"We need to expand
acceptable uploads."** Five photos is a five-page report, and photographing one
is what a patient does. Refusing (46b) was better than the empty table it
replaced and was still the wrong answer.

`docparse/ocr.py` reads text and GEOMETRY out of an image, so the existing
layout parser handles it unchanged. The same path fixes a second thing:
`extract.py` has detected scanned PDFs as **`needs_ocr` since it was written**
and nothing could act on it (§3ar), so a scan failed exactly like a photo.

### Tesseract, not a vision model, and the reason is not performance

- **Nothing leaves.** §3al records that a lab-report photo carries the
  patient's name, address and record number in its header, that
  `scrub_payload` redacts a message only when its content is a string so image
  bytes *could never* be redacted, and that whether a photo may reach a third
  party at all is a product decision. Tesseract makes that decision
  unnecessary.
- **It cannot invent.** A vision model asked for a potassium value can produce
  a plausible one. §3ab exists because a wrong value in `lab_results` is
  indistinguishable from a real one forever after.

### ⚠️ Three faults found by measuring, two of them clinically dangerous

**1. A lost decimal point, at high confidence.** At a 300-dpi render of the
test fixture, the A/G ratio **`1.8` came back as `18`** — **at confidence 85**.
No confidence threshold catches that; the engine is confident and wrong. At 400
dpi it reads correctly under every `--psm` tried, which is why `MIN_DPI` is 400
and not a rounder number.

**2. A liver enzyme recorded as a mineral.** This is the one that matters.
Tesseract's DEFAULT segmentation reads a lab table **column-major** — the word
order runs `CODE LAB TEST NAME … RESULT 18 4.6 637H …` — so the layout parser
grouped only the LAST word of each test name:

    default / --psm 4   raw='PHOS'      -> Phosphorus            637.0 U/L
    --psm 6             raw='ALK PHOS'  -> Alkaline Phosphatase  637.0 U/L

Alkaline phosphatase is a liver enzyme in U/L with a reference near 46-116.
**Phosphorus is a mineral a dialysis patient is managed on**, in mg/dL, where
637 is impossible. The characters were recognised correctly every time; only
the grouping differed. `--psm 6` is therefore not a tuning preference —
changing it changes which analyte a row claims to be.

**3. My own design decision caused a variant of the same thing.** I first left
OCR boxes in PIXELS, reasoning that the parser only compares positions to each
other. **It does not**: §3ab records the name/value boundary at `x_mid 162.0`
and separates "a gap INSIDE a name (2.0 pt)" from "the gap to the real value
(29.0 pt)". At 400 dpi one point is ~5.5 pixels, so every one of those figures
was meaningless. Boxes are scaled to a 612-point letter page now, and the
measured geometry then matches the PDF path to within a point
(`ALK` at x0 68.0 both ways).

**With all three fixed, a photograph parses identically to the PDF**, analyte
for analyte:

    PDF    [('A/G Ratio', 1.8, 'Calc'), ('Albumin', 4.6, 'g/dL'),
            ('Alkaline Phosphatase', 637.0, 'U/L'), ('ACTUAL DAYS/WEEK…', 6.0)]
    PHOTO  identical

### Nothing from an image is pre-ticked

The protection is **not** a threshold — the `1.8` → `18` corruption scored 85.
Every row from an OCR'd document is staged **unticked**, with the reason on it,
so a person reads the value against the paper first. That is §3ab's own pattern
for a row that might be wrong — *"an implausible row arrives unticked with its
reason"* — applied to a whole document.

Placed in `stage()` where items are attached, so labs, medications, conditions
and any fourth target added later are covered by one line. Half-wiring is what
left `session_drugs` ten months behind.

### What is still refused

Expanding what is acceptable is not accepting everything. Word, Excel, zip,
audio and video are refused by name with what to do instead. A file named
`.pdf` whose bytes are neither a PDF **nor an image** is refused; one that is a
renamed photo is read.

### Verified

    backend     191 passed across nine document suites — 8 new OCR tests,
                and the refusal tests rewritten to the new contract
    frontend    295 passed
    i18n        44 catalog tests; 3 strings × 10 languages, 0 refused
    ruff        F,E9 clean on every changed file
    iOS         ** BUILD SUCCEEDED ** (picker takes .image; HEIC included)
    Android     BUILD SUCCESSFUL, lint MissingTranslation = 0
    image       tesseract 5.5.0 in the backend container

> **A fixture that is not the thing it claims to be tests the wrong path.** My
> first JPEG was a hand-written header plus zero bytes; Pillow refuses to open
> it, so the `.pdf`-that-is-not-a-PDF guard rejected it and the test failed for
> a reason unrelated to what it was testing. Built by Pillow now (§3at).

### STILL OPEN

- **47a. Five photos are five IMPORTS, not one five-page report.** Each file is
  its own `DocumentImport` by design (46), which is right for five different
  reports and wrong for five pages of one. Nothing merges them, and nothing
  asks. A patient confirming page 3 separately from page 1 is workable but not
  what they meant.
- **47b. Only English is installed** (`tesseract-ocr-eng`). A report in another
  script will not read, and §3aw ships eleven languages.
- ⚠️ **47c. TESTED, AND IT FAILED.** The operator supplied real photographs the
  same day — a five-page DaVita Treatment Details Report on a desk. **Every
  page produced 0 records.** See **48**: one cause was mine (I measured Photos
  *derivatives*, 1024 px on the long edge, not the originals), one was a real
  gap now fixed (rotation).
- ✅ **47d (rotation).** Fixed — see **48**. Deskew, perspective and glare are
  still untouched.
- **47e. A low-confidence word is recorded and not surfaced.** `ocr.py` keeps
  per-word confidence; nothing shows the reviewer WHICH values were least
  certain. Since every row is unticked anyway the practical cost is low, but a
  reviewer with ten rows would benefit from knowing which three to check first.

---

## 48. Real photographs: every page read NOTHING — 2026-10-16

47c said *"no real photograph has been tested"* and warned that none of the
fixture numbers should be assumed to carry over. The operator supplied real
photographs the same day. **They do not carry over.**

Six images, a five-page DaVita Treatment Details Report photographed on a desk:

    page1 (upright)  768x1024   method=ocr  type=dialysis_flowsheet  records=0
    page2 (rotated) 1024x 768   method=ocr  type=unknown             records=0
    page3..6                    method=ocr  type=unknown             records=0

**Zero records from every one.** Two independent causes, and the first is a
measurement error of mine rather than a defect.

### Cause 1 — I measured thumbnails, not photographs

The files were Photos **derivatives**: 1024 px on the long edge. A 12 MP phone
original is about 4032 px. Upscaling a thumbnail cannot invent detail that was
never captured, and the word list shows exactly that:

    page1  384 words, 196 above confidence 60
    sample: 'net', 'p2', 'gat?', 'ils', '(mee', 'tment', 'Detal', 'eport'

`tment`, `Detal`, `eport` is "Treatment Details Report" dissolving. The engine
is not misreading a legible page; there is no legible page.

> **I could not fetch the originals myself** — the Photos library is
> TCC-protected, and the derivative paths only reached me because the operator
> passed them through. **So the pipeline has still not been judged on a real
> photograph**, and nothing here should be read as evidence that it fails on
> one. It is evidence that it fails on a 1024-px thumbnail of one.

### Cause 2 — a sideways page read as NOTHING, and that was real

Several pages are rotated 90°, which is simply what happens to paper on a desk.
`--psm 6` assumes horizontal lines. Measured on the fixture, same page:

    before          after
    0deg    4        4
    90deg   0        4
    180deg  0        4
    270deg  0        4

Not degradation — **total loss**. Tesseract's own orientation detection gets
the angle right every time on a legible image (90→90, 180→180, 270→270), so
`_upright()` asks it and turns the page before reading.

> ⚠️ **It asks; it never assumes.** The guess carries a confidence, and on a
> degraded image it is noise: the 1024-px thumbnail of a genuinely sideways
> page scored **0.43 and answered "rotate 0"**. Acting on a guess that weak
> would turn UPRIGHT pages over and break imports that work today, so anything
> below `MIN_ORIENTATION_CONF` is ignored. A clean page scores 4.6-7.1.

### What went right, and it is the part that matters

**Nothing garbage reached staging.** Every page returned `ok=False`, zero
records and a stated reason. The patient is told the document could not be
read — not shown an empty table that reads as "this document contained no
results" (§3aa), and not given invented rows. 384 words of OCR noise produced
no clinical record at all.

That is the design working as intended under the worst input it has seen.

### Verified

    backend   177 passed across seven document suites — 6 new tests, including
              all four orientations and an unreadable-photo case
    ruff      F,E9 clean

### STILL OPEN

- **48a. The real test has not happened.** It needs **full-resolution exports**
  of those photographs — AirDrop or "Export Unmodified Original" rather than a
  Photos derivative. Until then the honest statement is "untested on a real
  photograph", exactly as 47c said.
- **48b. A page that is upright but WARPED is untested.** The operator's paper
  is curled and shadowed; rotation is the only geometric correction here. No
  deskew, no perspective correction, no glare handling.
- **48c. Nothing tells the patient WHY a photo failed.** "No measurements could
  be read" is honest and unhelpful — it does not distinguish "too blurry",
  "too small", "sideways and I could not tell", or "this is not a report".
  Word count and mean confidence are already measured and could say which.
- **48d. A dialysis flowsheet still has no target table** (46a). Page 1 of this
  very report classified as `dialysis_flowsheet` — so even read perfectly, it
  has nowhere to go. That decision is still the operator's.

---

## 49. The arm photographs had nowhere to go — and "log my rash" opens Mental Health — 2026-10-16

The operator's uploads on 2026-10-16 were **two different things**, and only one
was answered. Five photographs were pages of a DaVita Treatment Details Report
and drove §§47-48. **Two were photographs of an arm with skin lesions**, and
nothing in this session acknowledged them. They are not documents; the document
pipeline would have refused them correctly and told the patient nothing useful.

Asking the code what a patient can do with a photograph of their own skin:

### 49a. Neither phone can record a symptom at all

    /symptoms call sites   web 1   iOS 0   Android 0
    symptom screen files   web Symptoms.jsx (10,151 bytes, routed)
                           iOS  — none
                           Android — none
    symptom_logs (dev copy of prod)   4 rows / 2 users / 2025-10-29 .. 2026-10-09

§3 is explicit that a feature is not done until web, iOS and Android have it.
This is not a half-wired control (§3ar) or an unrouted page (§3ad) — on mobile
the screen does not exist, and `symptom_logs` has two writers, both reached only
from web (`api/symptoms.py:44`, `api/personalization.py:299`).

### 49b. A symptom intent is routed to MENTAL HEALTH on both phones

    IOS/ALAFIA/Views/Prompt/PromptView.swift:70     case "log_symptom": return .mentalHealth
    Android .../views/prompt/PromptScreen.kt:59     "/symptoms" to "mental-health"

So a patient who types *"I have a rash on my arm"* into the prompt hub is taken
to a mental-health screen on both platforms. The Android file's own comment
says *"Screens not yet on mobile fall back to the closest available one"* — and
mental health is not the closest thing to a skin lesion; it is a destination
that reads as a judgement about the person asking. §0's rule applies to a
fallback as much as to a diagnosis: where there is no right screen, say so
rather than choose a confident wrong one. **This cannot be repaired by editing
the map — there is nothing to point it at until 49a is built.**

### 49c. The photo path writes NOTHING

`POST /image-ai/symptom-from-image` (`app/api/image_ai.py:736`) takes **no `db`
dependency**, so it cannot write, and it does not: it returns a description plus
suggested `symptom_name` / `body_part` to prefill a form the patient must then
submit themselves. §3am already paid for this exact shape on the TEXT path —
*"Symptoms described to the AI are clinical data"*, where "dizzy, weak" informed
one answer and left no trace. A photographed symptom is in that state today, and
a skin lesion is the case where the IMAGE is the finding: a description of a
photograph is not the photograph, and a clinician comparing the lesion to itself
in three weeks needs the picture.

### 49d. The photograph leaves, and nothing can redact it

`_vision_ask` goes through `alafia_infer("vision", …)`, which is the production
order: **hosted vision first**, Ollama last. §3al records the unresolved half of
that — `scrub_payload` redacts a message only when its `content` is a string, so
*"the prompt beside the photo is never scrubbed, and the bytes never could be"*,
and it states the conclusion plainly: *"whether a photo or a recording may reach
a third party at all is a product decision, not something `scrub_pii` can make
safe."*

A photograph of a patient's arm is that decision in its sharpest form. Skin,
unlike a plate of food, is **identifying** — a tattoo, a fistula, a scar, a
wristband — and unlike the document path (§47, where Tesseract made the question
unnecessary because nothing leaves) there is no local reader here.
`local_only=True` exists for exactly this and is not set on the vision path.

**This is the operator's call, not a defect to fix quietly.** Three routes, and
they are not equivalent:

1. **`local_only=True` for symptom photos** — ALAFIA-operated inference only,
   no fallback. Honest, and in production that is a scale-to-zero GPU (§5), so
   it is slow and sometimes unavailable.
2. **Ask, per photo.** The AI consent gate (§3al) covers text processing; it
   does not say "a photograph of your body will be sent to a vendor".
3. **Keep the current order and say so** — in the app, in the privacy copy, and
   in the App Review reply, all three of which §3al records were rewritten once
   already because they described a local-only architecture that had changed.

### What was NOT found, having gone looking for it

The wellness score does **not** penalise a patient for being unable to log.
`symptom_component` returns `None` with `"no symptoms logged in this window"`
when the window is empty, so the domain is UNSCORED rather than zero — §3ba's
own rule, correctly applied. §3ba's symptoms 10.0 on the reference record came
from a real symptom the patient rated 9/10, not from absence. Checked before
writing, because the opposite would have been the tidier finding.

**Nothing here is implemented.** 49a is a feature on two platforms, 49b is
blocked on it, 49c is a schema and consent question (a symptom photo has no
column and no retention rule — §3a's food corpus is gated on
`allow_collective_insights` and a symptom photo is not food), and 49d is a
product decision. Queued, not started.
