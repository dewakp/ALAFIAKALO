# Sending a bulk announcement

`send_announcement.py` mails the "return to ALAFIA" announcement to dormant
users. Dry run is the default; `--apply` sends.

---

## The three ways this goes wrong

**1. Tokens signed with the wrong key.** Every unsubscribe link is a JWT signed
with `SECRET_KEY`. Run the send inside the dev container without overriding it
and the tokens are signed with the *dev* key — every link then fails
verification against production, silently, and the recipient who tries to opt
out is told nothing is wrong. **Always inject the production key:**

```bash
-e SECRET_KEY="$(gcloud secrets versions access latest --secret=alafia-secret-key)"
```

> ⚠️ **This happened, on 2026-08-26, to a real batch of 17.** `alafia-secret-key`
> is stored with a TRAILING NEWLINE — 65 bytes ending `0x0a`. Cloud Run mounts a
> secret's bytes verbatim, so the service verified with all 65, while the
> `$(…)` above strips trailing newlines and signed with 64. The signatures never
> matched. Because an unverifiable token is *deliberately* indistinguishable
> from a forged one here, the endpoint answered `200` and rendered
> **"You're unsubscribed"** while recording nothing — every link in that mail was
> inert and told its reader the opposite. `_signing_key()` in
> `app/api/marketing.py` now strips on both sides so the two forms agree, which
> also repaired the links already sent.
>
> The general lesson: **a secret read through a shell is not always the secret
> the service holds.** Check with `gcloud secrets versions access … | xxd | tail`
> before trusting a signature minted outside the app. And note what nearly hid
> it — the module logged success via plain `logging.getLogger`, whose INFO the
> app's config filters, so the absent log line looked like evidence of rejection
> when it was evidence of nothing.

**2. Sending before the endpoint is deployed.** `/unsubscribe` and its migration
(`oo001_marketing_opt_out`) must be live on `api.alafia.app` *before* the send,
or every link in every message 404s. Verify by asking the endpoint, not the
deploy log:

```bash
curl -s -o /dev/null -w '%{http_code}\n' 'https://api.alafia.app/unsubscribe?token=x'   # expect 200
```

**3. Mailing accounts that are not people.** This database holds synthetic rows
that look like ordinary addresses — `firebase_<uid>@alafia.local` from the
Firebase migration, `plus_<ts>@alafiasmoke.com` from the deploy smoke test,
`@alafia.dev` from paywall testing. They are excluded by domain in
`EXCLUDED_DOMAINS`; the App Store review account and the owner address are
excluded by exact match in `OPERATIONAL_ADDRESSES`. Read the skip list in the
dry run — do not assume it caught everything.

## `last_login IS NULL` is a judgement call, not a fact

The column shipped after most accounts were created, and the SSO branch did not
stamp it at first (`app/api/auth.py:234`), so NULL means *"not seen since the
column shipped"* — which is **not** the same as "never used the app". The script
therefore excludes NULL by default and needs `--include-never-seen` to add them.

Before using that flag, check whether those accounts hold any data:

```sql
SELECT u.id, u.email, u.created_at::date, u.last_login::date,
  (SELECT count(*) FROM nutrition_logs n WHERE n.user_id=u.id)   AS meals,
  (SELECT count(*) FROM therapy_sessions t WHERE t.user_id=u.id) AS sessions,
  (SELECT count(*) FROM lab_results l WHERE l.user_id=u.id)      AS labs
FROM users u WHERE u.is_active AND u.last_login IS NULL ORDER BY u.created_at;
```

On 2026-08-26 all 19 such accounts had zero meals, sessions, labs and doses —
genuinely dormant, so including them was right. That was settled by reading the
rows, not by reasoning about the column.

## Compliance

`POSTAL_ADDRESS` is **required** — the script refuses to run without it, because
CAN-SPAM requires a valid physical postal address in commercial email and the app
carries none. Unsubscribe is honoured by `users.marketing_opt_out_at`, which the
audience query filters on, and the mail carries `List-Unsubscribe` +
`List-Unsubscribe-Post` (RFC 8058) so the mail client's own button works. Without
the one-click header recipients reach for "spam" instead, and that is what
actually damages a sending domain.

This gates MARKETING only. Transactional mail — password reset, verification,
billing — must never consult `marketing_opt_out_at`.

## Running it

```bash
cd WEB
CID=$(docker compose ps -q backend)
docker cp ../scripts/email/send_announcement.py  "$CID:/tmp/send_announcement.py"
docker cp ../scripts/email/return_to_alafia.html "$CID:/tmp/return_to_alafia.html"

ENVS=(
  -e POSTAL_ADDRESS="ALAFIA · 8201 164th Ave NE, Suite 200, Redmond, WA 98052"
  -e SECRET_KEY="$(gcloud secrets versions access latest --secret=alafia-secret-key)"
  -e RESEND_API_KEY="$(gcloud secrets versions access latest --secret=resend-api-key)"
  -e DATABASE_URL="<prod url — otherwise you are reading the DEV copy>"
)

# 1. Dry run — prints the audience and writes a rendered preview
docker compose exec -T "${ENVS[@]}" backend python /tmp/send_announcement.py --include-never-seen

# 2. One test copy to yourself
docker compose exec -T "${ENVS[@]}" backend python /tmp/send_announcement.py --to you@example.com --apply

# 3. The real send
docker compose exec -T "${ENVS[@]}" backend python /tmp/send_announcement.py --include-never-seen --apply
```

> ⚠️ Without `DATABASE_URL` pointing at production the script resolves its
> audience from the **dev copy**, which is only as fresh as the last
> `pull_prod.sh`. On 2026-08-26 dev and prod happened to agree exactly (28
> active / 19 NULL / 8 seen / 1 dormant) — that is luck, not a guarantee.

`--limit N` sends to the first N only, for a staged rollout. Sends are paced at
~0.6s to stay under Resend's 2 requests/second default.
