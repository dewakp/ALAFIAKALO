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

`condition_nutrient_quotas` (migration **`ap001_nutrient_quotas`**, dev only):
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

- **Migration `ao001` is applied to DEV ONLY.** Production remains on
  `an001_vital_thresholds`. Ask `alembic heads`, never this line (§5).
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

