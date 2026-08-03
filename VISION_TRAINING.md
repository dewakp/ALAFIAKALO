# Food vision — storing, labelling, identification, quantity

How ALAFIA turns meal photos into a labelled training corpus, and what still
stands between that corpus and ALAFIAModel **Phase 5** (an on-device food
classifier).

> Written 2026-08-03. Everything described here is implemented and verified
> end-to-end on web, iOS and Android unless explicitly marked as remaining work.

---

## Why this exists

Phase 5 was blocked on something that reads like a detail and isn't: **nothing
was collecting training data.**

- `LabeledFoodImage` stored a 64-bit dHash and **discarded the image**. Correct
  for "have I seen this meal before?", useless for training a CNN.
- `/ai/vision` recorded nothing at all. The model's guess was shown, the user
  edited it, saved the meal — and the correction was gone.
- Net result: **1 labelled row across 77 users**, and zero images.

A year of that produces the same nothing. The fix is not a model; it is a
pipeline that retains what users already tell us.

## The loop

```
photo ──▶ recall?  ──yes──▶ the user's own label            (~76 ms, free)
           │no
           ▼
        vision model  ──▶ items + portions
           │
           ▼
        portion → grams                                     (per-100g nutrients)
           │
           ▼
        FoodTrainingSample  (prediction recorded)
           │
        user corrects
           ▼
        FoodTrainingSample.corrected_items  ── supervised training pair
           │
           └──▶ recall index updated → next identical photo short-circuits
```

## Data model

| Table | Role | Write pattern |
|---|---|---|
| `labeled_food_images` | per-user recall index (dHash, names) | **upsert** — one row per meal |
| `food_training_samples` | the corpus: photo + prediction + correction | **append-only** — one row per analysis |
| `media_assets` (`category='food_training'`) | the retained photo | one per retained sample |

Keeping these separate matters: recall wants one current row per meal, training
wants every sample ever taken. Collapsing them loses history.

### `correction_kind` — the label that makes the corpus queryable

| Value | Meaning | Trains |
|---|---|---|
| `accepted` | user confirmed the model | calibration |
| `item` | wrong food named | identification |
| `quantity` | right food, wrong amount | portion estimation |
| `both` | a food renamed *and* a shared food re-weighed | both |

Comparison is **keyed by food name, not positional**. Reordering the same foods
is not a correction, and a dropped item is an `item` change — not `both`. Getting
this wrong mislabels most of the corpus; it is covered by tests.

## Consent

Images are retained **only** when `PrivacySettings.allow_collective_insights`
("cross-user AI learning") is true. It defaults to **false**, and an absent
settings row counts as no consent — a meal photo is health data.

Without consent the sample is **still recorded** (prediction, correction and
accuracy stay measurable) with `media_asset_id = NULL` and no photo kept. Both
paths are verified.

## Quantity estimation

`app/services/portion_estimator.py` turns prose into grams, because nutrients are
per 100 g and `"1 medium sized slice"` is not a number. Resolution order, most
trustworthy first:

| Rule | Example | Result | Confidence |
|---|---|---|---|
| stated weight | `1 cup / 150 g` | 150 g | 0.95 |
| volume × density | `1 cup` jollof | 158 g | 0.60 |
| per-food unit weight | `1 medium carrot` | 61 g | 0.55 |
| container word | `half a plate` | 175 g | 0.35 |
| user correction | *(learned)* | exact | 0.95 |

Density is per food — `1 cup` of rice is 158 g, of spinach 72 g. Every result
carries the rule that produced it (`grams_basis`), shown in the UI.

**When it cannot tell, it returns nothing.** A guessed number silently becomes a
calorie count; a blank asks the user.

## API

| Endpoint | Purpose |
|---|---|
| `POST /ai/vision` | analyse 1–3 photos of one plate → items, grams, `sample_id` |
| `POST /ai/vision/feedback` | `{sample_id, items:[{name, estimated_grams}]}` → ground truth |
| `GET /ai/vision/corpus-stats` | Phase 5 readiness: samples, retained, corrected |

`/ai/vision` accepts `file` (single) **or** `files` (up to 3). Several shots of
one plate are analysed in **one** model call so a dish photographed twice is not
counted twice.

## Client parity

Implemented on **web, iOS and Android** — editable food + grams rows, a
"Confirm / correct" action, and the learned-recall banner.

| | Web | iOS | Android |
|---|---|---|---|
| grams + basis shown | ✅ | ✅ | ✅ |
| editable correction rows | ✅ | ✅ | ✅ |
| submits to `/feedback` | ✅ | ✅ | ✅ |
| recall banner | ✅ | ✅ | ✅ |

## Model choice

Use **llava**. `OLLAMA_VISION_MODEL` previously defaulted to `moondream` in
compose, which is a *grounding* model: asked for the food schema it answers with
bounding boxes (`{"top": [...], "size": ...}`) and never emits `items`, so every
photo failed. Verified against both.

The parser tolerates markdown fences, prose-wrapped JSON, and output truncated by
the token limit (it closes unterminated brackets). A reply that parses but has
the wrong shape fails loudly and names the model, rather than reporting "no food
recognised" and blaming the photo.

## What still stands between here and Phase 5

The pipeline is no longer the blocker. These are:

1. **Corpus size.** Collection starts from ~0. A MobileNetV3 fine-tune needs
   order 10²–10³ images per class; the 200-class target needs sustained
   collection. Track with `GET /ai/vision/corpus-stats`.
2. **No training script.** `ML/scripts/train_food_vision.py` is referenced by
   `VisionCapability.get_model_spec()` and does not exist.
3. **No training framework.** `ML/requirements.txt` has `coremltools` (export)
   but no torch/tensorflow — you can convert a model you cannot yet train.
4. **Free-text labels.** Corrections are prose; the 200-class controlled
   vocabulary and the text→class mapping are unstarted.
5. **No West African dataset.** Food-101 covers almost none of it, and it is the
   product's differentiator.
6. **Storage.** Photos are base64 in Postgres — fine for accumulating now, wrong
   at scale. Move to GCS and populate `media_assets.storage_url`.
7. **Export + on-device inference.** Core ML / TFLite export and the
   `confidence < 0.7` backend-validation path are unwritten.

## Tests

```
WEB/backend/tests/test_portion_estimator.py   26 cases — portions, fractions, clamping
WEB/backend/tests/test_food_vision_store.py   10 cases — correction classification
ML/tests/test_vision.py                       18 cases — multi-image, parser, wrong-schema
```

Run: `/Users/woleakpose/Developer/dev_env/bin/python -m pytest tests/ -q`
