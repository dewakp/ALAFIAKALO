# ALAFIA — Deployment & Outstanding Tasks

Single source of truth for what's shipped and what's left. Status: ✅ done · 🟡 in progress ·
🔴 not started · 👤 **owner-only** (needs your accounts / credentials / money — I can't do it).

Last updated: 2026-07-22.

---

## Live now (Google Cloud — project `alafia-prod-6igma`)

| | URL |
|---|---|
| Web app | https://alafia-frontend-xj37wg452q-uk.a.run.app |
| API (mobile targets this) | https://alafia-backend-xj37wg452q-uk.a.run.app |
| Identity (PQC SSO) | https://alafia-identity-xj37wg452q-uk.a.run.app |

Cloud Run ×3 + Cloud SQL `alafia-db-va` (Postgres 16) + Secret Manager, region **`us-east4`**
(Northern Virginia). Migrated from europe-west1 2026-07-22; europe torn down.

---

## ✅ Completed this initiative

- ✅ **Subscription (ALAFIA Plus)** — 4 rails, backend-owned entitlement; migration-graph repair,
  idempotency bug fix, 213 tests green. `d6964df`
- ✅ **GCP deploy** — IaC + runbook in `deploy/gcp/`; backend + frontend + identity live on Cloud Run,
  Cloud SQL, Secret Manager. `4dfd9bb` `739c0f0`
- ✅ **Migration fixes** exposed by first clean deploy: notifications enum double-create `231948d`;
  model/schema drift `cc002` `a7764c9`.
- ✅ **Data + identity migration** — 75 app users + all health data + 124 identity credentials copied
  local → prod Cloud SQL; login verified (incl. `developer@hntsolutions.com`).
- ✅ **Hard paywall** — no free tier; every `/api/v1` data path requires an active subscription
  (owner email exempt). `54532a1`
- ✅ **Timezone fix (web)** — all dates/times in the machine locale; verified live. `27e63c8`
- ✅ **Timezone fix (mobile)** — iOS + Android local-timezone display; both compile. `9e7b9a6`

---

## 🔴 Outstanding — by track

### A. Payments go-live 👤 (biggest blocker for real users)
The rails are wired and the paywall is on, so **new users currently can't get in** until real payment
keys exist (checkout returns 503). Steps:

1. 🔴👤 Create a **Stripe** account; create a recurring **$12/mo** price → get `price_…`, secret key
   `sk_live_…`, and a webhook signing secret `whsec_…`.
2. 🔴👤 Create a **PayPal** account + **$12/mo** billing plan → client id/secret, plan id, webhook id.
3. 🔴 Put them in Secret Manager (I can run these once you paste the values):
   ```
   printf 'sk_live_…' | gcloud secrets versions add stripe-secret-key --data-file=-
   printf 'price_…'   | gcloud secrets versions add stripe-price-id --data-file=-
   printf 'whsec_…'   | gcloud secrets versions add stripe-webhook-secret --data-file=-
   # + paypal-client-id / -client-secret / -plan-id / -webhook-id
   ```
4. 🔴👤 Point the **Stripe webhook** at `…/api/v1/subscription/webhook/stripe` and **PayPal** at
   `…/webhook/paypal` (both are signature-verified).
5. 🔴 Re-run `deploy/gcp/deploy.sh` (mounts the now-configured secrets) and verify a real test checkout.
6. 🔴👤 Sign the **HIPAA BAA** in the Google Cloud console before real PHI/payments (free, self-service).

### B. Custom domain + TLS 🟡 — domain is **alafia.app** (owner-controlled)
Apps + backend now point at `alafia.app` in code ✅ (`9e7b9a6`+). Remaining:
1. ✅ Mobile + iOS/Android code repointed to `https://api.alafia.app`.
2. 🔴👤 **Verify domain ownership**: `gcloud domains verify alafia.app` (Search Console → add the TXT
   record to alafia.app DNS). Verifying the apex covers `api.`/`app.` subdomains.
3. 🔴 Map `api.alafia.app` → `alafia-backend` and `app.alafia.app` → `alafia-frontend`
   (`gcloud beta run domain-mappings create --region us-east4 …`; Cloud Run issues managed certs).
4. 🔴👤 Add the **CNAME/A records** the mapping outputs at your DNS provider; wait for cert provisioning.
5. 🔴 Re-run `deploy.sh` (or `gcloud run services update`) so `PUBLIC_WEB_URL`/`CORS_ORIGINS` =
   `https://app.alafia.app`.
   *Note: `.app` is HSTS-preloaded (HTTPS-only) — Cloud Run's managed cert satisfies this.*

### C. Deferred infra (app works without these; features degrade) 🔴
- 🔴 **LLM/AI** — no GPU attached → AI chat/vision/planner return 503. Enable: GKE L4 GPU node pool
  running Ollama, set `OLLAMA_BASE_URL`; or set `OPENAI_API_KEY`.
- 🔴 **Redis** (live messaging/telehealth WS) — add Memorystore, set `REDIS_URL`.
- 🔴 **Blockchain** anchoring — run Anvil on a small VM, set `CHAIN_NODE_URL`.
- 🔴 **Email** (password reset) — set `SMTP_*` (SendGrid or AWS SES).
- 🔴 **Media storage** — currently in Postgres (`image_base64`); set `S3_*`/GCS for large media.
- 🔴 **Firebase→PG sync + geocoder** — shipped OFF (in-process cron can't run on autoscale). Re-enable
  via Cloud Scheduler → a dedicated Cloud Run **job**; needs the Firebase service account on prod.
- 🔴 **Scale-out** — backend pinned to 1 instance because of the in-process schedulers; lift after C-Firebase.

### D. 📱 Google Play (Android) deployment — see full checklist below
### E. 🍎 Apple App Store (iOS) deployment — see full checklist below

### F. Mobile timezone fix — verify on device 🟡
Code compiles (Android + iOS) but not visually verified on a device/simulator. Confirm during the
store test-track builds (D/E).

---

## 📱 D. GOOGLE PLAY (Android) DEPLOYMENT TASKS

Current: `applicationId com.alafia.android`, `versionCode 1`, `versionName 1.0.0`,
minSdk 26 / targetSdk 36, release `minifyEnabled true`, release signing reads `keystore.properties`
(**absent**), release `API_BASE_URL = https://api.alafia.com/api/v1/`.

**Accounts & signing**
- [ ] 🔴👤 **Google Play Developer account** ($25 one-time).
- [ ] 🔴👤 Generate an **upload keystore** (`keytool -genkey … -keyalg RSA -keysize 2048 -validity 10000`);
      create `Android/keystore.properties` (`storeFile/storePassword/keyAlias/keyPassword`) — git-ignored.
- [ ] 🔴 Enable **Play App Signing** (Google manages the app signing key; you keep the upload key).

**Backend / config wiring**
- [x] ✅ `API_BASE_URL` = `https://api.alafia.app/api/v1/` (release buildConfigField + `AlafiaApplication`
      fallback). Goes live once the domain mapping (B) is up.
- [ ] 🔴 Real **cert-pinning SHA-512 pins** in `ApiClient` (currently `AAAA…`/`BBBB…` placeholders —
      release traffic is rejected until set), or disable pinning for launch.
- [ ] 🔴 Confirm **ProGuard/R8** keep-rules cover Gson/Retrofit models (`minifyEnabled true`).

**Play Billing (subscription)**
- [ ] 🔴👤 Create subscription product **`alafia_plus_monthly`** ($14/mo) in Play Console → Monetization.
- [ ] 🔴👤 Create a **Google Cloud service account** with Play access (Android Publisher), download JSON.
- [ ] 🔴 Store it as the `GOOGLE_PLAY_SERVICE_ACCOUNT` secret; grant the SA "View financial data /
      Manage orders" in Play Console (backend verifies purchase tokens via `subscriptionsv2`).
- [ ] 🔴 `GOOGLE_PLAY_PACKAGE_NAME=com.alafia.android` (already the config default). ✅ matches app.

**Store listing (👤 mostly yours)**
- [ ] 🔴👤 App name, short + full description, category (Medical/Health & Fitness).
- [ ] 🔴👤 Icon (512²), feature graphic (1024×500), **phone + 7"/10" tablet screenshots**.
- [ ] 🔴👤 **Privacy policy URL** (required — health data).
- [ ] 🔴👤 **Data safety** form (declare health data collection/handling).
- [ ] 🔴👤 **Content rating** questionnaire; target audience; ads declaration (none).
- [ ] 🔴👤 **Health apps declaration** (Play policy for medical/health apps).

**Build & ship**
- [ ] 🔴 `./gradlew bundleRelease` → signed **AAB**.
- [ ] 🔴 Upload to **Internal testing** → smoke test (login against prod, paywall, a real Play sandbox
      purchase → `/verify/google` → entitled).
- [ ] 🔴 Promote → Closed → **Production**; submit for review.

---

## 🍎 E. APPLE APP STORE (iOS) DEPLOYMENT TASKS

Current: Xcode bundle **`com.alafia.app`**, `MARKETING_VERSION 1.0`, `CURRENT_PROJECT_VERSION 1`,
automatic signing, release `baseURL = https://api.alafia.com/api/v1`.

**Bundle ID = `com.alafia.app`** (matches the alafia.app domain).
- [x] ✅ Backend `APPLE_BUNDLE_ID=com.alafia.app` (config default fixed; applies on next backend deploy).
- [ ] 🔴👤 Use the same bundle `com.alafia.app` when creating the app in App Store Connect.

**Accounts & signing**
- [ ] 🔴👤 **Apple Developer Program** membership ($99/yr).
- [ ] 🔴👤 Register App ID `com.alafia.app`; set the **DEVELOPMENT_TEAM** in the Xcode project; create
      distribution certificate + App Store provisioning profile (or automatic signing with the team).

**Backend / config wiring**
- [x] ✅ `baseURL` = `https://api.alafia.app/api/v1` (AppConfig). Goes live once the domain mapping (B) is up.
- [ ] 🔴 Real **cert-pin hashes** in `APIClient` (same placeholder issue as Android) or disable for launch.

**StoreKit (subscription)**
- [ ] 🔴👤 Create auto-renewable subscription **`alafia_plus_monthly`** ($14/mo) in a subscription group
      in App Store Connect.
- [ ] 🔴👤 Generate the **app-specific shared secret**; store as `APPLE_SHARED_SECRET`.
- [ ] 🔴 `APPLE_ENVIRONMENT=production` (already set on prod by `deploy.sh`). ✅
- [ ] 🔴 **Harden Apple JWS x5c cert-chain validation** in `subscription_service` (currently decoded but
      NOT chain-validated — do before trusting real iOS purchases). *(engineering task, I can do this)*

**Store listing (👤 mostly yours)**
- [ ] 🔴👤 App name, subtitle, description, keywords, category (Medical).
- [ ] 🔴👤 App icon + **screenshots per device size** (6.7"/6.5"/5.5" + iPad if supported).
- [ ] 🔴👤 **Privacy policy URL** + **App Privacy** nutrition labels (health data collection disclosure).
- [ ] 🔴👤 Medical/health **App Review** notes + demo account (Apple scrutinizes health apps).

**Build & ship**
- [ ] 🔴 Archive (`xcodebuild archive` / Xcode Organizer) → upload to **TestFlight** (Transporter).
- [ ] 🔴 TestFlight smoke test (login against prod, paywall, sandbox StoreKit purchase → `/verify/apple`
      → entitled).
- [ ] 🔴 Submit for **App Review** → release.

---

## Notes
- `deploy/gcp/README.md` — cloud runbook. `SubscriptionRail.md` — pricing. `docs/IDENTITY_DEPLOYMENT.md`
  — identity/PQC ops.
- Paywall kill-switch: `gcloud run services update alafia-backend --region us-east4
  --update-env-vars SUBSCRIPTION_REQUIRED=false`.
