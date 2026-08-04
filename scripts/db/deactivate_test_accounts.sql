-- Deactivate robot/test accounts (*@example.com, *@x.com) — REVERSIBLE.
--
-- Deliberately NOT a DELETE. 65 of the 101 foreign keys pointing at `users` are
-- NO ACTION, so a delete would fail rather than cascade, and forcing it would
-- mean tearing rows out of ~100 clinical tables. Deactivating keeps referential
-- integrity and the audit trail intact while taking the accounts out of every
-- "registered users" count.
--
-- What it does, in one transaction:
--   1. records each account's ORIGINAL email in deactivated_accounts
--   2. sets is_active = false
--   3. scrambles the email to a non-routable address so it cannot log in,
--      cannot be re-registered against, and cannot receive mail
--   4. marks the matching identity.users rows disabled
--
-- Reversal is `deactivate_test_accounts_rollback.sql` — the original addresses
-- are preserved, so this is undoable.
--
-- Usage (dry run first — it prints the target list and rolls back):
--   psql … -v dry_run=1 -f deactivate_test_accounts.sql
--   psql … -v dry_run=0 -f deactivate_test_accounts.sql

\set ON_ERROR_STOP on

BEGIN;

CREATE TABLE IF NOT EXISTS deactivated_accounts (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL,
    original_email  VARCHAR(255) NOT NULL,
    identity_email  VARCHAR(255),
    reason          VARCHAR(100) NOT NULL,
    deactivated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id)
);

-- The target set, computed once so every step below agrees on it.
CREATE TEMP TABLE _targets ON COMMIT DROP AS
SELECT id, email
FROM users
WHERE (lower(email) LIKE '%@example.com' OR lower(email) LIKE '%@x.com')
  AND is_active = true;

\echo ''
\echo '── accounts to deactivate ──'
SELECT count(*) AS target_count FROM _targets;
SELECT id, email FROM _targets ORDER BY id LIMIT 10;
\echo '(showing at most 10)'
\echo ''

-- 1. Preserve the originals so this is reversible.
INSERT INTO deactivated_accounts (user_id, original_email, reason)
SELECT t.id, t.email, 'robot/test account cleanup'
FROM _targets t
ON CONFLICT (user_id) DO NOTHING;

-- 2 + 3. Deactivate and neutralise the address.
--     `.invalid` is reserved by RFC 2606 and can never resolve, so a scrambled
--     address cannot accidentally reach a real mailbox.
UPDATE users u
SET is_active = false,
    email = 'deactivated.' || u.id || '@invalid'
FROM _targets t
WHERE u.id = t.id;

-- 4. Same accounts in the identity store (the primary credential store).
UPDATE identity.users i
SET account_status = 'disabled',
    updated_at = now()
FROM _targets t
WHERE lower(i.email) = lower(t.email);

-- Record which identity rows were touched, for the rollback.
UPDATE deactivated_accounts d
SET identity_email = t.email
FROM _targets t
WHERE d.user_id = t.id AND d.identity_email IS NULL;

-- 5. Identity-only robot accounts.
--
--    The IdP holds 56 matching accounts with NO public.users row. They look
--    harmless because ALAFIA has no user for them — but the login path
--    provisions an ALAFIA user on first successful identity auth, so leaving
--    them active means 56 robots can still materialise real accounts. Disable
--    them too, recorded with user_id = NULL so the rollback can find them.
CREATE TABLE IF NOT EXISTS deactivated_identity_only (
    id             SERIAL PRIMARY KEY,
    identity_email VARCHAR(255) NOT NULL UNIQUE,
    reason         VARCHAR(100) NOT NULL,
    deactivated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TEMP TABLE _identity_only ON COMMIT DROP AS
SELECT i.email
FROM identity.users i
WHERE (lower(i.email) LIKE '%@example.com' OR lower(i.email) LIKE '%@x.com')
  AND i.account_status = 'active'
  AND NOT EXISTS (SELECT 1 FROM users u WHERE lower(u.email) = lower(i.email));

INSERT INTO deactivated_identity_only (identity_email, reason)
SELECT email, 'robot/test account cleanup (identity-only)'
FROM _identity_only
ON CONFLICT (identity_email) DO NOTHING;

UPDATE identity.users i
SET account_status = 'disabled', updated_at = now()
FROM _identity_only o
WHERE i.email = o.email;

\echo '── result ──'
SELECT 'users deactivated: ' || count(*) FROM users WHERE email LIKE 'deactivated.%@invalid';
SELECT 'identity disabled: ' || count(*) FROM identity.users WHERE account_status = 'disabled';
SELECT 'active users remaining: ' || count(*) FROM users WHERE is_active = true;

\if :dry_run
  \echo ''
  \echo '*** DRY RUN — rolling back. Re-run with -v dry_run=0 to apply. ***'
  ROLLBACK;
\else
  COMMIT;
  \echo ''
  \echo '*** APPLIED. Reverse with deactivate_test_accounts_rollback.sql ***'
\endif
