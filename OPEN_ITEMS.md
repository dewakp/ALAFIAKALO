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

> ⚠️ **Not fixed: the garbage is still in production.** Nine sessions carry
> impossible weights and the dashboard average is wrong today. The validation
> stops new ones; existing rows need a cleanup pass, and per §3ab that is a
> delete-and-reimport decision rather than something to patch silently.

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
