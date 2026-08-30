# App Review — reply for submission 0ace0f33-c59f-4a82-ae58-5927d9a27c7d

Reviewed: **1.0 (2)**, iPad Air 11-inch (M3), iPadOS 26.6, 25 Aug 2026.
Resubmitting: **1.3 (5)**.

> Note for the reviewer: build 1.0 (2) predates our StoreKit and privacy work.
> The items below are addressed in 1.3 (5).

---

## Guideline 2.1 — Information Needed

**1. Does your app use any third-party service for the AI features?**

Yes. ALAFIA routes AI requests to established third-party model providers
(currently Anthropic, with OpenAI, DeepSeek and Moonshot configured as
fallbacks). We also run our own inference servers, which serve as a fallback and
can be required for specific features.

**2. If yes, what personal data does it collect and/or send to the third-party
AI service?**

No personal data is sent. The user is never identified to a provider.

Requests are de-identified before they leave our infrastructure, at a single
egress point that every AI call passes through:

- **The user is identified only by a token we issue** — an HMAC of our own app
  identifier and an internal user id (for example `alafia-ba9e8bb2f9077c6e`). It
  is stable, so a conversation keeps its subject, but it is meaningless outside
  our database and cannot be joined against anything a provider holds.
- **Direct identifiers are removed from the text**: name, email address, phone
  number, date of birth, national identifiers, payment card numbers, medical
  record numbers, URLs, and the names of clinicians the user mentions.
- The identifiers we hold for the signed-in user are registered automatically
  from the authentication layer, so no individual feature can omit them.

What does reach the provider is the clinical content needed to answer — for
example a potassium value, a drug name and a dose — attached to the token rather
than to a person. A representative request captured in full:

    user typed:  "I'm Jane Doe (jane.doe@example.com, +1 555 010-9999),
                  DOB 04/11/1962, record MRN0012345. Dr. Sarah Okafor put me on
                  calcitriol 0.5 mcg. My potassium was 5.2..."

    sent:        "I'm alafia-ba9e8bb2f9077c6e ([email], [phone]), DOB [dob],
                  record [id]. [name] put me on calcitriol 0.5 mcg.
                  My potassium was 5.2..."

**Meal photographs are the one case where an image leaves.** A photo the user
takes to estimate nutrition is analysed first by ALAFIA's own self-hosted vision
model. If that model is unavailable, the photo is sent to OpenAI's vision API
instead. Nothing accompanies it but a fixed food-recognition instruction — no
subject token, no name, no notes the user typed, and no other field from their
record. The provider receives an unlabelled photograph of a plate of food and
returns a list of foods.

The photo is kept with that meal in the user's own record, so they and any
clinician they have chosen to share with can open the entry later and see it.
Using those photos to train ALAFIA's shared food-recognition model is a separate
question, is off by default, and happens only if the user turns on collective
insights in Privacy Settings.

Providers are used under their API terms, which do not permit training on
submitted data, and no user data is used to train any third party's models.

**3. Does your app obtain the user's explicit consent (such as an 'Accept &
Enable AI Features' button) before sending the user's data?**

Yes. On first use of any AI feature the app presents **AI & Your Data**, which
states that requests are processed by third-party model providers, that the user
is identified only by an ALAFIA-issued token, and which identifiers are removed.
The user must accept before any AI request is made, and can withdraw at any time
in Profile → AI & Your Data, which disables the AI features.

The same screen links to the full Privacy Policy at https://alafia.app/privacy,
whose AI section describes exactly the behaviour above. Profile also carries
separate consent toggles for data sharing and AI training, both off by default.

---

## Guideline 1.4.1 — Safety: Physical Harm (citations)

1.3 adds **Profile → Sources & Citations**, reachable in two taps from the main
screen. It lists every source the app's health information derives from, what
each one is used for, and a link to the publisher:

| Source | Publisher | Used for |
|---|---|---|
| KDOQI Clinical Practice Guideline for Nutrition in CKD (2020 Update) | National Kidney Foundation | Protein, potassium, phosphorus and sodium targets |
| KDIGO Clinical Practice Guidelines | KDIGO | CKD staging and management context |
| FoodData Central | USDA Agricultural Research Service | Nutrient values for foods and branded products |
| Dietary Reference Intakes | National Academies of Sciences, Engineering, and Medicine | Baseline daily nutrient references |
| RxNorm / RxNav | U.S. National Library of Medicine | Drug name validation and supplied dose strengths |
| ICD-11 for Mortality and Morbidity Statistics | World Health Organization | Condition codes and official titles |
| Open Food Facts | Open Food Facts contributors | Packaged product details for scanned barcodes |

The same screen states that ALAFIA is not a medical device, does not diagnose,
treat or prescribe, and is not a substitute for the user's care team.

---

## Guideline 2.1(a) — Performance: content loading indefinitely

Reproduced and fixed. The cause was specific, not intermittent.

The app's membership gate has four states, and a `401` from
`GET /subscription/status` mapped to the `unknown` state on the assumption that
the authentication layer would handle the signed-out case. Nothing was listening:
`unknown` renders the launch spinner, its one-shot task does not re-run, and no
other code path could move it. A session whose refresh token had expired
therefore left the app **on the loading indicator permanently, with no retry and
no way out** — which matches the report exactly.

1.3 (5) broadcasts a 401 that has already survived one silent token refresh; the
authentication layer signs the user out and the app returns to the login screen
with "Your session expired. Please sign in again." Sign-in endpoints are excluded,
so a wrong password still shows an inline error instead of tearing down a session.

The identical defect existed on Android and was fixed in the same change.

---

## Guideline 2.1(b) — Performance: In-app purchase products not in the binary

The reviewed build, 1.0 (2), predates our StoreKit integration.

1.3 (5) implements StoreKit 2 for the ALAFIA Membership, with products
`alafia_plus_monthly` and `alafia_plus_annual`. The app loads them with
`Product.products(for:)`, purchases through `Product.purchase()`, verifies every
transaction server-side (including restores and renewals via
`Transaction.updates`), and offers **Restore purchases** on the paywall.

Before resubmitting, confirm in App Store Connect:

- [ ] Both product IDs exist, are **Ready to Submit** or Approved, and match the
      identifiers above exactly.
- [ ] Both are attached to this app version.
- [ ] Any previously rejected In-App Purchase is resubmitted alongside the binary.
- [ ] A sandbox purchase completes end to end on a physical device.
- [ ] The screen recording requested by App Review is attached in App Review
      Information → Notes: from the Home Screen, through the core flow with the
      demo account, showing a successful sandbox purchase.

---

## Guideline 5.1.1 — Legal: Privacy, Data Collection and Storage

- The Privacy Policy is reachable **inside the app** at Profile → Privacy Policy,
  alongside Terms of Service, and at https://alafia.app/privacy.
- Profile → AI & Your Data states what is stored and how AI requests are handled.
- The policy has been updated so its AI section describes exactly what the code
  enforces, including the pseudonymous token and identifier stripping described
  under 2.1 above.
- Consent toggles for data sharing and AI training are off by default.

---

## Demo account

Provided in App Review Information. The account clears the membership wall by its
subscription record, so the reviewer reaches the full app without purchasing —
the sandbox purchase flow can still be demonstrated separately.
