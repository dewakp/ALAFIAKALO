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

## Who reads the photo, in what order

In production, cheapest and most trustworthy first:

1. **The patient's own history.** A photo matching a meal they labelled before
   (dHash recall) is answered from their own correction and sent nowhere.
2. **Hosted vision providers**: those marked `supports_vision` in the provider
   registry (Anthropic, OpenAI), in the pool's selection order.
3. **Ollama (llava)**, the provider of last resort.

Dev puts Ollama first and makes it required (`OLLAMA_FIRST` / `OLLAMA_REQUIRED`,
CLAUDE.md §3ak), exactly as chat does.

The Image AI screens — medication labels, symptom and elimination photos, and the
meal caption fallback — ask their questions through the same order
(`task="image_question"`). They used to call Ollama directly, and only Ollama
(CLAUDE.md §3aw).

**Production had 2 and 3 the wrong way round.** `_vision_chat` asked Ollama first
whenever `OLLAMA_BASE_URL` was set, which in production is always. On 2026-09-15
three meal photos (two from iOS, one from web) each took 134–153 s: a cold GPU
start and queueing, then llava wrote `{"name": "Fried Chicken", …}` again and
again until `num_predict` (700) cut the reply off mid-word. The parser's
truncation repair had never worked on a cut-off list — 0 of 84 cut points
recovered on that reply — so each became a 503, shown on iOS as "Image analysis
unavailable" after two and a half minutes. The same public test photos, sent in
production order through Anthropic: **3.1–3.3 s**.

- The MODEL's copy of a photo is shrunk to 1568 px on the long edge (iOS sent
  9.6 MB for two photos). The stored photo is the original.
- Nothing identifying travels with it: the request is the fixed prompt and the
  images, with no name or account id.
- When nothing answers, the error names every provider tried and the exception
  type each raised.

Use **llava** for the Ollama rung, not moondream. `OLLAMA_VISION_MODEL`
previously defaulted to `moondream` in compose, which is a *grounding* model:
asked for the food schema it answers with bounding boxes
(`{"top": [...], "size": ...}`) and never emits `items`, so every photo failed.
Verified against both.

The parser tolerates markdown fences, prose-wrapped JSON, and replies cut off by
the token limit. It tracks which brackets are actually still open, keeps every
value that finished, and drops a half-written one: "Fried Chi" is worse than no
row. A food repeated with the same portion — or with none, the cut-off tail of a
loop — is merged, and the notes tell the patient so. A reply that parses but has
the wrong shape fails loudly and names the model, rather than reporting "no food
recognised" and blaming the photo.

## Phase 5 classifier — the training pipeline

Built 2026-09-15 in `ML/food_vision/`. **Verified end to end on synthetic photos
only — no model has been trained on real food yet.** It lives outside
`ML/src/alafia_model` on purpose: `deploy.sh` vendors that package into the
backend image, and torch, TensorFlow and coremltools do not belong in a web
server.

### Three outputs, because a composite is not one label

One softmax over dish names cannot say what is in the bowl. The network
(MobileNetV3-Small, ImageNet-pretrained trunk) has one output per kind of label:

| Output | Activation | Answers |
|---|---|---|
| `dish` | softmax | what is being made or served |
| `components` | sigmoid per class | what it is made of — several at once, including what cooking has hidden |
| `stage` | softmax | how far through preparation |

Photos of the preparation stages are what make `components` learnable: the raw
shot shows the melon seeds that the plated egusi no longer does.

### Preparing the photos: `labels.csv`

One CSV at the root of the photo folder, one row per photo:

```
file,session,dish,stage,components
egusi-0412/01.heic,egusi-0412,Egusi soup,raw,melon seeds;spinach;palm oil
egusi-0412/05.heic,egusi-0412,Egusi soup,plated,melon seeds;spinach;palm oil
jollof-0415/02.jpg,jollof-0415,Jollof rice,plated,rice;tomato;chicken;fried plantain
```

| Column | Required | Meaning |
|---|---|---|
| `file` | yes | path inside the folder — HEIC, JPEG or PNG |
| `session` | yes | ONE preparation. Every stage of it stays on the same side of the train/validation split |
| `dish` | at least one of these three | the dish being made or served |
| `stage` | | your own words: raw, chopped, cooking, plated … |
| `components` | | `;`-separated: what the food in frame is made of, **including what is no longer visible** |

- **`session` is what keeps validation honest.** Split photo by photo and the
  validation set holds the pot the model trained on minutes earlier; it would
  measure memory, not recognition. Sessions are assigned by hash, so adding
  photos later never moves an existing session across the split.
- **The vocabulary is whatever you type.** No alias table and no class list in
  code (§3c, §3ad). Case and spacing are normalised; near-identical spellings
  (`tomato` / `Tomatoes`) are **warned about, never merged**.
- A class needs `--min-support` (default 8) **training** photos to get an output.
  Rarer ones are listed in the report instead of being trained on three photos.
- A photo that lists no components is masked out of that loss. It does not
  teach "there is no rice in this jollof".
- Refused outright — every problem at once, by line: missing file, no session,
  no label, a path outside the folder, a duplicate row, a photo that will not
  decode, and the same photo bytes in two sessions (it would sit on both sides
  of the split).

### Running it

From `WEB/`:

```bash
# 1. Train. Native architecture; photos mount read-only from FOOD_PHOTOS.
FOOD_PHOTOS=/path/to/photos docker compose --profile ml run --rm food-vision \
    python scripts/train_food_vision.py

# 2. Convert for the phones (linux/amd64 image — see Dockerfile.export for why).
docker compose --profile ml run --rm food-vision-export \
    python scripts/export_food_vision.py models/food_vision/<version>
```

From the repo root — Core ML executes only on macOS, so this is the one host step:

```bash
ML/.venv-health-ml/bin/python ML/scripts/verify_food_vision_coreml.py ML/models/food_vision/<version>
```

Everything lands in `ML/models/food_vision/<version>/` (gitignored):
`food_vision.onnx`, `food_vision.tflite`, `food_vision.mlpackage`, `model.pt`,
`food_vision.json` (the client contract: input, outputs, classes, verdict, what
each export proved), `metrics.json`, `reference.npz` and `report.txt`.

### When a model is adoptable

Every figure is printed beside the trivial answer on held-out sessions: dish and
stage against *always the most common training class*, components against
*every class at its base rate* (§3ac's rule). Precision is printed beside recall
(§3ab). A head with no labelled validation photos is unmeasured, and unmeasured
is not adoptable.

The components headline says how many classes its mean covers. On the smoke run
"mAP 1.00" covered **1 of 3** components — the other two were in every validation
photo, where no ranking can be wrong — and printed bare it read as the head's score.

`export_food_vision.py` refuses a model that is not adoptable unless given
`--allow-unproven` (e.g. to exercise an app integration), and records that it was.

### The input contract

A client must prepare a photo exactly as training evaluated it (`dataset.to_input`):
EXIF orientation applied → RGB → **the whole photo squashed to 224×224**, bilinear,
no crop (a centre crop cuts off the plantain at the rim) → float32 in 0–255.
Normalisation, softmax and sigmoid are **inside** the model, so no client
re-implements them. Layout: ONNX NCHW, TFLite NHWC, Core ML Image.

### Every conversion is executed and compared — on decisions, not a tolerance

`reference.npz` holds real photos from the collection and the trained model's
answer for each. Every export is run on them and ships only if every decision
matches: the same top dish, the same stage, every component on the same side of
the threshold. A 0.001 shift across the threshold changes what the patient is
told; a 0.01 shift that changes nothing does not.

The first trained model — a smoke run on synthetic photos, deleted afterwards so
it cannot be mistaken for a real one:

| Export | Executed on | Result |
|---|---|---|
| ONNX | onnxruntime 1.30, linux/arm64 | decisions agree on 16/16 |
| TFLite float16 | LiteRT CPU interpreter | **does not load**: onnx2tf's float16 file is float16 end to end (input, weights, activations, no `DEQUANTIZE`) and `CONV_2D` refuses it |
| TFLite float32 | LiteRT 2.1.2, linux/amd64 | agrees 16/16 → **shipped** (6.1 MB) |
| Core ML float16 | macOS 26.6.2, arm64 | **a decision flipped** (max diff 1.9e-2) → not shipped |
| Core ML float32 | macOS 26.6.2, arm64 | agrees, max diff 1.3e-6 → **shipped** |

A "half the size, within tolerance" rule would have shipped both float16 files.
An untrained test model's float16 Core ML differed by only 4e-4 — the trained
weights are what exposed it.

### Toolchain facts, each learned the hard way

- **Two images.** Training and ONNX run native (`Dockerfile`). TFLite and Core ML
  conversion run `linux/amd64` even on Apple Silicon (`Dockerfile.export`):
  coremltools publishes Linux wheels for x86_64 only, and onnx2tf 2.6.9 pins
  onnxoptimizer, which has no arm64 wheel. On arm64 pip does not fail — it
  quietly resolves onnx2tf 1.28.8, two major versions older.
- **torch comes from the CPU wheel index.** PyPI's linux/arm64 torch is the CUDA
  build (`+cu130`).
- **ONNX export uses `dynamo=False`.** The default exporter writes the weights to
  a separate `.onnx.data`, a two-file artifact every consumer must keep together.
- **ai-edge-torch is not an option.** It is deprecated (renamed litert-torch),
  the version pip installed had no `convert`, and litert-torch did not resolve
  on Python 3.12 or 3.13.
- CPU training in Docker on an M3 measured **97 img/s** (batch 32, forward and
  backward): 2,000 photos × 25 epochs is under 10 minutes of training steps.

## What still stands between here and Phase 5

Neither the pipeline nor training is the blocker any more. These are:

1. **Real, labelled photos.** Prepare a folder as above. Until one is trained
   on, every result in the section above comes from synthetic images.
2. **Corpus size.** A MobileNetV3 fine-tune wants order 10²–10³ photos per class.
   Track in-app collection with `GET /ai/vision/corpus-stats`.
3. **The in-app corpus does not feed the trainer.** `food_training_samples`
   corrections are free-text names with no dish/component/stage split; only a
   `labels.csv` folder trains.
4. **No West African dataset.** Food-101 covers almost none of it, and it is the
   product's differentiator.
5. **Storage.** Photos are base64 in Postgres — fine for accumulating now, wrong
   at scale. Move to GCS and populate `media_assets.storage_url`.
6. **On-device inference.** The exports exist and are verified, but nothing in
   iOS, Android or the backend loads them, and the `confidence < 0.7`
   backend-validation path is unwritten. It needs a trained model first: the
   class list is part of the client contract, and it does not exist until the
   photos do.

## Tests

```
WEB/backend/tests/test_portion_estimator.py   26 cases — portions, fractions, clamping
WEB/backend/tests/test_food_vision_store.py   10 cases — correction classification
ML/tests/test_vision.py                       18 cases — multi-image, parser, wrong-schema
ML/tests/test_food_vision.py                  21 cases — manifest, split, vocabulary, metrics,
                                                         parity, training, TFLite/Core ML conversion
```

`test_food_vision.py` runs in Docker, in **both** ML images. Each skips by name
what it lacks — conversion runs only in the export image, HEIC and the
scikit-learn cross-check only in the training image — so run both:

```bash
cd WEB
docker compose --profile ml run --rm food-vision
docker compose --profile ml run --rm food-vision-export
```

Run: `/Users/woleakpose/Developer/dev_env/bin/python -m pytest tests/ -q`
