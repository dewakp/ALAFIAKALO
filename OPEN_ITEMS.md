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

## 4. `ai_engine` crashes for anyone with an active prescription — OPEN

`_get_current_medications` reads `m.medication_name`; the `Medication` model has
`name`. `AttributeError`, so `/personalization/health-score` **500s** for any
user holding an active prescription. It currently appears to work only because
the reference account has none — and `POST /medications/promote-logged` creates
exactly those rows, so using that feature breaks the health score.

§3ag's static guard was built to catch this class and misses it: its regex
`\b([A-Z][A-Za-z]+)\.([a-z_]+)\b` matches class-level references
(`Medication.is_active`) but not instance reads (`m.medication_name`).

## 5. Health score measures diligence, not health — NEEDS DECISION

- **Nutrition = logging frequency.** `(days_tracked / 30) * 100`. Log every day
  while malnourished and it reads 100%.
- **Missing data scores 0 and is still weighted.** Untracked fitness/sleep/vitals
  drag the total down as though they were failures — §3aa in a number.
- **…except where missing data scores full marks**: `(10 - avg_stress)` awards 30
  points when stress was never recorded.
- **Vitals is BMI only**, on dialysis patients, where BMI is confounded by fluid.
- **Nothing clinical enters it** — no labs, potassium, phosphorus, dialysis
  adequacy, medication adherence.

Direction given 2026-08-29: *"no hard coding. We need Intelligence not
prescription."* So the fix is not a better rubric — it is scoring measured values
against the patient's own context, with judgement delegated to the AI layer, and
unknown reported as unknown.

## 6. Journal invents a mood score — OPEN, small

`Journal.jsx:17` pre-sets `mood_score: 7` ("Good"). A patient who types
"I feel exhausted, might be low hemoglobin" and never touches the slider has
**7/10 Good** recorded as their own self-report, and a clinician reads it beside
that sentence. Same pattern in `Mood.jsx:12` and `MentalHealth.jsx:75` (all `5`).

Fix A (agreed shape, not yet built): no default; Save disabled until chosen.
Fix B (needs a call): let a journal entry carry no score at all — `mood_score` is
`nullable=False`, so that is a migration.

## 7. Captured images are not retained centrally — NEEDS DECISION

Meal photos are (via `/ai/vision` → `MediaAsset` + `FoodTrainingSample`, gated on
`allow_collective_insights`, opt-in). **Every `image-ai/*` endpoint persists
nothing** — medication labels, elimination, symptom, verify-dosage.

Requirement stated 2026-08-29: captures are essential for model training and must
live centrally, with device storage as cache only.

Blocker: the privacy policy authorises **meal photos** specifically, for food
recognition, on explicit opt-in. Retaining the other categories would make our
own published copy false — the §3al failure. The policy and both consent screens
have to change in the same commit as the code.

Also missing: `GET /media/{media_id}` (only list/create/delete exist), needed to
read an image back for history.

## 8. Photos are base64 in Postgres — OPEN

`VISION_TRAINING.md` already flags it: fine for accumulating, wrong at scale.
Move to GCS and populate `media_assets.storage_url`.

## 9. 109 backend routes have no client caller — OPEN

From `scripts/check_client_routes.py --list-uncalled`. Three kinds mixed
together: dormant by design (`/auth/signup/*`, gated off in DEPLOY.md), whole
features with no UI (`/blockchain/*` 11, `/physicians/*` 11, `/telehealth/*` 11,
`/diagnostics/*` 13 — the §3ad situation), and genuine leftovers. Needs a
walk-through by prefix; deleting on a count would be guessing.

## 10. An overridden dose leaves no trace — OPEN

`acknowledge_unusual` is a request flag only; nothing is persisted. A clinician
cannot tell a force-logged dose from a routine one.

## 11. `Calcium Calcitriol 1000 mg` is still in production — NEEDS DECISION

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
