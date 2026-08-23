# ALAFIA Admin Console

Single-operator console for **dew@6igma.com**, served at **`/minister`** on the
main app host.

Answers: who has registered, when they last signed in, how much LLM spend each
account is generating, and whether the app is healthy.

---

## Access model

Two conditions must both hold, checked on **every** request:

1. the caller's email is in `settings.ADMIN_EMAILS` (default `dew@6igma.com`)
2. the account is active

`is_superuser` is **deliberately not sufficient**. That flag is currently set on
a leftover test account in this database (`crossapp_1782548450@example.com`), and
console access should not follow from one stray `UPDATE`.

Non-admins get **404, not 403** — a logged-in prober is not told the console
exists.

> **The path is not security either.** `/minister` is just where the page is
> served; anyone can request `/api/v1/admin/*` directly. Authorization lives in
> `require_admin` (`app/core/admin_auth.py`) and depends on nothing about the
> URL. Do not add routing rules and assume they protect anything.
>
> A dedicated hostname was built and then removed: it required DNS and a Cloud
> Run domain mapping, and bought no security, because the boundary was never the
> host. A path is the same protection with none of the setup.

Every allowed and refused call is logged with caller identity, path and IP, under
logger `app.admin.access` — an admin console over patient-adjacent data needs an
access trail.

## What it shows

| Tab | Content |
|---|---|
| **Overview** | registered users, signups 30d, active 24h/7d/30d, never-signed-in, AI interactions + tokens 30d, subscriptions by status |
| **Users** | every account: name, email, signed up, last login, subscription, lifetime tokens, AI calls. Searchable, sortable, paginated |
| **App health** | DB reachability, **migration revision**, data counts, vision-corpus size, configured AI backends — each probe timed and independently statused |
| **Token usage** | 30-day totals, per-model breakdown, top users by spend |

It returns **counts and metadata only** — never clinical records. The console can
answer "is the app healthy and who is using it" without becoming a back door into
health data.

## API

All under `/api/v1/admin`, all gated by `require_admin`:

```
GET /admin/overview           headline counts
GET /admin/users              ?q=&sort=last_login|created_at|email|tokens&order=&limit=&offset=
GET /admin/users/{id}         one user, with per-model usage breakdown
GET /admin/health             live probes
GET /admin/token-usage        ?days=30
```

## Two things this required fixing first

**`last_login` did not exist.** Nothing recorded sign-ins, so "last login" was
unanswerable. Added `users.last_login` (migration `dd002_user_last_login`) and
stamping on every auth path.

The subtlety: `/auth/login` **early-returns** when the shared identity service
authenticates, before the local-password branch. That is the branch most logins
actually take, so stamping only the local path left `last_login` NULL for
everyone — verified by registering a probe account, logging in, and finding NULL.
Both branches now stamp.

**Token usage was always zero.** `AIInteraction.tokens_used` was modelled but
never written: the LLM capability put the provider's count into telemetry and
returned `data={"text": …}` only, so the number was discarded before the backend
saw it. The capability now returns `tokens_used`/`model`/`provider`, and
`alafia_chat_detailed()` carries them to the `AIInteraction` row.

> Historical rows stay at 0 — they were recorded before the fix. Usage accrues
> from now on. A provider that reports no usage still contributes 0 and would
> understate the total; the endpoint says so in its `note`.

## Where it lives

`/minister` on whatever host serves the app — `http://localhost:8080/minister` in
dev, `https://alafia.app/minister` in production. `/admin` redirects there, so
older links keep working.

No DNS record, no Cloud Run domain mapping, no nginx server block. The API
namespace is unchanged at `/api/v1/admin/*`.

## Verified

- **Access control, live:** admin `200` on all four endpoints; non-admin `404`;
  anonymous `401`. Confirmed in the browser: the admin sees the console, the
  non-admin sees "Not authorised".
- **Routing:** `/minister` → `200` and renders the console; `/admin` → redirects
  to `/minister`. The rest of the app is unaffected.
- **`last_login`:** registered a probe account, logged in, watched NULL → a
  timestamp, and saw it surface top of the console sorted by last login. Probe
  account deleted afterwards.
- **7 authorization tests** (`tests/test_admin_auth.py`) covering case/whitespace
  handling, non-admins, the superuser-flag trap, deactivated admin, empty
  identity, and settings-driven configuration.

## Adding or changing the admin

`ADMIN_EMAILS` is configuration, not code:

```bash
ADMIN_EMAILS='["dew@6igma.com","someone.else@6igma.com"]'
```

The account must also exist and be active. `dew@6igma.com` is additionally in
`SUBSCRIPTION_EXEMPT_EMAILS`, or the paywall would 402 the console in production
before `require_admin` ever ran.

---

# Signup: verify email → pay → account created

Direct registration created a `users` row for one unauthenticated POST. That is
how **55 of 77 accounts** in this database became `*@example.com` / `*@x.com`
automation leftovers. `/auth/register` is now **410 Gone**
(`TWO_STEP_SIGNUP_REQUIRED`, default on) and the only route to an account is:

```
POST /auth/signup/start          → pending row + verification token. NO user row.
POST /auth/signup/verify-email   → gate 1. Single-use token.
POST /auth/signup/checkout       → refuses until verified.
POST /auth/signup/complete       → gate 2. Records payment, THEN creates the account.
GET  /auth/signup/status?email=  → where a signup has got to.
POST /auth/signup/resend         → fresh token, capped at 10 attempts.
```

**The invariant:** `materialise()` refuses unless *both* gates pass, so no code
path produces a user for an unverified or unpaid signup. A robot that never
reads mail and never pays leaves one row in `pending_registrations` that expires
after 7 days.

Only the **SHA-256** of a verification token is stored — a dump of that table
does not let anyone verify an address they do not control. Signup responses are
identical whether or not the address already has an account, so the endpoint
cannot be used to enumerate users.

Verified end-to-end against the running stack: `/auth/register` → 410 with a
fully valid body; `start` → 202 with **0 users rows**; `complete` before
verification → 400; `checkout` before verification → 403; token replay → 400;
after verify + pay → account created and the pending row deleted.

## Email delivery

`send_verification_email()` sends a real message with a one-click link to
`/verify-email?token=…`, queued as a background task so signup does not block on
SMTP. Behaviour is deliberately three-way:

| SMTP | Env | Result |
|---|---|---|
| configured | any | mail queued; the token is **never** in the response |
| not configured | DEBUG | token returned inline, with a `warning` field |
| not configured | production | **503** — refuses rather than accept a signup that can never be verified |

**Verified against a real SMTP conversation**, not mocks: a local sink captured
the message, the response carried no token, verification succeeded using the
token taken *from the email*, and `resend` produced a fresh distinct token.
`resend` correctly declines for an already-verified address.

### Provider: Resend (HTTPS API), SMTP as fallback

Credentials are in **`smtp.md`**, which is now **gitignored** — it was not, and
was one `git add .` from being committed, exactly as `api_keys.md` had been.

`RESEND_API_KEY` set → Resend's HTTPS API. Otherwise SMTP. Otherwise mail is
unavailable and signup refuses in production.

The HTTPS API is preferred on Cloud Run: no outbound mail ports, no STARTTLS
negotiation, and a real error body instead of a socket failure. That body is
what diagnosed the problem below in one request.

```bash
printf 're_xxx' | gcloud secrets create resend-api-key --data-file=-
# SMTP fallback (self-hosting) — only used when RESEND_API_KEY is absent:
printf 'smtp.example.com'   | gcloud secrets create smtp-host       --data-file=-
printf 'apikey'             | gcloud secrets create smtp-user       --data-file=-
printf '<password>'         | gcloud secrets create smtp-password   --data-file=-
printf 'noreply@alafia.app' | gcloud secrets create smtp-from-email --data-file=-
```

`deploy.sh` mounts these **and** grants the runtime service account access —
mounting without the IAM binding fails the deploy.

### Verified sending domain: alafia.app

`alafia.app` is verified in Resend and sending works — confirmed by an actual
delivered message from `noreply@alafia.app`.

Three DNS records make that work, all in the Cloud DNS zone `alafia-app`
(project `alafia-prod-6igma`) — **not** at GoDaddy, which holds only the
registration and the NS delegation:

| Name | Type | Value |
|---|---|---|
| `resend._domainkey.alafia.app` | TXT | `p=MIGfMA0GCSqG…` (DKIM) |
| `send.alafia.app` | MX | `10 feedback-smtp.us-east-1.amazonses.com.` |
| `send.alafia.app` | TXT | `v=spf1 include:amazonses.com ~all` |

The SPF sits on the **`send` subdomain**, which is Resend's Return-Path/bounce
domain. It does not touch the apex record
(`v=spf1 include:_spf.firebasemail.com ~all`), so Firebase and Google Workspace
mail are unaffected — a domain may only carry one SPF record per name, and these
are different names.

> The sender is `noreply@alafia.app`, not `.com`. `alafia.app` is the Workspace
> mail domain, its DNS is at Namecheap, and it is not verified for sending.

## Payment verification

`/signup/checkout` creates a real Stripe Checkout session for a signup that has
no user row, correlating via `client_reference_id = signup:<email>`.

`/signup/complete` **verifies the session with Stripe** before creating the
account. This matters: trusting the caller's `reference_id` would mean any string
bought an account — the exact hole the two-step flow exists to close. Two checks
run against Stripe's own record: the session is paid, and its
`client_reference_id` matches *this* signup, so a genuinely paid session
belonging to someone else cannot be replayed into unlimited accounts.

Pinned by 11 tests with Stripe's HTTP layer stubbed: wrong owner → 403, forged
reference → 403, unpaid → 402, `no_payment_required` (100% coupon) → accepted,
unconfigured outside DEBUG → 503.

> With **no** Stripe key **and** `DEBUG`, `_test_mode` short-circuits
> verification and accepts anything. That is dev-only — it requires both
> conditions, and production sets neither — but it means a local
> "forged reference accepted" result proves nothing. The tests above force the
> production path.

Stripe is the only web rail. PayPal was withdrawn on 2026-08-23 — it had been
advertised by `/plans` and drawn as a button on the paywall while no PayPal
credential was ever mounted in production, so every attempt answered 503.

# Robot account cleanup

`scripts/db/deactivate_test_accounts.sql` — **deactivates, does not delete**.

65 of the 101 foreign keys pointing at `users` are `NO ACTION`, so a delete would
fail rather than cascade, and forcing it would mean tearing rows out of ~100
clinical tables. Deactivating preserves referential integrity and the audit trail
while removing the accounts from every active count.

It records each original email in `deactivated_accounts`, sets `is_active=false`,
scrambles the address to `deactivated.<id>@invalid` (RFC 2606 — can never
resolve), and disables the matching `identity.users` rows. Reverse with
`deactivate_test_accounts_rollback.sql`.

```bash
# dry run — prints the target list and rolls back
psql … -v dry_run=1 -f scripts/db/deactivate_test_accounts.sql
psql … -v dry_run=0 -f scripts/db/deactivate_test_accounts.sql
```

Applied to **dev**: 77 → **22 active users**, 55 deactivated (recoverable), plus
**56 identity-only robot accounts** that had no ALAFIA user row at all. Those
mattered: the login path provisions an ALAFIA user on first successful identity
auth, so leaving them active meant 56 robots could still materialise real
accounts.

**Prod is untouched** — run the same script against Cloud SQL when you are ready.
