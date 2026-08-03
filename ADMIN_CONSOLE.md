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
