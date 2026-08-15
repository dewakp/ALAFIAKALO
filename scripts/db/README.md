# Database parity — keeping dev identical to prod

**Deployed is the gospel. Dev must be an exact copy of it.**

This document exists because dev and prod kept diverging, and because a stale dev
database is invisible: the app runs, screens render, screenshots look fine — and
every one of them is wrong. The tooling here makes divergence *loud*.

---

## TL;DR

```bash
scripts/db/verify_parity.sh     # exit 0 = identical. Run before you trust the app.
scripts/db/pull_prod.sh         # replace dev with an exact copy of prod
```

One direction, always: **prod → dev**. There is no `push_prod.sh` on purpose.
Prod changes only through a migration plus a deploy.

## What "exact" means here

True *byte-for-byte block equality* between Cloud SQL and a local Docker Postgres
is not achievable and would not mean anything if it were: the two run different
storage layouts, and physical bytes differ over transaction ids, free-space maps,
vacuum state and index padding even when the data is identical. Cloud SQL also
gives no filesystem access.

So parity is defined and enforced **logically**, which is what actually matters:

| Checked | How |
|---|---|
| Every row of every table | order-independent MD5 over each row rendered as text |
| Row counts | `count(*)` per table |
| Column shape | hash of name/type/nullability/default/length for every column |
| Migration state | `alembic_version` must match |
| Both schemas | `public` **and** `identity` |

If all of those match, the databases are indistinguishable to the application.
Any mismatch fails the check and is printed by name.

### Why the fingerprint pins session settings

The content hash renders each row as text, so anything that changes text
rendering changes the hash. `fingerprint.sql` pins `TimeZone=UTC`,
`DateStyle='ISO, YMD'` and `extra_float_digits=3` before hashing. Without that,
two identical databases on servers with different defaults report a false
mismatch — which is worse than no check, because it trains you to ignore it.

## One-time setup per machine

Everything runs in pinned Docker images (`postgres:16-alpine`,
`cloud-sql-proxy:2.14.3`), so there is nothing to install and no client-version
drift. You only need credentials:

```bash
gcloud auth application-default login          # interactive, opens a browser
export PROD_DB_PASS='<the alafia DB password from Secret Manager>'
cd WEB && docker compose up -d db              # dev DB on :5435
```

`PROD_DB_PASS` is the Cloud SQL password for role `alafia`. Keep it in your
shell environment or a password manager — **never** commit it.

## The scripts

| File | Role |
|---|---|
| `scripts/db/db_lib.sh` | shared topology + pinned images + proxy lifecycle |
| `scripts/db/fingerprint.sql` | read-only; emits the parity fingerprint |
| `scripts/db/verify_parity.sh` | fingerprints both sides, diffs, exits non-zero on drift |
| `scripts/db/pull_prod.sh` | dump prod → restore into dev → verify |

`verify_parity.sh --dev-only` prints the dev fingerprint without touching prod —
useful offline.

### What `pull_prod.sh` does

1. `pg_dump --format=custom --no-owner --no-privileges` of `public` + `identity`
2. `pg_restore --clean --if-exists` into dev — **dev is replaced**, so leftovers
   from an older dev schema cannot survive and fake parity
3. runs `verify_parity.sh` and *fails* if the copy is not identical

It prompts for confirmation (type `replace dev`) unless given `-y`.

## PHI handling

The dump contains real patient data. It is written to `.db-parity/`
(gitignored) and **deleted after a successful verify** unless you pass
`--keep-dump`. Do not copy it elsewhere, and do not upload it to object storage
— an earlier migration had to delete PHI dumps out of GCS after an import.

## Topology gotchas that have bitten before

- The dev DB is on **port 5435**, not 5432. A `postgres` on 5432 on this machine
  belongs to a different project (`sigma_db`). Pointing at it looks like it works
  and serves wrong data.
- Sync **both** schemas. `identity` holds the SSO users; syncing only `public`
  leaves logins pointing at a different user set.
- `deploy/gcp/config.env` is authoritative for instance/region
  (`alafia-prod-6igma:us-east4:alafia-db-va`). `WORKLOG.md` still cites the older
  `europe-west1` / `alafia-db` and is stale.

## Why the app can still look stale after a sync

Clients read through the API, so the chain is *client → API → DB*. A local
simulator or `npm run dev` session points at `http://localhost:8005`, i.e. a
**local backend over the local DB**. Parity fixes the DB end; make sure the API
end is the one you meant:

- iOS simulator defaults to `http://localhost:8005/api/v1`
  (`IOS/ALAFIA/App/AppConfig.swift`). Override per-launch with
  `SIMCTL_CHILD_ALAFIA_API_URL=...` — note simctl requires the `SIMCTL_CHILD_`
  prefix and silently ignores `--setenv`.
- Web dev proxies `/api` → `localhost:8005` (`WEB/frontend/vite.config.js`).

## Migration hygiene (the other drift source)

Data parity does not fix schema drift if the migration state differs. The dev DB
is stamped `bb002_add_subscriptions` while the single head is
`dd001_food_training_samples`, so dev is missing later columns — e.g.
`media_assets.storage_url`, added by `u001_media_s3_storage`, is in the model but
not in the dev database.

Always ask alembic for the graph state; never grep for it:

```bash
alembic heads      # authoritative
alembic current    # what this database is stamped at
```

A hand-rolled scan of `down_revision` once reported five heads where there is
exactly one: many revisions use the annotated form
`down_revision: Union[str, None] = '…'`, which a `^down_revision\s*=` regex does
not match, so real parents look unreferenced.


## Robot-account cleanup

`deactivate_test_accounts.sql` deactivates `%@example.com` / `%@x.com` accounts.
It does **not** delete: 65 of the 101 foreign keys referencing `users` are
NO ACTION, so a DELETE fails rather than cascades, and forcing it would mean
tearing rows out of ~100 clinical tables.

What it does: records the original email in `deactivated_accounts`, sets
`is_active=false`, scrambles the address to `deactivated.<id>@invalid`
(RFC 2606 — can never resolve), and disables the matching `identity.users` rows,
including identity-only robots that have no ALAFIA user row (those matter: the
login path provisions an ALAFIA user on first successful identity auth).

Both domains are test-only in this deployment: **`example.com` is reserved by
RFC 2606** and can never be a real mail domain, and every `x.com` match here is a
seeded test account (owner-confirmed). Matches are deactivated including any that
carry subscription rows — a test subscription belongs to a test account, and the
ones in question are literally named `sub_smoke_…`.

Targets holding subscriptions are still **printed** before the target list, so an
operator sees which accounts carry billing rows. The dry run is the review step.

```bash
# dev
psql … -v dry_run=1 -f scripts/db/deactivate_test_accounts.sql   # preview
psql … -v dry_run=0 -f scripts/db/deactivate_test_accounts.sql   # apply

# production (dry run is the default)
export PROD_DB_PASS='…'
scripts/db/deactivate_test_accounts_prod.sh
scripts/db/deactivate_test_accounts_prod.sh --apply

# undo, either environment
psql … -f scripts/db/deactivate_test_accounts_rollback.sql
```


## Complimentary memberships and role grants

`grant_comp.sh` gives named accounts an active membership at no charge, and
optionally assigns a professional role (`physician`, `nurse_practitioner`, …).

It is SQL because there is no admin write surface to do it through: the admin
console (`/api/v1/admin/*`) is deliberately read-only, `/subscription` only
accepts *verified provider purchases*, and `POST /users/roles` needs the target
user's own bearer token — which you do not have for a user you are comping.

```bash
# production — DRY RUN is the default; it runs every statement then rolls back
export PROD_DB_PASS='…'
scripts/db/grant_comp.sh --emails someone@example.org --role physician --primary
scripts/db/grant_comp.sh --emails someone@example.org --role physician --primary --apply

# local dev database
scripts/db/grant_comp.sh --target dev --emails someone@example.org --apply
```

Behaviour worth knowing:

- **An email that matches no user aborts the whole run.** A comp that silently
  reached nobody is the failure worth being loud about.
- The role name is checked against the real `UserRole` enum before anything
  runs. The column is a plain `VARCHAR`, so a typo would otherwise be stored
  happily and then matched by nothing in the app.
- It **refuses to overwrite a subscription on a real billing rail**
  (stripe/paypal/google_play/apple) unless `--allow-overwrite` is passed:
  replacing one drops the provider reconciliation ids, leaving the next webhook
  with nothing to match.
- The row is written `status='active'`, `provider='none'`, `price_usd=0`,
  `cancel_at_period_end=true`. Nothing renews a `provider='none'` row, so that
  flag is the truth — and the web UI reads it to print "Access ends on <date>"
  instead of the wrong "Renews on <date>".
- Every grant also writes a `subscription_events` audit row
  (`event_type='complimentary_grant'`), so comps sit on the same record as real
  provider events.
- Re-running is safe: the subscription upserts on `user_id` and the role
  assignment upserts on `(user_id, role)`, reactivating a revoked one.

### Creating the account in the first place

Do **not** hand-write a `users` row. `POST /auth/register` also provisions the
account in the shared 6IGMA Identity service, mints the canonical System
Identifier and writes its `SystemIdLog` row; an account made with INSERTs has
none of that and diverges from every real account exactly where the login path
looks. `scripts/provision_account.py` drives that API end to end — register,
log in, claim roles, professional profile, optional sample clinical data — and
is idempotent.

```bash
export ALAFIA_NEW_PASSWORD='…'          # not on argv: it is visible in `ps`
scripts/provision_account.py --api https://api.alafia.app/api/v1 \
    --email someone@example.org --name 'Some One' \
    --role physician --primary --seed
```

On a paywalled deployment (`SUBSCRIPTION_REQUIRED=true`, which is production)
run `grant_comp.sh` **before** `--seed`: every clinical endpoint is behind the
paywall, so seeding 402s without a membership. The script says so when it hits
one.

### Professional profiles

`set_pro_profile.sh` attaches (or fills in) the `ProfessionalProfile` on a role
assignment — the credentials/practice card the Roles page renders. Same reason
it is SQL: `PUT /users/roles/{id}/profile` needs the target user's own token.

```bash
scripts/db/set_pro_profile.sh --emails someone@example.org --role physician \
    --license '000-XXXX-0000-XX'            # DRY RUN
scripts/db/set_pro_profile.sh --emails someone@example.org --role physician \
    --license '000-XXXX-0000-XX' --apply
```

- It **only writes the fields you pass.** Omitted ones keep whatever is already
  stored, so seeding a placeholder cannot wipe details the user later fills in
  themselves.
- Aborts if a target does not actually hold an active assignment for that role —
  otherwise the profile would have nothing to attach to and the run would
  silently do nothing.
- `verification_status` is written as `unverified` on insert and never touched
  on update. Credential verification is a real review step; a provisioning
  script does not get to skip it.

Note that the `verification_status` in `clinician_directory.py` is a **different
table** — it lives on the `Physician` model (the ingested public directory), not
on `ProfessionalProfile`. Nothing in the app gates a feature on either one.
