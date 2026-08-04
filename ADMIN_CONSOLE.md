# ALAFIA Admin Console

Single-operator console for **dew@6igma.com**, served at **minister.alafia.com**.

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

> **The hostname is routing, not security.** Anyone can send `Host:
> minister.alafia.com` to the API. Authorization lives in `require_admin`
> (`app/core/admin_auth.py`) and never inspects the host. Do not add nginx rules
> and assume they protect anything.

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

## Deploying to minister.alafia.com

The app is built and host routing is in place. **What remains needs your DNS
access**, so it is not done:

1. **Map the domain to the frontend Cloud Run service**
   ```bash
   gcloud beta run domain-mappings create \
     --service=alafia-frontend --domain=minister.alafia.com \
     --region=us-east4 --project=alafia-prod-6igma
   ```
2. **Add the DNS record** the command prints (a `CNAME` to `ghs.googlehosted.com`
   for a subdomain), at whoever hosts `alafia.com`.
3. Wait for the Google-managed certificate to issue (minutes to ~an hour), then
   check `https://minister.alafia.com` → redirects to `/minister`.

No backend change is needed: the console calls the same `/api/v1` the app does.

### Verifying locally without DNS

```bash
open http://localhost:8080/minister                                 # the console in dev
curl -H "Host: minister.alafia.com" http://localhost:8080/          # 302 → /minister
```

The dev path is **`/minister`**, matching the production hostname. `/admin`
still resolves — it redirects to `/minister` so older links keep working. Note
the **API** namespace stays `/api/v1/admin/*`; only the UI route was renamed.

## Verified

- **Access control, live:** admin `200` on all four endpoints; non-admin `404`;
  anonymous `401`. Confirmed in the browser: the admin sees the console, the
  non-admin sees "Not authorised".
- **Host routing:** `Host: minister.alafia.com` → `302 /minister`; `/minister` → `200`;
  `/api/` proxy → `200`. The default host is unaffected.
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

## Not done: email delivery

SMTP is deferred in this project, so **nothing is actually sent**. In `DEBUG` the
token is returned inline (same convention as password reset); in production it is
not returned and no mail goes out — meaning **production signup cannot complete
until email sending ships**. That is deliberate: refusing to finish is better
than issuing accounts to unverified addresses. It is the next thing to build.

Provider checkout for a not-yet-existing user is also unwired — `/signup/checkout`
returns 503. The subscription rails already 503 without live provider keys, so
wiring a pre-account checkout that cannot be tested would be inventing a flow.
`/signup/complete` accepts a payment reference so the gate is exercisable today.

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
