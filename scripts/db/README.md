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

**Accounts with a subscription are skipped** and printed for manual review. The
patterns are heuristics — `x.com` is a live domain, `example.com` is only
conventionally fake — and a subscription is the strongest available signal that
an account belongs to a real person.

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
